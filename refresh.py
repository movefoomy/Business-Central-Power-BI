"""Refresh the BC Sales Margin dashboard from Business Central OData.

Fetches PBI_ValueEntriesPage + PBI_Customer, applies the sales filters, aggregates to
(customer, product group, posting date) grain and injects the payload into
dashboard.template.html to produce dashboard.html.

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

# Control totals verified against the live service. A mismatch means the dedupe rule
# or a sign convention has changed upstream, so report it loudly rather than publish
# numbers nobody has checked. Set CHECK_TOTALS=0 in the environment to skip.
CONTROL_TOTALS = {
    "mt": 93548.61,
    "revenue": 26128244.00,
    "cogs": 25115282.42,
}
CONTROL_TOLERANCE = 0.01


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


def entity_url(cfg, entity, select, flt=None):
    base = "{0}/Company('{1}')/{2}".format(
        cfg["base_url"].rstrip("/"),
        urllib.parse.quote(cfg["company"]),
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


def build():
    cfg = load_config()
    header, ctx = make_opener(cfg)

    print("Fetching from Business Central...")

    doc_filter = " or ".join("Document_Type eq '{0}'".format(d) for d in SALES_DOC_TYPES)
    ve_filter = "({0}) and Source_No ne '{1}' and Posting_Date ge {2}".format(
        doc_filter, EXCLUDED_SOURCE_NO, cfg["min_posting_date"]
    )
    ve_select = (
        "Source_No,Item_No,Gen_Prod_Posting_Group,Posting_Date,"
        "Item_Ledger_Entry_Quantity,WIN_Total_Qty_in_Kg,"
        "Sales_Amount_Actual_New,Sales_Amount_Expected_New,"
        "Cost_Amount_Actual,Cost_Amount_Expected"
    )
    entries = fetch(
        entity_url(cfg, "PBI_ValueEntriesPage", ve_select, ve_filter),
        header, ctx, "value entries",
    )
    customer_rows = fetch(
        entity_url(cfg, "PBI_Customer", "Customer_Name,Customer_No"),
        header, ctx, "customers",
    )

    # PBI_Customer returns one row per ledger entry, so collapse to a No -> Name map.
    names = {}
    for row in customer_rows:
        no = row.get("Customer_No")
        if no and no not in names:
            names[no] = (row.get("Customer_Name") or no).strip()

    fetched = len(entries)
    entries = [
        r for r in entries
        if not (r.get("Item_No") or "").upper().startswith(EXCLUDED_ITEM_PREFIX)
    ]
    print("  {0} fetched -> {1} after excluding {2}* items".format(
        fetched, len(entries), EXCLUDED_ITEM_PREFIX))

    # Aggregate to (customer, product group, posting date).
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
    agg = collections.defaultdict(lambda: [0.0, 0.0, 0.0])
    for row in entries:
        key = (
            row.get("Source_No") or "",
            row.get("Gen_Prod_Posting_Group") or "(none)",
            row.get("Posting_Date") or "",
        )
        bucket = agg[key]
        if num(row, "Item_Ledger_Entry_Quantity") != 0:
            bucket[0] += num(row, "WIN_Total_Qty_in_Kg")
        bucket[1] += num(row, "Sales_Amount_Actual_New") + num(row, "Sales_Amount_Expected_New")
        bucket[2] += num(row, "Cost_Amount_Actual") + num(row, "Cost_Amount_Expected")

    # kg and cost are negative for outbound sales in BC, so negate to make them
    # display-positive. Negate rather than abs(): a return or credit memo carries the
    # opposite sign and must SUBTRACT from the bucket. Taking abs() per bucket would
    # turn those reversals into additions and overstate volume and cost.
    rows = [
        [no, group, date, round(-kg, 2), round(rev, 2), round(-cost, 2)]
        for (no, group, date), (kg, rev, cost) in sorted(agg.items())
    ]
    print("  {0} aggregate rows".format(len(rows)))

    used = sorted({r[0] for r in rows})
    missing = [no for no in used if no not in names]
    if missing:
        print("  WARNING: {0} customer no(s) not in PBI_Customer: {1}".format(
            len(missing), ", ".join(missing[:10])))

    dates = [r[2] for r in rows if r[2]]
    data = {
        "generated": datetime.datetime.now().strftime("%d %b %Y, %H:%M"),
        "company": cfg["company"],
        "minDate": min(dates) if dates else "",
        "maxDate": max(dates) if dates else "",
        "groups": sorted({r[1] for r in rows}),
        "customers": {no: names.get(no, no) for no in used},
        "rows": rows,
    }

    total_mt = sum(r[3] for r in rows) / 1000.0
    total_rev = sum(r[4] for r in rows)
    total_cogs = sum(r[5] for r in rows)
    print("")
    print("Totals over the full range ({0} -> {1}):".format(data["minDate"], data["maxDate"]))
    print("  Total MT       {0:>16,.2f}".format(total_mt))
    print("  Total Revenue  {0:>16,.2f}".format(total_rev))
    print("  Total COGS     {0:>16,.2f}".format(total_cogs))
    print("  Gross Profit   {0:>16,.2f}  ({1:.2f}%)".format(
        total_rev - total_cogs,
        (total_rev - total_cogs) / total_rev * 100 if total_rev else 0))

    if os.environ.get("CHECK_TOTALS", "1") != "0":
        actual = {"mt": total_mt, "revenue": total_rev, "cogs": total_cogs}
        bad = [
            "{0}: expected {1:,.2f} got {2:,.2f}".format(k, v, actual[k])
            for k, v in CONTROL_TOTALS.items()
            if abs(actual[k] - v) > CONTROL_TOLERANCE
        ]
        if bad:
            print("")
            print("Control totals moved (expected once BC has new postings):")
            for line in bad:
                print("  " + line)
            print("Review the figures above, then update CONTROL_TOTALS in refresh.py.")
        else:
            print("  Control totals OK")

    with open(os.path.join(HERE, "data.json"), "w", encoding="utf-8") as fh:
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
