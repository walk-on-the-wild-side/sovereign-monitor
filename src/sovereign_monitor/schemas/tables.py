"""Table schemas for the two storage grains (SPEC: grain and schema sketch).

A batch that fails any check here is quarantined, never ingested. Checks encode
the SPEC's validation rules that make sense per-batch; freshness and volume
checks arrive with B1's incremental pulls.
"""

from dataclasses import dataclass

import pandas as pd
import pandera.pandas as pa

OBSERVATION_KEY = ("source_id", "series_id", "country_iso3", "date")
NEWS_ITEM_KEY = ("source_id", "url_hash")


def _batch_is_not_empty(frame: pd.DataFrame) -> bool:
    # An empty batch means a fetch or parse regression; fail loudly rather than
    # silently landing nothing.
    return len(frame) > 0


def _observation_key_is_unique(frame: pd.DataFrame) -> bool:
    return not frame.duplicated(subset=list(OBSERVATION_KEY)).any()


def _news_key_is_unique(frame: pd.DataFrame) -> bool:
    return not frame.duplicated(subset=list(NEWS_ITEM_KEY)).any()


def _values_mostly_present(frame: pd.DataFrame) -> bool:
    return bool(frame["value"].notna().mean() >= 0.99)


def _spread_values_in_range(frame: pd.DataFrame) -> bool:
    # ICE BofA OAS series are quoted in percent on FRED; anything outside a generous
    # 0 to 10,000 bps window is a unit mix-up or a corrupted pull.
    spreads = frame.loc[frame["series_id"].str.startswith("BAML"), "value"].dropna()
    return bool(((spreads > 0) & (spreads < 10_000)).all())


OBSERVATION_SCHEMA = pa.DataFrameSchema(
    columns={
        "source_id": pa.Column(str),
        "series_id": pa.Column(str),
        "country_iso3": pa.Column(str, pa.Check.str_matches(r"^[A-Z]{3}$")),
        "date": pa.Column("datetime64[ns]"),
        "value": pa.Column(float, nullable=True),
        "ingested_at": pa.Column("datetime64[ns, UTC]"),
        "available_at": pa.Column("datetime64[ns]"),
        "batch_id": pa.Column(str),
    },
    checks=[
        pa.Check(_batch_is_not_empty, error="batch must not be empty"),
        pa.Check(_observation_key_is_unique, error="observation primary key must be unique"),
        pa.Check(_values_mostly_present, error="value must be at least 99% non-null per batch"),
        pa.Check(_spread_values_in_range, error="spread values must lie inside (0, 10000)"),
    ],
    strict=True,
    coerce=True,
)

NEWS_ITEM_SCHEMA = pa.DataFrameSchema(
    columns={
        "source_id": pa.Column(str),
        "url_hash": pa.Column(str, pa.Check.str_matches(r"^[0-9a-f]{64}$")),
        "url": pa.Column(str, pa.Check.str_startswith("http")),
        "title": pa.Column(str),
        "published_at": pa.Column("datetime64[ns, UTC]", nullable=True),
        "outlet": pa.Column(str),
        # Our own summary, written later by a human or a free local LLM — never the
        # article body (SPEC: link_only licensing).
        "summary_own": pa.Column(object, nullable=True),
        "theme_tags": pa.Column(object),
        "country_iso3": pa.Column(object),
        "tone": pa.Column(float, nullable=True),
        "ingested_at": pa.Column("datetime64[ns, UTC]"),
        "batch_id": pa.Column(str),
    },
    checks=[
        pa.Check(_batch_is_not_empty, error="batch must not be empty"),
        pa.Check(_news_key_is_unique, error="news item primary key must be unique"),
    ],
    strict=True,
    coerce=False,  # adapters build exact dtypes; coercing object columns would corrupt lists
)


@dataclass(frozen=True)
class TableSpecification:
    """Everything the store and adapters need to know about one curated table."""

    name: str
    file_name: str
    schema: pa.DataFrameSchema
    natural_key: tuple[str, ...]


TABLES = {
    "observations": TableSpecification(
        "observations", "observations.parquet", OBSERVATION_SCHEMA, OBSERVATION_KEY
    ),
    "news_items": TableSpecification(
        "news_items", "news_items.parquet", NEWS_ITEM_SCHEMA, NEWS_ITEM_KEY
    ),
}
