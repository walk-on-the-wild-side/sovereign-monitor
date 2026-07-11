"""Bulk-download adapters: ND-GAIN country index and AidData GCDF.

Both are on_release sources — run manually when a new release lands, never
scheduled. Download URLs live in config/countries.yaml with their verification
date; both datasets are attribution-licensed and storable.
"""

import io
import zipfile
from pathlib import PurePosixPath
from typing import Any, ClassVar, cast

import httpx
import pandas as pd
import yaml

from sovereign_monitor.ingestion.base import IngestionRuntimeError, SourceAdapter
from sovereign_monitor.schemas import OBSERVATION_COLUMNS

# ND-GAIN ships one CSV per component; these three are the index headline files.
ND_GAIN_FILES = {
    "gain.csv": "ND_GAIN.score",
    "vulnerability.csv": "ND_GAIN.vulnerability",
    "readiness.csv": "ND_GAIN.readiness",
}


def _download(url: str, user_agent: str, timeout_seconds: float) -> bytes:
    response = httpx.get(
        url,
        timeout=timeout_seconds,
        headers={"User-Agent": user_agent},
        follow_redirects=True,
    )
    response.raise_for_status()
    return response.content


class NdGainAdapter(SourceAdapter):
    """ND-GAIN country index: annual score, vulnerability, and readiness."""

    source_id: ClassVar[str] = "nd_gain"
    table: ClassVar[str] = "observations"
    raw_suffix: ClassVar[str] = ".zip"

    def _download_url(self) -> str:
        config = yaml.safe_load(self.settings.countries_path.read_text(encoding="utf-8"))
        return cast(str, config["series"]["nd_gain"]["download_url"])

    def fetch(self) -> bytes:
        return _download(
            self._download_url(),
            self.settings.http_user_agent,
            max(self.settings.http_timeout_seconds, 180.0),
        )

    def parse(self, payload: bytes, batch_id: str, ingested_at: pd.Timestamp) -> pd.DataFrame:
        archive = zipfile.ZipFile(io.BytesIO(payload))
        # The archive repeats these basenames elsewhere — trends/ holds slope
        # tables with the SAME names but no year columns, and __MACOSX/ holds
        # resource-fork junk — so a headline file only counts when its parent
        # directory is named after its component (gain/gain.csv, ...).
        selected: dict[str, str] = {}
        for name in archive.namelist():
            if name.startswith("__MACOSX/"):
                continue
            path = PurePosixPath(name)
            base = path.name
            if base in ND_GAIN_FILES and path.parent.name == base.removesuffix(".csv"):
                selected[base] = name
        missing = set(ND_GAIN_FILES) - set(selected)
        if missing:
            raise IngestionRuntimeError(
                f"nd-gain archive is missing component files {sorted(missing)}; "
                f"entries: {archive.namelist()[:10]}"
            )

        rows: list[dict[str, Any]] = []
        for base, member in selected.items():
            table = pd.read_csv(archive.open(member))
            year_columns = [c for c in table.columns if c.isdigit()]
            long = table.melt(
                id_vars=["ISO3"],
                value_vars=year_columns,
                var_name="year",
                value_name="value",
            ).dropna(subset=["value"])
            for record in long.to_dict("records"):
                year = int(record["year"])
                rows.append(
                    {
                        "source_id": self.source_id,
                        "series_id": ND_GAIN_FILES[base],
                        "country_iso3": record["ISO3"],
                        "date": pd.Timestamp(year=year, month=12, day=31),
                        "value": float(record["value"]),
                        "ingested_at": ingested_at,
                        # ND-GAIN releases lag the reference year by ~18 months.
                        "available_at": pd.Timestamp(year=year + 2, month=1, day=1),
                        "batch_id": batch_id,
                    }
                )
        return pd.DataFrame(rows, columns=OBSERVATION_COLUMNS)


class AidDataAdapter(SourceAdapter):
    """AidData GCDF: project-level Chinese lending aggregated to country-year."""

    source_id: ClassVar[str] = "aiddata_gcdf"
    table: ClassVar[str] = "observations"
    raw_suffix: ClassVar[str] = ".zip"

    def _dataset_config(self) -> dict[str, str]:
        config = yaml.safe_load(self.settings.countries_path.read_text(encoding="utf-8"))
        return cast(dict[str, str], config["series"]["aiddata"])

    def fetch(self) -> bytes:
        return _download(
            self._dataset_config()["download_url"],
            self.settings.http_user_agent,
            max(self.settings.http_timeout_seconds, 600.0),
        )

    def parse(self, payload: bytes, batch_id: str, ingested_at: pd.Timestamp) -> pd.DataFrame:
        dataset = self._dataset_config()
        archive = zipfile.ZipFile(io.BytesIO(payload))
        workbook_names = [n for n in archive.namelist() if n.lower().endswith(".xlsx")]
        if not workbook_names:
            raise IngestionRuntimeError(
                f"aiddata archive has no .xlsx; entries: {archive.namelist()[:10]}"
            )
        workbook_name = min(workbook_names, key=len)

        excel_file = pd.ExcelFile(archive.open(workbook_name))
        sheet = next(
            (name for name in excel_file.sheet_names if "gcdf" in str(name).lower()),
            excel_file.sheet_names[0],
        )
        table = pd.read_excel(archive.open(workbook_name), sheet_name=sheet)

        columns = {str(c).lower(): c for c in table.columns}

        def find_column(prefix: str) -> Any:
            for lower, original in columns.items():
                if lower.startswith(prefix):
                    return original
            raise IngestionRuntimeError(
                f"aiddata sheet {sheet!r} has no column starting {prefix!r}; "
                f"columns: {list(table.columns)[:15]}"
            )

        iso_column = find_column("recipient iso-3")
        year_column = find_column("commitment year")
        amount_column = find_column("amount (constant usd")
        recommended_column = find_column("recommended for aggregates")

        usable = table[table[recommended_column].astype(str).str.lower() == "yes"]
        usable = usable.dropna(subset=[iso_column, year_column, amount_column])
        aggregated = usable.groupby([iso_column, year_column])[amount_column].sum().reset_index()

        release_date = pd.Timestamp(dataset["release_date"])
        rows: list[dict[str, Any]] = []
        for record in aggregated.itertuples(index=False):
            iso3, year, amount = record
            rows.append(
                {
                    "source_id": self.source_id,
                    "series_id": "GCDF.COMMITMENTS_CONST_USD",
                    "country_iso3": str(iso3),
                    "date": pd.Timestamp(year=int(year), month=12, day=31),
                    "value": float(amount),
                    "ingested_at": ingested_at,
                    # Project data of ANY year in a release was only knowable when
                    # the dataset shipped — leakage rule for research datasets.
                    "available_at": release_date,
                    "batch_id": batch_id,
                }
            )
        return pd.DataFrame(rows, columns=OBSERVATION_COLUMNS)
