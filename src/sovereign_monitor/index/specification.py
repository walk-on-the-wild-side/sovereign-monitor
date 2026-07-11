"""The locked index recipe (SPEC stage B2): four equal-weighted pillars.

Every indicator is documented in docs/methodology.md with the same names used
here — the methodology page and this file must never drift apart, because the
published promise is that a reader can recompute any score by hand.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class IndicatorSpecification:
    """One index input: its name, its pillar, and which direction means stress."""

    name: str
    pillar: str
    higher_is_stress: bool


PILLARS = ("market", "external_debt", "macro", "climate")

INDICATORS = (
    # Market — the EM OAS proxy is a global series broadcast to every country
    # (no free country-level spread exists); FX terms differentiate countries.
    IndicatorSpecification("em_oas_level", "market", higher_is_stress=True),
    IndicatorSpecification("em_oas_change_3m", "market", higher_is_stress=True),
    IndicatorSpecification("fx_depreciation_12m", "market", higher_is_stress=True),
    IndicatorSpecification("fx_volatility_3m", "market", higher_is_stress=True),
    # External debt
    IndicatorSpecification("external_debt_gni", "external_debt", higher_is_stress=True),
    IndicatorSpecification("debt_service_exports", "external_debt", higher_is_stress=True),
    IndicatorSpecification("china_debt_share", "external_debt", higher_is_stress=True),
    # Macro — growth, current account, and reserves are protective: lower = stress.
    IndicatorSpecification("real_gdp_growth", "macro", higher_is_stress=False),
    IndicatorSpecification("cpi_inflation", "macro", higher_is_stress=True),
    IndicatorSpecification("current_account_gdp", "macro", higher_is_stress=False),
    IndicatorSpecification("reserves_import_months", "macro", higher_is_stress=False),
    # Climate
    IndicatorSpecification("climate_vulnerability", "climate", higher_is_stress=True),
)

# The daily overlay recomputes only these on a business-day grid.
MARKET_INDICATORS = tuple(spec for spec in INDICATORS if spec.pillar == "market")
