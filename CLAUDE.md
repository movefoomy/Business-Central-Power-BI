# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A single dashboard, "Sales Margin Control", over Business Central sales value entries for
**CI Manufacturing Pte. Ltd** — volume (MT), revenue, cost of sales and gross profit by customer, plus
revenue/COGS product mix. Published as an Artifact:
<https://claude.ai/code/artifact/e9a57277-d2fd-41aa-8ecb-7e077b5aeab1>

No package manager, no build tool, no test framework. `refresh.py` is standard-library Python;
`dashboard.html` is a self-contained page with no external JS.

## Commands

```bash
python refresh.py            # fetch -> filter -> aggregate -> rebuild data.json + dashboard.html
CHECK_TOTALS=0 python refresh.py   # skip the control-total assertion
```

There is nothing to install and nothing to lint. To republish after a refresh, call the Artifact tool on
`dashboard.html` — republishing the **same file path** keeps the existing URL; from a different
conversation pass that URL as `url`, or you will create a second artifact instead of updating this one.

`dashboard.html` also opens straight from disk in a browser — no server, no credentials.

## Architecture

Two-stage build, and the split is the important part:

```
BC OData ──refresh.py──> data.json ──┐
                                     ├──> dashboard.html  (generated, do not edit)
        dashboard.template.html ─────┘
```

`refresh.py` replaces the `/*__DATA__*/` placeholder in the template with the aggregated JSON.
**Always edit `dashboard.template.html`; `dashboard.html` is overwritten on every refresh.**

The data is embedded rather than fetched live because the browser cannot reach BC: self-signed cert, no
CORS headers, and Basic auth credentials must never ship to a client. The page carries only the
aggregate — 2,499 rows at (customer × product group × posting date) grain, ~129 KB — which is enough for
every filter combination to recompute instantly client-side. Keep it that way; do not add a live fetch.

Credentials live in `config.json` (gitignored). Never inline them into the template.

## Source data — non-obvious

Use **`PBI_ValueEntriesPage`**, never `PBI_ValueEntries`. The latter has no `Source_No` (so it cannot be
joined to a customer at all) and none of the `_New` amount or kilogram fields. Customer names come from
`PBI_Customer`, joined `Source_No` → `Customer_No`; that entity returns one row per ledger entry, so
collapse it to a `Customer_No` → `Customer_Name` map.

**Never add `$top` to an OData query here.** BC treats it as a hard cap *and* suppresses
`@odata.nextLink`, so the result is silently truncated with no error — a `$top=5000` probe returned 5,000
of 34,333 rows and looked complete. Page through `@odata.nextLink` instead.

## The measure rules — the part that is easy to get wrong

Two rules that look inconsistent but are exact mirrors of each other. BC writes several value entries per
goods movement: the original, a cost adjustment, the invoice's reversal of expected, and the invoice's
actual.

- **Volume** counts rows where `Item_Ledger_Entry_Quantity <> 0` **only**. `WIN_Total_Qty_in_Kg` repeats
  the same figure on every one of those rows, and only the originating entry carries an item ledger
  quantity. Summing every row overstates volume ~12× (1,146,035 MT vs the correct 93,549 MT).
- **Revenue and cost** sum **all** rows — `Sales_Amount_Actual_New + Sales_Amount_Expected_New` and
  `Cost_Amount_Actual + Cost_Amount_Expected`. The expected amount posts on the shipment and is reversed
  by the invoice, which carries the actual, so only the full set nets to the true figure.

Volume and cost are negative for outbound sales and are **negated** for display — never `abs()`. A return
or credit memo carries the opposite sign and must subtract; `abs()` per bucket turns those reversals into
additions. This shipped as a bug on the first build and the control totals caught it.

Scope filters: the four sales document types, `Source_No ne 'ZZZZZ'`, `Posting_Date ge 2023-04-01`, and
client-side removal of item codes beginning `YY` (delivery charges — revenue but zero tonnage).

## Verification

`refresh.py` asserts full-period totals against `CONTROL_TOTALS` on every run and reports loudly on
drift. Current values:

| Measure | Value |
| --- | --- |
| Total MT | 93,548.61 |
| Total revenue | 26,128,244.00 |
| Total cost of sales | 25,115,282.42 |
| Gross profit | 1,012,961.58 (3.88%) |

These will legitimately move once BC has new postings — confirm the new figures look right, then update
`CONTROL_TOTALS`. Treat an unexplained move as a sign or dedupe regression, not as noise.

To check the page's own logic rather than the pipeline's, extract `compute()` out of `dashboard.html`
with a regex and run it in Node against the embedded blob — that tests shipped code instead of a
re-implementation. Useful invariants: KPI tiles equal the table totals row, each donut's slices sum to
its KPI, a single-customer filter moves everything together, and an empty date range yields zeroes
rather than NaN. Spot check: Infineum Singapore LLP → 1,325.99 MT / 923,943.77 / 683,184.08 /
240,759.69 GP.

## Dashboard conventions

Seven product groups map to seven fixed palette slots (`--s1`…`--s7`) assigned from `DATA.groups`.
**Colour follows the product group, never its rank** — a filter that drops a group must not repaint the
survivors, and both donuts must use the same mapping or the revenue-vs-cost comparison misleads. Donut
slices are drawn in fixed group order, not sorted by value, so neighbouring slices are always adjacent
palette slots — the pairing the palette was validated on. If you change these hues, re-run the dataviz
skill's `validate_palette.js` in both light and dark mode.

Theme tokens are declared three times — bare `:root`, `@media (prefers-color-scheme: dark)` guarded with
`:root:not([data-theme="light"])`, and `:root[data-theme="dark"]`. Style through tokens only; a colour
defined solely inside a media or `[data-theme]` block breaks the un-stamped default state.

The generated page has no `<!doctype>`/`<html>`/`<body>` wrapper — that is deliberate, since the Artifact
host supplies it. It still renders correctly from disk.

## Known data issue, not a bug

The two largest accounts run negative gross margin — Sumitomo Seika (−2.8%) and Chemical Industries
(Far East) Ltd (−1.1%, apparently intercompany transfer at or below cost). The expected/actual netting
was verified at row level against a sample document. Do not "fix" the formulas to make these positive.

Company data currently spans 2026-04-01 → 2026-08-28 only, so the April 2023 floor is a no-op today.
