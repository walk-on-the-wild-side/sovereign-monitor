"""Bulk-download adapters exercised against small synthetic archives."""

import io
import zipfile

import pandas as pd

from sovereign_monitor.configuration import Settings
from sovereign_monitor.ingestion import AidDataAdapter, NdGainAdapter
from sovereign_monitor.registry import Registry


def _nd_gain_archive() -> bytes:
    """A minimal ND-GAIN zip: headline CSVs at the root, a decoy in a subdirectory."""
    wide_csv = "ISO3,Name,2022,2023\nPAK,Pakistan,38.1,38.4\nIND,India,45.2,45.6\n"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("resources/gain/gain.csv", wide_csv)
        archive.writestr("resources/vulnerability/vulnerability.csv", wide_csv)
        archive.writestr("resources/readiness/readiness.csv", wide_csv)
        # Sector file with the same basename, deeper path: must NOT be selected.
        archive.writestr(
            "resources/vulnerability/sectors/water/vulnerability.csv",
            "ISO3,Name,2023\nPAK,Pakistan,99.9\n",
        )
    return buffer.getvalue()


def _aiddata_archive() -> bytes:
    """A minimal GCDF zip holding one xlsx with the real column headings."""
    table = pd.DataFrame(
        {
            "AidData Record ID": [1, 2, 3, 4],
            "Recipient": ["Pakistan", "Pakistan", "Laos", "Laos"],
            "Recipient ISO-3": ["PAK", "PAK", "LAO", "LAO"],
            "Commitment Year": [2015, 2015, 2016, 2016],
            "Amount (Constant USD 2021)": [1_000_000.0, 2_000_000.0, 500_000.0, 700_000.0],
            "Recommended For Aggregates": ["Yes", "Yes", "Yes", "No"],
        }
    )
    xlsx_buffer = io.BytesIO()
    table.to_excel(xlsx_buffer, sheet_name="GCDF_3.0", index=False)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("AidDatas_GCDF_3_0.xlsx", xlsx_buffer.getvalue())
    return buffer.getvalue()


def test_nd_gain_melts_headline_files_only(registry: Registry, settings: Settings) -> None:
    adapter = NdGainAdapter(registry.sources["nd_gain"], settings)
    result = adapter.run(payload=_nd_gain_archive())
    assert not result.quarantined

    curated = pd.read_parquet(settings.data_directory / "curated" / "observations.parquet")
    assert set(curated["series_id"]) == {
        "ND_GAIN.score",
        "ND_GAIN.vulnerability",
        "ND_GAIN.readiness",
    }
    # 2 countries x 2 years x 3 files; the deeper sector decoy contributes nothing.
    assert len(curated) == 12
    assert not (curated["value"] == 99.9).any()


def test_aiddata_aggregates_recommended_commitments(registry: Registry, settings: Settings) -> None:
    adapter = AidDataAdapter(registry.sources["aiddata_gcdf"], settings)
    result = adapter.run(payload=_aiddata_archive())
    assert not result.quarantined

    curated = pd.read_parquet(settings.data_directory / "curated" / "observations.parquet")
    by_country = curated.set_index("country_iso3")["value"].to_dict()
    # PAK sums two recommended rows; LAO drops the not-recommended one.
    assert by_country == {"PAK": 3_000_000.0, "LAO": 500_000.0}
    # Leakage rule for research datasets: availability is the release date.
    assert (curated["available_at"] == pd.Timestamp("2023-11-01")).all()
