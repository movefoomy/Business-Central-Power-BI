# Sales Margin Control

Interactive dashboard over Business Central sales value entries for **CI Manufacturing Pte. Ltd** —
volume (MT), revenue, cost of sales and gross profit by customer, plus revenue and COGS product mix.

Published artifact: <https://claude.ai/code/artifact/e9a57277-d2fd-41aa-8ecb-7e077b5aeab1>

## Refreshing

```
python refresh.py
```

Pulls from OData, rebuilds `data.json` and `dashboard.html`, and prints the totals. Standard library
only — no pip install. Then republish `dashboard.html` to the same artifact URL so the link stays put.

`dashboard.html` also opens directly in a browser from disk; it needs no server and no credentials.

## Files

| File | Purpose |
| --- | --- |
| `config.json` | Endpoint and credentials. **Not committed** (see `.gitignore`). |
| `refresh.py` | Fetch, filter, aggregate, and inject data into the template. |
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
those reversals into additions; it inflated MT and COGS on the first build until the control totals
caught it.

## Control totals

`refresh.py` checks the full-period totals against `CONTROL_TOTALS` on every run and reports loudly if
they move. As at the 2026-04-01 → 2026-08-28 data:

| Measure | Value |
| --- | --- |
| Total MT | 93,548.61 |
| Total revenue | 26,128,244.00 |
| Total cost of sales | 25,115,282.42 |
| Gross profit | 1,012,961.58 (3.88%) |

These will legitimately move once BC has new postings. When they do, confirm the new figures look right,
then update `CONTROL_TOTALS`. Set `CHECK_TOTALS=0` to skip the check.

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
page holds only the aggregate — 2,499 rows at (customer × product group × posting date) grain, about
129 KB, which is enough for every filter combination to recompute instantly in the browser.
