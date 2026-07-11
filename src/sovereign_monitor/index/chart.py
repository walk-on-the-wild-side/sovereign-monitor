"""Index heatmap for the README and weekly issue.

Follows the validated reference palette: sequential single-hue blues for
magnitude, ink/muted tokens for text, attribution and the disclaimer baked into
the image. A heatmap (countries x months) keeps twelve series readable where a
twelve-line chart would not be.
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless: CLI and CI never have a display

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap

SURFACE, INK, INK_2, MUTED = "#fcfcfb", "#0b0b0b", "#52514e", "#898781"
# Sequential blue ramp steps 100 → 700 from the validated reference palette.
SEQUENTIAL_BLUES = [
    "#cde2fb",
    "#9ec5f4",
    "#6da7ec",
    "#3987e5",
    "#256abf",
    "#184f95",
    "#0d366b",
]
HEATMAP_MONTHS = 24

ATTRIBUTION = (
    "Sources: FRED® (ICE BofA index data © ICE Data Indices, LLC — derived, "
    "not redistributed), Yahoo Finance (derived), World Bank WDI/IDS (CC BY-4.0), "
    "ND-GAIN.  Methodology: see docs/methodology.md.  Not investment advice."
)


def write_index_heatmap(monthly: pd.DataFrame, output_path: Path) -> None:
    """Render the trailing two years of composite scores as a heatmap PNG."""
    recent_months = sorted(monthly["as_of"].unique())[-HEATMAP_MONTHS:]
    recent = monthly[monthly["as_of"].isin(recent_months)]
    matrix = recent.pivot(index="country_iso3", columns="as_of", values="composite")
    matrix = matrix.sort_index()

    colormap = LinearSegmentedColormap.from_list("stress_blues", SEQUENTIAL_BLUES)
    figure, axes = plt.subplots(figsize=(10, 0.45 * len(matrix) + 1.8), dpi=200, facecolor=SURFACE)
    mesh = axes.imshow(matrix.to_numpy(), aspect="auto", cmap=colormap, vmin=0, vmax=100)

    axes.set_yticks(range(len(matrix.index)), matrix.index, fontsize=9, color=INK_2)
    month_labels = [pd.Timestamp(m).strftime("%b %y") for m in matrix.columns]
    step = max(1, len(month_labels) // 12)
    axes.set_xticks(
        range(0, len(month_labels), step),
        month_labels[::step],
        fontsize=8,
        color=MUTED,
    )
    axes.tick_params(length=0)
    for side in axes.spines.values():
        side.set_visible(False)

    # Title and subtitle as separate anchored texts: set_title with a nearby
    # axes.text collides once bbox_inches="tight" crops the margins.
    axes.text(
        0,
        1.12,
        "Composite sovereign-stress index",
        transform=axes.transAxes,
        color=INK,
        fontsize=13,
        fontweight="bold",
        va="bottom",
    )
    axes.text(
        0,
        1.03,
        "0 = calmest observed, 100 = most stressed observed (pooled 2000-present scaling)",
        transform=axes.transAxes,
        color=INK_2,
        fontsize=9,
        va="bottom",
    )
    colorbar = figure.colorbar(mesh, ax=axes, fraction=0.025, pad=0.02)
    colorbar.ax.tick_params(labelsize=8, colors=MUTED, length=0)
    colorbar.outline.set_visible(False)  # type: ignore[operator]  # stubs mistype outline

    figure.text(0.01, 0.01, ATTRIBUTION, color=MUTED, fontsize=6.5)
    figure.savefig(output_path, bbox_inches="tight", facecolor=SURFACE)
    plt.close(figure)
