# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Four tabs, "Sales Margin Control", over Business Central sales value entries for
**two companies** — CI Manufacturing Pte. Ltd. (`CIM`) and Chemical Industries Limited
(`CIL`, whose BC display name is Chemical Industries (Far East) Limited) — selectable from
one dropdown above the tabs, plus a **Group** view that adds them together. Four KPI tiles, two product-mix bar charts, and a monthly grid of customers
showing MT, revenue, cost of sales, gross profit, GP % and price per MT for every month. Published as an Artifact:
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
'BC Sales Margin Refresh'` — `LastTaskResult` 0 is success.

**The task also publishes.** On a clean run it commits `dashboard.html` and pushes to
`dashboard/main` (`github.com/movefoomy/Business-Central-Power-BI`, private), and Vercel rebuilds
<https://business-central-power-bi.vercel.app/> from that push. This is the only shape that works:
Business Central is on-prem behind a self-signed cert, so no cloud cron can reach it — this machine
fetches, and pushing is how the result leaves it. It pushes **only when `refresh.py` exits 0**, so a
build the sanity gate rejected never reaches the site, and a push failure is logged without failing
the task — the commit stays local and the next hour retries. `GIT_TERMINAL_PROMPT=0` and
`GCM_INTERACTIVE=never` are set so an expired credential fails fast instead of hanging the task
forever on an invisible prompt. It pushes every hour even when the figures have not moved, because
the page's own refresh stamp goes amber past 90 minutes: skipping unchanged data would make a healthy
site look stalled.

The **claude.ai artifact is a separate publication** and does not follow: it embeds its data at build
time and must still be republished by Claude.

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
about 40,000 rows at
**(customer × product group × posting date × salesperson × sector × item × company)** grain — 3.6 MB raw,
about 560 KB gzipped, which is what actually crosses the wire — enough for every filter combination and
either company to recompute instantly client-side. Keep it that way; do not add a live fetch.

**CIL is an order of magnitude bigger than CIM and carries three more years**: 855,000 value entries against
37,000, and postings from 2023-04-01 where CIM starts 2026-04-01. That asymmetry is why the page opens on
`defaultFrom` (April 2026, the window both companies trade in) rather than on `minDate`, and it is most of the
payload. A full refresh now takes minutes rather than seconds — the hourly task has room, but do not add a
third large company without checking that first.

Payload keys: `rows`
(`[customer_no, group, date, salesperson_code, sector, item_no, company_code, kg, revenue, cost]`, all
display-positive), `companies` (ordered `{code, label, minDate, maxDate}`), `defaultCompany`, `defaultFrom`,
`customers` (no → name), `salespeople` (code → name), `sectors` (Shortcut Dimension 3
codes, see below), `items` (item no → description), `groups`, `minDate`/`maxDate`,
`generated` (display string) and `generatedISO` (offset-aware, for ageing), and `mtNotes` (see below).
Months are derived client-side from the daily dates, so changing the time grain needs no refresh.

**Dimensions are only ever APPENDED.** Item went in after sector and company after item, precisely so that
customer 0, group 1, date 2, salesperson 3 and sector 4 kept their positions — the trend tabs' `cfg.dims` read
those by index. What each one does move is the measures, which is the only reason `cfg.value` reads 7/8/9.

**The companies share one coding scheme, verified rather than assumed.** Across the full extract: 93 shared
customer codes with **zero** name conflicts, 70 shared item codes with **zero** description conflicts, and
salesperson codes naming the same people. So the lookup maps are a plain union keyed by code — no
namespacing, no mapping table. The single disagreement is salesperson `S06`, "How Huan Soon" in CIM and
"Huan Soon" in CIL; first company in `companies` wins, which is why that config key is ordered. Both companies
post in their own local currency and both read as SGD; value-entry amounts are already LCY, so there is no FX
step. **Re-check this before adding a third company** — it is a property of these two, not a guarantee.

**The measures sit at the end of the row, not at a fixed index.** Adding a dimension shifts them, and
`previous_totals()` in `refresh.py` reads the *previous* run's `data.json` — a file that may predate the
change. It indexes from the right (`-3, -2, -1`) for exactly that reason. Anything else new that reads a
persisted row must do the same, or the one run that spans a shape change either raises or reports
nonsense drift.

Credentials live in `config.json` (gitignored). Never inline them into the template. That file also
carries `companies` (ordered code → BC company name), `company_labels` (code → what the dropdown shows),
`default_company` and `default_from`. `company_list()` falls back to a single-company `company` key, so the
older config shape still runs.

## Source data — non-obvious

A fourth entity, **`PBI_SalesPersonCode`**, supplies salesperson names, joined
`Salespers_Purch_Code` → `Code`. Only `Code` and `Name` are read from it. **A value entry can carry no
salesperson at all** — currently 60 aggregate rows and about a quarter of revenue — so those rows
aggregate under the empty code and get their own "No salesperson" option in the picker. Dropping them
from the list would make a quarter of the business unreachable by that filter while still counting it in
every total.

Use **`PBI_ValueEntries_New`**, never `PBI_ValueEntries`. The latter has no `Source_No` (so it cannot be
joined to a customer at all) and none of the amount or kilogram fields. `PBI_ValueEntries_New` replaced
`PBI_ValueEntriesPage`: same rows, but the sales amounts lost the `_New` field-name suffix
(`Sales_Amount_Actual_New` → `Sales_Amount_Actual`) and it adds `Inventory_Posting_Group`, `Reason_Code`
and `Cost_Posted_to_GL`. The entity and its 39-field `$select` are `VALUE_ENTRY_ENTITY` /
`VALUE_ENTRY_SELECT`; only eleven of those fields feed the aggregation. Customer names come from
`PBI_Customer`, joined `Source_No` → `Customer_No`; it returns one row per ledger entry, so collapse it
to a `Customer_No` → `Customer_Name` map. `PBI_Item` supplies `Base_Unit_of_Measure` and the `Description` behind the grid's item breakdown. That
description falls back to the value entry's own `Description` and then to the item code, so `items` carries a
non-empty label for every code in `rows` — the breakdown must never draw a blank line under a customer.

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
- **Revenue and cost** sum **all** rows — `Sales_Amount_Actual + Sales_Amount_Expected` and
  `Cost_Amount_Actual + Cost_Amount_Expected`. The expected amount posts on the shipment and is reversed
  by the invoice, which carries the actual, so only the full set nets to the truth.
- **Missing conversions.** `WIN_Conversion_to_Kg` is kg per base unit and is sometimes unset, which
  silently drops that shipment's tonnage. `kg_per_unit()` derives it from the item's base UOM, whose
  codes encode it (`KG`=1, `MT`=1000, and packaging codes embed their fill weight: `DRUM-200`=200,
  `IBC-1250`=1250, `CARB-27.5`=27.5). This reproduces BC's stored factor on every row that has one — not
  a guess. `PCS`/`EACH`/`UNIT`/`JOB` carry no weight and stay excluded. **The suffix rule only holds
  because the prefix is a real container word.** CIL carries `XXXX-930`, a placeholder, and reading 930 kg
  out of it would be inventing tonnage rather than recovering it; `PLACEHOLDER_UOM_PREFIXES` refuses those
  and they surface in `mtNotes` like any other unconvertible unit. `mtNotes` entries carry a `company`, and
  the page shows only the selected company's. Both outcomes land in `mtNotes`,
  print in the log, and render in the dashboard footer. **Keep them visible**; the whole point is that
  the gap was previously invisible. Disable with `derive_missing_conversion: false` in `config.json`.

Volume and cost are negative for outbound sales and are **negated** for display — never `abs()`. A return
or credit memo carries the opposite sign and must subtract; `abs()` per bucket turns reversals into
additions. This shipped as a bug on the first build.

Scope: the four sales document types, `Source_No ne 'ZZZZZ'`, `Posting_Date ge 2023-04-01`, and
client-side removal of item codes beginning `YY` (delivery charges — revenue but zero tonnage).

## Self-checks

The refresh is unattended, so `refresh.py` guards its own output. Do not weaken these to print-only.

- **Sanity gate (refuses to write).** All measures positive, revenue per MT within 50–2,000 —
  **checked per company as well as overall**, because a blended figure lets a healthy company mask a broken
  one, which is exactly the failure this gate exists to catch. CIM sits near 274, CIL near 338, the blend
  near 328. Removing the volume dedupe drops it to ~23; a sign error moves it similarly. On failure it exits
  non-zero *before writing*, so the last good `dashboard.html` survives. Verified by fault injection.
- **Drift warning (logs only).** Flags any headline measure moving >25% versus the previous run.

**Never reintroduce frozen expected values** — not in `refresh.py`, not in a test. A `CONTROL_TOTALS`
constant was tried and began warning on every run within a day of BC posting new data; a test asserting
fixed totals rotted the same way. BC changes hourly. Assert invariants instead: months sum to the Total
column, the grid sums to the KPI tiles, bar values sum to their tile, GP = revenue − COGS per cell,
GP % and price per MT derived never summed, filters only ever narrow, empty ranges yield zeroes not
NaN.

To test the page rather than the pipeline, slice `compute()` out of `dashboard.html` and run it in Node
against the embedded blob — that exercises shipped code instead of a re-implementation. Two traps when
writing such a harness: `compute()` depends on the `measures` helper defined just above it, so slice from
`const measures = ` rather than matching `function compute()` alone; and a CSS lookup by `indexOf(sel)`
finds the wrong rule (`tfoot td {` is a substring of `tbody td, tfoot td {`), so anchor at line start and
merge every matching rule.

## Dashboard conventions

**The `hidden` attribute needs its own `!important` rule.** The browser's default
`[hidden] { display: none }` comes from the UA stylesheet, so *any* author `display` outranks it.
`.panel` sets `display: flex`, which made `panel.hidden = true` a no-op: the customer picker set the
attribute correctly on every close path and stayed on screen regardless. The Artifact host injects
`[hidden]{display:none!important}` into the wrapper it supplies, so the published page behaved while
the identical file opened from disk did not — the bug was invisible in exactly the place it was most
often looked at. The template now declares `[hidden] { display: none !important; }` itself.
**Do not remove it.** More generally: the page must not depend on anything the host injects, and a
change to open/close behaviour has to be checked from disk as well as published.

**SVG fill must come from CSS, never a presentation attribute.** `fill="var(--s1)"` is not resolved by
any browser; the attribute is discarded and the mark falls back to black, which on the dark surface is
invisible. This shipped and made both product-mix charts disappear, back when they were donuts. A
`.c1`–`.c7` class sets `--c` and CSS rules consume it — `.bfill { background: var(--c) }` for today's
bars. The same applies to `stroke`.

Nine product groups map to nine fixed palette slots (`--s1`…`--s9`) from `DATA.groups` — seven that both
companies post, plus `MAINTENANCE` and `MATERIAL`, which only CIL does. Slots 8 and 9 were added for them and
both themes were re-run through the dataviz skill's `validate_palette.js`: all checks pass in light and dark.
The light contrast WARN on three of the original seven is unchanged and is still discharged by the table view.
`classOf` is built from the **full** `DATA.groups`, never from the company-scoped `CO_GROUPS`, so switching
company cannot repaint a group; the harness asserts that and asserts the nine slots stay distinct. **Colour
follows the product group, never its rank** — a filter that drops a group must not repaint the survivors,
and both charts must share the mapping. Rows are drawn in fixed group order, not by value, so
neighbours are always adjacent palette slots — the pairing the palette was validated on. If you change
these hues, re-run the dataviz skill's `validate_palette.js` in light and dark. The product-group
picker makes that repaint rule directly reachable by a user, so it is asserted in the harness rather
than only written down: `classOf` is built once from the full `DATA.groups` and never from the filtered
list. The picker shows each group's palette swatch, which is only honest while that holds.

**An option list that rebuilds itself detaches the element that was clicked.** Every picker re-renders its
rows when one is ticked — the change handler calls `render()`, which re-runs the open picker's `render*Opts`.
By the time that click finishes bubbling to `document`, the clicked element is no longer in the tree, so
`panel.contains(e.target)` is `false` and the close-on-outside-click handler closed the panel **mid-selection**.
It affected all three pickers and was only obvious on the product tree, where ticking a group and then opening
it to pick descriptions takes two clicks. The fix is a **capture-phase** listener that records which panel the
click began in, before any option handler can run; the bubble-phase handler skips that panel. **Do not test
containment in the bubble phase alone**, and do not "fix" a future instance of this by suppressing the
re-render. Relatedly, the product tree's disclosure toggles `.kids.hidden` **in place** rather than calling
`renderGpOpts()`: opening a group changes no figure, so a rebuild would only throw away focus and scroll
position. The tree's checkboxes carry a `data-pkey` so focus is restored across the rebuilds that do happen.

**Three filter dropdowns share one open/close implementation** — customer, salesperson and product. They
share the panel markup and a single `PANELS` registry that owns open/close, so opening one closes the others
and a click inside any of them is never mistaken for a click outside. Add a fourth by adding a row to
`PANELS` and a `render*Opts`, not by copying the wiring. Customer and salesperson also share `fillOpts`;
**the product picker does not**, because it is a tree rather than a list — see below.

**The product filter is two levels: product group, then item description, on ALL FOUR TABS.** A group is too
coarse a question on its own — `NAOH` covers 22 item descriptions under CIM and 37 under CIL, at different
strengths and prices, so "which spec is losing money" cannot be asked of the group. `renderProductTree()` is
the single renderer; it owns no state, taking the two Sets to read and mutate, the totals to show, a formatter
and an `onChange`. **A fifth product picker is another call to it, never a copy.** The trend tabs replaced
their group chip row with it, for the same reason the customer filter was never chips: a chip cannot carry a
second level, and 175 descriptions is far past what a chip row holds. Each trend tab shows the figure beside
each entry in **its own measure** — tonnage on the MT tab, gross profit on the GP tab — via `productTotalsT()`,
not revenue.

- **The selection is two sets, not one.** The margin tab's are `state.grp`/`state.item`; each trend tab has its
  own `st.groups`/`st.item`, so the tabs stay independent while the meaning of a tick does not.
  `productPasses(grpSet, itemSet, grp, item)` is the single predicate: both empty means no filter, otherwise
  the row passes if **either** its group or its item is ticked. That OR is what makes a parent tick mean "all
  of these" and a child tick mean "just this one". Every filtering loop goes through it — never test a group
  Set directly again.
- **Both empty means everything, and so does every group ticked whole.** `productIsAll()` treats the two
  alike, so Select all does not light a pill that narrows nothing. The trend tabs' `st.groups` used to start
  as every group explicitly; it now starts empty, which is what let them share the predicate at all — the old
  shape could not express "all of NAOH plus one spec of HCL".
- **`selectedGroups()` decides which lines a trend tab draws**, in fixed palette order: a group is on screen
  if it is ticked whole or any of its items is. Colour still follows the group, so narrowing to one spec never
  repaints its neighbours — asserted.
- **Ticking a parent clears any part-selection under it**, and unticking one child of a whole group rewrites
  the selection as "every item except this one" (drop the group, add the siblings). Those two rules are what
  keep the parent checkbox honest: checked when the group is whole, **indeterminate** when only some items are,
  unchecked otherwise.
- **`ITEMS_BY_GROUP` is built in `applyCompanyScope()`**, so the tree follows the company, and its items are
  sorted by description. That sort calls `itemName`, which is why `applyCompanyScope()` is invoked *after*
  `itemName` is declared rather than before it — a `const` is in its temporal dead zone until then, and the
  earlier placement would throw on load.
- **`productTotals()` exists because `optionTotals` cannot serve a tree**: it keys both levels at once, and
  keys items by group *and* code so an item appearing under two groups stays two leaves rather than one
  double-counted row. Like every other picker, it excludes the filter being drawn from its own totals.
- Asserted in the harness, for the margin tab against `compute()` and for all three trend tabs against the
  real `createTrend().data()`: the tree covers exactly the (group, item) pairs the data holds and invents
  none; ticking every item of a group is identical to ticking the group on all three measures; item totals add
  back to their group; the two levels OR correctly and keep the fixed group order; every grain still totals
  the same under a narrowed selection; one tab's product selection does not touch another's; and an item
  belonging only to the other company matches nothing when scoped.

`optionTotals(dim)` computes the revenue shown beside each option under **every filter except the one
being drawn** — `dim` is the row index (0 customer, 1 group, 3 salesperson). A picker included in its
own totals would show zero against every unticked option, which is the opposite of the number a person
opening that list wants. `fillOpts` mutates the Set it is handed rather than replacing it, so
**never reassign `state.picked` / `state.sp` / `state.grp`** — Select all must add in a loop, or every
checkbox listener is orphaned against a dead Set.

**Each tab explains only its own figures.** There are three `<footer>` elements: one inside each panel
carrying that tab's "how this is calculated" definitions and notes, and a third, `#notes-footer`, outside
both for the tonnage-conversion flag — that one is a caveat about MT itself, so it belongs to both tabs.
It starts `hidden` and `renderMtNotes` un-hides it along with `#mt-notes`; un-hide only the inner div and
an empty card is drawn under every tab. **A measure added to one tab must be described in that tab's
footer and no other** — the single shared footer used to tell trend-tab readers about sorting columns and
two bar charts that are not on their screen.

**The trend tabs are one implementation, instantiated per measure.** `createTrend(cfg)` builds a tab
from a config naming its id prefix (`cfg.p`), which column of a row it reads (`cfg.value`) and how a
figure is written (`cfg.full`, `cfg.tick`, `cfg.axis`, `cfg.noun`, `cfg.totalCol`). `TRENDS` holds the
instances — `mt` reads `r[4] / 1000`, `rev` reads `r[5]`. Everything else is shared: the grain
machinery, the plot, the crosshair, the legend, the table twin, the slicers, the grain-comparison
footer.

Each instance carries date range, grain, the product tree (`groups` + `item` + `gpOpen`) **and customers** in its own `st`. The customer
picker is the searchable panel, not chips — 98 customers is far past what a chip row can hold — and it
registers itself into the one `PANELS` registry via the `panel` descriptor the factory returns, so a
click outside any dropdown on any tab behaves identically. Its option list shows each customer's figure
under the tab's *other* filters but not its own, for the same reason the margin tab's pickers do.

**A third measure is a `TRENDS` entry plus a markup panel — never a copy of the block.** The panels are
duplicated in the template because their ids must differ, but they are generated from one string in the
build script for the same reason. Each instance owns its own `st` (date range, grain, groups), so the
tabs do not disturb one another; that independence is asserted.

**Shortcut Dimension 3 is shown as "Sector" and is EMPTY in BC.** Not the field name, not the query —
the dimension itself is unset on every value entry: `Dimension_Set_ID` is `0` there, and Global
Dimension 1 and 2 and Shortcut Dimensions 3–8 all come back `''`. Probed directly against the endpoint.
The plumbing is in place through the grain and the payload, and the Revenue tab's Sector dropdown hides
itself below two options, so it will appear on its own the day the dimension is populated. **Do not
"fix" it page-side.** If it must work sooner, the fix is in Business Central.

**Extra per-measure dimensions are declared, not hand-built.** `cfg.dims` takes
`{key, idx, label, icon, all, options, name}` and the factory gives each one a Set on `st`, a dropdown,
a registry entry, a pill and a line in reset. Revenue declares salesperson (`idx: 3`) and sector
(`idx: 4`); the other tabs declare none. A dimension never filters its own option list.

`cfg.value` is the only place a measure's column appears. Row shape is
`[customer, group, date, salesperson, sector, item, company, kg, revenue, cost]`, tonnage in **kilograms**,
revenue already display-positive. Gross profit is **derived, not stored** — `r[8] - r[9]` — and reconciles to
revenue minus cost of sales, which is asserted.

**All three trend panels are generated from one string** in the build script. They were diverging by
copy-paste before the third arrived. A change to the slicer band must land on every tab, so edit the
template, not a panel.

**Coarser grain does not steady every measure.** It does for tonnage and revenue, which is why month is
the default. Gross profit nets gains against losses inside a bucket, so monthly currently reads spikier
than weekly. The claim that survives all three, and the one the default rests on, is that **daily is the
spikiest** — that is what the harness asserts; the order-of-magnitude claim is asserted only where it
holds.

**Both measures go negative.** A credit memo subtracts, so tonnage and revenue each dip below zero —
tonnage on a return day, revenue where PROJECT posted about −S$26k in one month. The y scale opens
downwards for both; do not clamp either.

**The filter band is one 12-column grid.** Every field spans a whole number of columns and the two
rows each total exactly twelve — `date 3 + quick 4 + grain 3 + view 2`, then
`customer 3 + groups 7 + reset 2`. **Keep them summing to 12**, or the band goes ragged. Labels sit on
one line and controls on the line below, which is what makes it read as aligned; every `.ctl` carries
`min-height: 34px` so the rows stay level whatever they hold.

Chip rows are grids of their own: `.presets.even` gives equal-width columns (quick range, grain, view)
and `.presets.fill` an `auto-fit` track (product groups), so a chip row **reaches the edge of its cell**
instead of trailing off. That trailing edge was what made an earlier version look unaligned. An attempt
at three bordered `.sgroup` sections was worse — blocks of differing height with labels floating at
whatever height their control happened to be — and was removed.

**Icons come from one `<svg class="sprite">` of `<symbol>`s at the top of the wrap**, referenced by
`<use href="#ic-…">` in markup and by `icon12()` from script. Build them through `createElementNS`, not
`innerHTML`: an HTML-parsed `<use>` is an inert element that renders nothing. Marks take colour from
CSS via `currentColor` — the same rule that keeps `var()` out of `fill`/`stroke`.

**Colour on this band means state, never decoration.** An `.active` pill lights up only when its
dimension is *narrowing* the view, and Reset gains `.armed` only when there is something to reset —
grain excluded, since a grain is a way of looking rather than a filter. Whole-range, all-groups and
no-customer are defaults and stay unlit, so anything highlighted is a deliberate restriction. `sync()`
redraws the strip; add a filter and it needs a pill, or the strip starts lying.

**The seven series hues are deliberately not used here.** Colour follows the product group everywhere
on this page; borrowing those hues for chrome would break that reading. Chrome uses accent, ink and the
warning tone only.

**The trend tabs.** A line chart over time, one line per product group, with its own date range, grain
and group selection in `st` — deliberately independent of the margin tab's filters, since they answer
"what did we ship or bill, when", not "what did that customer pay". Notes that are load-bearing:

- **Grain is the difference between a trend and a heart monitor, and `month` is the default for that
  reason.** Shipments arrive in lumps, so per posting date the busiest period runs well over a hundred
  times the median and the line is a row of spikes against a flat floor. Weekly is still around ten
  times — the bulk cargoes themselves land about monthly — and monthly is close to even. `GRAINS` maps a
  date to a bucket key and a key back to the span it covers. Nothing is smoothed: every grain totals to
  identical tonnage, which is asserted. **Do not change the default to `day` without re-reading this**;
  the first cut shipped daily and the chart was unreadable.
- **`renderGrainStats` computes that comparison live**, into the footer table, from the current
  selection — the standing no-frozen-values rule applies to prose in the page as much as to
  `CONTROL_TOTALS`. The figures above drifted within a day of being written down, which is why the page
  computes its own. It swaps `tstate.grain` to sample each grain and **must restore it**; the harness
  asserts that, and that its row for the selected grain agrees with the plot.
- **The tab explains itself in two parts**, and they must not blur: the first footer describes the
  chart, the second describes the bucketing. A note about the table view or the grains does not belong
  in the first. That second footer is written for a **business reader, not a maintainer** — no buckets,
  keys, ISO weeks or ratios in the prose. Keep it that way; the terms of art belong here.
- **`partial` only detects a trailing period the DATA has not filled** (`G.end(last) > DATA.maxDate`).
  It does **not** detect a period cut short by `tstate.from`/`tstate.to`. With a custom range the first
  and last points can each hold part of a period and are drawn as ordinary points: from 2026-07-01 the
  first week is keyed 2026-06-29 but holds only 1–5 July, and 30 June carries a ~19,800 MT cargo, so the
  point moves by an order of magnitude if the range starts two days earlier. Documented in the tab's
  footer as a caveat for now; the fix is a per-point clipped test against both the filter and the data
  bounds, drawn hollow like the trailing case.
- **The footer's worked example is a fixed illustration, by request.** It is written as a hypothetical
  — "you set the range to 1–31 July" — rather than as a statement about the data, and it names no year
  and asserts no weekday, so it does not go stale. It was briefly generated from the live selection
  instead; that was reverted. If it is ever reinstated, remember that a weekday in prose is a frozen
  value like any other: 29 June is a Monday in 2026 and a Tuesday in 2027, so any example that carries
  a real date has to be derived rather than typed.
- **A trailing bucket the data has not filled is flagged, not hidden.** `partial` is set when the last
  period's `end` runs past `DATA.maxDate`; that point is drawn hollow and labelled in the hint and the
  table. Without it, three days of September plot as a collapse after a full August.

- **The y scale must open downwards.** Daily tonnage goes negative when a credit memo lands; HCL posts
  −54.92 MT on 2026-07-31. Anchoring the scale at zero put that point below the plot box, where
  `overflow: visible` drew it across the date labels. `yMin` is `-niceMax(-min)` when any point is
  negative, and the baseline is drawn at `y(0)`, not at the bottom edge.
- **The scale follows the selected groups**, which is the whole point of the slicer: NAOH is three
  quarters of all tonnage, so with it shown the other six are flat lines. Deselecting it rescales them.
- A day a group did not ship is a real **0**, not a gap, so two groups can be read against each other
  on the same day.
- Colour comes from the same `classOf` map as the bars. A group is one colour on both tabs, and
  deselecting one never repaints the others.
- **Only the margin tab's filter band is sticky.** `.filters` carries `position: sticky; top: 0; z-index: 40`;
  the trend tabs' `.slicers` deliberately does not. Making it sticky was tried and reverted by request. If it
  is ever revisited: sticky is bounded by its containing block, so a band inside its chart tile holds only
  while that tile is on screen, and it is broken outright by an `overflow`, `transform`, `filter` or `contain`
  anywhere up the ancestor chain — nothing on `.wrap`, `.card` or the tab panel has one today.

- **The slicer lives inside the tile.** The dataviz skill calls per-chart filters an anti-pattern, its
  rule being one filter row above everything it scopes. That tab holds exactly one chart plus its table
  twin, so the band at the top of the tile *is* that row. Do not add a second chart to that tab without
  moving the slicer out.
- **The table view is not optional.** Three of the seven hues fall under 3:1 against the light card, and
  the palette validator's contrast WARN obligates visible labels or a table view. It is also the
  accessibility pass's table twin. Removing it breaks both.
- `renderTrend` clears the SVG but **keeps `<title>`/`<desc>`** — `aria-labelledby` points at them, the
  same trap the bars hit.

**A customer row opens into its items.** The customer name is a `button.disc`, and clicking it draws one line
per item beneath, across the same months and the same six measures. The lines are built in `compute()` from
exactly the rows that made the customer's own total — same filters, same accumulation one level down — so they
reconcile by construction rather than by a second query; the harness asserts it per month and per total. They
are shaped like customer rows (`name`, `no`, `byMonth`, the six measures) so `cmp` and `cell` take either
without a branch, which is what makes the breakdown follow whichever column the grid is sorted by. Open rows
live in `state.open` keyed by customer no, **not in the DOM**, so a filter or a re-sort leaves them open.
Unlike a customer, an item line with no tonnage is **not** dropped: an item that only ever carried a credit is
part of how that customer's total came about.

**A customer is dropped from the grid only when they moved NOTHING** — no tonnage, no revenue, no cost.
Tonnage alone used to be the test, on the reasoning that a customer with no MT is not a sale. That holds for a
chemical shipment and fails for a service: CIL bills `MAINTENANCE` and `MATERIAL` that carry revenue and no
weight, and dropping those rows hid real revenue from the grid while the KPI tile above it still counted it,
so the two disagreed by a few hundred dollars. The grid must sum to the tiles; the harness asserts it, and it
is what caught this.

**The monthly grid.** `SUBS` defines the six measure columns repeated under each month band. Adding a
seventh is a `SUBS` entry plus a key on `measures()`; the header, footer, colspans and sort keys all
follow from it. The one place that does **not** follow is the grand-total object in `renderTable`, which
is built by hand — a derived measure added to `SUBS` and forgotten there renders `undefined` in the
bottom-right corner only.

**Two of the six are rates, not sums: `gpm` and `ppmt`.** Both are recomputed from the revenue and
tonnage of the cell they sit in, at every level — cell, row total, month footer, grand total. Summing
them is always wrong and rarely looks wrong: the per-customer price-per-MT column currently adds to
about 61,600 against a true blended 271.52. Both guard their divisor, because a month can carry revenue
with no tonnage and must read 0, not `Infinity`. Sort keys
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
it. It still renders from disk. **Do not add one**, but do remember that everything else in that wrapper
is absent from disk too: that is how the `[hidden]` bug above survived, and it is why "works in the
artifact" is not evidence that the file works.

## The company selector

**One dropdown above the tabs re-scopes the entire page** — KPI tiles, both product-mix charts, the monthly
grid and all three trend tabs. Nothing reloads: the payload carries every company, so a switch is a re-filter
and a re-render. It is deliberately *not* one of the filters; it decides which ledger is being read, which is
why it sits outside the tabs rather than in the margin tab's filter band.

**`ROWS` is the only thing downstream may read. A loop that reads `DATA.rows` ignores the selector.**
`applyCompanyScope()` materialises `ROWS` once per switch rather than testing the company inside every loop —
six separate passes read it and the payload runs to 40,000 rows — and rebuilds `CO_CUSTOMERS`, `CO_GROUPS`,
`SP_CODES` and `SECTORS` from it. Those four were payload-wide constants before and are now company-scoped
`let`s: with CIM selected, offering CIL's 112 other customers at zero is the opposite of useful. `cfg.dims`
reads `SP_CODES`/`SECTORS` through closures, so reassigning them is what makes the trend dropdowns follow.

**Switching clears selections but keeps the date range.** A customer or salesperson picked in one company
usually does not exist in the other, and carrying one over silently shows an empty chart with a lit pill and
no explanation. A date range means the same thing in either ledger, so it survives. Each trend tab does the
same through the `recompany()` its factory returns; the group chips are rebuilt there, which is why
`buildGroupChips()` is a function rather than a loop inside `build()`.

**Group is a PLAIN SUM, by explicit decision — do not quietly net it off.** The two companies trade with each
other: CIM sells to customer `C0002` (which *is* CIL) for about S$7.9M, 26% of CIM's revenue, and CIL sells to
`CI07` (which is CIM) for about S$11.3M, 5% of CIL's. Group therefore counts roughly S$19M twice and overstates
external revenue by about 8%. That is intended, and `#group-note` in the notes footer says so in the reader's
words. If the decision is ever reversed, the elimination and that note move together.

**The page opens on `defaultFrom`, not `minDate`.** CIL has three years CIM does not exist for, and a combined
view starting there reads as CIM collapsing rather than as CIM being absent. Earlier dates stay reachable —
"All time" and the date inputs still go back to `minDate` — and return CIL only. Reset returns to `defaultFrom`,
and the trend tabs' "whole range" pill compares against it, not against `minDate`.

**The notes footer has two independent children** — `#group-note` and `#mt-notes` — so `syncNotesFooter()`
un-hides the card when *either* has something to say. Un-hiding it from one renderer draws an empty panel under
every tab, which is the same trap `#mt-notes` hit on its own.

## Known data issues, not bugs

The two largest accounts run negative gross margin. Chemical Industries (Far East) Ltd sits near −1%,
apparently intercompany transfer at or below cost. **Sumitomo Seika deteriorated through FY27 — roughly
+12% in April to −23% in July, with no August postings at all** — and since May its COGS exceeds revenue
outright while tonnage held steady, so it is a price or unit-cost problem rather than a volume one. The
expected/actual netting was verified at row level against a sample document. Do not "fix" the formulas
to make these positive.

CIM spans 2026-04-01 onward; CIL spans 2023-04-01 onward, so the April 2023 floor now binds on CIL.

**CIL sells services as well as chemicals.** `MAINTENANCE`, `MATERIAL` and similar groups post revenue with no
tonnage at all. Their price-per-MT is 0 by design (the divisor guard), not a missing figure.

## Repository layout

This folder is its own git repo whose `main` branch holds these files at the root. They are pushed to
`github.com/movefoomy/Business-Central-AI-Agent`, branch `Power-BI-CIM`, under a **`power-bi-cim/`**
subdirectory alongside the existing `bc_odata_mcp/`. The two histories are unrelated, so a push grafts a
new commit onto the remote tip using a temporary index — never `--force`, and never a checkout, which
would dump the whole monorepo into this folder. The remote also carries a dangling
`value-entries-dashboard` submodule gitlink with no `.gitmodules`; pre-existing, left alone.
