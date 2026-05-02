"""
Inject hover tooltips into the Folium layer-control labels.

Each Leaflet `L.control.layers` checkbox / radio is rendered as
`<label><input ...><span> Label text</span></label>`. The user wants
hover descriptions on those rows so they understand what each
overlay or basemap actually represents. We do that without
JavaScript libraries:

  * Server-side, build a dict mapping each label string to a short
    explanation. For variable overlays we resolve the column code
    from the human-readable label via `schema.COLUMN_LABELS` and
    pull the canonical text from `tools.charts.VARIABLE_GLOSSARY`.
    For basemaps we have a small hand-curated list. The ML map's
    own layer names ("Normal Clusters", "Anomalous Clusters", …)
    are wired up too.
  * Client-side, a tiny script walks the layer-control labels,
    looks up the tooltip for each row's text, and attaches a
    `data-tooltip` attribute. A `::after` pseudo-element renders
    the bubble on hover or keyboard focus.
"""

from __future__ import annotations

import json
from typing import Dict, Iterable

import schema
from tools.charts import VARIABLE_GLOSSARY


_BASEMAP_TOOLTIPS: Dict[str, str] = {
    "Dark": (
        "Mapbox dark-v11. Low-luminance basemap; lets coloured "
        "overlays carry the visual weight without competing with "
        "ground detail."
    ),
    "Satellite": (
        "Mapbox satellite-streets-v12. Aerial imagery with a thin "
        "label layer; closest to the original Esri default."
    ),
    "Outdoors": (
        "Mapbox outdoors-v12. Topographic style with hillshade and "
        "relief — useful when slope context matters for the analysis."
    ),
    "Light": (
        "Mapbox light-v11. Light minimalist basemap; high contrast "
        "for vector overlays and printable screenshots."
    ),
    "Esri Satellite": (
        "Esri World Imagery. Aerial imagery fallback — used when no "
        "Mapbox token is configured."
    ),
}


_ML_TOOLTIPS: Dict[str, str] = {
    "Normal Clusters": (
        "HDBSCAN clusters with outlier_score below the 95th "
        "percentile threshold for this week. These pixels behave "
        "like the dominant modes of the feature distribution."
    ),
    "Anomalous Clusters": (
        "HDBSCAN clusters whose mean outlier_score sits above the "
        "95th percentile. Likely vigour anomalies, structural loss, "
        "or pruning events worth field-checking."
    ),
    "Outlier Heatmap": (
        "Per-pixel outlier_score from HDBSCAN, rendered as a "
        "weighted heatmap. Bright clusters indicate dense regions of "
        "anomalous behaviour rather than isolated pixels."
    ),
}


def build_overlay_tooltips() -> Dict[str, str]:
    """
    Return label → tooltip for the Interactive Map's variable
    overlays. The label is the human-readable text Folium shows in
    the layer control (e.g. "Vegetation Index (NDVI)"); we resolve
    it back to the column code so the same `VARIABLE_GLOSSARY` the
    Data Analysis tab uses powers the tooltip text.
    """
    out: Dict[str, str] = {}
    for col, label in schema.COLUMN_LABELS.items():
        text = VARIABLE_GLOSSARY.get(col)
        if text:
            out[label] = text
    # ML cluster overlay: parameterised name like "ML Clusters
    # (2025-W45)"; the JS does a prefix match for unknown labels so
    # we register the bare prefix here.
    out["ML Clusters"] = (
        "HDBSCAN clusters from the latest weekly anomaly run. "
        "Markers are coloured by cluster id and sized by pixel "
        "count. Click a marker for the detailed track sidebar."
    )
    return out


_TOOLTIP_CSS = """
<style>
.leaflet-control-layers label[data-tooltip] {
    position: relative;
    cursor: help;
}
.leaflet-control-layers label[data-tooltip]::after {
    content: attr(data-tooltip);
    position: absolute;
    top: -8px;
    left: calc(100% + 10px);
    transform: translateY(-100%) translateY(8px);
    width: max-content;
    max-width: 300px;
    padding: 8px 12px;
    background: #121212;
    color: #d6d6d6;
    border: 1px solid #2e2e2e;
    border-radius: 6px;
    font-family: system-ui, -apple-system, "Helvetica Neue", Helvetica, Arial, sans-serif;
    font-size: 11.5px;
    line-height: 1.5;
    font-weight: 400;
    text-transform: none;
    letter-spacing: 0;
    opacity: 0;
    visibility: hidden;
    pointer-events: none;
    transition:
        opacity 120ms cubic-bezier(0.25, 1, 0.5, 1),
        visibility 120ms;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.45);
    z-index: 1100;
}
.leaflet-control-layers label[data-tooltip]:hover::after,
.leaflet-control-layers label[data-tooltip]:focus-within::after {
    opacity: 1;
    visibility: visible;
}
@media (prefers-reduced-motion: reduce) {
    .leaflet-control-layers label[data-tooltip]::after { transition-duration: 0.01ms; }
}
</style>
"""


_TOOLTIP_JS_TEMPLATE = """
<script>
window.__SH_LAYER_TOOLTIPS = true;
(function () {{
    var tooltips = {tooltips};
    var basemapTooltips = {basemap_tooltips};
    var mlTooltips = {ml_tooltips};

    function lookup(text) {{
        if (!text) return null;
        var trimmed = text.trim();
        if (tooltips[trimmed]) return tooltips[trimmed];
        if (basemapTooltips[trimmed]) return basemapTooltips[trimmed];
        if (mlTooltips[trimmed]) return mlTooltips[trimmed];
        // Variable overlays are sometimes named "Layer (CODE)" — try
        // matching just the prefix before the parenthesis.
        var paren = trimmed.indexOf("(");
        if (paren > 0) {{
            var prefix = trimmed.substring(0, paren).trim();
            if (tooltips[prefix]) return tooltips[prefix];
        }}
        // ML Clusters layer name is "ML Clusters (2025-Wxx)" — match
        // the static prefix.
        if (trimmed.indexOf("ML Clusters") === 0) return tooltips["ML Clusters"] || null;
        return null;
    }}

    function decorate() {{
        var labels = document.querySelectorAll(".leaflet-control-layers label");
        labels.forEach(function (lbl) {{
            // Layer-control label markup is `<label><input ...><span> Name</span></label>`
            // (folium variant) or `<label><input ...> Name</label>` (vanilla
            // leaflet). Either way we want the trimmed text content.
            var raw = (lbl.textContent || "").trim();
            var tip = lookup(raw);
            if (tip) {{
                lbl.setAttribute("data-tooltip", tip);
            }} else {{
                lbl.removeAttribute("data-tooltip");
            }}
        }});
    }}

    // Run once after the layer control mounts (Folium emits its
    // script at the bottom of <body>). The control re-renders when
    // overlays come and go, so observe its container too.
    function init() {{
        decorate();
        var control = document.querySelector(".leaflet-control-layers");
        if (!control) {{
            setTimeout(init, 100);
            return;
        }}
        var observer = new MutationObserver(decorate);
        observer.observe(control, {{ childList: true, subtree: true }});
    }}

    if (document.readyState === "loading") {{
        document.addEventListener("DOMContentLoaded", init);
    }} else {{
        init();
    }}
}})();
</script>
"""


def layer_tooltip_payload(extra: Iterable[Dict[str, str]] = ()) -> str:
    """
    Compose the CSS + JS block to inject into a Folium HTML so the
    layer-control labels carry hover tooltips. `extra` is a list of
    extra label→tooltip dicts to merge on top of the variable +
    basemap defaults — useful for the ML map's cluster layer names.
    """
    overlay = build_overlay_tooltips()
    for d in extra or ():
        overlay.update(d)
    return _TOOLTIP_CSS + _TOOLTIP_JS_TEMPLATE.format(
        tooltips=json.dumps(overlay),
        basemap_tooltips=json.dumps(_BASEMAP_TOOLTIPS),
        ml_tooltips=json.dumps(_ML_TOOLTIPS),
    )
