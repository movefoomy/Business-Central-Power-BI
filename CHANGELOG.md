# Changelog

All notable changes to Sales Margin Control.

This project has no release process, no version tags and no package manifest, so entries are keyed by
**date and commit** rather than a version number. If it ever gains tags, these become the 0.1 / 0.2 /
0.3 releases in order.

Generated files (`dashboard.html`, `data.json`, `refresh.log`) change on every hourly run and are not
tracked here — only changes to the pipeline, the template and the documentation are.

---

## Unreleased

### Changed

- **`README.md` substantially rewritten** to match the code as it now stands. It had fallen behind by
  one commit and carried several outright errors.
  - Added a *What is on the page* section — the README documented the pipeline but never the dashboard
    itself: filters and quick ranges, the KPI tiles, the monthly grid, the two bar charts, the refresh
    stamp, the footer.
  - Added a *Configuration* table. Four of the seven `config.json` keys (`base_url`, `company`,
    `username`, `access_key`) were undocumented, and `min_posting_date` / `verify_tls` were not
    mentioned at all.
  - Added a *Dependencies* section stating plainly that there are none, and naming the standard-library
    modules `refresh.py` imports so the claim can be checked in a second.
  - Documented **`PBI_Item`** as the third OData entity read. It has been fetched since `5f07763` and
    was never in the README; it is what feeds the tonnage fallback.
  - Corrected the unit-of-measure rules. The README presented `CARB-25` / `BAG-1000` as a fixed list,
    when the code uses a fixed table (`KG`, `MT`, `DMT`, `TON`, `G`) plus a generic `PREFIX-NUMBER`
    parse; `DMT`, `TON`, `G`, `EA`, `HOUR` and `DAY` were all missing.
  - Removed frozen figures that had already rotted — "all 3,593 rows", "1,146,035 MT instead of
    93,549 MT", and the stale "Sumitomo Seika (−2.8%)". The margin note now reflects the FY27
    deterioration. Same reasoning that removed `CONTROL_TOTALS` from the pipeline: remembered numbers
    rot against an hourly feed.
- `README.md` now links to this changelog.

### Published

- Artifact republished 2026-09-01 with the 10:09 data. It had been carrying the 2026-08-31 16:35 build
  for roughly 18 hours — the hourly task refreshes the local file only, and nothing republishes the
  artifact automatically. The local pipeline was healthy throughout (`LastTaskResult 0`, no missed runs).

---

## 2026-08-31 — `7c4d7af` · Show all measures per month, fix grid scrolling, swap in bar charts

Five changes to how the dashboard reads.

### Changed

- **The customer table shows every measure at once** instead of hiding four behind a toggle. Each month
  is a band of five columns — MT, revenue, COGS, gross profit, GP % — under a spanning header, with a
  matching Total band and one row per customer. All 31 columns sort independently.
- **Donuts replaced by horizontal bar charts**, and the table and charts swapped places. Length compares
  far better than arc angle, and it allows one shared scale across both charts plus one shared row
  order, so a product's revenue bar reads straight across against its cost bar.
- Months are separated by a rule and a faint alternating wash. Per-cell magnitude shading was removed —
  at this column count it was noise rather than a cue.
- `border-collapse` changed from `collapse` to `separate`. Collapsed borders belong to the table, not
  the cell, so sticky cells drop them while scrolling; every rule in the grid is now an inset
  `box-shadow`.
- The footnotes became a definition list covering every column in business terms, keeping the
  underlying BC expression in small type for anyone reconciling against the source, plus notes on
  scope, reading the table, rounding, and the filters driving the whole page.
- `CLAUDE.md` rewritten for all of the above.

### Fixed

- **The grid is now its own scroll viewport**, capped near half the screen. The horizontal scrollbar
  previously sat below all 98 rows, so reaching it meant scrolling the whole page to the end. Header
  pins to the top, totals to the bottom, customer column to the left.
- An absent month now yields `undefined` rather than `0`, so non-trading customers sort **below**
  traders instead of among the zeros.
- The measure header row sticks at a *measured* band height, re-measured on resize and once webfonts
  load. Assuming the height made the two header rows overlap when the webfont swapped in.
- **Restored the `.c1`–`.c7` palette slot classes**, which were swallowed along with the donut CSS that
  had happened to define them. Every bar and every tooltip swatch would have rendered in the same flat
  accent. Caught before publishing; they now sit beside the bar rules with a comment recording why.

### Removed

- A frozen spot check in `CLAUDE.md` that had already rotted — the same failure as the `CONTROL_TOTALS`
  canary. The standing rule is now recorded: **never assert fixed expected values**, in the pipeline or
  in a test.

### Observed in the data at the time

Two of the seven product groups (PROJECT, HCL) sit visibly below cost. NAOH is 68% of revenue at roughly
1.3% margin, which is what holds the business near 4% overall.

---

## 2026-08-31 — `5f07763` · Fix invisible pie charts, add hourly refresh, monthly pivot, MT conversion fallback

Four changes, in the order they were found.

### Fixed

- **The pie charts rendered black and were therefore invisible on the dark card.** Slice colours were
  set with `fill="var(--sN)"` as an SVG *presentation attribute*, where `var()` is never resolved, so
  fill fell back to its initial black. The legend used an inline style, which does resolve — hence
  coloured legend rows beside an empty chart. Colours now come from CSS rules via a per-slot `--c`
  custom property.
- A lone 100% slice painted nothing: an arc from *a* to *a*+2π is degenerate. It is now drawn as a
  stroked ring.
- The mark-clearing step no longer deletes the SVG `<title>` that `aria-labelledby` references.
- **Tonnage was being silently dropped** wherever BC had left `WIN_Conversion_to_Kg` unset — see below.

### Added

- **Hourly refresh.** A `BC Sales Margin Refresh` scheduled task runs `run_refresh.ps1` under
  interactive logon with no stored password, appending each run to `refresh.log`.
- **A sanity gate that refuses to write** when any measure is non-positive or revenue per MT leaves the
  50–2,000 band, so an unattended run cannot overwrite a good dashboard with implausible numbers.
  Verified by fault injection: with the dedupe bug reintroduced it refused at 22.81 per MT and left the
  dashboard intact.
- **A drift warning** (log only) for any headline measure moving more than 25% against the previous run.
- **A kilograms-per-unit fallback** (`kg_per_unit()`), deriving the factor from the item's base unit of
  measure where BC has left the conversion unset. The codes are self-describing (`KG`=1, `MT`=1000, and
  packaging codes embed their fill weight). Not a guess: it reproduced BC's own stored factor on all
  3,593 rows that had one, with zero mismatches. It recovered 15.82 MT of citric acid to Public
  Utilities Board across three August shipments that had shown no tonnage at all. Weightless units
  (`PCS` and similar) stay excluded.
  - Both outcomes — derived and weightless — are printed by `refresh.py` and shown in the dashboard
    footer, rather than being absorbed silently.
  - New config key `derive_missing_conversion` (default `true`) turns the fallback off.
- **A third OData entity, `PBI_Item`** (`No`, `Description`, `Base_Unit_of_Measure`), to support the
  above.
- `Document_No` added to the value-entry `$select`, so the conversion notes can report document counts.
- **A monthly pivot** for customer performance: customers down, months across, a Total column, a toggle
  for which measure fills the grid, a pinned customer column, and a hover card giving all five measures
  at full precision.
- **A last-refreshed stamp** in the header with a live relative age that turns amber past 90 minutes, so
  a stopped refresh cannot look healthy.

### Removed

- **`CONTROL_TOTALS` / `CONTROL_TOLERANCE`** — a frozen set of expected totals asserted on every run. It
  began warning on every single run the moment BC posted new data, which is exactly the noise that
  trains you to ignore a log. Replaced by the sanity gate and drift warning above, which assert
  invariants rather than remembered numbers.

### Verified

The Total MT rule already behaved as intended, and this is now proven: 3,597 qty-bearing rows map to
3,597 distinct item ledger entries, so each goods movement is counted exactly once.

### Observed in the data at the time

The monthly split showed Sumitomo Seika's margin falling from 12.0% to −22.6% across April–July, which
the blended −2.8% total had hidden.

---

## 2026-08-30 — `6d30cec` · Initial build

### Added

- **The dashboard.** Volume (MT), revenue, cost of sales and gross profit by customer, plus revenue and
  COGS product mix, filterable by posting date and customer.
- **`refresh.py`** — pulls `PBI_ValueEntriesPage` and `PBI_Customer`, applies the sales filters,
  aggregates to (customer × product group × posting date) grain, and injects the payload into
  `dashboard.template.html`.
- **`config.json`** for endpoint and credentials, gitignored.
- Full-period control totals asserted on every run, to catch sign and dedupe regressions. (Replaced the
  following day — see `5f07763`.)

### Design decisions recorded at the time

- **Data is embedded rather than fetched live.** The browser cannot reach BC: self-signed certificate,
  no CORS headers, and Basic auth credentials must never ship to a client.
- **`PBI_ValueEntriesPage` is the only usable entity.** `PBI_ValueEntries` exposes no `Source_No`, so it
  cannot be joined to a customer, and lacks the `_New` amount and kilogram fields.
- **Tonnage counts only rows with `Item_Ledger_Entry_Quantity <> 0`.** BC writes several value entries
  per goods movement and repeats the same kilogram figure on each; summing every row overstates volume
  about 12×. Revenue and cost deliberately use *all* rows, since the shipment's expected amount and the
  invoice's reversal net correctly only together.
- **Volume and cost are negated, not `abs()`'d**, so returns and credit memos subtract rather than add.
