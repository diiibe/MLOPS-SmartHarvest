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
    """Return a layout dict matching the page's dark-muted design."""
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
        xaxis=dict(
            gridcolor=COLORS["grid"],
            linecolor=COLORS["grid"],
            tickcolor=COLORS["grid"],
            zerolinecolor=COLORS["grid"],
            tickfont=dict(color=COLORS["tick"], size=11),
            title_font=dict(color=COLORS["axis"], size=11),
        ),
        yaxis=dict(
            gridcolor=COLORS["grid"],
            linecolor=COLORS["grid"],
            tickcolor=COLORS["grid"],
            zerolinecolor=COLORS["grid"],
            tickfont=dict(color=COLORS["tick"], size=11),
            title_font=dict(color=COLORS["axis"], size=11),
        ),
        showlegend=False,
    )
    layout.update(overrides)
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
                    symbol="line-ns",
                    size=22,
                    line=dict(width=2, color=SENSOR_COLOR[sensor]),
                ),
                name=sensor,
                hovertemplate=f"<b>{sensor}</b> — %{{x|%Y-%m-%d}}<extra></extra>",
            )
        )

    layout = _base_layout(
        height=220,
        yaxis=dict(
            tickmode="array",
            tickvals=list(range(len(order))),
            ticktext=order,
            autorange="reversed",
            gridcolor=COLORS["canvas"],
            linecolor=COLORS["grid"],
            tickfont=dict(color=COLORS["tick"], size=11),
        ),
        xaxis=dict(
            gridcolor=COLORS["grid"],
            linecolor=COLORS["grid"],
            tickfont=dict(color=COLORS["tick"], size=11),
            title=None,
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


# -- Backward-compatible re-exports -----------------------------------
# Old template branches still reference `temporal_trends`, `histograms`,
# and `correlation`. We keep the old names pointing at the new renderers
# so no template fix-up is needed if someone reverts the layout.

create_temporal_trends = create_index_trends
create_histograms = create_distributions
create_correlation_matrix = create_correlation
