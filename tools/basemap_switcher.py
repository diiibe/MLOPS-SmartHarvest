"""
Basemap switcher injection for the Folium maps embedded in the
dashboard iframes.

Both the "Interactive Map" tab (`tools/visualize_data_map.py`) and the
"Anomaly Detection" tab (`tools/visualize_ml_map.py`) want the same
panel of four Mapbox styles — Outdoors / Light / Satellite / Dark —
that the index page uses, plus the same hover and active-pill
treatment from the landslide-app design language. Folium does not
ship a control like that, so we render it ourselves: a small CSS
block + a DOM panel + a JS bootstrap that finds the map global
(`map_<hex>` declared by Folium at the bottom of its HTML) and swaps
the active raster layer on click.

When `mapbox_token` is empty the function returns `None`; the
caller falls back to whatever default tile layer it would have
shipped (usually `Esri.WorldImagery`) and no panel appears.
"""

from __future__ import annotations

import json
from typing import Optional


# Surface tokens here mirror `static/css/tokens.css` so the switcher
# inside the iframe matches the parent dashboard chrome regardless of
# the active theme. The iframe doesn't share `<html>`'s `data-theme`,
# so we hard-code the dark values that are SmartHarvest's default.
_PANEL_CSS = """
<style>
.sh-basemap {
    position: absolute;
    top: 12px;
    right: 12px;
    z-index: 1000;
    background: #25221C;
    border: 1px solid #3A352A;
    border-radius: 6px;
    box-shadow: 0 4px 14px rgba(0, 0, 0, 0.45);
    padding: 10px 12px 12px;
    font-family: system-ui, -apple-system, "Helvetica Neue", Helvetica, Arial, sans-serif;
    color: #ECE4D2;
    min-width: 220px;
}
.sh-basemap__head {
    font-size: 9.5px;
    font-weight: 700;
    letter-spacing: 0.22em;
    text-transform: uppercase;
    text-align: center;
    color: #9C988B;
    padding-bottom: 8px;
    border-bottom: 1px solid #322E25;
    margin-bottom: 8px;
}
.sh-basemap__row {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 6px;
}
.sh-basemap__btn {
    appearance: none;
    background: #2C2820;
    color: #9C988B;
    border: 1px solid #322E25;
    border-radius: 4px;
    padding: 6px 8px;
    font-family: inherit;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.04em;
    cursor: pointer;
    transition:
        background 150ms cubic-bezier(0.25, 1, 0.5, 1),
        color 150ms cubic-bezier(0.25, 1, 0.5, 1),
        border-color 150ms cubic-bezier(0.25, 1, 0.5, 1),
        transform 200ms cubic-bezier(0.16, 1, 0.3, 1);
}
.sh-basemap__btn:hover {
    color: #ECE4D2;
    border-color: #C09137;
    transform: translateY(-1px);
}
.sh-basemap__btn:active { transform: translateY(0) scale(0.96); }
.sh-basemap__btn[data-active="true"] {
    color: #E2B95C;
    background: #251F12;
    border-color: #C09137;
}
@media (prefers-reduced-motion: reduce) {
    .sh-basemap__btn { transition-duration: 0.01ms; }
}
</style>
"""


_PANEL_HTML = """
<div class="sh-basemap" id="sh-basemap">
    <div class="sh-basemap__head">Basemap</div>
    <div class="sh-basemap__row" id="sh-basemap-row"></div>
</div>
"""


# Bootstrap script. Reads the embedded `__SH_BASEMAP_CONFIG` (token +
# styles list), waits for the Folium-generated `map_<hex>` global to
# exist, mounts the four raster layers and wires the panel buttons.
_PANEL_JS = """
<script>
(function () {
    function findLeafletMap() {
        for (var k in window) {
            if (k.indexOf("map_") === 0 && window[k] instanceof L.Map) {
                return window[k];
            }
        }
        return null;
    }

    function buildLayer(token, styleId) {
        return L.tileLayer(
            "https://api.mapbox.com/styles/v1/mapbox/" + styleId +
                "/tiles/512/{z}/{x}/{y}@2x?access_token=" + token,
            {
                tileSize: 512,
                zoomOffset: -1,
                attribution:
                    "&copy; <a href='https://www.mapbox.com/about/maps/'>Mapbox</a> " +
                    "&copy; <a href='https://www.openstreetmap.org/about/'>OSM</a>",
                maxZoom: 22
            }
        );
    }

    function init() {
        var map = findLeafletMap();
        if (!map) {
            setTimeout(init, 80);
            return;
        }
        var cfg = window.__SH_BASEMAP_CONFIG;
        if (!cfg || !cfg.token) return;

        // Folium ships a default tile layer; if it's still on the map
        // when we arrive, remove it so the new active basemap is the
        // single source of truth.
        var defaultLayer = null;
        map.eachLayer(function (layer) {
            if (layer instanceof L.TileLayer && !defaultLayer) {
                defaultLayer = layer;
            }
        });

        var layers = {};
        cfg.styles.forEach(function (s) {
            layers[s.id] = buildLayer(cfg.token, s.styleId);
        });

        var defaultId = cfg.default || cfg.styles[0].id;
        if (defaultLayer) map.removeLayer(defaultLayer);
        layers[defaultId].addTo(map);
        var active = defaultId;

        var row = document.getElementById("sh-basemap-row");
        if (!row) return;
        cfg.styles.forEach(function (s) {
            var btn = document.createElement("button");
            btn.type = "button";
            btn.className = "sh-basemap__btn";
            btn.textContent = s.label;
            btn.dataset.id = s.id;
            btn.dataset.active = s.id === active ? "true" : "false";
            btn.addEventListener("click", function () {
                if (s.id === active) return;
                map.removeLayer(layers[active]);
                layers[s.id].addTo(map);
                active = s.id;
                row.querySelectorAll("button").forEach(function (b) {
                    b.dataset.active = b.dataset.id === active ? "true" : "false";
                });
            });
            row.appendChild(btn);
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
</script>
"""


_DEFAULT_STYLES = [
    {"id": "outdoors",  "label": "Outdoors",  "styleId": "outdoors-v12"},
    {"id": "light",     "label": "Light",     "styleId": "light-v11"},
    {"id": "satellite", "label": "Satellite", "styleId": "satellite-streets-v12"},
    {"id": "dark",      "label": "Dark",      "styleId": "dark-v11"},
]


# Sentinel string the dashboard's `/map/<project>` self-heal grep
# uses to decide whether a cached HTML predates the basemap-switcher
# feature. Bumped whenever the embed changes shape.
SENTINEL = "__SH_BASEMAP_CONFIG"


def basemap_switcher_html(
    mapbox_token: Optional[str], default: str = "satellite"
) -> Optional[str]:
    """
    Return the CSS + panel + script block to drop into a Folium map
    HTML, or `None` when no Mapbox token is configured (so the
    caller can ship its hard-coded fallback tile layer untouched).
    """
    if not mapbox_token:
        return None
    config = {
        "token": mapbox_token,
        "styles": _DEFAULT_STYLES,
        "default": default,
    }
    config_block = (
        "<script>window.__SH_BASEMAP_CONFIG = "
        + json.dumps(config)
        + ";</script>"
    )
    return _PANEL_CSS + _PANEL_HTML + config_block + _PANEL_JS
