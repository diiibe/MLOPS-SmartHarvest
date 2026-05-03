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
    /* Mounted as a Leaflet `L.control` at "topleft", below the
       Variables and Week panels. Width matches the other two so
       the column reads cohesive. Padding and inner sizing kept
       tight (head-only `padding-top: 8 px`, header `margin-bottom:
       6 px`) so the four basemap pills + header stack in a
       compact ~110 px tall card — the user wanted the basemap
       footprint as short as possible to leave room for Variables
       and the Week navigator above it. */
    background: #25221C;
    border: 1px solid #3A352A;
    border-radius: 6px;
    box-shadow: 0 4px 14px rgba(0, 0, 0, 0.45);
    padding: 6px 10px 8px;
    font-family: system-ui, -apple-system, "Helvetica Neue", Helvetica, Arial, sans-serif;
    color: #ECE4D2;
    width: 240px;
    box-sizing: border-box;
}
.sh-basemap__head {
    /* `position: relative` + flex-center carries the chevron
       button in `::after`-like absolute positioning without
       knocking the centred eyebrow text off-axis. */
    position: relative;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 9.5px;
    font-weight: 700;
    letter-spacing: 0.22em;
    text-transform: uppercase;
    color: #9C988B;
    padding-bottom: 6px;
    border-bottom: 1px solid #322E25;
    margin-bottom: 6px;
    cursor: pointer;
}
.sh-basemap__row {
    /* 2-column grid keeps the basemap card half the height of a
       4-row vertical stack — necessary now that all three panels
       (Variables / Week / Maps) share the top-left corner. */
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 5px;
}
.sh-basemap__btn {
    appearance: none;
    background: #2C2820;
    color: #9C988B;
    border: 1px solid #322E25;
    border-radius: 4px;
    padding: 5px 6px;
    font-family: inherit;
    font-size: 10.5px;
    font-weight: 600;
    letter-spacing: 0.04em;
    line-height: 1.2;
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

/* Collapsed state — body hidden, head loses its bottom divider
   so the card collapses into a flat eyebrow strip. */
.sh-basemap[data-collapsed="true"] .sh-basemap__row {
    display: none;
}
.sh-basemap[data-collapsed="true"] .sh-basemap__head {
    border-bottom: 0;
    padding-bottom: 0;
    margin-bottom: 0;
}
</style>
"""


# ---------------------------------------------------------------------
# Shared collapse + ochre-border bootstrap. Both the data-map iframe
# (Variables / Week / Maps / Statistics) and the ml-map iframe (Layers
# / Maps) call `panel_collapse_html()` to inject this block once. The
# CSS adds the ochre `border-left` to the LayerControl + Week panels
# (the basemap and Stats legend already include it), wires the small
# chevron button look, and the JS bootstrap finds whichever panels
# exist in the document and makes their head row clickable.
# ---------------------------------------------------------------------

_COLLAPSE_CSS = """
<style>
/* Chevron toggle — small caret pinned to the right edge of the
   eyebrow head; rotates -90° when the panel collapses so the
   affordance reads as "click to expand / collapse". `cubic-bezier
   (0.16, 1, 0.3, 1)` is a gentle ease-out-quint that decelerates
   the rotation naturally without overshoot. */
.sh-collapse {
    appearance: none;
    background: transparent;
    border: 0;
    color: #9C988B;
    cursor: pointer;
    font-size: 11px;
    line-height: 1;
    padding: 2px 4px;
    margin: 0;
    position: absolute;
    right: 0;
    top: 50%;
    transform: translateY(-50%);
    transition:
        transform 320ms cubic-bezier(0.16, 1, 0.3, 1),
        color 150ms cubic-bezier(0.25, 1, 0.5, 1);
}
.sh-collapse:hover { color: #ECE4D2; }
.sh-collapse:focus-visible {
    outline: 1px solid #C09137;
    outline-offset: 2px;
    border-radius: 2px;
}

/* Rotated -90° in the collapsed state. The transform combines the
   vertical centre alignment and the rotation, so both must be
   restated together — `translateY(-50%) rotate(-90deg)` rather
   than just `rotate(-90deg)` (which would lose the centring). */
[data-collapsed="true"] .sh-collapse {
    transform: translateY(-50%) rotate(-90deg);
}

/* --- Animated collapse body ----------------------------------- */
/* Every panel's body uses `max-height + opacity + padding`
   transitions so the collapse is a soft glide rather than a
   pop. The max-height ceilings are chosen larger than any
   realistic content height — overshooting only delays the
   animation by a few ms once the body is already off screen,
   which the eye can't see. */
.sh-basemap__row,
.sh-date-nav .sh-dn-body,
.sh-legend__body,
.leaflet-control-layers-list {
    overflow: hidden;
    transition:
        max-height 320ms cubic-bezier(0.16, 1, 0.3, 1),
        opacity 220ms cubic-bezier(0.25, 1, 0.5, 1),
        margin 320ms cubic-bezier(0.16, 1, 0.3, 1),
        padding 320ms cubic-bezier(0.16, 1, 0.3, 1);
    max-height: 600px;
    opacity: 1;
}

@media (prefers-reduced-motion: reduce) {
    .sh-collapse,
    .sh-basemap__row,
    .sh-date-nav .sh-dn-body,
    .sh-legend__body,
    .leaflet-control-layers-list {
        transition-duration: 0.01ms !important;
    }
}

/* --- Variables / Layers panel (Folium LayerControl) ----------- */
/* Hide the original CSS pseudo-header — JS replaces it with a
   real `<div class="sh-vars-head">` element that supports the
   chevron button and click-to-collapse. */
.leaflet-control-layers-overlays::before {
    content: none !important;
    display: none !important;
}
.sh-vars-head {
    position: relative;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 9.5px;
    font-weight: 700;
    letter-spacing: 0.22em;
    text-transform: uppercase;
    color: #9C988B;
    text-align: center;
    padding-bottom: 6px;
    border-bottom: 1px solid #322E25;
    margin-bottom: 6px;
    cursor: pointer;
    user-select: none;
    /* Margin-bottom is animated alongside the body so it folds
       cleanly when collapsing. */
    transition: margin-bottom 320ms cubic-bezier(0.16, 1, 0.3, 1),
                padding-bottom 320ms cubic-bezier(0.16, 1, 0.3, 1),
                border-bottom-color 320ms cubic-bezier(0.25, 1, 0.5, 1);
}
.leaflet-control-layers-expanded[data-collapsed="true"] .sh-vars-head {
    border-bottom-color: transparent;
    padding-bottom: 0;
    margin-bottom: 0;
}
/* Folium nests the variable labels and the (now-empty) base /
   separator inside the `.leaflet-control-layers-list` wrapper.
   The wrapper holds both the head we injected and the labels —
   collapsing it with max-height: 0 hides the labels but the
   head stays visible because we move the head OUT of the list
   in the JS bootstrap. */
.leaflet-control-layers-expanded[data-collapsed="true"] .leaflet-control-layers-list {
    max-height: 0;
    opacity: 0;
    margin-top: 0;
    margin-bottom: 0;
    padding-top: 0;
    padding-bottom: 0;
}
.leaflet-control-layers-expanded[data-collapsed="true"] {
    overflow: visible !important;
    max-height: none !important;
}

/* --- Week navigator -------------------------------------------- */
.sh-date-nav .sh-dn-label {
    position: relative;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    user-select: none;
    transition: margin-bottom 320ms cubic-bezier(0.16, 1, 0.3, 1),
                padding-bottom 320ms cubic-bezier(0.16, 1, 0.3, 1),
                border-bottom-color 320ms cubic-bezier(0.25, 1, 0.5, 1);
}
.sh-date-nav[data-collapsed="true"] .sh-dn-label {
    border-bottom-color: transparent;
    padding-bottom: 0;
    margin-bottom: 0;
}
.sh-date-nav[data-collapsed="true"] .sh-dn-body {
    max-height: 0;
    opacity: 0;
    margin: 0;
    padding: 0;
}

/* --- Maps / basemap panel -------------------------------------- */
.sh-basemap__head {
    transition: margin-bottom 320ms cubic-bezier(0.16, 1, 0.3, 1),
                padding-bottom 320ms cubic-bezier(0.16, 1, 0.3, 1),
                border-bottom-color 320ms cubic-bezier(0.25, 1, 0.5, 1);
}
.sh-basemap[data-collapsed="true"] .sh-basemap__head {
    border-bottom-color: transparent;
    padding-bottom: 0;
    margin-bottom: 0;
}
.sh-basemap[data-collapsed="true"] .sh-basemap__row {
    max-height: 0;
    opacity: 0;
    margin: 0;
    padding: 0;
}

/* --- Statistics legend ----------------------------------------- */
.sh-legend__head {
    position: relative;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    user-select: none;
}
.sh-legend[data-collapsed="true"] .sh-legend__body {
    max-height: 0;
    opacity: 0;
    margin: 0;
    padding: 0;
}
.sh-legend[data-collapsed="true"] .sh-legend__sub {
    /* Subtitle is in the body wrapper, but covered by the rule
       above. The head padding-bottom collapses for free since
       it's already 4 px and not animated explicitly. */
}
</style>
"""


_COLLAPSE_JS = """
<script>
(function () {
    function makeChevron() {
        var btn = document.createElement("button");
        btn.type = "button";
        btn.className = "sh-collapse";
        btn.setAttribute("aria-label", "Toggle panel");
        btn.innerHTML = "▾"; // ▾
        return btn;
    }

    function wire(panel, head) {
        if (!panel || !head) return;
        if (head.querySelector(".sh-collapse")) return;
        head.appendChild(makeChevron());
        function toggle(e) {
            // Ignore clicks on form controls inside the head so the
            // overlay checkboxes / arrow buttons keep working.
            var t = e.target;
            if (t.tagName === "INPUT" || t.tagName === "A" ||
                (t.tagName === "BUTTON" && !t.classList.contains("sh-collapse"))) {
                return;
            }
            var col = panel.getAttribute("data-collapsed") === "true";
            panel.setAttribute("data-collapsed", col ? "false" : "true");
        }
        head.addEventListener("click", toggle);
    }

    function injectVarsHead() {
        // Folium's LayerControl ships with a `::before` pseudo we
        // already hid via CSS. Replace it with a real `<div>` so the
        // chevron + click handler have a host element. The label
        // depends on the embed: data-map says "Variables", ml-map
        // says "Layers" — we read it from the global the embed sets.
        // The head is injected as a direct child of the panel root
        // (outside `.leaflet-control-layers-list`) so the list
        // wrapper can be collapsed via `max-height: 0` while the
        // head stays visible + clickable for the user to re-expand.
        var label = window.__SH_LAYERS_LABEL || "Variables";
        document.querySelectorAll(".leaflet-control-layers-expanded").forEach(function (panel) {
            if (panel.querySelector(".sh-vars-head")) return;
            var head = document.createElement("div");
            head.className = "sh-vars-head";
            head.textContent = label;
            panel.insertBefore(head, panel.firstChild);
        });
    }

    function init() {
        var anything = document.querySelector(
            ".sh-basemap, .sh-date-nav, .sh-legend, .leaflet-control-layers-expanded"
        );
        if (!anything) {
            setTimeout(init, 100);
            return;
        }

        injectVarsHead();

        document.querySelectorAll(".sh-basemap").forEach(function (panel) {
            wire(panel, panel.querySelector(".sh-basemap__head"));
        });
        document.querySelectorAll(".sh-date-nav").forEach(function (panel) {
            wire(panel, panel.querySelector(".sh-dn-label"));
        });
        document.querySelectorAll(".sh-legend").forEach(function (panel) {
            wire(panel, panel.querySelector(".sh-legend__head"));
        });
        document.querySelectorAll(".leaflet-control-layers-expanded").forEach(function (panel) {
            wire(panel, panel.querySelector(".sh-vars-head"));
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", function () {
            setTimeout(init, 50);
        });
    } else {
        setTimeout(init, 50);
    }
})();
</script>
"""


def panel_collapse_html(layers_label: str = "Variables") -> str:
    """
    Return the CSS + JS block that adds the unified collapse toggle
    + ochre left accent to all floating Leaflet panels in the iframe.

    `layers_label` is the eyebrow text injected on top of Folium's
    `LayerControl` ("Variables" on the data-map, "Layers" on the
    ml-anomaly map).
    """
    label_script = (
        '<script>window.__SH_LAYERS_LABEL = '
        + json.dumps(layers_label)
        + ';</script>'
    )
    return _COLLAPSE_CSS + label_script + _COLLAPSE_JS


_PANEL_HTML = """"""


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

        // Mount the panel as a Leaflet control at bottom-left so it
        // auto-stacks with the Week navigator (also bottom-left).
        // Adding this control AFTER the navigator places it lower in
        // the corner — the basemap pill stack ends up directly above
        // the bottom edge of the iframe.
        var control = L.control({ position: "topleft" });
        control.onAdd = function () {
            var div = L.DomUtil.create("div", "sh-basemap leaflet-bar");
            L.DomEvent.disableClickPropagation(div);
            L.DomEvent.disableScrollPropagation(div);
            div.innerHTML =
                '<div class="sh-basemap__head">Basemap</div>' +
                '<div class="sh-basemap__row"></div>';
            return div;
        };
        control.addTo(map);

        var rootEl = control.getContainer();
        var row = rootEl.querySelector(".sh-basemap__row");
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
    # Satellite leads so the dashboard iframe boots on its preferred
    # default (Mapbox `satellite-streets-v12`). Order also drives
    # the visual stack of buttons inside the panel — Satellite at
    # the top makes the active pill the easiest to click first.
    {"id": "satellite", "label": "Satellite", "styleId": "satellite-streets-v12"},
    {"id": "dark",      "label": "Dark",      "styleId": "dark-v11"},
    {"id": "outdoors",  "label": "Outdoors",  "styleId": "outdoors-v12"},
    {"id": "light",     "label": "Light",     "styleId": "light-v11"},
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
