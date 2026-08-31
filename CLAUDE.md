# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A single dashboard, "Sales Margin Control", over Business Central sales value entries for
**CI Manufacturing Pte. Ltd**. Four KPI tiles, two product-mix donuts, and a monthly grid of customers
showing MT, revenue, cost of sales, gross profit and GP % for every month. Published as an Artifact:
<https://claude.ai/code/artifact/e9a57277-d2fd-41aa-8ecb-7e077b5aeab1>

No package manager, no build tool, no test framework. `refresh.py` is standard-library Python;
`dashboard.html` is self-contained with no external JS.

## Commands

```bash
python refresh.py                  # fetch -> filter -> aggregate -> rebuild data.json + dashboard.html
CHECK_TOTALS=0 python refresh.py   # skip the sanity and drift checks
```

A Windows scheduled task, **BC Sales Margin Refresh**, runs `run_refresh.ps1` hourly (interactive logon,
no stored password) and appends to `refresh.log`. Inspect with `Get-ScheduledTaskInfo -TaskName
'BC Sales Margin Refresh'` — `LastTaskResult` 0 is success. The hourly job refreshes the **local file
only**; the published artifact embeds its data at build time and must be republished by Claude.

Nothing to install, nothing to lint. To republish, call the Artifact tool on `dashboard.html` —
republishing the **same file path** keeps the URL; from another conversation pass that URL as `url`, or
you create a second artifact instead of updating this one. `dashboard.html` also opens straight from
disk — no server, no credentials.

## Architecture

```
BC OData ──refresh.py──> data.json ──┐
                                     ├──> dashboard.html  (generated, do not edit)
        dashboard.template.html ─────┘
```

`refresh.py` replaces the `/*__DATA__*/` placeholder in the template with the aggregated JSON.
**Always edit `dashboard.template.html`; `dashboard.html` is overwritten on every refresh.**

Data is embedded rather than fetched live because the browser cannot reach BC: self-signed cert, no CORS
headers, and Basic auth credentials must never ship to a client. The page carries only the aggregate —
about 2,500 rows at **(customer × product group × posting date)** grain, ~130 KB — enough for every
filter combination to recompute instantly client-side. Keep it that way; do not add a live fetch.

Payload keys: `rows` (`[customer_no, group, date, kg, revenue, cost]`, all display-positive), `customers`
(no → name), `groups`, `minDate`/`maxDate`, `generated` (display string) and `generatedISO`
(offset-aware, for ageing), and `mtNotes` (see below). Months are derived client-side from the daily
dates, so changing the time grain needs no refresh.

Credentials live in `config.json` (gitignored). Never inline them into the template.

## Source data — non-obvious

Use **`PBI_ValueEntriesPage`**, never `PBI_ValueEntries`. The latter has no `Source_No` (so it cannot be
joined to a customer at all) and none of the `_New` amount or kilogram fields. Customer names come from
`PBI_Customer`, joined `Source_No` → `Customer_No`; it returns one row per ledger entry, so collapse it
to a `Customer_No` → `Customer_Name` map. `PBI_Item` supplies `Base_Unit_of_Measure`.

**Never add `$top` to an OData query here.** BC treats it as a hard cap *and* suppresses
`@odata.nextLink`, so the result is silently truncated with no error — a `$top=5000` probe returned 5,000
of 34,000+ rows and looked complete. Page through `@odata.nextLink` instead.

## The measure rules — the part that is easy to get wrong

BC writes several value entries per goods movement: the original, a cost adjustment, the invoice's
reversal of expected, and the invoice's actual. The volume and amount rules look contradictory but are
exact mirrors.

- **Volume** counts rows where `Item_Ledger_Entry_Quantity <> 0` **only**, then
  `WIN_Total_Qty_in_Kg / 1000`. That field repeats on every row of the movement and only the originating
  entry carries a ledger quantity, so summing every row overstates volume ~12×. Verified: the
  qty-bearing rows map one-to-one onto distinct item ledger entries.
- **Revenue and cost** sum **all** rows — `Sales_Amount_Actual_New + Sales_Amount_Expected_New` and
  `Cost_Amount_Actual + Cost_Amount_Expected`. The expected amount posts on the shipment and is reversed
  by the invoice, which carries the actual, so only the full set nets to the truth.
- **Missing conversions.** `WIN_Conversion_to_Kg` is kg per base unit and is sometimes unset, which
  silently drops that shipment's tonnage. `kg_per_unit()` derives it from the item's base UOM, whose
  codes encode it (`KG`=1, `MT`=1000, and packaging codes embed their fill weight: `DRUM-200`=200,
  `IBC-1250`=1250, `CARB-27.5`=27.5). This reproduces BC's stored factor on every row that has one — not
  a guess. `PCS`/`EACH`/`UNIT`/`JOB` carry no weight and stay excluded. Both outcomes land in `mtNotes`,
  print in the log, and render in the dashboard footer. **Keep them visible**; the whole point is that
  the gap was previously invisible. Disable with `derive_missing_conversion: false` in `config.json`.

Volume and cost are negative for outbound sales and are **negated** for display — never `abs()`. A return
or credit memo carries the opposite sign and must subtract; `abs()` per bucket turns reversals into
additions. This shipped as a bug on the first build.

Scope: the four sales document types, `Source_No ne 'ZZZZZ'`, `Posting_Date ge 2023-04-01`, and
client-side removal of item codes beginning `YY` (delivery charges — revenue but zero tonnage).

## Self-checks

The refresh is unattended, so `refresh.py` guards its own output. Do not weaken these to print-only.

- **Sanity gate (refuses to write).** All measures positive, revenue per MT within 50–2,000 (sits near
  279). Removing the volume dedupe drops it to ~23; a sign error moves it similarly. On failure it exits
  non-zero *before writing*, so the last good `dashboard.html` survives. Verified by fault injection.
- **Drift warning (logs only).** Flags any headline measure moving >25% versus the previous run.

**Never reintroduce frozen expected values** — not in `refresh.py`, not in a test. A `CONTROL_TOTALS`
constant was tried and began warning on every run within a day of BC posting new data; a test asserting
fixed totals rotted the same way. BC changes hourly. Assert invariants instead: months sum to the Total
column, the grid sums to the KPI tiles, donut slices sum to their tile, GP = revenue − COGS per cell,
GP % derived never summed, filters only ever narrow, empty ranges yield zeroes not NaN.

To test the page rather than the pipeline, slice `compute()` out of `dashboard.html` and run it in Node
against the embedded blob — that exercises shipped code instead of a re-implementation. Two traps when
writing such a harness: `compute()` depends on the `measures` helper defined just above it, so slice from
`const measures = ` rather than matching `function compute()` alone; and a CSS lookup by `indexOf(sel)`
finds the wrong rule (`tfoot td {` is a substring of `tbody td, tfoot td {`), so anchor at line start and
merge every matching rule.

## Dashboard conventions

**SVG fill must come from CSS, never a presentation attribute.** `fill="var(--s1)"` is not resolved by
any browser; the attribute is discarded and the mark falls back to black, which on the dark surface is
invisible. This shipped and made both donuts disappear. A `.c1`–`.c7` class sets `--c` and CSS rules
(`.donut path { fill: var(--c) }`) consume it. The same applies to `stroke`.

**A 360° arc is degenerate.** Start and end points coincide and nothing paints, so a lone 100% slice is
drawn as a stroked `<circle>`, not a path.

Seven product groups map to seven fixed palette slots (`--s1`…`--s7`) from `DATA.groups`. **Colour
follows the product group, never its rank** — a filter that drops a group must not repaint the survivors,
and both donuts must share the mapping. Slices are drawn in fixed group order, not by value, so
neighbours are always adjacent palette slots — the pairing the palette was validated on. If you change
these hues, re-run the dataviz skill's `validate_palette.js` in light and dark.

**The monthly grid.** `SUBS` defines the five measure columns repeated under each month band. Sort keys
are `name`, `total:<measure>` or `m:YYYY-MM:<measure>`; an absent month must yield `undefined`, not 0, so
non-trading customers sort below traders rather than among zeros. Month cells abbreviate money
(`compact()`); the Total band and the hover card carry full 2-decimal precision.

**The grid is its own scroll viewport** (`max-height: min(58vh, 640px)`), so the horizontal scrollbar is
reachable without scrolling the page past all 98 rows. Three consequences, all load-bearing:

- `border-collapse` **must stay `separate`**. Collapsed borders belong to the table, not the cell, so
  sticky cells lose them while scrolling. Every rule in the grid is an inset `box-shadow`.
- The z-order ladder is corner `6` > footer name `5` > header `4` > footer `3` > body left column `2`.
  Get this wrong and the pinned corner slides under the header mid-scroll.
- The measure header row sticks at `top: var(--band-h)`, and `syncBandHeight()` **measures** the band
  rather than assuming it — re-run on resize and on `document.fonts.ready`, or the rows overlap once the
  webfont swaps in.

**The refresh stamp** (top right) shows the absolute time from `generated` and a live relative age from
`generatedISO`, re-ticking every 30s. Past 90 minutes it turns amber, because the task runs hourly and a
stopped refresh otherwise looks identical to a healthy one.

Theme tokens are declared three times — bare `:root`, `@media (prefers-color-scheme: dark)` guarded with
`:root:not([data-theme="light"])`, and `:root[data-theme="dark"]`. Style through tokens only; a colour
defined solely inside a media or `[data-theme]` block breaks the un-stamped default state.

The generated page has no `<!doctype>`/`<html>`/`<body>` wrapper — deliberate, the Artifact host supplies
it. It still renders from disk.

## Known data issues, not bugs

The two largest accounts run negative gross margin. Chemical Industries (Far East) Ltd sits near −1%,
apparently intercompany transfer at or below cost. **Sumitomo Seika deteriorated through FY27 — roughly
+12% in April to −23% in July, with no August postings at all** — and since May its COGS exceeds revenue
outright while tonnage held steady, so it is a price or unit-cost problem rather than a volume one. The
expected/actual netting was verified at row level against a sample document. Do not "fix" the formulas
to make these positive.

Company data currently spans 2026-04-01 onward only, so the April 2023 floor is a no-op today.

## Repository layout

This folder is its own git repo whose `main` branch holds these files at the root. They are pushed to
`github.com/movefoomy/Business-Central-AI-Agent`, branch `Power-BI-CIM`, under a **`power-bi-cim/`**
subdirectory alongside the existing `bc_odata_mcp/`. The two histories are unrelated, so a push grafts a
new commit onto the remote tip using a temporary index — never `--force`, and never a checkout, which
would dump the whole monorepo into this folder. The remote also carries a dangling
`value-entries-dashboard` submodule gitlink with no `.gitmodules`; pre-existing, left alone.
