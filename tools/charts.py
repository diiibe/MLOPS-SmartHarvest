"""
Plotly charts for the dashboard's Data Analysis tab.

Design language
---------------
All charts share the same visual tokens so the tab reads like one
document, not a collage of defaults. The tokens align with the rest
of the dashboard (wine-red / gray) — no blue, no colourful pastel
categoricals.

    canvas      : transparent (section background shows through)
    grid        : #262626 (1px, solid, horizontal only)
    axis label  : #9a9a9a 11px
    tick        : #b4b4b4
    primary     : #8a1f33   (wine red — default series colour)
    secondary   : #c9a227   (warm amber — accent / comparison)
    muted fill  : #2b2b2b   (ranges, bands)

Every figure returns an HTML snippet ready to drop into a Jinja
template via `{{ ... | safe }}`. The first snippet on a page includes
`plotly.js` from the CDN; every subsequent snippet sets
`include_plotlyjs=False` to avoid re-downloading the library.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
from plotly.subplots import make_subplots


# -- Shared design tokens ---------------------------------------------

COLORS = {
    "canvas": "rgba(0,0,0,0)",
    "grid": "#262626",
    "axis": "#9a9a9a",
    "tick": "#b4b4b4",
    "primary": "#8a1f33",
    "secondary": "#c9a227",
    "muted_fill": "#2b2b2b",
    "soft_fill": "rgba(138, 31, 51, 0.18)",
    "diverge_low": "#3a6c7a",
    "diverge_mid": "#1d1d1d",
    "diverge_high": "#8a1f33",
}

FONT = dict(
    family="system-ui, -apple-system, 'Segoe UI', sans-serif",
    color="#cccccc",
    size=12,
)

SENSOR_COLOR = {
    "S2": "#8a1f33",
    "S1": "#5a7b6f",
    "L8": "#c9a227",
    "SRTM": "#7a7a7a",
}


def _base_layout(**overrides) -> Dict[str, Any]:
    """Return a layout dict matching the page's dark-muted design.

    Nested axis overrides are deep-merged, not replaced. Without this
    a caller like `yaxis=dict(tickmode="array", ...)` would wipe out
    the base's `zerolinecolor`, and Plotly would fall back to its
    default (white) — visible as a stray horizontal line crossing the
    row at y = 0.
    """
    axis_defaults = dict(
        gridcolor=COLORS["grid"],
        linecolor=COLORS["grid"],
        tickcolor=COLORS["grid"],
        zerolinecolor=COLORS["grid"],
        zerolinewidth=1,
        tickfont=dict(color=COLORS["tick"], size=11),
        title_font=dict(color=COLORS["axis"], size=11),
    )
    layout = dict(
        paper_bgcolor=COLORS["canvas"],
        plot_bgcolor=COLORS["canvas"],
        font=FONT,
        margin=dict(l=56, r=24, t=24, b=48),
        hoverlabel=dict(
            bgcolor="#121212",
            bordercolor="#333",
            font_size=12,
            font_family=FONT["family"],
        ),
        xaxis=dict(axis_defaults),
        yaxis=dict(axis_defaults),
        showlegend=False,
    )
    for key, value in overrides.items():
        if key in ("xaxis", "yaxis") and isinstance(value, dict):
            merged = dict(axis_defaults)
            merged.update(value)
            layout[key] = merged
        else:
            layout[key] = value
    return layout


def _to_html(fig: go.Figure, include_plotlyjs: bool = False) -> str:
    """Serialise a figure with uniform config (no plotly branding bar)."""
    return pio.to_html(
        fig,
        full_html=False,
        include_plotlyjs="cdn" if include_plotlyjs else False,
        config=dict(
            displaylogo=False,
            modeBarButtonsToRemove=[
                "lasso2d",
                "select2d",
                "toggleSpikelines",
                "autoScale2d",
            ],
            responsive=True,
        ),
    )


# -- 1. Acquisition coverage timeline ---------------------------------

def create_acquisition_timeline(df: pd.DataFrame) -> Optional[str]:
    """
    One row per sensor × one tick per observation date.

    Reads the `satellite` column produced by `assembly.py`, which is a
    comma-joined list of sensor codes per row (`"S1,S2"` is a common
    value). We explode those memberships, group to unique (sensor,
    date) pairs, and draw each as a vertical tick. A quick glance
    tells the agronomist when the vineyard was actually observed and
    where the revisit gaps sit.
    """
    if df is None or df.empty or "date" not in df.columns:
        return None
    if "satellite" not in df.columns:
        return None

    sat = df[["date", "satellite"]].dropna()
    if sat.empty:
        return None

    sat = sat.assign(
        satellite=sat["satellite"].astype(str).str.split(",")
    ).explode("satellite")
    sat["satellite"] = sat["satellite"].str.strip()
    sat = sat[sat["satellite"].isin(SENSOR_COLOR)]
    sat = sat.drop_duplicates(["date", "satellite"])
    if sat.empty:
        return None

    sat["date"] = pd.to_datetime(sat["date"])
    # Consistent row ordering top-to-bottom.
    order = ["S2", "S1", "L8", "SRTM"]
    sat["_y"] = sat["satellite"].map({s: i for i, s in enumerate(order)})
    sat = sat.dropna(subset=["_y"])
    if sat.empty:
        return None

    fig = go.Figure()
    for sensor in order:
        block = sat[sat["satellite"] == sensor]
        if block.empty:
            continue
        fig.add_trace(
            go.Scatter(
                x=block["date"],
                y=block["_y"],
                mode="markers",
                marker=dict(
                    symbol="circle",
                    size=13,
                    color=SENSOR_COLOR[sensor],
                    line=dict(width=0),
                    opacity=0.95,
                ),
                name=sensor,
                hovertemplate=f"<b>{sensor}</b> — %{{x|%Y-%m-%d}}<extra></extra>",
            )
        )

    layout = _base_layout(
        height=240,
        yaxis=dict(
            tickmode="array",
            tickvals=list(range(len(order))),
            ticktext=order,
            autorange="reversed",
            gridcolor=COLORS["canvas"],
            linecolor=COLORS["canvas"],
            tickcolor=COLORS["canvas"],
            tickfont=dict(color=COLORS["tick"], size=12),
            zeroline=False,
            showline=False,
        ),
        xaxis=dict(
            gridcolor=COLORS["grid"],
            linecolor=COLORS["grid"],
            tickfont=dict(color=COLORS["tick"], size=11),
            title=None,
            zeroline=False,
        ),
    )
    fig.update_layout(layout)
    return _to_html(fig, include_plotlyjs=True)


# -- 2. Cloud coverage per Sentinel-2 scene ---------------------------

def create_cloud_coverage(metadata_list: Optional[List[Dict[str, Any]]]) -> Optional[str]:
    """
    Horizontal lollipop of `CLOUDY_PIXEL_PERCENTAGE` per S2 scene.

    Needs the per-image array that `modules/sentinel2.py` persists
    into metadata. Scenes above the configured threshold are drawn
    in muted gray with a tooltip that says "discarded". The threshold
    line is dashed and labelled with the percentage used. On runs
    that predate this metadata feature (e.g. the demo bundle) we
    return `None` and the section skips cleanly.
    """
    if not metadata_list:
        return None

    s2 = next(
        (m for m in metadata_list if m.get("source") == "Sentinel-2"), None
    )
    if not s2:
        return None

    per_image = s2.get("cloud_per_image_pct") or []
    if not per_image:
        return None

    threshold = int(s2.get("cloud_threshold_used", 50))
    values = sorted([float(v) for v in per_image if v is not None])

    x = list(range(1, len(values) + 1))
    kept_mask = [v < threshold for v in values]
    colors_marker = [
        COLORS["primary"] if kept else "#4a4a4a" for kept in kept_mask
    ]

    fig = go.Figure()
    # "Stems" from zero to each value.
    for xi, yi, kept in zip(x, values, kept_mask):
        fig.add_shape(
            type="line",
            x0=xi,
            x1=xi,
            y0=0,
            y1=yi,
            line=dict(color=colors_marker[xi - 1], width=1),
            layer="below",
        )
    fig.add_trace(
        go.Scatter(
            x=x,
            y=values,
            mode="markers",
            marker=dict(size=7, color=colors_marker),
            hovertemplate=(
                "Scene #%{x}<br>"
                "Cloud %{y:.1f}%<br>"
                "<extra></extra>"
            ),
        )
    )
    # Threshold line.
    fig.add_shape(
        type="line",
        x0=0.5,
        x1=len(values) + 0.5,
        y0=threshold,
        y1=threshold,
        line=dict(color=COLORS["secondary"], width=1, dash="dot"),
    )
    fig.add_annotation(
        x=len(values),
        y=threshold,
        text=f"threshold: {threshold}%",
        showarrow=False,
        xanchor="right",
        yanchor="bottom",
        xshift=-4,
        yshift=4,
        font=dict(color=COLORS["secondary"], size=11),
    )

    kept_count = sum(kept_mask)
    fig.add_annotation(
        xref="paper",
        yref="paper",
        x=0,
        y=1.08,
        text=(
            f"{kept_count} of {len(values)} scenes kept · "
            f"median cloud cover {np.median(values):.1f}%"
        ),
        showarrow=False,
        font=dict(color=COLORS["axis"], size=11),
        xanchor="left",
    )

    fig.update_layout(
        _base_layout(
            height=260,
            xaxis=dict(
                title="Scene (sorted by cloud cover)",
                tickmode="auto",
                nticks=8,
                gridcolor=COLORS["canvas"],
                linecolor=COLORS["grid"],
                tickfont=dict(color=COLORS["tick"], size=11),
                title_font=dict(color=COLORS["axis"], size=11),
            ),
            yaxis=dict(
                title="Cloud cover (%)",
                range=[0, max(100, max(values) * 1.05)],
                gridcolor=COLORS["grid"],
                linecolor=COLORS["grid"],
                tickfont=dict(color=COLORS["tick"], size=11),
                title_font=dict(color=COLORS["axis"], size=11),
            ),
        )
    )
    return _to_html(fig)


# -- 3. Vegetation index temporal trends ------------------------------

def create_index_trends(df: pd.DataFrame) -> Optional[str]:
    """
    Time-series of ROI-mean value per index, with an IQR ribbon.

    The band shows the spatial variance of the vineyard for that date
    — wide band = heterogeneous response — while the solid line is
    the ROI mean. One small-multiples row per index keeps scales
    independent (NDVI in [0,1] is not comparable to IRECI in
    thousands on a shared y).
    """
    if df is None or df.empty or "date" not in df.columns:
        return None

    optical = [c for c in ["NDVI", "NDRE", "NDWI", "MNDWI"] if c in df.columns]
    if not optical:
        return None

    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])

    n = len(optical)
    fig = make_subplots(
        rows=n,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.06,
        subplot_titles=optical,
    )

    for i, col in enumerate(optical, start=1):
        block = df[["date", col]].dropna()
        if block.empty:
            continue
        daily = block.groupby("date")[col].agg(["mean", "median"]).reset_index()
        quartiles = (
            block.groupby("date")[col]
            .quantile([0.25, 0.75])
            .unstack()
            .reset_index()
        )
        quartiles.columns = ["date", "q25", "q75"]
        merged = daily.merge(quartiles, on="date")

        # IQR ribbon (q75 → q25 closed via reverse).
        fig.add_trace(
            go.Scatter(
                x=list(merged["date"]) + list(merged["date"][::-1]),
                y=list(merged["q75"]) + list(merged["q25"][::-1]),
                fill="toself",
                fillcolor=COLORS["soft_fill"],
                line=dict(color="rgba(0,0,0,0)"),
                hoverinfo="skip",
                showlegend=False,
            ),
            row=i,
            col=1,
        )
        fig.add_trace(
            go.Scatter(
                x=merged["date"],
                y=merged["mean"],
                mode="lines+markers",
                line=dict(color=COLORS["primary"], width=1.5),
                marker=dict(size=4, color=COLORS["primary"]),
                hovertemplate=(
                    "%{x|%Y-%m-%d}<br>"
                    "mean %{y:.3f}<extra></extra>"
                ),
                showlegend=False,
            ),
            row=i,
            col=1,
        )
        fig.update_yaxes(
            row=i,
            col=1,
            gridcolor=COLORS["grid"],
            linecolor=COLORS["grid"],
            tickfont=dict(color=COLORS["tick"], size=10),
            title=None,
            zeroline=False,
        )
        fig.update_xaxes(
            row=i,
            col=1,
            gridcolor=COLORS["grid"],
            linecolor=COLORS["grid"],
            tickfont=dict(color=COLORS["tick"], size=10),
        )

    fig.update_layout(
        _base_layout(
            height=180 * n,
            margin=dict(l=48, r=16, t=28, b=40),
        )
    )
    # Force subplot titles to the muted axis colour.
    for ann in fig.layout.annotations:
        ann.font = dict(color=COLORS["axis"], size=11, family=FONT["family"])
        ann.x = 0
        ann.xanchor = "left"
    return _to_html(fig)


# -- 4. Per-variable distributions ------------------------------------

def create_distributions(df: pd.DataFrame) -> Optional[str]:
    """
    Stepped histograms (no fill) for the main measurables.

    Plotly's default bar-filled histogram hides detail on dense data.
    A stepped outline plus a median line communicates shape +
    central tendency in one glance without visual noise.
    """
    if df is None or df.empty:
        return None

    candidates = [
        "NDVI",
        "NDWI",
        "MNDWI",
        "NDRE",
        "IRECI",
        "S2REP",
        "VH",
        "VV",
        "Ratio",
        "LST",
        "Slope",
    ]
    cols = [c for c in candidates if c in df.columns and df[c].notna().any()]
    if not cols:
        return None

    n_cols = 3
    n_rows = math.ceil(len(cols) / n_cols)
    fig = make_subplots(
        rows=n_rows,
        cols=n_cols,
        subplot_titles=cols,
        horizontal_spacing=0.08,
        vertical_spacing=0.18,
    )

    for idx, col in enumerate(cols):
        r = idx // n_cols + 1
        c = idx % n_cols + 1
        series = df[col].dropna()
        if series.empty:
            continue
        # Histogram as step outline.
        counts, edges = np.histogram(series, bins=40)
        centers = (edges[:-1] + edges[1:]) / 2
        fig.add_trace(
            go.Scatter(
                x=centers,
                y=counts,
                mode="lines",
                line=dict(color=COLORS["primary"], width=1.5, shape="hv"),
                fill="tozeroy",
                fillcolor=COLORS["soft_fill"],
                hovertemplate="%{x:.3f}<br>count %{y}<extra></extra>",
                showlegend=False,
            ),
            row=r,
            col=c,
        )
        median = float(series.median())
        fig.add_shape(
            type="line",
            x0=median,
            x1=median,
            yref=f"y{idx + 1}" if idx else "y",
            xref=f"x{idx + 1}" if idx else "x",
            y0=0,
            y1=counts.max() if counts.size else 0,
            line=dict(color=COLORS["secondary"], width=1, dash="dot"),
        )
        fig.update_yaxes(
            row=r,
            col=c,
            gridcolor=COLORS["grid"],
            linecolor=COLORS["grid"],
            tickfont=dict(color=COLORS["tick"], size=10),
        )
        fig.update_xaxes(
            row=r,
            col=c,
            gridcolor=COLORS["grid"],
            linecolor=COLORS["grid"],
            tickfont=dict(color=COLORS["tick"], size=10),
            nticks=4,
        )

    fig.update_layout(
        _base_layout(
            height=220 * n_rows,
            margin=dict(l=40, r=16, t=28, b=32),
        )
    )
    for ann in fig.layout.annotations:
        ann.font = dict(color=COLORS["axis"], size=11, family=FONT["family"])
    return _to_html(fig)


# -- 5. Feature correlation heatmap -----------------------------------

def create_correlation(df: pd.DataFrame) -> Optional[str]:
    """
    Pearson correlation across measurable features.

    Diverging colourscale centred on zero, with annotations embedded
    only where `|rho| >= 0.4` so the matrix does not disappear
    behind clutter.
    """
    if df is None or df.empty:
        return None

    candidates = [
        "NDVI",
        "NDWI",
        "MNDWI",
        "NDRE",
        "IRECI",
        "S2REP",
        "VH",
        "VV",
        "Ratio",
        "LST",
        "Slope",
    ]
    cols = [c for c in candidates if c in df.columns and df[c].notna().any()]
    if len(cols) < 2:
        return None

    corr = df[cols].corr().round(2)

    colorscale = [
        [0.0, COLORS["diverge_low"]],
        [0.5, COLORS["diverge_mid"]],
        [1.0, COLORS["diverge_high"]],
    ]

    fig = go.Figure(
        data=go.Heatmap(
            z=corr.values,
            x=corr.columns,
            y=corr.columns,
            zmin=-1,
            zmax=1,
            colorscale=colorscale,
            hovertemplate="%{y} ↔ %{x}<br>ρ = %{z:.2f}<extra></extra>",
            colorbar=dict(
                outlinecolor=COLORS["grid"],
                tickfont=dict(color=COLORS["tick"], size=10),
                thickness=10,
                len=0.8,
                title=dict(text="ρ", font=dict(color=COLORS["axis"], size=10)),
            ),
        )
    )

    annotations = []
    for yi, ry in enumerate(corr.index):
        for xi, cx in enumerate(corr.columns):
            v = corr.iloc[yi, xi]
            if abs(v) >= 0.4:
                annotations.append(
                    dict(
                        x=cx,
                        y=ry,
                        text=f"{v:.2f}",
                        showarrow=False,
                        font=dict(
                            color="#f0f0f0" if abs(v) > 0.75 else "#d6d6d6",
                            size=10,
                        ),
                    )
                )

    fig.update_layout(
        _base_layout(
            height=48 + 40 * len(cols),
            margin=dict(l=80, r=40, t=24, b=60),
            annotations=annotations,
            xaxis=dict(
                gridcolor=COLORS["canvas"],
                tickfont=dict(color=COLORS["tick"], size=10),
                tickangle=-40,
            ),
            yaxis=dict(
                gridcolor=COLORS["canvas"],
                tickfont=dict(color=COLORS["tick"], size=10),
                autorange="reversed",
            ),
        )
    )
    return _to_html(fig)


# -- 6. NDVI by terrain quartile --------------------------------------

def create_ndvi_by_slope(df: pd.DataFrame) -> Optional[str]:
    """
    Mean NDVI per Slope quartile, with a thin CI whisker.

    Flatter terrain generally holds water longer and develops more
    uniform canopies; this chart turns that intuition into a single
    agronomic number the user can compare across projects.
    """
    if df is None or df.empty:
        return None
    if "NDVI" not in df.columns or "Slope" not in df.columns:
        return None

    block = df[["NDVI", "Slope"]].dropna()
    if len(block) < 20:
        return None

    try:
        block["bucket"] = pd.qcut(
            block["Slope"],
            q=4,
            labels=["Q1 flat", "Q2", "Q3", "Q4 steep"],
            duplicates="drop",
        )
    except ValueError:
        return None

    grouped = (
        block.groupby("bucket", observed=True)["NDVI"]
        .agg(["mean", "std", "count"])
        .reset_index()
    )
    if grouped.empty:
        return None
    grouped["se"] = grouped["std"] / np.sqrt(grouped["count"])

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=grouped["bucket"].astype(str),
            y=grouped["mean"],
            error_y=dict(
                type="data",
                array=1.96 * grouped["se"],
                thickness=1,
                width=6,
                color=COLORS["axis"],
            ),
            marker=dict(
                color=COLORS["primary"],
                line=dict(color=COLORS["primary"], width=0),
            ),
            hovertemplate=(
                "%{x}<br>"
                "mean NDVI %{y:.3f}<br>"
                "n %{customdata[0]:,}<extra></extra>"
            ),
            customdata=grouped[["count"]].values,
        )
    )

    fig.update_layout(
        _base_layout(
            height=240,
            xaxis=dict(
                title="Slope quartile",
                gridcolor=COLORS["canvas"],
                linecolor=COLORS["grid"],
                tickfont=dict(color=COLORS["tick"], size=11),
                title_font=dict(color=COLORS["axis"], size=11),
            ),
            yaxis=dict(
                title="Mean NDVI (95% CI)",
                gridcolor=COLORS["grid"],
                linecolor=COLORS["grid"],
                tickfont=dict(color=COLORS["tick"], size=11),
                title_font=dict(color=COLORS["axis"], size=11),
            ),
            bargap=0.35,
        )
    )
    return _to_html(fig)


# -- 7. Multi-variable overlays ---------------------------------------

# Extra hues used strictly for the overlay plots — a curated rotation
# with the two base tokens (primary + secondary) so every chart in the
# tab still reads as one family.
OVERLAY_COLORS = [
    COLORS["primary"],      # wine red — first series
    COLORS["secondary"],    # amber — second series
    "#5a7b6f",              # muted teal — third (S1-family)
    "#7a7a7a",              # mid grey — fourth (reference / baseline)
]


def _overlay_timeseries(
    df: pd.DataFrame,
    columns: List[str],
    y_title: str,
    normalize: Optional[str] = None,
    height: int = 280,
) -> Optional[str]:
    """
    Shared implementation for "several variables on the same axes".

    Each series shows its daily ROI mean; the lines use the curated
    `OVERLAY_COLORS` rotation so they stay readable against each
    other on the dark surface.

    Args:
        columns: variable column names to overlay. Missing or all-NaN
            columns are skipped silently.
        y_title: y-axis label to apply after any normalization.
        normalize: `None` (raw values), `"minmax"` (rescale each
            series to 0-1 across its own range), or `"zscore"`
            (subtract per-series mean, divide by std). Normalization
            is necessary when the variables would otherwise not share
            a sensible scale (e.g. NDVI in [0,1] vs LST in °C).
    """
    if df is None or df.empty or "date" not in df.columns:
        return None
    present = [c for c in columns if c in df.columns and df[c].notna().any()]
    if len(present) < 2:
        return None

    work = df[["date"] + present].dropna(how="all", subset=present).copy()
    work["date"] = pd.to_datetime(work["date"])

    fig = go.Figure()
    legend_items = []

    for i, col in enumerate(present):
        daily = (
            work[["date", col]]
            .dropna()
            .groupby("date", as_index=False)[col]
            .mean()
            .sort_values("date")
        )
        if daily.empty:
            continue

        display = daily[col].copy()
        raw = daily[col].copy()
        if normalize == "minmax":
            lo, hi = display.min(), display.max()
            if hi > lo:
                display = (display - lo) / (hi - lo)
        elif normalize == "zscore":
            mu, sd = display.mean(), display.std(ddof=0)
            if sd > 0:
                display = (display - mu) / sd

        colour = OVERLAY_COLORS[i % len(OVERLAY_COLORS)]
        customdata = raw.to_numpy().reshape(-1, 1)
        fig.add_trace(
            go.Scatter(
                x=daily["date"],
                y=display,
                mode="lines+markers",
                name=col,
                line=dict(color=colour, width=1.8),
                marker=dict(size=5, color=colour, line=dict(width=0)),
                customdata=customdata,
                hovertemplate=(
                    "<b>%{fullData.name}</b><br>"
                    "%{x|%Y-%m-%d}<br>"
                    "raw %{customdata[0]:.3f}<extra></extra>"
                ),
            )
        )
        legend_items.append(col)

    if not legend_items:
        return None

    fig.update_layout(
        _base_layout(
            height=height,
            showlegend=True,
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="left",
                x=0,
                bgcolor=COLORS["canvas"],
                bordercolor=COLORS["canvas"],
                font=dict(color=COLORS["tick"], size=11),
            ),
            xaxis=dict(
                gridcolor=COLORS["grid"],
                linecolor=COLORS["grid"],
                tickfont=dict(color=COLORS["tick"], size=11),
            ),
            yaxis=dict(
                title=y_title,
                gridcolor=COLORS["grid"],
                linecolor=COLORS["grid"],
                tickfont=dict(color=COLORS["tick"], size=11),
                title_font=dict(color=COLORS["axis"], size=11),
            ),
            hovermode="x unified",
        )
    )
    return _to_html(fig)


def create_canopy_overlay(df: pd.DataFrame) -> Optional[str]:
    """NDVI and NDRE on a shared [0, 1] axis — both are vigour proxies,
    red-edge saturates later so divergence flags dense mature canopies."""
    return _overlay_timeseries(
        df, ["NDVI", "NDRE"], y_title="Index value"
    )


def create_water_overlay(df: pd.DataFrame) -> Optional[str]:
    """NDWI (McFeeters) and MNDWI (Xu) on a shared axis. Both track water
    signal but MNDWI uses SWIR so it handles wet soil / built-up areas
    more gracefully."""
    return _overlay_timeseries(
        df, ["NDWI", "MNDWI"], y_title="Index value"
    )


def create_radar_overlay(df: pd.DataFrame) -> Optional[str]:
    """Sentinel-1 VH + VV + their ratio — all in dB so a shared axis
    is honest. Lines diverging indicates a change in canopy structure
    vs surface roughness."""
    return _overlay_timeseries(
        df, ["VH", "VV", "Ratio"], y_title="Backscatter (dB)"
    )


def create_thermal_vs_vigour(df: pd.DataFrame) -> Optional[str]:
    """LST (°C) next to NDVI ([0, 1]) — unrelated scales, so z-score
    each series. A classic evapotranspiration check: well-watered
    canopies stay cooler even when NDVI plateaus."""
    return _overlay_timeseries(
        df,
        ["NDVI", "LST"],
        y_title="Standard deviations from series mean",
        normalize="zscore",
    )


# -- Overview KPI strip + sparkline + recent-acquisitions --------------
#
# These three blocks land at the top of the new "Overview" sub-tab.
# They render as plain HTML (no Plotly bundle hit) so the landing
# section paints instantly even on a cold-cache reload — the heavy
# Plotly figures live deeper, on the Temporal / Spatial / Quality
# sub-tabs.


def _safe_mean(series: "pd.Series") -> Optional[float]:
    series = series.dropna()
    return float(series.mean()) if len(series) else None


def _safe_isoweek(date: "pd.Timestamp") -> str:
    return date.strftime("%G-W%V")


def _format_metric(value: Optional[float], unit: str = "", digits: int = 2) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "—"
    return f"{value:.{digits}f}{unit}"


def _format_delta(delta: Optional[float], digits: int = 2) -> str:
    if delta is None or math.isnan(delta):
        return ""
    sign = "+" if delta >= 0 else "−"
    return f"{sign}{abs(delta):.{digits}f}"


def _delta_class(delta: Optional[float]) -> str:
    if delta is None or math.isnan(delta):
        return "kpi__delta--neutral"
    if delta > 0.005:
        return "kpi__delta--up"
    if delta < -0.005:
        return "kpi__delta--down"
    return "kpi__delta--neutral"


def create_kpi_strip(
    df: "pd.DataFrame",
    metadata_list: Optional[List[Dict[str, Any]]] = None,
    ml_dir: Optional[str] = None,
) -> Optional[str]:
    """4-tile KPI strip for the Overview sub-tab.

    Tiles:
        1. Latest-week ROI mean NDVI + delta vs prior week.
        2. Latest-week S2 cloud-cover median (from metadata).
        3. Latest-week scene count (S2 + S1 + L8 unique dates).
        4. Latest-week ML hot-spot count (from cluster CSVs in ml_dir).

    Each tile is plain HTML; the CSS class hierarchy lives in
    `static/css/app.css` under `.kpi-strip`.
    """
    if "date" not in df.columns:
        return None

    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])
    if df.empty:
        return None

    df["iso_week"] = df["date"].dt.strftime("%G-W%V")
    weeks = sorted(df["iso_week"].unique())
    latest_week = weeks[-1]
    prior_week = weeks[-2] if len(weeks) >= 2 else None

    # --- Tile 1: NDVI mean current vs prior ---
    ndvi_col = df["NDVI"] if "NDVI" in df.columns else None
    ndvi_now = (
        _safe_mean(df.loc[df["iso_week"] == latest_week, "NDVI"])
        if ndvi_col is not None
        else None
    )
    ndvi_prev = (
        _safe_mean(df.loc[df["iso_week"] == prior_week, "NDVI"])
        if prior_week and ndvi_col is not None
        else None
    )
    ndvi_delta = (
        ndvi_now - ndvi_prev
        if ndvi_now is not None and ndvi_prev is not None
        else None
    )

    # --- Tile 2: latest-week S2 cloud median ---
    cloud_pct = None
    if metadata_list:
        for entry in metadata_list:
            if entry.get("source") == "Sentinel-2":
                per_image = entry.get("cloud_per_image_pct") or []
                if per_image:
                    cloud_pct = float(np.median(per_image))
                else:
                    cloud_pct = entry.get("cloud_coverage", {}).get("mean")
                break

    # --- Tile 3: latest-week scene count ---
    latest_df = df[df["iso_week"] == latest_week]
    if "satellite" in latest_df.columns and not latest_df.empty:
        latest_scenes = latest_df.groupby("satellite")["date"].nunique()
        scene_count = int(latest_scenes.sum())
    else:
        scene_count = int(latest_df["date"].nunique()) if not latest_df.empty else 0

    # --- Tile 4: ML hot-spot count from latest cluster CSV ---
    hotspot_count: Optional[int] = None
    if ml_dir:
        import glob
        import os

        cluster_glob = os.path.join(ml_dir, "weekly", latest_week, "cluster_map_*.csv")
        candidates = sorted(glob.glob(cluster_glob))
        if candidates:
            try:
                cdf = pd.read_csv(candidates[-1])
                if "is_anomalous" in cdf.columns:
                    hotspot_count = int(cdf["is_anomalous"].sum())
                elif "outlier_score" in cdf.columns:
                    threshold = cdf["outlier_score"].quantile(0.95)
                    hotspot_count = int((cdf["outlier_score"] > threshold).sum())
            except Exception:
                hotspot_count = None

    # --- Render ---
    tiles = [
        {
            "label": "NDVI · latest week",
            "value": _format_metric(ndvi_now, digits=3),
            "delta": _format_delta(ndvi_delta, digits=3),
            "delta_class": _delta_class(ndvi_delta),
            "sub": f"vs {prior_week}" if prior_week else "first week",
        },
        {
            "label": "Cloud median · S2",
            "value": _format_metric(cloud_pct, unit="%", digits=1),
            "delta": "",
            "delta_class": "kpi__delta--neutral",
            "sub": "across all scenes",
        },
        {
            "label": "Acquisitions · latest week",
            "value": str(scene_count) if scene_count else "—",
            "delta": "",
            "delta_class": "kpi__delta--neutral",
            "sub": latest_week,
        },
        {
            "label": "Anomaly hot-spots",
            "value": str(hotspot_count) if hotspot_count is not None else "—",
            "delta": "",
            "delta_class": "kpi__delta--neutral",
            "sub": "ML clustering · latest week",
        },
    ]

    tile_html = "".join(
        f"""<div class="kpi">
            <div class="kpi__label">{t['label']}</div>
            <div class="kpi__row">
              <div class="kpi__value">{t['value']}</div>
              <div class="kpi__delta {t['delta_class']}">{t['delta']}</div>
            </div>
            <div class="kpi__sub">{t['sub']}</div>
        </div>"""
        for t in tiles
    )
    return f'<div class="kpi-strip">{tile_html}</div>'


def create_ndvi_sparkline(df: "pd.DataFrame", weeks: int = 12) -> Optional[str]:
    """Compact NDVI sparkline for the Overview sub-tab.

    Plots the ROI-mean NDVI per ISO week for the most recent
    `weeks` weeks. No axis, no grid — a clean trace with a single
    dot on the latest point. Designed to read at a glance, not to
    replace the full index_trends chart.
    """
    if "date" not in df.columns or "NDVI" not in df.columns:
        return None
    if df["NDVI"].dropna().empty:
        return None

    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date", "NDVI"])
    if df.empty:
        return None

    df["iso_week"] = df["date"].dt.strftime("%G-W%V")
    by_week = df.groupby("iso_week")["NDVI"].mean().sort_index()
    if len(by_week) > weeks:
        by_week = by_week.iloc[-weeks:]
    if len(by_week) < 2:
        return None

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=list(by_week.index),
            y=list(by_week.values),
            mode="lines",
            line=dict(color=COLORS["primary"], width=2.4, shape="spline", smoothing=0.6),
            fill="tozeroy",
            fillcolor=COLORS["soft_fill"],
            hovertemplate="<b>%{x}</b><br>NDVI %{y:.3f}<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=[by_week.index[-1]],
            y=[by_week.values[-1]],
            mode="markers",
            marker=dict(color=COLORS["secondary"], size=8, line=dict(color="#0a0a0a", width=2)),
            hovertemplate="<b>Latest %{x}</b><br>NDVI %{y:.3f}<extra></extra>",
        )
    )
    layout = _base_layout(
        height=120,
        margin=dict(l=8, r=8, t=8, b=8),
        xaxis=dict(visible=False),
        yaxis=dict(visible=False, range=[0, max(0.9, float(by_week.max()) * 1.15)]),
    )
    fig.update_layout(**layout)
    return _to_html(fig)


def create_recent_acquisitions(df: "pd.DataFrame", limit: int = 5) -> Optional[str]:
    """Tabular block listing the last `limit` acquisitions.

    One row per (date × satellite) tuple. Designed to live in the
    Overview sub-tab as a quiet "what just happened" panel — no
    chart, just typography.
    """
    if "date" not in df.columns or "satellite" not in df.columns:
        return None

    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date", "satellite"])
    if df.empty:
        return None

    # Each (date, satellite) appears many times (one row per pixel).
    # Collapse to one row per (date, satellite-string in CSV form),
    # then split combos like "L8,S2" into separate rows so the table
    # reads as a clean acquisition log.
    grouped = (
        df.groupby([df["date"].dt.date, "satellite"])
        .size()
        .reset_index(name="pixel_rows")
    )
    grouped.columns = ["date", "satellite", "pixel_rows"]

    # Explode combos
    grouped["satellite"] = grouped["satellite"].astype(str).str.split(",")
    grouped = grouped.explode("satellite").reset_index(drop=True)
    grouped["satellite"] = grouped["satellite"].str.strip()

    grouped = grouped.sort_values("date", ascending=False).head(limit * 4)
    seen = set()
    rows = []
    for _, r in grouped.iterrows():
        key = (r["date"], r["satellite"])
        if key in seen:
            continue
        seen.add(key)
        rows.append(r)
        if len(rows) >= limit:
            break
    if not rows:
        return None

    sensor_label = {"S2": "Sentinel-2", "S1": "Sentinel-1", "L8": "Landsat 8/9"}
    items = "".join(
        f"""<li class="recent__row" data-sensor="{r['satellite'].lower()}">
            <span class="recent__date">{r['date'].strftime('%Y-%m-%d')}</span>
            <span class="recent__sensor">{sensor_label.get(r['satellite'], r['satellite'])}</span>
        </li>"""
        for r in rows
    )
    return f'<ol class="recent">{items}</ol>'


# -- Spatial: change detection ΔNDVI summary --------------------------


def create_change_detection_summary(df: "pd.DataFrame") -> Optional[str]:
    """ΔNDVI summary card for the Spatial sub-tab.

    For every pixel (`spatial_id` or `.geo`), compute the mean NDVI
    in the last 30 days vs the prior 30 days. Bucket pixels into
    {improved, stable, declined} based on |Δ| ≥ 0.05. Render as a
    horizontal stacked bar plus a count breakdown so the magnitude
    of change is immediate.
    """
    if "date" not in df.columns or "NDVI" not in df.columns:
        return None

    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date", "NDVI"])
    if df.empty:
        return None

    pixel_key = "spatial_id" if "spatial_id" in df.columns else ".geo"
    if pixel_key not in df.columns:
        return None

    end = df["date"].max()
    mid = end - pd.Timedelta(days=30)
    start = end - pd.Timedelta(days=60)

    recent = df[(df["date"] > mid) & (df["date"] <= end)]
    prior = df[(df["date"] > start) & (df["date"] <= mid)]
    if recent.empty or prior.empty:
        return None

    recent_mean = recent.groupby(pixel_key)["NDVI"].mean()
    prior_mean = prior.groupby(pixel_key)["NDVI"].mean()
    common = recent_mean.index.intersection(prior_mean.index)
    if len(common) < 4:
        return None
    delta = (recent_mean.loc[common] - prior_mean.loc[common]).dropna()
    if delta.empty:
        return None

    threshold = 0.05
    improved = int((delta >= threshold).sum())
    declined = int((delta <= -threshold).sum())
    stable = int(len(delta) - improved - declined)
    total = improved + stable + declined
    if total == 0:
        return None

    pct_improved = improved / total * 100
    pct_stable = stable / total * 100
    pct_declined = declined / total * 100

    median_delta = float(delta.median())
    p10 = float(delta.quantile(0.10))
    p90 = float(delta.quantile(0.90))

    bar_html = f"""
    <div class="change__bar" role="img"
         aria-label="Pixel change distribution: {pct_improved:.0f}% improved,
                    {pct_stable:.0f}% stable, {pct_declined:.0f}% declined">
        <span class="change__seg change__seg--up"
              style="--w:{pct_improved:.2f}%"
              title="{improved} pixels improved (Δ ≥ +{threshold:.2f})"></span>
        <span class="change__seg change__seg--flat"
              style="--w:{pct_stable:.2f}%"
              title="{stable} pixels stable (|Δ| < {threshold:.2f})"></span>
        <span class="change__seg change__seg--down"
              style="--w:{pct_declined:.2f}%"
              title="{declined} pixels declined (Δ ≤ -{threshold:.2f})"></span>
    </div>"""

    counts_html = f"""
    <ul class="change__counts">
        <li class="change__count change__count--up">
            <span class="change__pct">{pct_improved:.0f}%</span>
            <span class="change__num">{improved} px</span>
            <span class="change__lbl">improved</span>
        </li>
        <li class="change__count change__count--flat">
            <span class="change__pct">{pct_stable:.0f}%</span>
            <span class="change__num">{stable} px</span>
            <span class="change__lbl">stable</span>
        </li>
        <li class="change__count change__count--down">
            <span class="change__pct">{pct_declined:.0f}%</span>
            <span class="change__num">{declined} px</span>
            <span class="change__lbl">declined</span>
        </li>
    </ul>"""

    stats_html = f"""
    <div class="change__stats">
        <span class="change__stat">Median Δ <b>{_format_delta(median_delta, 3)}</b></span>
        <span class="change__stat">P10 <b>{_format_delta(p10, 3)}</b></span>
        <span class="change__stat">P90 <b>{_format_delta(p90, 3)}</b></span>
        <span class="change__stat change__stat--mute">
            window: {mid.strftime('%Y-%m-%d')} → {end.strftime('%Y-%m-%d')}
            vs {start.strftime('%Y-%m-%d')} → {mid.strftime('%Y-%m-%d')}
        </span>
    </div>"""

    return (
        '<div class="change-card">'
        + bar_html
        + counts_html
        + stats_html
        + "</div>"
    )


# -- Quality: data-completeness matrix --------------------------------


def create_completeness_matrix(df: "pd.DataFrame") -> Optional[str]:
    """Data-completeness heatmap: ISO week × variable.

    Each cell shows the percentage of pixels with a valid (non-null)
    value for that variable in that week. Surfaces missing-band
    regressions (the cormor_2 S2 case where every NDVI cell came
    back null) immediately as an empty row in the heatmap.
    """
    if "date" not in df.columns:
        return None

    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])
    if df.empty:
        return None

    df["iso_week"] = df["date"].dt.strftime("%G-W%V")
    candidate_vars = [
        "NDVI", "NDRE", "NDWI", "MNDWI", "IRECI", "S2REP",
        "VH", "VV", "Ratio", "LST", "Slope",
    ]
    variables = [v for v in candidate_vars if v in df.columns]
    if not variables:
        return None

    weeks = sorted(df["iso_week"].unique())
    if not weeks:
        return None

    z = []
    text = []
    for var in variables:
        z_row = []
        text_row = []
        for wk in weeks:
            slice_ = df.loc[df["iso_week"] == wk, var]
            n = len(slice_)
            if n == 0:
                z_row.append(None)
                text_row.append("no data")
                continue
            non_null = int(slice_.notna().sum())
            pct = non_null / n * 100
            z_row.append(pct)
            text_row.append(f"{non_null}/{n} px<br>{pct:.0f}%")
        z.append(z_row)
        text.append(text_row)

    fig = go.Figure(
        data=go.Heatmap(
            z=z,
            x=weeks,
            y=variables,
            text=text,
            texttemplate="",
            hovertemplate=(
                "<b>%{y} · %{x}</b><br>%{customdata}<extra></extra>"
            ),
            customdata=text,
            colorscale=[
                [0.0, "#2b1014"],
                [0.4, "#5a1f2c"],
                [0.7, "#8a1f33"],
                [1.0, COLORS["secondary"]],
            ],
            zmin=0,
            zmax=100,
            colorbar=dict(
                tickfont=dict(color=COLORS["tick"], size=10),
                title=dict(text="% valid", font=dict(color=COLORS["axis"], size=10)),
                len=0.85,
                thickness=10,
                outlinewidth=0,
            ),
            xgap=2,
            ygap=2,
        )
    )

    layout = _base_layout(
        height=max(180, 28 * len(variables) + 70),
        margin=dict(l=72, r=24, t=12, b=72),
        xaxis=dict(
            tickangle=-45,
            type="category",
            showgrid=False,
            title=None,
        ),
        yaxis=dict(
            type="category",
            autorange="reversed",
            showgrid=False,
            title=None,
        ),
    )
    fig.update_layout(**layout)
    return _to_html(fig)


# -- Variable glossary --------------------------------------------------
# One-liner definitions shown as tooltips and rendered in the Data
# Analysis tab's glossary block. Kept deliberately short so they fit
# in a browser's native title popup without being truncated.
VARIABLE_GLOSSARY: Dict[str, str] = {
    "NDVI": (
        "Normalized Difference Vegetation Index — how vigorous and green the "
        "canopy is. Values run from −1 to 1; bare soil sits near 0 and a "
        "healthy vineyard canopy is typically above 0.6. Computed from "
        "Sentinel-2 as (NIR − Red) / (NIR + Red)."
    ),
    "NDRE": (
        "Normalized Difference Red-Edge Index — chlorophyll and nitrogen "
        "status of the canopy. Behaves like NDVI but keeps responding when "
        "leaves get dense, so it is the better vigor signal late in the "
        "season. Formula: (NIR − RedEdge) / (NIR + RedEdge)."
    ),
    "NDWI": (
        "Normalized Difference Water Index — how much water is in the leaves "
        "(or standing on the soil). Higher values mean wetter, well-hydrated "
        "canopies; low values flag drying vegetation. McFeeters formula: "
        "(Green − NIR) / (Green + NIR)."
    ),
    "MNDWI": (
        "Modified Normalized Difference Water Index — soil and surface "
        "wetness, more reliable than NDWI when there are bare rows or roads. "
        "High values mark waterlogged or recently irrigated patches. Xu "
        "formula: (Green − SWIR1) / (Green + SWIR1)."
    ),
    "IRECI": (
        "Inverted Red-Edge Chlorophyll Index — chlorophyll load, the same "
        "trait nitrogen leaf tests measure. Higher values point to richer, "
        "well-fed canopies; low values can warn of nitrogen deficit. "
        "Formula: (NIR − Red) / (RE1 / RE2) on Sentinel-2 red-edge bands."
    ),
    "S2REP": (
        "Sentinel-2 Red-Edge Position — wavelength (nm) where canopy "
        "reflectance bends in the red-edge. It shifts up as leaves gain "
        "chlorophyll and nitrogen and slides back down at senescence, so it "
        "tracks phenology through the season."
    ),
    "VH": (
        "Sentinel-1 VH radar backscatter (dB) — how much canopy mass is "
        "there, day or night, through clouds. Higher (less negative) values "
        "mean denser leaves and clusters; low values mean sparse or bare "
        "rows. Cross-polarized C-band return."
    ),
    "VV": (
        "Sentinel-1 VV radar backscatter (dB) — surface roughness and soil "
        "moisture under the canopy. Rises with wetter soil and rougher "
        "ground, drops on dry smooth surfaces. Co-polarized C-band return."
    ),
    "Ratio": (
        "VH/VV radar ratio (dB) — canopy structure versus bare ground. Less "
        "negative values mean a fuller, leafier canopy dominating the "
        "signal; more negative values flag sparser rows or exposed soil. "
        "Ratio of Sentinel-1 VH to VV."
    ),
    "LST": (
        "Land Surface Temperature (°C) — how hot the canopy surface is. A "
        "transpiring, well-watered vineyard runs cooler than the air; sharp "
        "rises above air temperature are an early warning of water stress. "
        "From the Landsat 8/9 thermal band."
    ),
    "Slope": (
        "Terrain slope (degrees) — how steep the parcel is. Drives water "
        "runoff, sun exposure, frost pooling and whether mechanization is "
        "feasible. It does not change in time. Derived from the SRTM "
        "digital elevation model."
    ),
}


# -- Backward-compatible re-exports -----------------------------------
# Old template branches still reference `temporal_trends`, `histograms`,
# and `correlation`. We keep the old names pointing at the new renderers
# so no template fix-up is needed if someone reverts the layout.

create_temporal_trends = create_index_trends
create_histograms = create_distributions
create_correlation_matrix = create_correlation
