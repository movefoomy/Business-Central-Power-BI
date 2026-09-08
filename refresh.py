"""Refresh the BC Sales Margin dashboard from Business Central OData.

Fetches PBI_ValueEntries_New + PBI_Customer + PBI_SalesPersonCode for EVERY company in
config.json, applies the sales filters, aggregates to (customer, product group, posting
date, salesperson, sector, item, company) grain and injects the payload into
dashboard.template.html to produce dashboard.html.

The companies share one BC instance and one coding scheme: a customer no, item no,
salesperson code or product posting group means the same thing in both, verified across
the full extract (93 shared customer codes and 70 shared item codes, zero conflicts). So
the lookup maps are a plain union keyed by code -- no per-company namespacing, no mapping
table. The one cosmetic disagreement is salesperson S06, named "How Huan Soon" in CIM and
"Huan Soon" in CIL; first company wins, which is why COMPANIES is ordered.

The Group view is a PLAIN SUM of the companies, by decision. The two trade with each
other -- CIM sells to customer C0002 (which is CIL) and CIL sells to CI07 (which is CIM),
about S$19M between them -- so Group revenue counts that trade twice. That is intended
and is stated in the dashboard footer. Do not quietly net it off.

Usage:  python refresh.py
"""

import base64
import collections
import datetime
import json
import os
import ssl
import sys
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))

# Document types that represent a sale (or the reversal of one).
SALES_DOC_TYPES = [
    "Sales Shipment",
    "Sales Invoice",
    "Sales Return Receipt",
    "Sales Credit Memo",
]

# Source No. used in BC for non-customer / dummy postings.
EXCLUDED_SOURCE_NO = "ZZZZZ"

# Item codes with this prefix are delivery charges: revenue but zero tonnage.
EXCLUDED_ITEM_PREFIX = "YY"

# The value-entry source. PBI_ValueEntries_New supersedes PBI_ValueEntriesPage: it carries
# the same rows plus Inventory_Posting_Group, Reason_Code and Cost_Posted_to_GL, and it
# publishes the sales amounts under their plain BC names rather than the _New suffix the
# older page used. Still never PBI_ValueEntries, which has no Source_No at all.
#
# Eleven of these fields drive the aggregation; the rest are selected because this is the
# specified field list for the endpoint. They cost a little bandwidth and nothing else --
# everything not aggregated below is discarded. Do NOT add $top to narrow the result: BC
# treats it as a hard cap and drops @odata.nextLink, truncating silently.
VALUE_ENTRY_ENTITY = "PBI_ValueEntries_New"
VALUE_ENTRY_SELECT = ",".join([
    "Entry_No", "Item_No", "Posting_Date", "Item_Ledger_Entry_Type", "Source_No",
    "Document_No", "Description", "Location_Code", "Inventory_Posting_Group",
    "Item_Ledger_Entry_No", "Valued_Quantity", "Item_Ledger_Entry_Quantity",
    "Invoiced_Quantity", "Cost_per_Unit", "Sales_Amount_Actual", "Salespers_Purch_Code",
    "User_ID", "Source_Code", "Global_Dimension_1_Code", "Global_Dimension_2_Code",
    "Cost_Amount_Actual", "Cost_Posted_to_GL", "Reason_Code", "Gen_Bus_Posting_Group",
    "Gen_Prod_Posting_Group", "Document_Date", "External_Document_No", "Document_Type",
    "Entry_Type", "Sales_Amount_Expected", "Cost_Amount_Expected",
    "Shortcut_Dimension_3_Code", "Shortcut_Dimension_4_Code", "Shortcut_Dimension_5_Code",
    "Shortcut_Dimension_6_Code", "Shortcut_Dimension_7_Code", "Shortcut_Dimension_8_Code",
    "WIN_Total_Qty_in_Kg", "WIN_Conversion_to_Kg",
])

# Salesperson names, joined Salespers_Purch_Code -> Code. Only Code and Name are used;
# the rest are the specified field list for the endpoint. A value entry can carry no
# salesperson at all, which is a real state and not an error -- those rows aggregate
# under UNASSIGNED_SALESPERSON so the filter can still reach them and the totals with
# no salesperson filter stay identical to the totals without this dimension.
SALESPERSON_ENTITY = "PBI_SalesPersonCode"
SALESPERSON_SELECT = ",".join([
    "Code", "Name", "Global_Dimension_1_Code", "Global_Dimension_2_Code", "E_Mail",
    "Phone_No", "No_of_Opportunities", "No_of_Interactions", "Job_Title",
    "Search_E_Mail", "E_Mail_2",
])
UNASSIGNED_SALESPERSON = ""

# Shortcut Dimension 3 is the business's sector analysis code. Like the salesperson it is
# often unset, which is a real state rather than an error: those rows aggregate under the
# empty string so a filter can still reach them and the unfiltered totals stay identical.
UNASSIGNED_SECTOR = ""

# WIN_Conversion_to_Kg is kilograms per base unit. Where BC has set it, it is used as is.
# Where it is zero the base unit of measure still carries the answer, because the codes are
# self-describing: KG=1, MT=1000, and the packaging codes embed their fill weight
# (DRUM-200=200, IBC-1250=1250, CARB-25=25, BAG-1000=1000). Every conversion observed in the
# sales data matches its base UOM this way. The genuinely weightless units are listed below
# and stay excluded from tonnage -- a drum sold as a drum is not product weight.
NON_WEIGHT_UOM = {"PCS", "EACH", "EA", "UNIT", "JOB", "HOUR", "DAY"}
FIXED_UOM_KG = {"KG": 1.0, "MT": 1000.0, "DMT": 1000.0, "TON": 1000.0, "G": 0.001}

# The suffix rule below only holds because the PREFIX is a real container word that names
# something with a fill weight. CIL carries XXXX-930, which is a placeholder, and reading
# 930 kg out of it would be inventing tonnage rather than recovering it. Such codes are
# refused and surface in mtNotes like any other unconvertible unit -- visible, not silent.
PLACEHOLDER_UOM_PREFIXES = {"XXXX", "XXX", "ZZZZ", "ZZZ", "TBA", "TBD", "N/A", "NA"}


def kg_per_unit(uom):
    """Kilograms per base unit, or None when the unit carries no weight."""
    u = (uom or "").strip().upper()
    if not u or u in NON_WEIGHT_UOM:
        return None
    if u in FIXED_UOM_KG:
        return FIXED_UOM_KG[u]
    if "-" in u:  # packaging codes embed the fill weight, e.g. CARB-27.5
        head, tail = u.rsplit("-", 1)
        if head in PLACEHOLDER_UOM_PREFIXES:
            return None
        try:
            n = float(tail)
        except ValueError:
            return None
        return n if n > 0 else None
    return None

# Sanity bands. Unlike a frozen set of expected totals, these do not drift as BC posts
# new data, but they trip immediately if the volume dedupe or a sign convention breaks:
# dropping the Item_Ledger_Entry_Quantity filter inflates MT about 12x, which drags
# revenue per MT from roughly 280 down to 23. Failing these REFUSES to write, so an
# unattended run can never overwrite a good dashboard with implausible numbers.
# Checked per company as well as overall: one healthy company must not be able to mask
# the other going wrong, which a single blended figure would let it do.
MIN_REVENUE_PER_MT = 50.0
MAX_REVENUE_PER_MT = 2000.0

# An hourly refresh should not move the headline figures much. A jump beyond this is a
# code change or a bulk repost rather than ordinary trading, so it is worth a line in
# the log -- but it is only a warning, since a genuine large backposting is possible.
DRIFT_WARN = 0.25

# Set CHECK_TOTALS=0 in the environment to skip both checks.


def load_config():
    path = os.path.join(HERE, "config.json")
    if not os.path.exists(path):
        sys.exit("config.json not found next to refresh.py")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def make_opener(cfg):
    """Basic-auth header plus SSL context. The BC host serves a self-signed cert."""
    token = "{0}:{1}".format(cfg["username"], cfg["access_key"]).encode("utf-8")
    header = "Basic " + base64.b64encode(token).decode("ascii")
    ctx = ssl.create_default_context()
    if not cfg.get("verify_tls", True):
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return header, ctx


def fetch(url, header, ctx, label):
    """Page through an OData collection.

    Never add $top: BC treats it as a hard cap AND suppresses @odata.nextLink, which
    silently truncates the result set. Following nextLink is the only safe way to
    read the whole collection.
    """
    rows = []
    while url:
        req = urllib.request.Request(url, headers={"Authorization": header})
        with urllib.request.urlopen(req, context=ctx, timeout=300) as resp:
            payload = json.load(resp)
        rows.extend(payload["value"])
        url = payload.get("@odata.nextLink")
        print("  {0}: {1} rows".format(label, len(rows)), end="\r", flush=True)
    print("  {0}: {1} rows      ".format(label, len(rows)))
    return rows


def entity_url(cfg, company, entity, select, flt=None):
    base = "{0}/Company('{1}')/{2}".format(
        cfg["base_url"].rstrip("/"),
        urllib.parse.quote(company),
        entity,
    )
    parts = ["$select=" + urllib.parse.quote(select)]
    if flt:
        parts.append("$filter=" + urllib.parse.quote(flt))
    return base + "?" + "&".join(parts)


def num(row, key):
    """OData omits or nulls numeric fields; treat both as zero."""
    value = row.get(key)
    return value if isinstance(value, (int, float)) else 0.0


def previous_totals(path):
    """Headline totals from the last successful run, for the drift check."""
    try:
        with open(path, encoding="utf-8") as fh:
            rows = json.load(fh).get("rows") or []
    except (OSError, ValueError, AttributeError):
        return None
    if not rows:
        return None
    # The measures sit at the end of the row, after however many dimensions the run that
    # wrote the file used. Index from the right so a file written before the salesperson
    # dimension existed still compares correctly, instead of summing a dimension string
    # and either raising or reporting nonsense drift on the one run that spans the change.
    kg, rev, cost = -3, -2, -1
    return {
        "mt": sum(r[kg] for r in rows) / 1000.0,
        "revenue": sum(r[rev] for r in rows),
        "cogs": sum(r[cost] for r in rows),
    }


def company_list(cfg):
    """[(code, BC company name)] in config order. First company wins name collisions."""
    cos = cfg.get("companies")
    if cos:
        return [(str(k), str(v)) for k, v in cos.items()]
    # Single-company config, the shape this started as.
    return [("CO", cfg["company"])]


def fetch_company(cfg, header, ctx, name):
    """Every entity this company contributes, already filtered to sales documents."""
    doc_filter = " or ".join("Document_Type eq '{0}'".format(d) for d in SALES_DOC_TYPES)
    ve_filter = "({0}) and Source_No ne '{1}' and Posting_Date ge {2}".format(
        doc_filter, EXCLUDED_SOURCE_NO, cfg["min_posting_date"]
    )
    entries = fetch(
        entity_url(cfg, name, VALUE_ENTRY_ENTITY, VALUE_ENTRY_SELECT, ve_filter),
        header, ctx, "  value entries",
    )
    customer_rows = fetch(
        entity_url(cfg, name, "PBI_Customer", "Customer_Name,Customer_No"),
        header, ctx, "  customers",
    )
    item_rows = fetch(
        entity_url(cfg, name, "PBI_Item", "No,Description,Base_Unit_of_Measure"),
        header, ctx, "  items",
    )
    sp_rows = fetch(
        entity_url(cfg, name, SALESPERSON_ENTITY, SALESPERSON_SELECT),
        header, ctx, "  salespeople",
    )
    return entries, customer_rows, item_rows, sp_rows


def build():
    cfg = load_config()
    header, ctx = make_opener(cfg)
    companies = company_list(cfg)
    labels = cfg.get("company_labels") or {}

    derive = cfg.get("derive_missing_conversion", True)
    note = lambda: {"units": 0.0, "kg": 0.0, "custs": set(), "docs": set(),
                    "uom": "", "desc": "", "co": ""}
    derived = collections.defaultdict(note)     # conversion recovered from the base UOM
    weightless = collections.defaultdict(note)  # genuinely not weight-bearing

    agg = collections.defaultdict(lambda: [0.0, 0.0, 0.0])
    names, sp_names, item_desc, entry_desc = {}, {}, {}, {}
    per_company = collections.OrderedDict()

    for code, bc_name in companies:
        print("Fetching {0} ({1})...".format(code, bc_name))
        entries, customer_rows, item_rows, sp_rows = fetch_company(cfg, header, ctx, bc_name)

        items = {i["No"]: i for i in item_rows if i.get("No")}
        # Union the lookups by code. Verified safe across the full extract: a customer no,
        # item no or salesperson code names the same party in both companies. First
        # company wins, so the config order decides the one cosmetic disagreement (S06).
        for row in customer_rows:
            no = row.get("Customer_No")
            if no and no not in names:
                names[no] = (row.get("Customer_Name") or no).strip()
        for row in sp_rows:
            c = (row.get("Code") or "").strip()
            if c and c not in sp_names:
                sp_names[c] = (row.get("Name") or c).strip() or c
        for no, meta in items.items():
            d = (meta.get("Description") or "").strip()
            if d and no not in item_desc:
                item_desc[no] = d

        fetched = len(entries)
        entries = [
            r for r in entries
            if not (r.get("Item_No") or "").upper().startswith(EXCLUDED_ITEM_PREFIX)
        ]
        print("  {0} fetched -> {1} after excluding {2}* items".format(
            fetched, len(entries), EXCLUDED_ITEM_PREFIX))

        for row in entries:
            item_no = (row.get("Item_No") or "").strip()
            if item_no and item_no not in entry_desc:
                d = (row.get("Description") or "").strip()
                if d:
                    entry_desc[item_no] = d

        # Aggregate to (customer, product group, posting date, salesperson, sector, item,
        # company).
        #
        # Tonnage is counted ONLY on rows carrying an item ledger quantity. BC writes
        # several value entries per goods movement (original, cost adjustment, invoice
        # reversal, invoice actual) and repeats the same WIN_Total_Qty_in_Kg on each; only
        # the originating entry has Item_Ledger_Entry_Quantity <> 0. Summing every row
        # overstates volume by roughly 12x.
        #
        # Revenue and cost, by contrast, must use ALL rows: the expected amounts post on
        # the shipment and are reversed by the invoice, which carries the actual amounts,
        # so the pair nets to the true figure only when both are summed.
        c_kg = c_rev = c_cost = 0.0
        c_dates = []
        for row in entries:
            key = (
                row.get("Source_No") or "",
                row.get("Gen_Prod_Posting_Group") or "(none)",
                row.get("Posting_Date") or "",
                (row.get("Salespers_Purch_Code") or UNASSIGNED_SALESPERSON).strip(),
                (row.get("Shortcut_Dimension_3_Code") or UNASSIGNED_SECTOR).strip(),
                (row.get("Item_No") or "").strip(),
                code,
            )
            bucket = agg[key]
            if row.get("Posting_Date"):
                c_dates.append(row["Posting_Date"])
            qty = num(row, "Item_Ledger_Entry_Quantity")
            if qty != 0:
                kg = num(row, "WIN_Total_Qty_in_Kg")
                if kg == 0:
                    # BC left the conversion unset on this item. Fall back to the base unit
                    # of measure, and record it either way so the gap is never silent.
                    item_no = row.get("Item_No") or ""
                    meta = items.get(item_no, {})
                    per = kg_per_unit(meta.get("Base_Unit_of_Measure")) if derive else None
                    target = derived if per else weightless
                    rec = target[(code, item_no)]
                    rec["co"] = code
                    rec["uom"] = meta.get("Base_Unit_of_Measure") or "?"
                    rec["desc"] = meta.get("Description") or row.get("Description") or ""
                    rec["units"] += -qty
                    rec["custs"].add(row.get("Source_No") or "")
                    rec["docs"].add(row.get("Document_No") or "")
                    if per:
                        kg = qty * per
                        rec["kg"] += -kg
                bucket[0] += kg
                c_kg += kg
            r_rev = num(row, "Sales_Amount_Actual") + num(row, "Sales_Amount_Expected")
            r_cost = num(row, "Cost_Amount_Actual") + num(row, "Cost_Amount_Expected")
            bucket[1] += r_rev
            bucket[2] += r_cost
            c_rev += r_rev
            c_cost += r_cost

        per_company[code] = {
            "label": labels.get(code, bc_name),
            "bcName": bc_name,
            "minDate": min(c_dates) if c_dates else "",
            "maxDate": max(c_dates) if c_dates else "",
            "mt": -c_kg / 1000.0,
            "revenue": c_rev,
            "cogs": -c_cost,
        }

    # kg and cost are negative for outbound sales in BC, so negate to make them
    # display-positive. Negate rather than abs(): a return or credit memo carries the
    # opposite sign and must SUBTRACT from the bucket. Taking abs() per bucket would
    # turn those reversals into additions and overstate volume and cost.
    rows = [
        [no, group, date, sp, sector, item, co,
         round(-kg, 2), round(rev, 2), round(-cost, 2)]
        for (no, group, date, sp, sector, item, co), (kg, rev, cost) in sorted(agg.items())
    ]
    print("")
    print("  {0} aggregate rows across {1} companies".format(len(rows), len(companies)))

    used = sorted({r[0] for r in rows})
    missing = [no for no in used if no not in names]
    if missing:
        print("  WARNING: {0} customer no(s) not in PBI_Customer: {1}".format(
            len(missing), ", ".join(missing[:10])))

    def summarise(store):
        out = []
        for (co, item_no), rec in sorted(store.items()):
            out.append({
                "company": co,
                "item": item_no,
                "desc": rec["desc"],
                "uom": rec["uom"],
                "units": round(rec["units"], 2),
                "kg": round(rec["kg"], 2),
                "docs": len(rec["docs"]),
                "customers": sorted(names.get(c, c) for c in rec["custs"] if c),
            })
        return out

    mt_notes = {"derived": summarise(derived), "weightless": summarise(weightless)}
    if mt_notes["derived"]:
        print("")
        print("  Conversion to kg was not set in BC; taken from the base unit of measure:")
        for e in mt_notes["derived"]:
            print("    [{0}] {1} ({2}) base {3}: {4:,.2f} units -> {5:,.2f} kg over {6} doc(s) - {7}".format(
                e["company"], e["item"], e["desc"][:32], e["uom"], e["units"], e["kg"],
                e["docs"], ", ".join(e["customers"])[:46]))
        print("    Fix at source: set the kg conversion on these items in Business Central.")
    if mt_notes["weightless"]:
        for e in mt_notes["weightless"]:
            print("  Not weight-bearing, excluded from tonnage: [{0}] {1} ({2}) base {3}, {4:,.2f} units".format(
                e["company"], e["item"], e["desc"][:32], e["uom"], e["units"]))

    items_used = sorted({r[5] for r in rows})
    item_names = {}
    for item_no in items_used:
        item_names[item_no] = (item_desc.get(item_no) or entry_desc.get(item_no)
                               or item_no or "(no item)")

    dates = [r[2] for r in rows if r[2]]
    sp_used = sorted({r[3] for r in rows})
    sectors_used = sorted({r[4] for r in rows})
    min_date = min(dates) if dates else ""
    max_date = max(dates) if dates else ""
    # The dashboard opens on the window in which every company actually trades, not on the
    # whole extract: one company carries three years the other does not exist for, and a
    # combined view starting there reads as a collapse rather than as an absence.
    default_from = cfg.get("default_from") or min_date
    if min_date and default_from < min_date:
        default_from = min_date
    if max_date and default_from > max_date:
        default_from = min_date

    data = {
        "generated": datetime.datetime.now().strftime("%d %b %Y, %H:%M"),
        # Offset-aware, so the page can age it correctly from any timezone.
        "generatedISO": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "companies": [
            {"code": code, "label": per_company[code]["label"],
             "minDate": per_company[code]["minDate"],
             "maxDate": per_company[code]["maxDate"]}
            for code, _ in companies
        ],
        "defaultCompany": cfg.get("default_company") or companies[0][0],
        "defaultFrom": default_from,
        "minDate": min_date,
        "maxDate": max_date,
        "groups": sorted({r[1] for r in rows}),
        "mtNotes": mt_notes,
        "customers": {no: names.get(no, no) for no in used},
        "salespeople": {c: sp_names.get(c, c) for c in sp_used if c},
        # Shortcut Dimension 3, shown as "Sector". No name table for it in BC, so the code
        # is the label; the empty code is dropped here and handled page-side.
        "sectors": [c for c in sectors_used if c],
        "items": item_names,
        "rows": rows,
    }

    # Measures sit at the end of the row; index from the right so adding a dimension
    # cannot silently shift them (see previous_totals for the same reasoning).
    total_mt = sum(r[-3] for r in rows) / 1000.0
    total_rev = sum(r[-2] for r in rows)
    total_cogs = sum(r[-1] for r in rows)
    print("")
    print("Totals over the full range ({0} -> {1}):".format(min_date, max_date))
    for code, _ in companies:
        c = per_company[code]
        print("  {0:<5} {1:>13,.2f} MT {2:>16,.2f} rev {3:>16,.2f} cogs   {4} -> {5}".format(
            code, c["mt"], c["revenue"], c["cogs"], c["minDate"], c["maxDate"]))
    print("  {0:<5} {1:>13,.2f} MT {2:>16,.2f} rev {3:>16,.2f} cogs".format(
        "ALL", total_mt, total_rev, total_cogs))
    print("  Gross Profit   {0:>16,.2f}  ({1:.2f}%)".format(
        total_rev - total_cogs,
        (total_rev - total_cogs) / total_rev * 100 if total_rev else 0))

    data_path = os.path.join(HERE, "data.json")
    totals = {"mt": total_mt, "revenue": total_rev, "cogs": total_cogs}
    rev_per_mt = total_rev / total_mt if total_mt else 0.0

    if os.environ.get("CHECK_TOTALS", "1") != "0":
        # Read the previous run's figures before this run overwrites them.
        prev = previous_totals(data_path)

        problems = ["{0} is {1:,.2f}, expected above zero".format(k, v)
                    for k, v in sorted(totals.items()) if v <= 0]
        # Per company as well as overall: a blended figure lets a healthy company hide a
        # broken one, which is exactly the failure this gate exists to catch.
        bands = [("ALL", total_mt, total_rev)]
        bands += [(code, per_company[code]["mt"], per_company[code]["revenue"])
                  for code, _ in companies]
        for label, mt, rev in bands:
            if mt <= 0 or rev <= 0:
                problems.append(
                    "{0}: MT {1:,.2f} and revenue {2:,.2f} must both be above zero".format(
                        label, mt, rev))
                continue
            rpm = rev / mt
            if not MIN_REVENUE_PER_MT <= rpm <= MAX_REVENUE_PER_MT:
                problems.append(
                    "{0}: revenue per MT is {1:,.2f}, outside the plausible {2:,.0f}-{3:,.0f}"
                    " band -- check the volume dedupe and the sign handling".format(
                        label, rpm, MIN_REVENUE_PER_MT, MAX_REVENUE_PER_MT))
        if problems:
            sys.exit("REFUSING TO WRITE, existing dashboard left untouched:\n  " +
                     "\n  ".join(problems))

        moved = []
        if prev:
            for key in sorted(totals):
                was = prev.get(key) or 0.0
                if was and abs(totals[key] - was) / abs(was) > DRIFT_WARN:
                    moved.append("{0}: {1:,.2f} -> {2:,.2f}".format(key, was, totals[key]))
        if moved:
            print("  WARNING: moved more than {0:.0%} since the last refresh:".format(DRIFT_WARN))
            for line in moved:
                print("    " + line)
        else:
            print("  Checks OK  (S$ {0:,.2f} revenue per MT)".format(rev_per_mt))

    with open(data_path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, separators=(",", ":"))

    template_path = os.path.join(HERE, "dashboard.template.html")
    if not os.path.exists(template_path):
        sys.exit("dashboard.template.html not found -- wrote data.json only")
    with open(template_path, encoding="utf-8") as fh:
        template = fh.read()
    if "/*__DATA__*/" not in template:
        sys.exit("template is missing the /*__DATA__*/ placeholder")

    # Escape "</" so the payload can never terminate the host <script> element.
    blob = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    with open(os.path.join(HERE, "dashboard.html"), "w", encoding="utf-8") as fh:
        fh.write(template.replace("/*__DATA__*/", blob))
    print("")
    print("Wrote dashboard.html ({0:.1f} KB embedded data)".format(len(blob) / 1024))


if __name__ == "__main__":
    build()
