# Sales Margin Control

Interactive dashboard over Business Central sales value entries for **CI Manufacturing Pte. Ltd** —
volume (MT), revenue, cost of sales and gross profit by customer and by month, plus revenue and COGS
product mix.

Published artifact: <https://claude.ai/code/artifact/e9a57277-d2fd-41aa-8ecb-7e077b5aeab1>

What changed and why: [CHANGELOG.md](CHANGELOG.md).

## What is on the page

**Filters** drive everything at once — the four headline figures, the table and both charts move
together.

- Posting date **from / to**, plus quick ranges: All time, Last 30 days, Last 90 days, and
  **Financial YTD** (the year starts 1 April, so before April it reaches back into the prior year).
- A **customer picker** — multi-select with a search box, Select all and Clear. The button reports
  the selection ("All customers", the name when one is picked, otherwise a count). It stays open while
  you tick, so several customers can be chosen in one go; close it with the Customer button again, a
  click anywhere outside it, or Escape.
- **Reset filters** returns everything to the full range and all customers.

**Four KPI tiles** — total volume, revenue, cost of sales and gross profit for the current selection.

**Customer performance by month** — the main grid. Months run left to right and every month band
shows all five measures side by side:

| Column | Meaning |
| --- | --- |
| `MT` | Tonnage |
| `Rev` | Revenue |
| `COGS` | Cost of sales |
| `GP` | Gross profit |
| `GP %` | Gross profit ÷ revenue, worked out from that month's own figures — never averaged across months |

A period **Total** band sits on the right. Every column sorts. A dash means no trade that month, and
non-trading customers sort below traders rather than among the zeros. Month cells are abbreviated to
thousands (K) or millions (M) to keep the grid scannable; the Total band and the hover card carry full
precision, so a column can differ by a cent from adding up what is on screen.

The grid is **its own scroll viewport**, so the horizontal scrollbar stays reachable without scrolling
the page past every customer row. The header rows and the customer-name column stay pinned.

**Two product-mix bar charts** — Revenue by product and COGS by product, both by general product
posting group. They share **one scale and one row order**, so a product's revenue bar reads straight
across against its cost bar: wherever the lower bar is the longer one, that product sold below cost.

**A last-refreshed stamp** (top right) shows the build time and a live relative age that re-ticks on
its own. Past 90 minutes it turns amber — the task runs hourly, so a stopped refresh would otherwise
look identical to a healthy one. Underneath it, the posting date range actually present in the data.

**A footer** explaining each measure in business terms, and any tonnage conversion notes from the last
run (see *Missing conversions* below).

## Refreshing

A Windows scheduled task, **BC Sales Margin Refresh**, runs every hour and keeps `dashboard.html` on
disk current. It runs as you, only while you are logged on, with no stored password, and appends each
run to `refresh.log`. Nothing needs to be open for it to work.

To run it by hand, or to check on it:

```powershell
python refresh.py                                    # refresh now, output to the console
Start-ScheduledTask  -TaskName 'BC Sales Margin Refresh'   # trigger the hourly job now
Get-ScheduledTaskInfo -TaskName 'BC Sales Margin Refresh'  # LastRunTime / LastTaskResult (0 = success)
Get-Content refresh.log -Tail 20                     # what the last run did
Unregister-ScheduledTask -TaskName 'BC Sales Margin Refresh'   # stop the hourly refresh
```

**The published artifact does not update itself.** Its data is embedded at build time, so the hourly
task refreshes the local file only. To move a refresh onto the claude.ai link, ask Claude to republish
`dashboard.html` to the same artifact URL.

## Dependencies

**None.** `refresh.py` is standard-library Python only — no `pip install`, no virtualenv, no lockfile.
It imports `base64`, `collections`, `datetime`, `json`, `os`, `ssl`, `sys`, `urllib.parse` and
`urllib.request`.

`dashboard.html` is likewise self-contained: no bundler, no framework, no external JavaScript. It
loads one webfont from Google Fonts and falls back to system fonts without it. The page opens directly
from disk in a browser — no server, no credentials.

If you are tempted to add a package, weigh it against this: the whole thing currently runs on a stock
Python install and a browser.

## Configuration

Everything lives in `config.json`, next to `refresh.py`. It is **not committed** (see `.gitignore`).
`refresh.py` exits immediately if it is missing.

| Key | Required | Default | What it does |
| --- | --- | --- | --- |
| `base_url` | yes | — | OData v4 service root for the BC instance. A trailing slash is fine; it is stripped. |
| `company` | yes | — | BC company name, URL-encoded into `Company('…')` in the request path. |
| `username` | yes | — | Basic-auth user. |
| `access_key` | yes | — | Basic-auth web service access key. |
| `min_posting_date` | yes | — | Server-side floor on `Posting_Date`, as `YYYY-MM-DD`. Currently `2023-04-01`, which is a no-op while company data starts later than that. |
| `verify_tls` | no | `true` | Set `false` when the BC host serves a self-signed certificate — this disables hostname and chain verification for the fetch. |
| `derive_missing_conversion` | no | `true` | Whether to fall back to the item's base unit of measure when BC has left `WIN_Conversion_to_Kg` unset. Set `false` for the literal rule with no fallback. |

One environment variable: **`CHECK_TOTALS=0`** skips the sanity gate and the drift warning (see
*Self-checks*). Anything else, including unset, leaves both on.

## Files

| File | Purpose |
| --- | --- |
| `CHANGELOG.md` | What changed, by date and commit. |
| `config.json` | Endpoint and credentials. **Not committed** (see `.gitignore`). |
| `refresh.py` | Fetch, filter, aggregate, and inject data into the template. |
| `run_refresh.ps1` | What the hourly task runs: calls `refresh.py`, timestamps the output into `refresh.log`, trims the log to 1,000 lines. |
| `refresh.log` | Generated. Run history and errors. Not committed. |
| `dashboard.template.html` | The dashboard. Edit this, never `dashboard.html`. |
| `dashboard.html` | Generated. Overwritten on every refresh. |
| `data.json` | Generated. The aggregated payload, handy for checking figures. |

## Source data

Three OData collections are read, all under the same service root. `refresh.py` builds each request as:

```
{base_url}/Company('{company}')/{entity}?$select=...&$filter=...
```

| Entity | `$select` | Why |
| --- | --- | --- |
| `PBI_ValueEntriesPage` | `Source_No, Item_No, Document_No, Gen_Prod_Posting_Group, Posting_Date, Item_Ledger_Entry_Quantity, WIN_Total_Qty_in_Kg, Sales_Amount_Actual_New, Sales_Amount_Expected_New, Cost_Amount_Actual, Cost_Amount_Expected` | Every figure on the dashboard. |
| `PBI_Customer` | `Customer_No, Customer_Name` | Customer names, joined `Source_No` → `Customer_No`. Returns one row per ledger entry, so it is collapsed to a no → name map. |
| `PBI_Item` | `No, Description, Base_Unit_of_Measure` | The base UOM behind the tonnage fallback, and item descriptions for the conversion notes. |

Use `PBI_ValueEntriesPage` — **not** `PBI_ValueEntries`, which exposes neither `Source_No` (so it
cannot be linked to a customer) nor the `_New` amount and kilogram fields.

Server-side filter, applied to `PBI_ValueEntriesPage` only:

```
(Document_Type eq 'Sales Shipment' or 'Sales Invoice' or 'Sales Return Receipt' or 'Sales Credit Memo')
and Source_No ne 'ZZZZZ'
and Posting_Date ge {min_posting_date}
```

Then, client side, item codes beginning `YY` (delivery charges — revenue but zero tonnage) are dropped.

Note for anyone extending the queries: **never add `$top`**. Business Central treats it as a hard cap
*and* suppresses `@odata.nextLink`, so the result is silently truncated with no error. Page through
`@odata.nextLink` instead — `fetch()` already does.

## How the measures are calculated

**Total MT** — `WIN_Total_Qty_in_Kg / 1000`, counted **only on rows where
`Item_Ledger_Entry_Quantity <> 0`**.

This is the part worth understanding. BC writes several value entries per goods movement — the original,
a cost adjustment, the invoice's reversal of expected cost, and the invoice's actual — and repeats the
*same* kilogram figure on every one. Only the originating entry carries an item ledger quantity. Summing
every row overstates volume by about 12x.

**Missing conversions.** Where BC has left `WIN_Conversion_to_Kg` unset (so the kg field is 0 and the
tonnage would silently vanish), the factor is derived from the item's base unit of measure instead,
because the UOM codes are self-describing:

- A fixed table covers the bare weight units — `KG`=1, `MT`=1000, `DMT`=1000, `TON`=1000, `G`=0.001.
- Any code of the form `PREFIX-NUMBER` yields that number as its fill weight, so `DRUM-200`=200,
  `IBC-1250`=1250 and `CARB-27.5`=27.5 all fall out of the same rule rather than a hand-kept list.
- Genuinely weightless units — `PCS`, `EACH`, `EA`, `UNIT`, `JOB`, `HOUR`, `DAY` — stay excluded. A
  drum sold as a drum is not product weight.

This is not a guess: the derivation reproduces BC's own stored factor on every row where BC has one,
with zero mismatches. Every substitution and every exclusion is printed by `refresh.py` and shown in
the dashboard footer, so the gap is never silent. Set `derive_missing_conversion` to `false` for the
literal rule with no fallback.

**Total revenue** — `Sales_Amount_Actual_New + Sales_Amount_Expected_New` across **all** rows.

**Total cost of sales** — `Cost_Amount_Actual + Cost_Amount_Expected` across **all** rows.

Both amounts must use all rows, which is the mirror image of the volume rule: the expected amount posts
on the shipment and is reversed by the invoice, which carries the actual, so only the full set nets to
the true figure.

**Gross profit** — revenue minus cost of sales. **GP %** — gross profit as a share of revenue, always
derived from the underlying figures and never averaged across months.

Volume and cost are negative for outbound sales in BC and are **negated** for display, not `abs()`'d — a
return or credit memo carries the opposite sign and has to subtract. Taking `abs()` per bucket turns
those reversals into additions; it inflated MT and COGS on the first build until the totals check
caught it.

## Self-checks

Because the refresh is unattended, `refresh.py` guards its own output rather than trusting it.

**Sanity gate — refuses to write.** Every measure must be positive, and revenue per MT must fall in the
50–2,000 band (it currently sits near 280). This is the tripwire for the two bugs that actually happened
during development: removing the volume dedupe inflates MT about 12x and drags revenue per MT down to
roughly 23, and a sign error moves it similarly. On failure the script exits non-zero **without writing
anything**, so a broken run leaves the last good `dashboard.html` in place and Task Scheduler shows a
non-zero Last Run Result. This was verified by injecting the dedupe bug: the run refused and the
dashboard was left untouched.

**Drift warning — logs only.** Each run compares its totals with the previous run's and notes any
measure that moved more than 25%. Ordinary trading never trips it; a code change or a bulk backposting
does. It is a warning, not a failure, because a genuine large backposting is possible.

Set `CHECK_TOTALS=0` to skip both.

An earlier version compared against a frozen set of expected totals. That was the right tool for a
one-off build and the wrong one for an hourly job — it began warning on every single run the moment BC
posted new data, which is exactly the noise that trains you to ignore a log. Assert invariants, not
remembered numbers.

## Two things to be aware of

**Rotate the access key.** The key in `config.json` was shared over chat, so treat it as exposed. It
never reaches the published page — only aggregated numbers are embedded — but it sits in plain text on
disk. `config.json` is gitignored.

**The negative margins are real.** The two largest accounts by revenue both run at a loss on these
figures. Chemical Industries (Far East) Ltd sits near −1%, which looks like intercompany transfer at or
below cost. **Sumitomo Seika has deteriorated through FY27** — roughly +12% in April down to −23% in
July, with no August postings at all — and since May its cost of sales has exceeded revenue outright
while tonnage held steady, so it is a price or unit-cost problem rather than a volume one. The
expected/actual netting was checked at row level against a sample document, so this reflects the source
data rather than a formula error. Worth a business review; do not "fix" the formulas to make it
positive.

## Why the data is embedded rather than fetched live

The browser cannot call BC directly: the host serves a self-signed certificate, sends no CORS headers,
and Basic auth credentials must never ship to a client. So `refresh.py` holds the credentials and the
page holds only the aggregate — about 2,500 rows at (customer × product group × posting date) grain,
roughly 130 KB, which is enough for every filter combination to recompute instantly in the browser.
Months are derived in the browser from the daily dates, so changing the time grain needs no refresh.
