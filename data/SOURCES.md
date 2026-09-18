# Sources

Every number the pipeline uses comes from one of these. Tier 1 is a primary statistical
agency or exchange; Tier 2 is a major agency forecast; Tier 3 is wire reporting used only
for event dates. Nothing below Tier 3 is used.

| tier | source | what | cadence | fetched by | url |
| --- | --- | --- | --- | --- | --- |
| 1 | EIA Weekly Petroleum Status Report | crude and distillate stocks, production, imports, exports, refinery inputs, product supplied, Cushing, SPR | weekly, week ending Friday, released Wednesday 10:30 ET | scripts/fetch_eia.py (API v2) | https://www.eia.gov/petroleum/supply/weekly/ |
| 1 | CFTC Commitments of Traders, disaggregated futures-only | managed money and producer/merchant positions, NYMEX WTI and NY Harbor ULSD | weekly, Tuesday positions, released Friday 15:30 ET | scripts/fetch_cftc.py (Public Reporting Environment, dataset 72hh-3qpy) | https://publicreporting.cftc.gov/resource/72hh-3qpy.json |
| 1 | EIA spot prices | WTI Cushing, Brent, NY Harbor ULSD, Gulf Coast ULSD and conventional gasoline, daily | daily | scripts/fetch_eia.py (series in config) | https://www.eia.gov/dnav/pet/pet_pri_spt_s1_d.htm |
| 1 | EIA monthly average spot prices via FRED (MCOILBRENTEU, MDFUELUSGULF, MGASUSGULF) | Brent, Gulf Coast ULSD, Gulf Coast conventional gasoline | monthly | data/eia_spot_monthly.csv, committed | https://fred.stlouisfed.org/data/MDFUELUSGULF |
| 1 | Valero Energy earnings releases (Form 8-K exhibit 99.01), 10-Q and 10-K | reported refining margin per barrel of throughput, refining margin in USD mm, throughput | quarterly, about four weeks after quarter end | data/refiner_margins.csv, hand entered with source url, release date and status per row | https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=1035002&type=8-K |
| 2 | EIA Short-Term Energy Outlook | monthly global balance, Brent forecast, US distillate stock forecast | monthly | data/global_balance_monthly.csv, hand entered with release date | https://www.eia.gov/outlooks/steo/ |
| 2 | IEA Oil Market Report (public summary) | world supply, demand, Gulf export flows, inventory draws | monthly | data/global_balance_monthly.csv, hand entered with release date | https://www.iea.org/reports/oil-market-report-september-2026 |
| 2 | OPEC Monthly Oil Market Report | OPEC demand forecast, OPEC+ production | monthly | data/global_balance_monthly.csv | https://www.opec.org/opec_web/en/publications/338.htm |
| 3 | Dated wire reporting (CNBC) | the 2026-09-11 East-West pipeline shutdown | as it happens | data/events.csv, each row carries its source url | |

## Known measurement issues, in the order they bit

1. **API vs EIA.** The API's Tuesday estimate and the EIA's Wednesday print can disagree
   by millions of barrels (week ending 2026-09-11: API +7.1 mb, EIA -0.6 mb). The pipeline
   uses EIA only. The API number is a consensus input at best, never a data point.
2. **EIA adjustment.** The balance identity never closes; the EIA publishes an
   "adjustment" line. `balance.adjustment` reports it every week. When it exceeds
   two standard deviations, that week is flagged in the panel.
3. **Benchmark revisions.** Weekly data are benchmarked to the Petroleum Supply Monthly
   with a lag of roughly two months (e.g. the week ending 2026-09-04 was benchmarked to
   May data). The pipeline stores the fetch date so a re-fetch can be diffed.
4. **EIA format change 2026-09-23.** The full PDF is discontinued; data files are unchanged.
   The pipeline reads the API, not the PDF, so nothing breaks.
5. **Holiday weeks.** WPSR shifts to Thursday after a Monday holiday. `align.py` takes
   the release calendar from `data/release_calendar.csv`, not from a fixed +5 days.
6. **One company's definition.** The margin is Valero's own measure: refining margin divided by throughput barrels. Other refiners define theirs differently (per barrel of crude, realized margin, with or without marketing), so the model is fitted per company and levels are never pooled.
7. **COT timing.** The report is released Friday 15:30 ET, after the 14:30 ET futures settlement. It is therefore not usable at that Friday's close; the pipeline treats it as public from the following day.
