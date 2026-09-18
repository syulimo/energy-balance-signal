# Data

Fetched files are not committed (`.gitignore`). Hand-entered files are committed, and every row carries its source.

## Fetched

| file | script | source | notes |
| --- | --- | --- | --- |
| `eia_weekly.csv` | `scripts/fetch_eia.py` | EIA API v2, 13 weekly series listed in `configs/default.yaml` | free key in `EIA_API_KEY`; the script sends the APIv1 style id (`PET.WCESTUS1.W`) to the `/v2/seriesid/` route and pages past the 5,000 row cap |
| `prices_daily.csv` | `scripts/fetch_eia.py` | EIA daily spot: WTI Cushing, Brent, NY Harbor ULSD, Gulf Coast ULSD, Gulf Coast conventional gasoline | the last two feed the Gulf Coast 3-2-1 crack |
| `cot_wti.csv`, `cot_ulsd.csv` | `scripts/fetch_cftc.py` | CFTC Public Reporting Environment, disaggregated futures only (dataset 72hh-3qpy), no key | matched on contract codes 067651 (WTI) and 022651 (NY Harbor ULSD); index is the Friday before the Tuesday position date |

## Hand entered, committed

| file | what | rule |
| --- | --- | --- |
| `events.csv` | dated events that set the regime label | one source url per row: IEA, EIA or dated wire reporting |
| `global_balance_monthly.csv` | IEA, EIA STEO and OPEC figures used by the scenario tool | release date on every row |
| `release_calendar.csv` | EIA release dates that differ from week ending plus five days | only exceptions need a row |
| `eia_spot_monthly.csv` | EIA monthly average spot prices: Brent, Gulf Coast ULSD, Gulf Coast conventional gasoline, 2022-01 to 2026-08 | retrieved from FRED on 2026-09-18, series urls in the file header; lets `run_refiners.py --prices monthly` run with no key |
| `refiner_margins.csv` | Valero's reported refining margin per barrel of throughput, one row per calendar quarter | `release_date` is the day the quarter was first published; `value_status` says whether the figure was read directly (primary) or derived, with the arithmetic in `note` |

### How `refiner_margins.csv` was built

Sixteen Valero quarters, 2022Q3 to 2026Q2. Each quarterly release prints the quarter and the same quarter a year earlier in the table "Refining Segment Operating Highlights", row "Refining margin per barrel of throughput". Where the printed figure was not read directly, it is derived from refining margin (USD mm) and throughput in the release, the 10-Q or the 10-K, with the arithmetic in the row; every derived figure that also has a published value reproduces it exactly. Release dates come from the filing text or from earnings calendars. The loader rejects a release date on or before the period end, duplicate rows, and a test rejects a gap between quarters.

To add a company, add its rows with the same columns and list its ticker under `refiners.companies` in the config. It gets its own model.

## Alignment

EIA data for the week ending Friday t are released Wednesday t+5 (Thursday after a Monday holiday; `release_calendar.csv` overrides). COT positions as of Tuesday t+4 are released Friday t+7 at 15:30 ET, after the futures settlement, so they are treated as usable from t+8. `align.py` merges backward only, and a test asserts it.
