# Sales Margin Control

Interactive dashboard over Business Central sales value entries for **CI Manufacturing Pte. Ltd** —
volume (MT), revenue, cost of sales and gross profit by customer, plus revenue and COGS product mix.

Published artifact: <https://claude.ai/code/artifact/e9a57277-d2fd-41aa-8ecb-7e077b5aeab1>

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

`refresh.py` uses the standard library only — no pip install. `dashboard.html` opens directly in a
browser from disk; it needs no server and no credentials.

**The published artifact does not update itself.** Its data is embedded at build time, so the hourly
task refreshes the local file only. To move a refresh onto the claude.ai link, ask Claude to republish
`dashboard.html` to the same artifact URL.

## Files

| File | Purpose |
| --- | --- |
| `config.json` | Endpoint and credentials. **Not committed** (see `.gitignore`). |
| `refresh.py` | Fetch, filter, aggregate, and inject data into the template. |
| `run_refresh.ps1` | What the hourly task runs: calls `refresh.py`, timestamps the output into `refresh.log`, trims the log to 1,000 lines. |
| `refresh.log` | Generated. Run history and errors. Not committed. |
| `dashboard.template.html` | The dashboard. Edit this, never `dashboard.html`. |
| `dashboard.html` | Generated. Overwritten on every refresh. |
| `data.json` | Generated. The aggregated payload, handy for checking figures. |

## Source data

`PBI_ValueEntriesPage` — **not** `PBI_ValueEntries`, which exposes neither `Source_No` (so it cannot be
linked to a customer) nor the `_New` amount and kilogram fields. Customer names come from
`PBI_Customer`, joined `Source_No` → `Customer_No`.

Server-side filter:

```
(Document_Type eq 'Sales Shipment' or 'Sales Invoice' or 'Sales Return Receipt' or 'Sales Credit Memo')
and Source_No ne 'ZZZZZ'
and Posting_Date ge 2023-04-01
```

Then, client side, item codes beginning `YY` (delivery charges — revenue but zero tonnage) are dropped.

Note for anyone extending the queries: **never add `$top`**. Business Central treats it as a hard cap
*and* suppresses `@odata.nextLink`, so the result is silently truncated with no error. Page through
`@odata.nextLink` instead.

## How the measures are calculated

**Total MT** — `WIN_Total_Qty_in_Kg / 1000`, counted **only on rows where
`Item_Ledger_Entry_Quantity <> 0`**.

Where BC has left `WIN_Conversion_to_Kg` unset (so the kg field is 0 and the tonnage would
silently vanish), the factor is derived from the item's base unit of measure instead. The UOM
codes are self-describing and encode kg per unit: `KG`=1, `MT`=1000, `DRUM-200`=200,
`IBC-1250`=1250, `CARB-25`=25, `BAG-1000`=1000. This is not a guess — the derivation reproduces
BC's own stored factor on all 3,593 rows where BC has one, with zero mismatches. Units that carry
no weight (`PCS`, `EACH`, `UNIT`, `JOB`) stay excluded from tonnage. Every substitution and every
exclusion is printed by `refresh.py` and shown on the dashboard, so the gap is never silent. Set
`derive_missing_conversion` to `false` in `config.json` for the literal rule with no fallback.

This is the part worth understanding. BC writes several value entries per goods movement — the original,
a cost adjustment, the invoice's reversal of expected cost, and the invoice's actual — and repeats the
*same* kilogram figure on every one. Only the originating entry carries an item ledger quantity. Summing
every row overstates volume by about 12× (1,146,035 MT instead of 93,549 MT).

**Total revenue** — `Sales_Amount_Actual_New + Sales_Amount_Expected_New` across **all** rows.

**Total cost of sales** — `Cost_Amount_Actual + Cost_Amount_Expected` across **all** rows.

Both amounts must use all rows, which is the mirror image of the volume rule: the expected amount posts
on the shipment and is reversed by the invoice, which carries the actual, so only the full set nets to
the true figure.

**Gross profit** — revenue − cost of sales.

Volume and cost are negative for outbound sales in BC and are **negated** for display, not `abs()`'d — a
return or credit memo carries the opposite sign and has to subtract. Taking `abs()` per bucket turns
those reversals into additions; it inflated MT and COGS on the first build until the totals check
caught it.

## Self-checks

Because the refresh is unattended, `refresh.py` guards its own output rather than trusting it.

**Sanity gate — refuses to write.** Every measure must be positive, and revenue per MT must fall in the
50–2,000 band (it currently sits near 279). This is the tripwire for the two bugs that actually happened
during development: removing the volume dedupe inflates MT about 12× and drags revenue per MT down to
roughly 23, and a sign error moves it similarly. On failure the script exits non-zero **without writing
anything**, so a broken run leaves the last good `dashboard.html` in place and Task Scheduler shows a
non-zero Last Run Result. This was verified by injecting the dedupe bug: the run refused at 22.81 per MT
and the dashboard was left untouched.

**Drift warning — logs only.** Each run compares its totals with the previous run's and notes any
measure that moved more than 25%. Ordinary trading never trips it; a code change or a bulk backposting
does. It is a warning, not a failure, because a genuine large backposting is possible.

Set `CHECK_TOTALS=0` to skip both.

An earlier version compared against a frozen set of expected totals. That was the right tool for a
one-off build and the wrong one for an hourly job — it began warning on every single run the moment BC
posted new data, which is exactly the noise that trains you to ignore a log.

## Two things to be aware of

**Rotate the access key.** The key in `config.json` was shared over chat, so treat it as exposed. It
never reaches the published page — only aggregated numbers are embedded — but it sits in plain text on
disk. `config.json` is gitignored.

**The negative margins are real.** Sumitomo Seika (−2.8%) and Chemical Industries (Far East) Ltd (−1.1%)
are the two largest accounts by revenue and both run at a loss on these figures; the latter looks like
intercompany transfer at or below cost. The expected/actual netting was checked at row level against a
sample document, so this reflects the source data rather than a formula error. Worth a business review.

## Why the data is embedded rather than fetched live

The browser cannot call BC directly: the host serves a self-signed certificate, sends no CORS headers,
and Basic auth credentials must never ship to a client. So `refresh.py` holds the credentials and the
page holds only the aggregate — about 2,500 rows at (customer × product group × posting date) grain,
129 KB, which is enough for every filter combination to recompute instantly in the browser.
