# Changelog

All notable changes to Sales Margin Control.

This project has no release process, no version tags and no package manifest, so entries are keyed by
**date and commit** rather than a version number. If it ever gains tags, these become the 0.1 / 0.2 /
0.3 releases in order.

Generated files (`dashboard.html`, `data.json`, `refresh.log`) change on every hourly run and are not
tracked here — only changes to the pipeline, the template and the documentation are.

---

## Unreleased

### Added

- **The grain explanation rewritten for a business reader.** The previous version was accurate but
  written for whoever maintains the code — buckets, keys, ISO weeks, spikiness ratios. It now says what
  a point means, which setting to use when, and where the numbers can mislead, in plain English.
  - Adds a worked example of **periods cut short by the date filter**, which the chart does not yet
    flag. One common scenario, both edges: with the range set to 1–31 July, the first point is the week
    commencing 29 June but holds only 1–5 July (29 and 30 June excluded by *from*), and the last is the
    week commencing 27 July but holds only 27–31 July (1 and 2 August excluded by *to*). Both hold five
    days rather than seven, so both sit low for a reason that has nothing to do with trading.
  - Written as a hypothetical rather than a claim about the data — no year, no weekday — so it does not
    go stale. An earlier version generated these examples from the live selection; reverted at the
    user's request in favour of the simpler fixed wording.
  - `partial` catches only a trailing period the *data* has not filled, not one clipped by the *filter*.
    Recorded as a known gap in `README.md` and `CLAUDE.md` pending a per-point clipped test.
  - Makes explicit that **weeks do not add up to months**, since a week can straddle a month end.

- **The MT trend tab explains its grains properly, in a section of their own.** *How the trend is
  calculated* now covers only the chart; *How Day, Week and Month are calculated* sits at the bottom of
  the tab and sets out each grain — what it buckets by, where the point is plotted, and how part periods
  differ — plus where a point sits on the date axis and which grain to reach for when.
  - It carries a **live comparison of the three grains** (points, total tonnage, busiest ÷ typical
    period) computed from the current selection rather than written into the prose. The same rule that
    removed `CONTROL_TOTALS` from the pipeline applies to numbers in the page: the figures written into
    the README a day earlier had already drifted from 136 points and 122× to 137 and 123.5×. The table
    also demonstrates its own claim that the grains agree, by showing identical totals for all three.
  - `renderGrainStats` samples each grain by swapping `tstate.grain`, and restores it; the harness
    asserts both that and that the row for the selected grain matches the plot above it.
  - The table-view note moved out of the chart section, being about the table.

- **Each tab now explains only its own figures.** The "how each figure is calculated" footer was shared,
  so the MT trend tab carried definitions of revenue, cost of sales, gross profit, GP % and price per MT —
  none of which appear on it — along with notes about sorting table columns and two bar charts sharing a
  scale, neither of which is on that screen. Each panel now has its own footer. The tonnage-conversion
  flag moved to a third footer outside both tabs, since a missing kg conversion understates tonnage on
  either; its card hides with it when there is nothing to report.
  - Two stale notes fixed while splitting: the grid was still described as "all five figures" (six since
    the Price per MT column), and the filters note still named only the date range and customer
    (salesperson and product group have since been added).

- **Salesperson and Sector filters on the Revenue trend tab**, and Shortcut Dimension 3 carried through
  the pipeline as `sector`.
  - The aggregation grain gains the dimension, so the row shape is now
    `[customer, group, date, salesperson, sector, kg, revenue, cost]`. Headline totals are unchanged.
  - **Sector is empty in Business Central**, so its dropdown does not currently appear. A direct probe
    of the endpoint found Shortcut Dimension 3 unset on every value entry — along with Global Dimension
    1 and 2 and Shortcut Dimensions 4–8, with `Dimension_Set_ID` of `0` throughout, meaning no dimension
    set is attached at all. Not a field-name or query problem. The control hides itself below two
    options and will appear on its own once BC populates the dimension; nothing page-side needs
    changing then.
  - The salesperson filter works on real data: S01 is 40.5% of revenue, and the **quarter of revenue
    carrying no salesperson code** gets its own option rather than being unreachable.
  - Extra dimensions are declared through `cfg.dims` rather than hand-built, so the factory supplies the
    Set, the dropdown, the registry entry, the pill and the reset line. A dimension never filters its
    own option list, for the same reason the other pickers do not.
  - `SP_CODES` / `spName` moved out of the margin tab's picker block into the shared derived-data
    section, since two features now read them.
  - `refresh.py` and the trend test suite both index the measures **from the right** now, so the next
    dimension cannot silently shift them — which is exactly what caught this change: 18 tests failed
    with the measures reading a dimension string.
  - 12 new checks: salespeople partition revenue, an unmatched code yields zeroes not NaN, salesperson
    and customer intersect rather than union, sector survives the payload as a real dimension, and the
    extra dimensions do not leak into the MT or Gross profit tabs. Suite is 33 margin + 155 trend.

- **The trend filter band redesigned.** It was a wrapping flex row that left the right-hand side of a
  wide screen empty and gave no visual cue that filtering existed.
  - **Now one 12-column grid.** Every field spans whole columns and each of the two rows totals exactly
    twelve — date 3 + quick 4 + grain 3 + view 2, then customer 3 + groups 7 + reset 2 — so labels
    align across the band and controls align beneath them. `.ctl` carries a shared minimum height so
    the rows stay level whatever they hold.
  - **Chip rows fill their cells.** Quick range, grain and view are equal-width column grids; product
    groups use an `auto-fit` track. A chip row that stopped short of its cell was what made the band
    look ragged.
  - A first attempt used three bordered sections with headings above them. That was worse — blocks of
    differing height, labels floating wherever their control put them — and was replaced. Its dead
    `.sgroup` rules and a stale 900px media query that would have collapsed the new grid were removed
    with it.
  - **Icons**, from one `<symbol>` sprite: a calendar for which period, a funnel for which postings, an
    eye for how shown, and calendar / layers / grid / person on the Showing pills. Section headings
    moved to the accent colour so the three decisions register at a glance.
  - **Colour means state.** A Showing pill lights up only when its dimension narrows the view, and
    Reset gains an amber `armed` style only when there is something to reset — grain excluded, being a
    way of looking rather than a filter. The seven series hues are deliberately not used for chrome:
    colour follows the product group everywhere else on the page.
  - `icon12()` builds sprite references through `createElementNS`. An `<use>` parsed as HTML is inert
    and renders nothing — the same class of trap as `var()` in a presentation attribute.
  - Also fixed the structural checker, which reported false tag mismatches: `HTMLParser` fires both
    start and end callbacks for a self-closing `<rect/>`, popping a stack entry that was never pushed.

- **A Gross profit trend tab**, and the filter band reworked across all three trend tabs.
  - Gross profit is **derived, not stored** — revenue less cost of sales per row — and reconciles to
    the other two tabs exactly, which is asserted. It is the measure most often below zero: three of the
    seven product groups are negative over the period, so the downward-opening scale and the zero line
    built earlier do their real work here.
  - **All three panels are now generated from one string** in the build script. MT was hand-written and
    Revenue was cloned from it; a third copy would have guaranteed drift, and a change to the filter
    band would have landed on two tabs out of three.
  - **The filter band is grouped, summarised and resettable.** Six controls in an undifferentiated
    wrapping row now sit in three labelled sections — which period, which postings, how shown — with a
    **Reset filters** button that the trend tabs had been missing entirely. Under the band, a
    **Showing** strip carries one pill per dimension, lit only when that dimension is narrowing the
    view, so what is applied is readable without inspecting each control.
  - Two test corrections, both found by the third measure rather than by eye:
    - The suite asserted that monthly is an order of magnitude steadier than daily. True for tonnage and
      revenue, **false for gross profit**, which nets gains against losses inside a bucket and currently
      reads spikier monthly than weekly. The claim that holds for all three — and the one the default
      actually rests on — is that daily is the spikiest; the stronger claim is now asserted only where
      it is true.
    - It also dropped the group with the largest *total* and expected the *peak* to fall. Those differ
      for gross profit: CI2 earns the most over the period while NAOH owns the single highest month. It
      now drops the peak-holder.
  - Suite is 33 margin + 143 trend.

- **A customer filter on both trend tabs.** Written once in `createTrend`, so MT trend and Revenue trend
  both gained it. It is the searchable multi-select picker rather than the chip row the product groups
  use, since 98 customers is far past what chips can hold, and each option shows that customer's figure
  for the measure in question.
  - It registers into the single `PANELS` registry through a descriptor the factory returns, so a click
    outside it, or Escape, behaves exactly as on the margin tab's three pickers — no second copy of the
    open/close logic.
  - Option totals respect the tab's date range and product groups but **not** its own customer
    selection; included in its own totals, every unticked name would read zero.
  - Filters stay per-tab: narrowing to a customer on one trend tab leaves the other, and the margin tab,
    untouched. Asserted, not assumed.
  - 16 new checks, including that individual customers partition the total for both measures, that
    customer and group filters intersect rather than union, and that an unmatched customer yields
    zeroes rather than NaN. Suite is now 33 margin + 95 trend.
  - Caught by those tests rather than by eye: the suite's own `reset()` predated the filter and left a
    customer selection standing between assertions, which made five unrelated checks fail. A test-only
    bug, but it is the reason the new state is cleared explicitly.

- **A Revenue trend tab**, and the trend code refactored into one implementation serving both.
  `createTrend(cfg)` builds a tab from a config naming its id prefix, which column of a row it reads and
  how a figure is written; `TRENDS` holds the two instances. Everything else — the grain machinery, the
  plot, the crosshair, the legend, the table twin, the slicers, the grain-comparison footer — is shared
  rather than copied, so the two tabs cannot drift apart. A third measure is a `TRENDS` entry plus a
  markup panel.
  - The panels are duplicated in the template because their ids must differ, but they are generated
    from a single string in the build script for the same reason the JS is shared.
  - Each tab keeps its **own** date range, grain and product-group selection. Changing one leaves the
    others untouched, which is asserted rather than assumed.
  - Revenue goes negative too — PROJECT posted about −S$26k in one month — so the downward-opening y
    scale built for tonnage returns earns its keep on the second tab without change.
  - The test suite now runs every structural check against **both** measures: a shared factory that
    passes for tonnage and quietly breaks for revenue is exactly the failure this guards against.
    Grew from 43 checks to 79, including per-group geometry at every grain for each measure.

- **An MT trend tab.** The page is now two tabs. The new one carries a line chart of tonnage shipped
  per posting date, one line per general product posting group, with its own date range and group
  selection — independent of the margin tab's filters, since it answers "what did we ship, when".
  - **Grain: Day / Week / Month, defaulting to Month.** This is what makes it a trend. Shipments arrive
    in lumps, so per posting date the peak period is 122x the median and the line is 136 spikes against
    a flat floor. Weekly is still 11.5x, because the bulk cargoes themselves land about monthly; monthly
    is 1.3x. Nothing is smoothed or averaged — every grain totals to identical tonnage, asserted in the
    harness — and Day remains available for finding the shipment behind a spike.
  - **A part period is drawn hollow** and called out in the hint and the table. Three days of September
    after a full August would otherwise plot as a collapse rather than as a month that has barely
    started. Markers are drawn on every observation once a selection is 40 points or fewer, since a
    six-point polyline with no marks reads as an estimate.
  - The slicer band sits **inside the tile**, as asked. The dataviz skill calls per-chart filters an
    anti-pattern, its rule being one filter row above everything it scopes; the tab holds exactly one
    chart plus its table twin, so the band at the top of the tile is that row. Adding a second chart to
    that tab means moving the slicer out.
  - **The y scale follows the selected groups**, which is what makes the slicer worth having: NAOH is
    three quarters of all tonnage, so with it shown the other six are flat. Deselecting it rescales them.
  - **The scale opens below zero.** Daily tonnage goes negative when a credit memo lands — HCL posts
    −54.92 MT on 2026-07-31. Anchoring at zero drew that point below the plot box and across the date
    labels, since the SVG sets `overflow: visible`. Caught by a geometry check, not by eye.
  - A day a group did not ship is a real `0`, not a gap, so groups can be compared on the same day.
  - Colour comes from the same `classOf` map as the bars, so a group is one colour on both tabs and
    hiding one never repaints the others.
  - **A table view ships with it, and is not optional.** The palette validator raises a contrast WARN in
    light mode — three of the seven hues fall under 3:1 against the card — which obligates visible
    labels or a table view; it is also the accessibility pass's required table twin.
  - Crosshair and tooltip on hover, over a hit area spanning the whole plot rather than the lines, so
    there is no pinpoint target. `renderTrend` keeps the SVG's `<title>`/`<desc>`, which
    `aria-labelledby` points at.
  - Palette re-validated for line marks against both card surfaces before any chart code was written:
    all checks pass in dark, and light passes with the contrast WARN noted above.
  - Verified by a second Node harness over the shipped `trendData()` — 38 checks, including that tonnage
    and every group's total are conserved across all three grains, that monthly is an order of magnitude
    less spiky than daily (the property the default rests on), that the part-period flag points at the
    last bucket and only the last, that `weekStart` always lands on a Monday and is idempotent, that
    hiding a group leaves the others' values and colours untouched, that an empty range yields zeroes
    rather than NaN, and that every plotted point of every single-group selection at every grain lands
    inside the plot box.

- **A `Price per MT` column** (`S$/MT`) in the monthly grid — revenue ÷ tonnage, the average realised
  selling price. It repeats under every month band and in the Total band like the other measures, sorts
  independently, and appears in the hover card at full precision and in the footnotes.
  - **Derived, never summed**, at every level — cell, row total, month footer and grand total. Adding
    the monthly rates instead would be wrong and would not look wrong: the per-customer column
    currently sums to about 61,600 against a true blended 271.52. This is asserted, not just intended.
  - Guards its divisor. A month can carry revenue with no tonnage, which reads `0.00` rather than
    `Infinity`; September currently exercises this with four all-zero postings.
  - The grand-total row in `renderTable` is built by hand rather than from `SUBS`, so it needed the new
    key explicitly — noted in `CLAUDE.md` as the one place a seventh measure would silently render
    `undefined`.

- **A product group filter.** A third dropdown over `Gen_Prod_Posting_Group`, which was already a
  dimension of the payload — no new fetch, no grain change, so `data.json` is unchanged by it. Each
  option carries the palette swatch of that group's bar and the list is drawn in the fixed group order
  the charts use.
  - **Filtering must not repaint the survivors.** `classOf` is built once from the full `DATA.groups`,
    never from the filtered list, so a group keeps its colour whatever else is hidden. Previously a
    written-down rule with no user-reachable way to violate it; now asserted in the harness.
  - The swatch rule was scoped to `#tip .sw`, so it is now `#tip .sw, .opt .sw`.

- **A salesperson filter.** `PBI_SalesPersonCode` is now read as a fourth entity and joined
  `Salespers_Purch_Code` → `Code`, the aggregation grain gains the salesperson, and a second
  multi-select dropdown sits beside the customer picker. Six salespeople are currently in the data.
  - **Entries carrying no salesperson get their own "No salesperson" option.** They are 60 aggregate
    rows and roughly a quarter of revenue; leaving them out of the list would have made a quarter of
    the business unreachable by the filter while still counting it in every total.
  - Each picker now shows revenue per option computed under the *other* picker's selection, so the
    figure beside a name says what ticking it would contribute rather than what it is worth alone. A
    picker excluding itself from its own totals is what stops every unticked option reading zero.
  - The picker hides itself when the data holds fewer than two salespeople — a filter that cannot
    narrow anything invites a click and does nothing.
  - The dropdowns share one open/close registry rather than a copy of the logic each, so opening one
    closes the others and a click inside any of them is never mistaken for a click outside. A fourth
    filter is a row in `PANELS` plus a render function.
  - `fillOpts` mutates the selection Set it is handed, so Select all adds in a loop rather than
    reassigning — a reassignment orphans every checkbox listener against a dead Set.
  - Row shape changed to `[customer_no, group, date, salesperson_code, kg, revenue, cost]`, and the
    payload gains a `salespeople` code → name map. `previous_totals()` now indexes the measures from
    the right, so the one run whose previous `data.json` predates the change compares correctly instead
    of summing a dimension string.
  - Verified with a Node harness driving the shipped `compute()` against the embedded payload — 26
    invariants, not frozen numbers: for both new filters, selecting every option equals selecting none,
    the individual selections partition the totals, a filter only ever narrows, an unmatched value
    yields zeroes rather than NaN, the pickers intersect rather than union, each picker's option totals
    ignore itself but respect the others, the palette survives filtering, and the existing month/Total,
    grid/tile, bar/tile and GP identities still hold under the new dimension.

### Changed

- **The value-entry source moved from `PBI_ValueEntriesPage` to `PBI_ValueEntries_New`**, with the
  39-field `$select` agreed for that endpoint. The new page carries the same rows and adds
  `Inventory_Posting_Group`, `Reason_Code` and `Cost_Posted_to_GL`; the sales amounts lost the `_New`
  field-name suffix (`Sales_Amount_Actual_New` → `Sales_Amount_Actual`), which is the only code change
  the swap required beyond the entity name.
  - Verified rather than assumed: the regenerated `data.json` is identical to the previous run's
    field for field — same 2,597 aggregate rows, same 98 customers, same 7 groups, same date range,
    same conversion notes, and Total MT / revenue / COGS matching to the cent. Only the timestamp
    differs.
  - The entity and its field list are now the constants `VALUE_ENTRY_ENTITY` and `VALUE_ENTRY_SELECT`
    rather than literals inside `build()`. Eleven of the 39 fields feed the aggregation; the rest are
    selected to keep the query identical to the one documented for the endpoint, and cost only
    bandwidth. Fetch time was unaffected (~15s for 35,861 rows).
  - `PBI_ValueEntries_New` previously lacked `WIN_Total_Qty_in_Kg` and `WIN_Conversion_to_Kg`, which
    would have left Total MT with no source. Both were added to the page in BC, so the migration became
    possible; a `$metadata` check confirmed all 39 fields before any code was touched.

### Fixed

- **The customer picker could not be closed when the page was opened from disk.** The browser's default
  `[hidden] { display: none }` is a UA-stylesheet rule, so `.panel { display: flex }` outranked it and
  `panel.hidden = true` had no visual effect. Every close path — the Customer button, a click outside,
  Escape — set the attribute correctly and left the panel on screen. The Artifact host injects
  `[hidden]{display:none!important}` into the wrapper it supplies, so the published page was unaffected
  and the bug only appeared in the local file. The template now declares the rule itself, and both
  contexts behave identically.
  - `#mt-notes` uses the same attribute. It has no competing `display` rule so it was never broken, but
    it is now covered by the same guarantee.

### Changed

- `CLAUDE.md` brought in line with the code: the opening description still said "two product-mix
  donuts", stale since `7c4d7af` swapped them for bar charts, and the palette convention referred to
  donut slices and `.donut path`. Added the `[hidden]` rule as a standing convention, and recorded the
  general lesson — the page must not depend on anything the Artifact host injects, so "works in the
  artifact" is not evidence that the file works from disk.
- Dropped the "a 360° arc is degenerate" note from `CLAUDE.md`. It described the lone-100%-slice case in
  the donut renderer, which no longer exists.

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
- Corrected the revenue footnote in the dashboard, which still cited
  `Sales_Amount_Actual_New + Sales_Amount_Expected_New` after the move to `PBI_ValueEntries_New` had
  dropped the `_New` suffix from those field names.

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
