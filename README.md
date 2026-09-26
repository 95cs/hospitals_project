# Access to Healthcare in Rural Romania

Locality-level analysis of the relationship between population ageing and access to medical
services, built to support a decision about where to open new medical centres.

Every figure below is reproducible from the raw data in this repository with three commands.

---

## The question

> **The Ministry of Health has to decide where to open 10 new medical centres. In which
> localities do a large elderly population, distance to the nearest hospital, and below-average
> medical staffing overlap most strongly?**

It has a decision-maker allocating a fixed budget, a concrete action attached (a shortlist of
localities), it needs three sources that do not line up naturally, and the answer is not
guessable in advance.

### Still open in that formulation

| Open question | Why it matters |
|---|---|
| What distance counts as "far"? | The threshold (25 km? 30?) changes the final list and has to be defended |
| How do the three criteria combine? | A filter joined by AND could return 3 localities or 400. Producing a *top 10* requires a prioritisation rule, and the weights chosen will be the first thing anyone asks about |
| Straight-line distance or road distance? | In Hunedoara, Caraș-Severin and the Apuseni mountains — exactly where the oldest under-served communes are — the difference is large |

The distance criterion is not yet implemented: it needs geographic coordinates, which the
SIRUTA code does not carry. See *Data sources*, row 4.

---

## Scope

Validation runs on **all 3,181 localities**. Only **Bucharest** is excluded from locality-level
analysis, for now.

| | Units | Population | People 65+ | 65+ share |
|---|---|---|---|---|
| Complete set (validated) | 3,181 | 21,646,220 | 4,076,589 | 18.8% |
| Bucharest (excluded) | 1 | 2,108,049 | 426,601 | 20.2% |
| **Working set** | **3,180** | **19,538,171** | **3,649,988** | **18.7%** |

**The reason for excluding Bucharest is technical, not thematic:** it arrives aggregated, a
single row of 2.1 million people with no breakdown by sector, while the rest of the country is
at territorial-unit level with a median population of 3,003. One data point representing 10% of
the country is not comparable with the other 3,180 and would dominate any locality-level chart.

Validation stays on the complete set, ahead of the exclusion — a fully validated set is a
stronger baseline and keeps the national totals available for comparison.

### Deferred: narrowing to rural localities

The question targets under-served areas, and towns and cities concentrate the hospitals. One
option is to restrict the analysis to the 2,862 communes:

| | Units | Population | People 65+ |
|---|---|---|---|
| Communes | 2,862 | 9,697,493 | 1,701,854 |
| Towns + municipalities | 319 | 11,948,727 | 2,374,735 |

That would exclude 55.2% of the country's population and bring the 65+ share down to 17.5% —
urban Romania holds more elderly people in absolute terms.

**Not applied, because the administrative filter cuts wrong in both directions.** The
commune / town / municipality classification is legal, not functional: it tracks neither size,
nor isolation, nor actual access.

- `FLORESTI` (Cluj) has 58,010 inhabitants and is a commune — it would stay in, despite being
  a suburb of Cluj-Napoca within a few kilometres of three major hospitals.
- `ORAS VASCAU` (Bihor) has 2,041 inhabitants and 27.7% aged 65+, deep in the Apuseni
  mountains — it would drop out, despite being exactly the profile being looked for.
- 120 towns and municipalities have fewer than 10,000 inhabitants; `ORAS BAILE TUSNAD` (1,550)
  is smaller than the median of the working set.

The decision waits until the health-unit source shows how access is actually distributed. A
size-based or access-based criterion may serve better than the administrative one.

---

## Data sources

| # | Source | Contents | Granularity | Status |
|---|---|---|---|---|
| 1 | INS TEMPO, matrix POP107D | Population by age group, 2026, both sexes | locality (SIRUTA code) | ✅ 42/42 files, processed and validated |
| 2 | INS TEMPO, matrix SAN101B | Health units by category and ownership, 2024 | locality (SIRUTA code) | ✅ 41/42 files downloaded |
| 3 | INS TEMPO, matrix SAN104B | Medical staff | locality | ⬜ not started |
| 4 | _(to be determined)_ | Geographic coordinates per SIRUTA code | locality | ⬜ required for the distance criterion |

**Source 1.** 42 CSV exports (41 counties plus Bucharest), downloaded manually from TEMPO.
Age groups selected: `Total`, `65-69`, `70-74`, `75-79`, `80-84`, `85+`. 19,086 raw rows →
3,181 localities after the pivot → 3,180 after excluding Bucharest.

**Source 2.** 41 CSV exports, one per county. Bucharest is missing deliberately — it is
excluded from locality-level analysis anyway.

**Source 4 was not part of the original plan.** The distance criterion in the business question
requires coordinates for both localities and hospitals, and the SIRUTA code carries none. It is
a geospatial component that materially widens the scope of the project.

---

## What the data does not say

**1. Population by registered residence, not resident population.**
The raw total is **21,646,220**, against roughly 19 million actual residents. The difference is
people whose legal residence is registered in Romania but who live abroad. The figures therefore
**overstate** population precisely in the rural communes with heavy emigration — the ones most
likely to appear in the final answer. Every per-capita indicator here has an inflated
denominator in rural areas, and the effect grows the smaller the commune. This is the single
most important limitation of the whole analysis.

**2. Locality names are not unique.**
239 names repeat across counties (`ADANCATA`, `ALBESTI`, `POPESTI`…).
**The join key is `siruta_code`, never the name.**

**3. Health units: 2025 was unpublished, and zeros are exported inconsistently.**

Source 2 uses **2024**, not 2026 like the population data — a two-year gap, accepted knowingly.
At the time of download, 2025 held only the `Spitale` category: 13 rows for the whole of Alba
county, against 274 in 2024. That was not a fact about access, it was a partial publication.

More consequential for the code: **TEMPO exports zeros inconsistently from county to county.**

| County | Rows | Of which value 0 | Actual units |
|---|---|---|---|
| Alba | 274 | 5 (2%) | 804 |
| Prahova | 903 | 444 (49%) | 2,067 |
| Bacău | 3,922 | 3,577 (91%) | 1,769 |

Bacău has four times as many rows as Prahova and fewer health units. So **a row count means
nothing.** A locality has a unit of a given category only if a row exists with a strictly
positive value; a missing row and a row holding 0 say the same thing. An indicator built by
counting rows would declare Bacău the best-served county in the country.

A further trap in the same source: if `TOTAL` is left selected under LOCALITATI in the TEMPO
interface, the export carries per-county aggregate rows alongside the per-locality ones. The
September 2026 download contained 41 such rows for Constanța, double-counting 2,694 units —
a 4.7% inflation of the national total. `src/prep_health_units.py` removes them defensively and
logs what it removed.

**4. Small localities have exact but hard-to-compare shares.**
The data is exhaustive, not a sample: `BATRANA` (Hunedoara) really does have 51 people over 65
out of 109 inhabitants, and 46.8% is the correct figure. There is no measurement error. The
problems are different ones: the indicator is **unstable over time** (five deaths move it four
points) and **hard to compare** with a locality of 20,000.

**No population threshold is applied to the dataset.** A 2,000-inhabitant threshold would drop
848 localities holding 270,201 people over 65 — precisely the population with the worst access
to medical services, which is the subject of the analysis. The comparability problem is handled
differently: by always showing the share, the absolute count and the total population together,
and by encoding locality size visually rather than hiding data. A threshold does appear in the
prioritisation rule below, where it answers a different question: not *what is true*, but *where
a new centre could realistically operate*.

---

## Results

### The two access indicators

Access is measured on two axes rather than one:

| Indicator | Definition | Localities |
|---|---|---|
| `has_family_doctor` | at least one family-medicine practice | 2,821 of 3,180 |
| `has_pharmacy` | at least one pharmacy **or** one pharmacy point | 2,553 of 3,180 |

**Why pharmacy points count.** The pharmacy point is the reduced form, permitted by law
precisely in localities too small to sustain a full pharmacy. 516 localities have one without
having a pharmacy; excluding them would declare those localities cut off from medication when
residents do have somewhere to fill a prescription. The caveat: a pharmacy point holds less
stock and keeps shorter hours, so "has access" does not mean equal access.

### The four situations

```
has_pharmacy       False  True
has_family_doctor
False                169    190
True                 458   2363
```

The first observation runs against intuition: **missing a pharmacy is almost twice as common as
missing a doctor** — 627 localities without a pharmacy against 359 without a family doctor. A
single indicator built on the family doctor alone would have missed the larger problem.

### Access falls as population ages

Average 65+ share across the four groups:

| | without pharmacy | with pharmacy |
|---|---|---|
| **without doctor** | **23.6%** | 19.3% |
| **with doctor** | 21.2% | 18.8% |

A monotone gradient: the fewer services a locality has, the older it is.

### Localities with neither

**169 localities have neither a family doctor nor a pharmacy** — 224,756 inhabitants, 47,750 of
them over 65. By county: Caraș-Severin 18, Hunedoara 16, Mehedinți 14, Vaslui 12, Buzău 11,
Cluj 11. The western mountains and Moldova — with the notable exception of Cluj, a prosperous
county holding 11 localities with no medical service at all.

### The answer: ten localities

Two rules take the 169 candidates down to 10, each chosen explicitly.

**Rule 1 — a 1,000-inhabitant threshold**, leaving 113 candidates.

The reason is not convention but the shape of the trade-off curve. Ranking by 65+ share under
different thresholds:

| Threshold | Candidates | Elderly in top 10 | Lowest share in top 10 |
|---|---|---|---|
| none | 169 | 1,936 | 36.4% |
| 500 | 156 | 3,906 | 32.7% |
| **1,000** | **113** | **4,762** | **29.5%** |
| 1,500 | 55 | 5,213 | 23.1% |
| 2,000 | 15 | 5,396 | 16.9% |

With no threshold the ten centres would serve 1,936 elderly people, about 190 each. A practice
cannot sustain itself on that — which is exactly why the doctor left already. At the other end,
a 2,000 threshold pushes the entry bar below the national average of 18.7%: the list starts
selecting large communes that happen to lack services rather than ageing ones.

The knee of the curve sits between 500 and 1,000 — the point past which every additional
elderly person served costs increasingly more in the acuteness of the need being addressed.

**Rule 2 — at most 2 localities per county.** Without it, Teleorman takes 5 of the 10 places.
That is mathematically correct, but a national allocation placing half the investment in a
single county needs a justification the data cannot supply.

The constraint is nearly free:

| | unconstrained | max 2 per county |
|---|---|---|
| Elderly people served | 4,762 | **4,798** |
| Lowest 65+ share | 29.5% | 28.7% |
| Counties covered | 5 | **7** |

The number of elderly people served actually rises slightly, geographic coverage widens from 5
counties to 7, and the entry bar costs 0.8 percentage points.

**Result:**

| # | Locality | County | Population | 65+ | Share |
|---|---|---|---|---|---|
| 1 | TOMESTI | Hunedoara | 1,001 | 394 | 39.4% |
| 2 | UDA-CLOCOCIOV | Teleorman | 1,149 | 441 | 38.4% |
| 3 | FANTANELE | Teleorman | 1,248 | 426 | 34.1% |
| 4 | PIETRARI | Vâlcea | 2,891 | 971 | 33.6% |
| 5 | OBARSIA DE CAMP | Mehedinți | 1,502 | 458 | 30.5% |
| 6 | NAIDAS | Caraș-Severin | 1,077 | 322 | 29.9% |
| 7 | MARTINESTI | Hunedoara | 1,008 | 297 | 29.5% |
| 8 | STROESTI | Vâlcea | 2,532 | 743 | 29.3% |
| 9 | ISVOARELE | Giurgiu | 1,334 | 384 | 28.8% |
| 10 | MANASTIRENI | Cluj | 1,263 | 362 | 28.7% |

4,798 people over 65, across 7 counties, none below a 28.7% elderly share.

**Why not a simple ranking.** Ordering by the absolute number of elderly people produces a
completely different list — zero overlap with the one above — serving 5,974 people, 25% more.
But it includes communes such as VLASINESTI (11.5% elderly) and GROSI (13.9%), both below the
national average: large localities without services rather than ageing ones. That ranking
answers a different question from the one asked.

### What these figures do not prove

**Correlation, not causation.** The link between ageing and missing services is clear, but the
direction cannot be established from this data. Does a commune age until the practice closes
for lack of patients, or do the services disappear and young families leave? Almost certainly
both, reinforcing each other. The analysis cannot separate them.

The practical consequence for the recommendation: a commune that lost its doctor because it has
109 inhabitants will present a new centre with the same problem. *Where the need is greatest*
and *where building makes sense* produce different lists. The 1,000-inhabitant threshold reduces
that risk without eliminating it; assessing the viability of each site is beyond what this data
can say.

**"No practice registered in the locality" does not mean no care at all.** A doctor from a
neighbouring commune may hold hours there. TEMPO cannot say. It is the best available signal,
not a certainty.

### One more thing worth stating: the mean of ratios is not the ratio of sums

| Figure | Value | Meaning |
|---|---|---|
| Mean of the `share_65plus` column | **19.4%** | the arithmetic mean of 3,180 percentages — `BATRANA` (109 people) weighs as much as `MUNICIPIUL IASI` (370,437) |
| Total 65+ ÷ total population | **18.7%** | every person weighs the same |

Both are correct and answer different questions: *what share of people are over 65?* → 18.7%;
*how aged is a typical locality?* → 19.4%. The difference is not noise, it is the finding
itself: Romania has many small, ageing communes, and they pull the unweighted mean up. In a
dashboard, each indicator has to be labelled so it is clear which of the two it is.

---

## Cleaning decisions

| # | Decision | Choice | Rationale |
|---|---|---|---|
| 1 | Source column names | `.str.strip()`, INS labels kept as they are | traceability — anyone comparing against the TEMPO export finds the same labels, with no mental translation |
| 2 | Type of `siruta_code` | text (`str`) | it is an **identifier**, not a quantity: no arithmetic is performed on it, keeping it as text removes any risk of losing leading zeros, and it forces types to be matched explicitly at join time. **Note for consumers:** CSV does not preserve dtypes — any re-read must force `dtype={"siruta_code": "str"}`, or it becomes `int64` and the join with the health-unit source matches nothing without raising |
| 3 | Column names for derived fields | English identifiers (`population_65plus`, `share_65plus`, `has_pharmacy`) | the pipeline owns these columns; the 33 health-unit **category** names stay verbatim from INS, because those remain columns of the source itself and are how any figure is traced back |
| 4 | Splitting code from name | `str.split(" ", n=1)` | a single cut at the first space keeps compound names intact (`MUNICIPIUL ALBA IULIA`, `VIZANTEA-LIVEZI`). Verified: all 19,086 rows follow the `<code> <name>` pattern |
| 5 | `pivot` vs `pivot_table` for population | `pivot` | `pivot_table` silently aggregates duplicates (mean by default). `pivot` raises — validating for free that each locality has exactly 6 age groups |
| 6 | `pivot` vs `pivot_table` for health units | `pivot_table(aggfunc="sum")` | the mirror case: each locality has up to three rows per category (public, mixed, private) and they are meant to be added. The aggregation is intentional, and a total-preserved check guards it |
| 7 | Scale of `share_65plus` | ratio, 0–1 | percent formatting belongs to the presentation layer; Power BI multiplies by 100 on display, so storing a 0–100 scale yields `1880%` |
| 8 | Zero-valued health-unit rows | dropped before the pivot | TEMPO exports zeros inconsistently by county; only a strictly positive value means the unit exists |
| 9 | Scope | validate on 3,181; exclude Bucharest from locality-level analysis | technical: it arrives aggregated, 2.1M in one row, no sectors. Narrowing to rural localities remains deferred |

---

## Validation

Reference figures were computed **independently**, with `awk` straight from the raw CSVs,
without pandas. The pipeline reproduces the same values — a cross-check across two
implementations sharing no code.

Validation runs on the complete set of 3,181 localities, before any exclusion.

| Check | Expected |
|---|---|
| Localities | 3,181 (= 2,862 communes + 216 towns + 103 municipalities, the official count of territorial units) |
| `siruta_code` unique | 0 duplicates |
| Missing values | 0 |
| `population_65plus ≤ population_total` | on every row |
| `share_65plus ∈ [0, 1]` | on every row |
| Total population 65+ | 4,076,589 |
| Total population | 21,646,220 |
| National 65+ share | 18.8% |
| Extremes | max 46.8% `BATRANA` (HD) · min 2.8% `BARBULESTI` (IL) |
| Health units, after dropping aggregates and zeros | 57,027 units across 3,040 localities |
| Localities with no unit at all | 140 |

After excluding Bucharest: 3,180 localities, between 109 and 370,437 inhabitants, median 3,003.

---

## Project layout

```
data/raw/         raw exports, never edited by hand
data/processed/   cleaning output (git-ignored)
notebooks/        interactive exploration
src/              code that runs repeatedly
```

| File | Role |
|---|---|
| `src/prep_population.py` | 42 CSVs → `population_by_locality.csv` (3,180 rows) |
| `src/prep_health_units.py` | 41 CSVs → `health_units_by_locality.csv` (3,040 rows) |
| `src/build_dataset.py` | joins both → `analysis_dataset.csv` (3,180 rows, 47 columns) |
| `src/build_dashboard_dataset.py` | serving layer for the report → `dashboard_dataset.csv` (3,180 rows, 23 columns) |
| `notebooks/01_exploration.ipynb` | how the population cleaning was worked out |
| `notebooks/02_indicators.ipynb` | how the indicators and the shortlist were designed |

## Setup

```bash
python3 -m venv venv && source venv/bin/activate && pip install pandas jupyter
```

## Running

Rebuilds the whole chain, from the raw CSVs to the analysis dataset:

```bash
python src/prep_population.py      # 42 CSVs  -> population_by_locality.csv    (3,180)
python src/prep_health_units.py    # 41 CSVs  -> health_units_by_locality.csv  (3,040)
python src/build_dataset.py        # joins    -> analysis_dataset.csv          (3,180)
python src/build_dashboard_dataset.py  #       -> dashboard_dataset.csv         (3,180)
```

Each script stops with `DataError` and exit code 1 if any assumption about the data fails to
hold. The notebooks remain as the record of how the logic was worked out.

---

## Status

**Source 1 — population**
- [x] Ingest 42 CSVs, clean, split SIRUTA, pivot
- [x] 8 automated checks on the complete set of 3,181 localities
- [x] Exclude Bucharest after validation → 3,180 localities
- [x] `src/prep_population.py`

**Source 2 — health units**
- [x] 41 CSVs, SAN101B, 2024
- [x] `src/prep_health_units.py` — 3,040 localities with at least one unit
- [x] Join on `siruta_code` → `src/build_dataset.py`
- [x] Access indicators, on two axes
- [x] Prioritisation rule — 1,000-inhabitant threshold, at most 2 per county

**Scope decisions still open**
- [ ] Narrow the analysis to rural localities? (see *Scope*)
- [ ] Keep the distance criterion? It requires source 4 and geocoding
- [ ] What distance threshold counts as poor access?

**Next**
- [ ] Source 3 — medical staff (SAN104B)
- [ ] Power BI dashboard — serving dataset ready, report in progress
