# Composite sovereign-stress index — methodology

> Version 1.0 (SPEC stage B2). This page is the contract: anyone can recompute any
> published score by hand from free public data using only what is written here.
> The code that implements it is `src/sovereign_monitor/index/`, and a unit test
> (`tests/test_index.py::test_hand_recomputed_composite_matches_exactly`) holds
> the arithmetic to this document.

## What the index is

A transparent, descriptive measure of sovereign financial stress for twelve
countries — Pakistan, Sri Lanka, Bangladesh, Nepal, Maldives, India, Kazakhstan,
Uzbekistan, Kyrgyz Republic, Tajikistan, Mongolia, Laos — scored 0 (calmest
observed) to 100 (most stressed observed) monthly, from 2000 where data exists.
It is built **only** from free, public sources and uses no proprietary
methodology. It is a monitoring lens, **not** a default-probability model (that
is the companion `sovereign-pd` project) and not investment advice.

## Indicators

Twelve indicators in four equal-weighted pillars. *Direction* says which way
means stress; protective indicators are inverted during scoring.

| Indicator | Pillar | Source series | Direction |
|---|---|---|---|
| `em_oas_level` — EM credit spread, % | market | FRED `BAMLEMCBPIOAS` (global, broadcast to every country) | higher = stress |
| `em_oas_change_3m` — 3-month change, pp | market | derived from the above | higher = stress |
| `fx_depreciation_12m` — USD/local, 12-month % change | market | Yahoo Finance per-country pair | higher = stress |
| `fx_volatility_3m` — annualized σ of daily FX returns, % | market | derived from the above | higher = stress |
| `external_debt_gni` — external debt stock, % of GNI | external_debt | WDI `DT.DOD.DECT.GN.ZS` | higher = stress |
| `debt_service_exports` — PPG debt service, % of exports | external_debt | WDI `DT.TDS.DPPG.XP.ZS` | higher = stress |
| `china_debt_share` — bilateral debt to China / total external debt, % | external_debt | IDS `DT.DOD.BLAT.CD` (counterpart 730) ÷ WDI `DT.DOD.DECT.CD` | higher = stress |
| `real_gdp_growth` — % | macro | WDI `NY.GDP.MKTP.KD.ZG` | **lower** = stress |
| `cpi_inflation` — % | macro | WDI `FP.CPI.TOTL.ZG` | higher = stress |
| `current_account_gdp` — % of GDP | macro | WDI `BN.CAB.XOKA.GD.ZS` | **lower** = stress |
| `reserves_import_months` — months of import cover | macro | WDI `FI.RES.TOTL.MO` | **lower** = stress |
| `climate_vulnerability` — ND-GAIN vulnerability score | climate | ND-GAIN country index | higher = stress |

## Point-in-time discipline (no look-ahead)

Every observation carries an `available_at` date — when the value became
publicly knowable — distinct from its reference date. All index inputs are
as-of joins on `available_at`:

- Daily market series: available the next calendar day.
- Annual World Bank data for year Y: available 1 July of Y+1.
- ND-GAIN scores for year Y: available 1 January of Y+2 (≈18-month release lag).
- Monthly evaluation happens at month-ends; all windows are trailing, never centered.

A CI mutation test alters strictly-future observations and fails if any earlier
feature value moves.

## Scoring arithmetic

For each indicator, pooled across **all** countries and months:

1. **Winsorize** at the 1st and 99th percentile of observed values.
2. **Min-max scale** to [0, 100]: `score = (clipped − p01) / (p99 − p01) × 100`.
   A constant column maps to 50 (neutral).
3. **Invert protective indicators**: `score = 100 − scaled` for real GDP growth,
   current account, and reserves cover.

Then:

- **Pillar score** = arithmetic mean of that pillar's *available* indicator scores.
- **Composite** = arithmetic mean of available pillar scores, **only if at least
  two pillars are present**; otherwise no composite is published for that
  country-month.

Because scaling is pooled over the full history, adding new months can slightly
re-scale past scores (the bounds move). Published scores are therefore versioned
by run date; the forecasting layer (stage B3) uses expanding-window
normalization instead and never sees future scaling bounds.

## Daily market overlay

The market pillar alone is recomputed on business days (3-month ≈ 63 trading
days, 12-month ≈ 252), normalized over its own pooled daily history, and
published as `market_daily.csv` for "what moved this week" reads between monthly
index points.

## Known limitations (stated, not hidden)

- **Spread history**: FRED serves only the trailing ~3 years of the ICE BofA EM
  OAS series via its API, and no free country-level EM sovereign spread exists;
  the OAS terms are a global proxy shared by all twelve countries.
- **FX coverage**: Yahoo's Kyrgyz som feed has been stale since 2025-09 and
  Tajikistan/Mongolia quotes are sparse; affected FX indicators are simply
  absent (the pillar averages what exists) rather than imputed.
- **Annual cadence**: debt, macro, and climate pillars move once a year by
  construction; intra-year movement comes from the market pillar.
- **China share definition**: bilateral official debt to China over total
  external debt understates exposure routed through commercial or
  special-purpose lenders (see AidData's GCDF for the broader lens).

## Sources & attribution

FRED®, Federal Reserve Bank of St. Louis — ICE BofA index data © ICE Data
Indices, LLC (used derived, never redistributed). Yahoo Finance via yfinance
(unofficial; derived values only). World Bank World Development Indicators and
International Debt Statistics (CC BY-4.0). University of Notre Dame Global
Adaptation Initiative (ND-GAIN). Full licensing register:
[`data_sources.yaml`](../data_sources.yaml).

---

*This is a research and educational project. Nothing here is investment advice.*
