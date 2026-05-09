"""
Map visualization for the temporal dataset.

Reads the SmartHarvest temporal CSV and creates a Folium map
showing the latest acquisition date's statistics as layers.
Supports date filtering via the `selected_date` parameter.
"""

import json
import os
from typing import Optional

import branca.colormap as cm
import folium
import numpy as np
import pandas as pd
from branca.element import MacroElement
from jinja2 import Template
from folium.plugins import HeatMap
from matplotlib.colors import to_hex

import schema


def _resolve_to_hex(colors):
    """
    Normalise a list of branca/CSS colour specs to `#rrggbb` strings.

    The per-variable `COLUMN_COLORS` table uses named CSS colours (e.g.
    ``["red", "yellow", "green"]``) because branca accepts them as-is.
    The date-navigator's client-side colour interpolation only knows
    how to parse hex, so we convert here before embedding.
    """
    return [to_hex(c) for c in colors]


def _parse_coords(geo_str):
    """Parse .geo GeoJSON string to [lon, lat]."""
    try:
        data = json.loads(geo_str) if isinstance(geo_str, str) else geo_str
        return data["coordinates"]  # [lon, lat]
    except Exception:
        return [0, 0]


# Single-active basemap setup for the Folium maps. Registering the
# tiles as `overlay=False` makes Folium's LayerControl render them as
# a radio group at the top of the panel — exactly the UX the user
# wanted: pick one, the others come off automatically. Falls back to
# Esri-only when there is no Mapbox token.
_MAPBOX_BASEMAPS = [
    # Order is significant — Folium auto-adds the first registered
    # tile layer to the map, so it becomes the default basemap.
    # Satellite leads so the iframe paints once on the chosen
    # default and the basemap switcher's `default="satellite"`
    # config doesn't have to swap layers right after first paint.
    ("Satellite", "satellite-streets-v12"),
    ("Dark",      "dark-v11"),
    ("Outdoors",  "outdoors-v12"),
    ("Light",     "light-v11"),
]

_MAPBOX_ATTR = (
    '&copy; <a href="https://www.mapbox.com/about/maps/">Mapbox</a> '
    '&copy; <a href="https://www.openstreetmap.org/about/">OSM</a>'
)


def _add_basemap_layers(m: "folium.Map", mapbox_token: Optional[str]) -> None:
    """
    Register a small set of base layers (radio-grouped) on `m`.

    Order is significant — Folium adds the first layer to the map by
    default, so the topmost entry below is what the user sees on
    first paint. Mapbox layers are skipped when no token is present.
    """
    if mapbox_token:
        for name, style_id in _MAPBOX_BASEMAPS:
            url = (
                "https://api.mapbox.com/styles/v1/mapbox/" + style_id +
                "/tiles/512/{z}/{x}/{y}@2x?access_token=" + mapbox_token
            )
            folium.TileLayer(
                tiles=url,
                name=name,
                attr=_MAPBOX_ATTR,
                # `control=False` keeps the basemap OUT of Folium's
                # layer panel — the user wants Map and Variables in
                # two distinct overlays. Basemap selection is rendered
                # by the standalone floating panel injected below.
                control=False,
                overlay=False,
                max_zoom=22,
                tile_size=512,
                zoom_offset=-1,
            ).add_to(m)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        name="Esri Satellite",
        attr="Tiles &copy; Esri",
        control=False,  # basemap lives in the standalone panel
        overlay=False,
        max_zoom=19,
    ).add_to(m)


# Shared SmartHarvest dashboard chrome injected into both the
# Interactive Map and the Anomaly Detection iframe so the popups +
# layer control match the parent dashboard's dark/ochre palette.
# Colours are hard-coded on purpose: the iframe doesn't share
# `data-theme` with the host document, so importing tokens.css would
# only paint half of the surface.
_SH_POPUP_CSS = """
<style>
    /* --- Leaflet popup chrome ----------------------------------- */
    .leaflet-popup-content-wrapper {
        background: #25221C !important;
        color: #ECE4D2 !important;
        border: 1px solid #3A352A !important;
        border-left: 3px solid #C09137 !important;
        border-radius: 6px !important;
        box-shadow: 0 6px 18px rgba(0,0,0,0.45) !important;
        padding: 0 !important;
        max-width: 260px !important;
    }
    .leaflet-popup-content {
        margin: 0 !important;
        padding: 12px 14px !important;
        font-family: system-ui, -apple-system, "Helvetica Neue", Helvetica, Arial, sans-serif !important;
        line-height: 1.4 !important;
    }
    .leaflet-popup-tip {
        background: #25221C !important;
        border: none !important;
        box-shadow: 0 2px 6px rgba(0,0,0,0.45) !important;
    }
    .leaflet-popup-close-button {
        color: #9C988B !important;
        padding: 6px 8px 0 0 !important;
    }
    .leaflet-popup-close-button:hover {
        color: #ECE4D2 !important;
    }

    /* --- Card markup -------------------------------------------- */
    .sh-popup { color: #ECE4D2; }
    .sh-popup__title {
        font-size: 13px;
        font-weight: 700;
        color: #ECE4D2;
        margin: 0 0 2px 0;
    }
    .sh-popup__sub {
        font-size: 10px;
        color: #9C988B;
        text-transform: uppercase;
        letter-spacing: 0.18em;
        margin: 0 0 8px 0;
        padding-bottom: 6px;
        border-bottom: 1px solid #322E25;
    }
    .sh-popup__kv {
        width: 100%;
        border-collapse: collapse;
        font-size: 11.5px;
        font-family: system-ui, -apple-system, "Helvetica Neue", Helvetica, Arial, sans-serif;
    }
    .sh-popup__kv td {
        padding: 3px 0;
        border-top: 1px solid #322E25;
    }
    .sh-popup__kv tr:first-child td {
        border-top: none;
    }
    .sh-popup__kv td:first-child {
        color: #9C988B;
        font-weight: 500;
        text-align: left;
    }
    .sh-popup__kv td:last-child {
        color: #ECE4D2;
        font-weight: 600;
        text-align: right;
        font-variant-numeric: tabular-nums;
    }
    .sh-badge {
        display: inline-block;
        padding: 1px 7px;
        border-radius: 3px;
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 0.1em;
        text-transform: uppercase;
    }
    .sh-badge--new {
        background: #251F12;
        color: #E2B95C;
        border: 1px solid #3a2f18;
    }
    .sh-badge--continued {
        background: #1A1F27;
        color: #9DBADD;
        border: 1px solid #243140;
    }
    .sh-badge--unknown {
        background: #2A2620;
        color: #9C988B;
        border: 1px solid #3A352A;
    }

    /* Map and Variables now live in two separate floating panels —
       the basemap section title that used to sit in the same
       layer-control was removed. The Folium control still draws an
       internal separator if there are base layers; we hide it. */
    .leaflet-control-layers-separator {
        display: none !important;
    }
    /* Kill the default hover tint + cursor on overlay rows so the
       layer control reads as a quiet panel, not a clickable link
       list. The radio rows still use the browser default. */
    .leaflet-control-layers-overlays label,
    .leaflet-control-layers-overlays label:hover {
        cursor: default !important;
        background: transparent !important;
    }
</style>
"""


# Vanilla JS that injects "MAP" / "VARIABLES" titles into the existing
# Folium layer control by locating the separator the control already
# emits between basemaps and overlays. Also clears any leftover
# `data-tooltip` attribute on overlay labels so the help-cursor
# tooltip from earlier iterations doesn't fire. The function is
# idempotent (guarded by a data flag) and survives layer-control
# rebuilds via a MutationObserver.
_SH_LAYER_TITLES_JS = """
<script>
window.__SH_POPUP_CARDS = true; window.__SH_WEEKLY_NAV = true; window.__SH_WEEKLY_LEGEND = true; window.__SH_LEGEND_ADAPT = true; window.__SH_LEGEND_BULK = true; window.__SH_MAXPX_FIX = true; window.__SH_CACHE_FAST = true;
(function () {
    function decorate(panel) {
        if (!panel || panel.dataset.shDecorated === '1') return;
        var basesList = panel.querySelector('.leaflet-control-layers-base');
        var overlaysList = panel.querySelector('.leaflet-control-layers-overlays');
        var separator = panel.querySelector('.leaflet-control-layers-separator');
        if (!basesList && !overlaysList) return;

        if (basesList && !panel.querySelector('.sh-layer-section-title[data-section="map"]')) {
            var mapTitle = document.createElement('div');
            mapTitle.className = 'sh-layer-section-title';
            mapTitle.dataset.section = 'map';
            mapTitle.textContent = 'Map';
            basesList.parentNode.insertBefore(mapTitle, basesList);
        }
        if (overlaysList && !panel.querySelector('.sh-layer-section-title[data-section="variables"]')) {
            var varsTitle = document.createElement('div');
            varsTitle.className = 'sh-layer-section-title';
            varsTitle.dataset.section = 'variables';
            varsTitle.textContent = 'Variables';
            var anchor = separator && separator.parentNode === overlaysList.parentNode
                ? separator.nextSibling
                : overlaysList;
            overlaysList.parentNode.insertBefore(varsTitle, overlaysList);
        }
        // Strip any stale data-tooltip attribute and force a default
        // cursor on overlay rows.
        if (overlaysList) {
            var labels = overlaysList.querySelectorAll('label');
            for (var i = 0; i < labels.length; i++) {
                labels[i].removeAttribute('data-tooltip');
                labels[i].style.cursor = 'default';
            }
        }
        panel.dataset.shDecorated = '1';
    }

    function tick() {
        var panels = document.querySelectorAll('.leaflet-control-layers');
        for (var i = 0; i < panels.length; i++) decorate(panels[i]);
    }

    function init() {
        tick();
        // The layer control is rebuilt whenever Folium re-runs add_to
        // (e.g. on overlay toggle in some plugins) so observe the
        // body subtree and re-decorate on demand.
        var obs = new MutationObserver(tick);
        obs.observe(document.body, { childList: true, subtree: true });
        // Belt-and-braces retry in case the control mounts after the
        // observer attaches (Folium initialises async on slow
        // devices).
        setTimeout(tick, 200);
        setTimeout(tick, 800);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
</script>
"""


# Client-side date navigator injected into the map HTML.
#
# Contract with the surrounding Python code:
#   * `window.__SH_MAP_CONFIG.variables[label]` holds the timeline metadata
#     for one overlay. `fg_name` is the folium-generated global JS variable
#     of the matching Leaflet feature group.
#   * The global Leaflet map object is the only one on the page; Folium
#     always names it `map_<hex>`. We find it by iterating `window` keys.
#
# Behaviour:
#   * `overlayadd` makes the toggled variable the "active" one.
#   * Arrows page through `config.variables[active].dates`; the selected
#     frame is fetched from /api/variable_frame/<project>/<col>/<date>
#     and re-rendered inside the feature group by `clearLayers()` + new
#     CircleMarkers.
#   * `overlayremove` falls back to the most recently added overlay still
#     visible (if any), so the date label stays in sync.
#   * Nothing is persisted across page reloads — that's why a refresh
#     returns every variable to its latest acquisition.
_DATE_NAV_JS = """
(function () {
    function findLeafletMap() {
        for (var k in window) {
            if (k.indexOf("map_") === 0 && window[k] instanceof L.Map) {
                return window[k];
            }
        }
        return null;
    }

    function init() {
        var map = findLeafletMap();
        if (!map) {
            setTimeout(init, 80);
            return;
        }
        var cfg = window.__SH_MAP_CONFIG;
        if (!cfg || !cfg.variables) return;

        var variables = cfg.variables;
        // `currentWeek[label]` = ISO week id currently displayed for
        // that variable (e.g. "2025-W45"). Seeded with the variable's
        // latest week, which is also what the Python initial render
        // averaged for the default-on layer.
        var currentWeek = {};
        // `currentRange[label]` = human-readable date range covered
        // by the currently-loaded frame, populated after the first
        // fetch for that variable. Used in the popups so a click on
        // a pixel shows "2025-11-03 → 2025-11-09" rather than the
        // bare week id.
        var currentRange = {};
        Object.keys(variables).forEach(function (k) {
            currentWeek[k] = variables[k].latest_week;
        });

        // Stack of active overlay labels, most-recent-on-top. Used to
        // resolve "the last selected one" for the date display. Folium
        // renders a `show=True` overlay before this script runs so
        // `overlayadd` won't fire for it — prime the stack by walking
        // the map's current layers instead.
        var activeStack = [];
        // `loadedOnce[label]` becomes true the first time we have
        // populated that layer's FeatureGroup with markers. Layers
        // that start hidden lazy-load on first overlayadd; the
        // default-on layer (e.g. NDVI) is bootstrapped right after
        // the map mounts so the user never sees an empty canvas.
        var loadedOnce = {};
        map.eachLayer(function (layer) {
            Object.keys(variables).forEach(function (label) {
                if (window[variables[label].fg_name] === layer) {
                    activeStack.push(label);
                }
            });
        });

        // Build the DOM control.
        var control = L.control({ position: "topleft" });
        control.onAdd = function () {
            var div = L.DomUtil.create("div", "sh-date-nav leaflet-bar");
            L.DomEvent.disableClickPropagation(div);
            L.DomEvent.disableScrollPropagation(div);
            // Body is wrapped in `.sh-dn-body` so the collapse
            // animation can target a single element with
            // `max-height: 0` instead of N siblings.
            div.innerHTML =
                '<div class="sh-dn-label">Week</div>' +
                '<div class="sh-dn-body">' +
                  '<div class="sh-dn-row">' +
                  '  <button class="sh-dn-btn sh-dn-prev" title="Previous week">&#9664;</button>' +
                  '  <div class="sh-dn-date">—</div>' +
                  '  <button class="sh-dn-btn sh-dn-next" title="Next week">&#9654;</button>' +
                  '</div>' +
                  '<div class="sh-dn-range"></div>' +
                  '<div class="sh-dn-var"></div>' +
                  '<div class="sh-dn-count"></div>' +
                  '<div class="sh-dn-cloud"></div>' +
                '</div>';
            return div;
        };
        control.addTo(map);

        var rootEl = control.getContainer();
        var dateEl = rootEl.querySelector(".sh-dn-date");
        var rangeEl = rootEl.querySelector(".sh-dn-range");
        var varEl = rootEl.querySelector(".sh-dn-var");
        var countEl = rootEl.querySelector(".sh-dn-count");
        var cloudEl = rootEl.querySelector(".sh-dn-cloud");
        var prevBtn = rootEl.querySelector(".sh-dn-prev");
        var nextBtn = rootEl.querySelector(".sh-dn-next");

        // `currentCount[label]` tracks the number of pixels rendered
        // for the active frame of each variable. Priming with the
        // Python-side initial count means the widget shows the right
        // number immediately on load, before any fetch happens.
        var currentCount = {};
        Object.keys(variables).forEach(function (k) {
            currentCount[k] = variables[k].initial_count;
        });

        function activeLabel() {
            return activeStack.length ? activeStack[activeStack.length - 1] : null;
        }

        function render() {
            var label = activeLabel();
            if (!label) {
                dateEl.textContent = "—";
                rangeEl.textContent = "";
                varEl.textContent = "No layer active";
                varEl.classList.add("sh-dn-empty");
                countEl.textContent = "";
                cloudEl.textContent = "";
                prevBtn.disabled = true;
                nextBtn.disabled = true;
                return;
            }
            varEl.classList.remove("sh-dn-empty");
            var meta = variables[label];
            var week = currentWeek[label];
            var idx = meta.weeks.indexOf(week);
            dateEl.textContent = week || "—";
            rangeEl.textContent = currentRange[label] || "";
            varEl.textContent = label;
            var n = currentCount[label];
            countEl.textContent = (n == null)
                ? ""
                : n.toLocaleString() + " pixel" + (n === 1 ? "" : "s");
            // Optical / thermal sensors: estimate cloud coverage from
            // how much of the variable's peak weekly footprint is
            // missing on this frame. Radar / topography are not
            // cloud-affected so we just report coverage without the
            // "cloud" framing.
            if (n == null || !meta.max_pixels) {
                cloudEl.textContent = "";
            } else {
                var coveragePct = Math.round((n / meta.max_pixels) * 100);
                var lostPct = Math.max(0, 100 - coveragePct);
                if (meta.cloud_sensitive) {
                    if (lostPct <= 2) {
                        cloudEl.textContent = "clear — ~" + coveragePct + "% of ROI";
                    } else {
                        cloudEl.textContent =
                            "~" + lostPct + "% cloud-masked · " +
                            coveragePct + "% of ROI";
                    }
                } else {
                    cloudEl.textContent = coveragePct + "% of ROI observed";
                }
            }
            prevBtn.disabled = idx <= 0;
            nextBtn.disabled = idx === -1 || idx >= meta.weeks.length - 1;
        }

        function colorFor(val, meta) {
            // Linear interpolation between meta.colors stops.
            if (val == null || isNaN(val)) return "#888";
            var t = (val - meta.vmin) / (meta.vmax - meta.vmin);
            t = Math.max(0, Math.min(1, t));
            var stops = meta.colors;
            if (stops.length === 1) return stops[0];
            var pos = t * (stops.length - 1);
            var i = Math.floor(pos);
            var f = pos - i;
            if (i >= stops.length - 1) return stops[stops.length - 1];
            return mixHex(stops[i], stops[i + 1], f);
        }

        function toRgb(hex) {
            // Accept #rgb, #rrggbb, or named — caller passes hex strings
            // because Python side produces them from branca colormaps.
            hex = hex.replace("#", "");
            if (hex.length === 3) {
                hex = hex.split("").map(function (c) { return c + c; }).join("");
            }
            return [
                parseInt(hex.substr(0, 2), 16),
                parseInt(hex.substr(2, 2), 16),
                parseInt(hex.substr(4, 2), 16),
            ];
        }

        function mixHex(a, b, f) {
            var ra = toRgb(a);
            var rb = toRgb(b);
            var r = Math.round(ra[0] + (rb[0] - ra[0]) * f);
            var g = Math.round(ra[1] + (rb[1] - ra[1]) * f);
            var bl = Math.round(ra[2] + (rb[2] - ra[2]) * f);
            return "#" + [r, g, bl].map(function (v) {
                return ("0" + v.toString(16)).slice(-2);
            }).join("");
        }

        var inflight = 0;
        var statsInflight = 0;

        // Pre-build a lookup from `col` to the matching variable label
        // so the bulk stats endpoint (`/api/week_stats/...`) can update
        // each `meta` entry by column code in O(1).
        var varByCol = {};
        Object.keys(variables).forEach(function (label) {
            varByCol[variables[label].col] = label;
        });

        // Pulls vmin / vmax for every variable in one round trip and
        // applies them to (a) `meta.vmin` / `meta.vmax`, so the next
        // colour pass uses the right scale, and (b) the legend row's
        // text labels, so the user reads the bounds for the active
        // week even on variables they have never toggled on.
        function refreshAllLegendStats(week) {
            var ticket = ++statsInflight;
            var url = "/api/week_stats/" + encodeURIComponent(cfg.project) +
                      "/" + encodeURIComponent(week);
            fetch(url).then(function (r) {
                if (!r.ok) throw new Error("HTTP " + r.status);
                return r.json();
            }).then(function (payload) {
                if (ticket !== statsInflight) return;  // a newer step won
                var stats = (payload && payload.variables) || {};
                Object.keys(stats).forEach(function (col) {
                    var label = varByCol[col];
                    if (!label) return;
                    var meta = variables[label];
                    var s = stats[col];
                    var row = document.querySelector(
                        ".sh-legend-row[data-var='" + col + "']"
                    );
                    if (!row) return;
                    var minEl = row.querySelector(".sh-legend-vmin");
                    var maxEl = row.querySelector(".sh-legend-vmax");
                    if (s && typeof s.vmin === "number" && typeof s.vmax === "number") {
                        meta.vmin = s.vmin;
                        meta.vmax = s.vmax;
                        if (minEl) minEl.textContent = formatLegendValue(s.vmin);
                        if (maxEl) maxEl.textContent = formatLegendValue(s.vmax);
                        row.style.opacity = "1";
                    } else {
                        // No data this week — keep the global meta
                        // bounds so colour mapping keeps working when
                        // the user toggles this layer on, but visually
                        // dim the row + show dashes.
                        if (minEl) minEl.textContent = "—";
                        if (maxEl) maxEl.textContent = "—";
                        row.style.opacity = "0.45";
                    }
                });
            }).catch(function (err) {
                console.error("[SH-date-nav] week_stats failed", err);
            });
        }

        function formatLegendValue(v) {
            // Mirrors Python's `:.2f` formatting so the JS-driven
            // updates stay visually consistent with the server-rendered
            // initial labels. Falls back to scientific notation only
            // when the value is large enough that 2 decimals would
            // make the cell too wide to fit the 38 px slot.
            if (v == null || isNaN(v)) return "—";
            if (Math.abs(v) >= 10000) return v.toExponential(1);
            return v.toFixed(2);
        }

        function loadFrame(label, week) {
            var meta = variables[label];
            var fg = window[meta.fg_name];
            if (!fg) return;

            var ticket = ++inflight;
            var url = "/api/variable_week/" + encodeURIComponent(cfg.project) +
                      "/" + encodeURIComponent(meta.col) +
                      "/" + encodeURIComponent(week);
            fetch(url).then(function (r) {
                if (!r.ok) throw new Error("HTTP " + r.status);
                return r.json();
            }).then(function (payload) {
                if (ticket !== inflight) return;  // superseded
                fg.clearLayers();
                var rows = payload.points || [];
                var rangeText = payload.date_range || week;
                // Update the legend gradient endpoints + `meta.vmin/vmax`
                // BEFORE we colour any markers, so the new scale flows
                // into `colorFor`. Falls back to the original (global)
                // bounds when the week didn't expose a finite range.
                if (typeof payload.vmin === "number" && typeof payload.vmax === "number"
                    && payload.vmin !== payload.vmax) {
                    meta.vmin = payload.vmin;
                    meta.vmax = payload.vmax;
                    var legendRow = document.querySelector(
                        ".sh-legend-row[data-var='" + meta.col + "']"
                    );
                    if (legendRow) {
                        var minEl = legendRow.querySelector(".sh-legend-vmin");
                        var maxEl = legendRow.querySelector(".sh-legend-vmax");
                        if (minEl) minEl.textContent = formatLegendValue(payload.vmin);
                        if (maxEl) maxEl.textContent = formatLegendValue(payload.vmax);
                    }
                }
                // Canvas renderer instead of the default SVG one. For
                // ROIs with > 5 k pixels (Fantinel ships ~14 k per
                // week) SVG creates one DOM node per marker and the
                // browser spends 1-2 s laying them out on every
                // prev/next click — switching to canvas drops that
                // to roughly 100-200 ms because all markers share
                // a single <canvas> element.
                if (!meta._renderer) {
                    meta._renderer = L.canvas({ padding: 0.5 });
                }
                var renderer = meta._renderer;
                rows.forEach(function (p) {
                    var color = colorFor(p.value, meta);
                    var m = L.circleMarker([p.lat, p.lon], {
                        radius: 4,
                        color: color,
                        fillColor: color,
                        fillOpacity: 0.85,
                        weight: 1,
                        renderer: renderer,
                    });
                    m.bindPopup(
                        "<div class='sh-popup'>" +
                            "<div class='sh-popup__title'>" + label + "</div>" +
                            "<div class='sh-popup__sub'>Week " + week + "</div>" +
                            "<table class='sh-popup__kv'>" +
                                "<tr><td>Mean</td><td>" +
                                    (p.value != null ? p.value.toFixed(4) : "n/a") +
                                "</td></tr>" +
                                "<tr><td>Range</td><td>" + rangeText + "</td></tr>" +
                                "<tr><td>Lat / Lon</td><td>" +
                                    p.lat.toFixed(5) + " / " + p.lon.toFixed(5) +
                                "</td></tr>" +
                            "</table>" +
                        "</div>"
                    );
                    m.addTo(fg);
                });
                currentWeek[label] = week;
                currentRange[label] = rangeText;
                currentCount[label] = rows.length;
                loadedOnce[label] = true;
                render();
                // Bring every other variable's legend row in line
                // with the same week — the user wants the whole
                // statistics panel to scrub together, not just the
                // active layer's row.
                refreshAllLegendStats(week);
                // Pre-fetch the immediately adjacent weeks (silent,
                // no DOM update) so the next prev / next click hits
                // the browser HTTP cache instead of touching the
                // server. Cuts perceived lag on rapid scrub-back.
                prefetchAdjacent(label, week);
            }).catch(function (err) {
                console.error("[SH-date-nav] load failed", err);
            });
        }

        // Pre-fetch the responses for the two adjacent weeks so a
        // later prev / next click is served from the HTTP cache.
        // Tracks a small set so we never refetch the same URL twice.
        var prefetched = {};
        function prefetchAdjacent(label, week) {
            var meta = variables[label];
            var idx = meta.weeks.indexOf(week);
            if (idx === -1) return;
            [idx - 1, idx + 1].forEach(function (j) {
                if (j < 0 || j >= meta.weeks.length) return;
                var nextWeek = meta.weeks[j];
                var url = "/api/variable_week/" + encodeURIComponent(cfg.project) +
                          "/" + encodeURIComponent(meta.col) +
                          "/" + encodeURIComponent(nextWeek);
                if (prefetched[url]) return;
                prefetched[url] = true;
                // `keepalive` lets the request finish even if the
                // user navigates away mid-fetch; no-op on browsers
                // that don't support it.
                fetch(url, { credentials: "same-origin", keepalive: true })
                    .catch(function () { /* silent */ });
            });
        }

        // Lazy-load helper used by both the boot path (active layers
        // at first paint) and overlayadd (newly toggled layer with
        // an empty FG). No-op once the layer has been populated at
        // least once — subsequent week scrubs go through `loadFrame`
        // directly.
        function ensureLoaded(label) {
            if (!label || loadedOnce[label]) return;
            loadFrame(label, currentWeek[label] || variables[label].latest_week);
        }

        function step(direction) {
            var label = activeLabel();
            if (!label) return;
            var meta = variables[label];
            var idx = meta.weeks.indexOf(currentWeek[label]);
            if (idx === -1) return;
            var next = idx + direction;
            if (next < 0 || next >= meta.weeks.length) return;
            // Optimistically flip currentWeek BEFORE the fetch so
            // rapid double-clicks compute the right next index from
            // the user's perspective ("idx-1, idx-2" instead of
            // "idx-1, idx-1" which the previous code did).
            currentWeek[label] = meta.weeks[next];
            loadFrame(label, meta.weeks[next]);
        }

        prevBtn.addEventListener("click", function () { step(-1); });
        nextBtn.addEventListener("click", function () { step(1); });

        map.on("overlayadd", function (e) {
            if (variables[e.name]) {
                var i = activeStack.indexOf(e.name);
                if (i !== -1) activeStack.splice(i, 1);
                activeStack.push(e.name);
                ensureLoaded(e.name);
                render();
            }
        });
        map.on("overlayremove", function (e) {
            if (variables[e.name]) {
                var i = activeStack.indexOf(e.name);
                if (i !== -1) activeStack.splice(i, 1);
                render();
            }
        });

        render();

        // Boot path: any layer that was added to the map by Folium
        // (i.e. `show=True` server-side, currently NDVI) starts with
        // an empty FeatureGroup since Python no longer pre-renders
        // markers. Pull the latest frame for each so the user sees
        // pixels immediately on first paint.
        activeStack.slice().forEach(function (label) {
            ensureLoaded(label);
        });

        // Surface "data missing" ghost rows for variables the schema
        // declares but the run lost (cormor_2's S2 indices being the
        // canonical case — every value column was null after
        // ingestion). Rendered as disabled rows below the active
        // checkboxes so the user knows the variable exists
        // conceptually but has no data to plot. Polled because the
        // panel_collapse_html bootstrap is the one that actually
        // creates the `.sh-vars-head` container we want to live
        // beneath, and it runs after a 50 ms timeout.
        if (cfg.missing_variables && cfg.missing_variables.length) {
            injectMissingRows(cfg.missing_variables, 0);
        }
    }

    function injectMissingRows(rows, attempts) {
        var overlays = document.querySelector(
            ".leaflet-control-layers-overlays"
        );
        if (!overlays) {
            if (attempts > 30) return; // give up after ~3 s
            setTimeout(function () {
                injectMissingRows(rows, attempts + 1);
            }, 100);
            return;
        }
        if (overlays.querySelector(".sh-vars-missing")) return; // idempotent
        var divider = document.createElement("div");
        divider.className = "sh-vars-missing-head";
        divider.textContent = "Data missing";
        overlays.appendChild(divider);
        rows.forEach(function (entry) {
            var row = document.createElement("div");
            row.className = "sh-vars-missing";
            row.setAttribute("data-sensor", String(entry.sensor || "").toLowerCase());
            row.title =
                "The schema declares " + (entry.label || entry.col) +
                " but every value came back null in this run. " +
                "Re-run the project to recover.";
            var sw = document.createElement("span");
            sw.className = "sh-vars-missing__swatch";
            row.appendChild(sw);
            var lbl = document.createElement("span");
            lbl.className = "sh-vars-missing__label";
            lbl.textContent = entry.label || entry.col;
            row.appendChild(lbl);
            var pill = document.createElement("span");
            pill.className = "sh-vars-missing__pill";
            pill.textContent = "no data";
            row.appendChild(pill);
            overlays.appendChild(row);
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
"""


def get_available_dates(csv_path):
    """Return sorted list of unique dates in the temporal CSV."""
    if not os.path.exists(csv_path):
        return []
    try:
        df = pd.read_csv(csv_path, usecols=["date"])
        return sorted(df["date"].dropna().unique().tolist())
    except Exception:
        return []


def _add_ml_anomaly_heatmap_layer(m, ml_dir, df):
    """
    Add ML anomaly heatmap layer to map.
    Shows weighted heatmap from latest processed week.
    """
    # Find latest week folder
    weekly_dir = os.path.join(ml_dir, "weekly")
    if not os.path.exists(weekly_dir):
        return

    week_folders = [f for f in os.listdir(weekly_dir) if f.startswith("20")]
    if not week_folders:
        return

    latest_week = sorted(week_folders)[-1]
    cluster_csv = os.path.join(
        weekly_dir, latest_week, f"cluster_map_{latest_week}.csv"
    )

    if not os.path.exists(cluster_csv):
        return

    # Load cluster data
    cluster_df = pd.read_csv(cluster_csv)

    # Merge with main df to get coordinates if needed
    if "lat" not in cluster_df.columns or "lon" not in cluster_df.columns:
        if "spatial_id" in cluster_df.columns and "spatial_id" in df.columns:
            # Merge on spatial_id
            coords_df = df[["spatial_id", "lat", "lon"]].drop_duplicates("spatial_id")
            cluster_df = cluster_df.merge(coords_df, on="spatial_id", how="left")

    # Cluster layer is off by default — the user toggles it from the
    # layer control alongside the per-sensor variable layers.
    fg = folium.FeatureGroup(name=f"ML Clusters ({latest_week})", show=False)

    # Color palette for clusters — Tableau 10 (perceptually well-separated,
    # works against the Esri satellite basemap and the dark sidebar).
    unique_clusters = cluster_df["cluster_label"].unique()
    unique_clusters = [c for c in unique_clusters if c != -1]  # Exclude noise
    colors_palette = [
        "#4E79A7",  # blue
        "#F28E2B",  # orange
        "#E15759",  # red
        "#76B7B2",  # teal
        "#59A14F",  # green
        "#EDC948",  # yellow
        "#B07AA1",  # purple
        "#FF9DA7",  # pink
        "#9C755F",  # brown
        "#BAB0AC",  # warm grey
    ]

    cluster_colors = {}
    for i, c in enumerate(unique_clusters):
        cluster_colors[c] = colors_palette[i % len(colors_palette)]
    cluster_colors[-1] = "#4C4C4C"  # Dark grey for noise (distinct from #BAB0AC)

    # Add markers
    for _, row in cluster_df.iterrows():
        if pd.isna(row.get("lat")) or pd.isna(row.get("lon")):
            continue

        cluster_label = row["cluster_label"]
        track_id = row.get("track_id", -1)
        outlier_score = row.get("outlier_score", 0)

        color = cluster_colors.get(cluster_label, "#7f8c8d")

        # Pixel count is per-cluster, computed once outside the row loop
        # would be cleaner but keeping this inline avoids a second pass.
        pixel_count = int((cluster_df["cluster_label"] == cluster_label).sum())

        popup_text = (
            '<div class="sh-popup">'
            f'<div class="sh-popup__title">Cluster #{cluster_label}</div>'
            f'<div class="sh-popup__sub">Week {latest_week} &middot; Track #{track_id}</div>'
            '<table class="sh-popup__kv">'
            f'<tr><td>Outlier score</td><td>{outlier_score:.3f}</td></tr>'
            f'<tr><td>Pixel count</td><td>{pixel_count:,}</td></tr>'
            f"<tr><td>Lat / Lon</td><td>{row['lat']:.5f}° / {row['lon']:.5f}°</td></tr>"
            '</table>'
            '</div>'
        )

        # Size based on outlier score (larger = more anomalous)
        marker_size = 3 + int(outlier_score * 5)

        folium.CircleMarker(
            location=[row["lat"], row["lon"]],
            radius=marker_size,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.7,
            weight=1,
            popup=folium.Popup(popup_text, max_width=260),
        ).add_to(fg)

    fg.add_to(m)
    print(
        f"[Map] Added ML cluster layer: {latest_week} ({len(cluster_df)} pixels, {len(unique_clusters)} clusters)"
    )


def create_verification_map(
    csv_path,
    output_file,
    selected_date=None,
    project_name=None,
    mapbox_token=None,
):
    """
    Create a Folium map with one layer per statistic.

    Args:
        csv_path: Path to the temporal SmartHarvest CSV.
        output_file: Path for the output HTML map.
        selected_date: Date string (YYYY-MM-DD) to display.
                      If None, each variable uses its own latest date with data.
        project_name: Flask project name. When supplied, the rendered map
                      exposes a date-navigator control below the layer panel
                      that pages through each variable's historical
                      acquisitions via the /api/variable_frame endpoint.
        mapbox_token: Public Mapbox token. When supplied, the map
                      registers the four landslide-app basemap
                      styles (Outdoors / Light / Satellite / Dark)
                      plus the Esri fallback as base layers in the
                      Folium layer control — Leaflet's single-active
                      radio behaviour means picking one automatically
                      removes the others, so the user can swap basemap
                      from the same panel that holds the variable
                      overlays. Empty / None keeps just the Esri
                      tiles as before.
    Returns:
        str: Path to the output HTML file, or None on error.
    """
    if not os.path.exists(csv_path):
        print(f"Error: {csv_path} not found.")
        return None

    print(f"Loading {csv_path}...")
    df = pd.read_csv(csv_path)

    # Parse coordinates for all rows
    df["coords"] = df[".geo"].apply(_parse_coords)
    df["lon"] = df["coords"].apply(lambda x: x[0])
    df["lat"] = df["coords"].apply(lambda x: x[1])

    # Fit the map to the actual ROI bounding box instead of a fixed zoom=16
    # that worked for a 30 ha vineyard but dropped everything else off-screen.
    lat_min, lat_max = float(df["lat"].min()), float(df["lat"].max())
    lon_min, lon_max = float(df["lon"].min()), float(df["lon"].max())
    center_lat = (lat_min + lat_max) / 2
    center_lon = (lon_min + lon_max) / 2

    # `prefer_canvas` switches Leaflet's renderer to canvas instead of
    # SVG so the thousands of CircleMarkers in the variable layers
    # paint as one canvas pass instead of thousands of DOM nodes.
    # Initialise without a built-in basemap; we add base layers
    # explicitly below so they all appear as radio options inside the
    # Folium layer control.
    m = folium.Map(
        location=[center_lat, center_lon],
        tiles=None,
        prefer_canvas=True,
    )
    _add_basemap_layers(m, mapbox_token)
    # fit_bounds accepts [[south, west], [north, east]] and handles tiny
    # single-point ROIs by falling back to its own default zoom.
    if lat_min != lat_max or lon_min != lon_max:
        m.fit_bounds([[lat_min, lon_min], [lat_max, lon_max]], padding=(20, 20))
    else:
        m.options["zoom"] = 16

    if selected_date:
        print(f"Adding layers for date: {selected_date}")
    else:
        print("Adding layers with latest weekly mean per variable...")

    # Build legend HTML — when no `selected_date` is supplied the
    # navigator drives a weekly view, so the legend reflects the
    # latest week's averaged values per variable rather than a
    # single acquisition.
    # Eyebrow + subtitle adopt the same `Variables / Week / Maps`
    # design language: an uppercase 9.5 px / 0.22 em letter-spaced
    # head in muted ochre, then a thin secondary line for context
    # (the date or the "latest week per variable" caveat).
    if selected_date:
        legend_subtitle = f"Day · {selected_date}"
    else:
        legend_subtitle = "Latest week per variable"

    # The body wrapper lets the collapse animation target a single
    # element (`max-height: 0` on `.sh-legend__body`) instead of
    # iterating over the per-variable rows.
    legend_html = f"""
        <div class='sh-legend__head'>Statistics</div>
        <div class='sh-legend__body'>
        <div class='sh-legend__sub'>{legend_subtitle}</div>
    """

    numeric_stats = [c for c in schema.STATS_COLUMNS if c in df.columns]

    # Index of layer metadata the date-navigator needs to page through
    # historical acquisitions. Keys are the layer labels shown in the
    # layer control (so we can match them against Leaflet's overlayadd
    # event), values carry the underlying column key, the vmin/vmax
    # scale, the ordered list of dates with data, and the folium-
    # generated feature-group JS variable name.
    variable_index = {}

    for col in numeric_stats:
        if col not in df.columns:
            continue

        # When the caller supplies an explicit `selected_date` we
        # honour the strict single-date filter (the optional date
        # picker still routes through this branch). Otherwise we
        # mirror the navigator's contract: the layer ships the
        # latest *week* averaged per pixel, so the legend's
        # vmin/vmax describe the same range the user will see on
        # the default frame.
        if selected_date:
            col_df = df[df["date"] == selected_date][
                ["lat", "lon", ".geo", "date", col]
            ].copy()
            col_df = col_df.groupby(
                [".geo", "lat", "lon"], as_index=False
            )[col].mean()
            display_date = selected_date
        else:
            col_data_df = df[df[col].notna()].copy()
            if col_data_df.empty:
                continue
            col_data_df["date_dt"] = pd.to_datetime(
                col_data_df["date"], errors="coerce"
            )
            col_data_df["week"] = col_data_df["date_dt"].dt.strftime("%G-W%V")
            latest_week_id = col_data_df["week"].max()
            week_block = col_data_df[col_data_df["week"] == latest_week_id]
            if week_block.empty:
                continue
            col_df = week_block.groupby(
                [".geo", "lat", "lon"], as_index=False
            )[col].mean()
            # `display_date` keeps an honest "most recent date" value
            # for the metadata field, separate from the week token
            # used by the legend below.
            display_date = str(week_block["date"].max())

        col_data = col_df[col].dropna()
        if col_data.empty:
            continue

        vmin = float(col_data.min())
        vmax = float(col_data.max())
        if np.isnan(vmin) or np.isnan(vmax) or vmin == vmax:
            continue

        label = schema.COLUMN_LABELS.get(col, col)
        colors = schema.COLUMN_COLORS.get(col, ["red", "yellow", "green"])
        colormap = cm.LinearColormap(colors=colors, vmin=vmin, vmax=vmax)

        gradient_str = ", ".join(colors)
        # `data-var` lets the date-navigator JS find the row when the
        # active week changes so it can rewrite vmin / vmax labels.
        # Per-variable gradient is intentionally left as an inline
        # `background` because each row's colour ramp is unique
        # (NDVI green ramp ≠ LST blue ramp ≠ …) — only the chrome
        # (border, radius) is delegated to the shared CSS class.
        legend_html += f"""
        <div class='sh-legend-row' data-var='{col}'>
            <div class='sh-legend-row__label'>{label}</div>
            <div class='sh-legend-row__bar'>
                <span class='sh-legend-vmin'>{vmin:.2f}</span>
                <div class='sh-legend-row__ramp'
                     style='background:linear-gradient(to right,{gradient_str});'></div>
                <span class='sh-legend-vmax'>{vmax:.2f}</span>
            </div>
        </div>
        """

        # The variable's pixels are NOT serialised into the HTML
        # anymore — pre-rendering 12 layers × ~5 000 markers each
        # was inflating Map_<project>.html to ~50 MB and forcing
        # the browser to construct as many DOM / canvas children
        # before first paint. Instead we register an empty
        # FeatureGroup; the date-navigator JS bootstrap loads the
        # default-on layer's points from `/api/variable_frame`
        # on init, and any other layer the first time the user
        # toggles it on (`overlayadd`).
        show = col == "NDVI"
        fg = folium.FeatureGroup(name=label, show=show)
        fg.add_to(m)

        # Record the timeline so the date-navigator can page through
        # this variable's history without a full map reload. The
        # navigator works on ISO weeks now: weeks without any
        # observation are skipped, weeks with multiple acquisitions
        # are averaged per pixel by the API.
        block = df[df[col].notna()][["date", "lat", "lon", col]].copy()
        block["date_dt"] = pd.to_datetime(block["date"])
        # `%G-W%V` is the ISO 8601 year-week ("2025-W45"). It survives
        # the year boundary correctly (a Jan-1 in week 53 of the
        # previous year stays in that week's bucket).
        block["week"] = block["date_dt"].dt.strftime("%G-W%V")
        # `max_pixels` is the largest *unique-pixel* footprint in any
        # single week — the cloud-coverage hint uses it as the
        # denominator for "% of ROI observed". Counting raw rows here
        # (the previous shape) over-counts whenever a week has
        # several acquisitions: each pixel shows up once per pass,
        # so the denominator was N× the true unique count and the
        # hint was permanently saying "more clouds than reality".
        unique_pixels_per_week = (
            block.drop_duplicates(["week", "lat", "lon"])
                 .groupby("week")
                 .size()
        )
        variable_weeks = sorted(unique_pixels_per_week.index.tolist())
        max_pixels = (
            int(unique_pixels_per_week.max())
            if len(unique_pixels_per_week)
            else 0
        )
        latest_week = variable_weeks[-1] if variable_weeks else None
        sensor = schema.COLUMN_SATELLITE.get(col)
        cloud_sensitive = sensor in ("S2", "L8")
        variable_index[label] = {
            "col": col,
            "label": label,
            "vmin": vmin,
            "vmax": vmax,
            "colors": _resolve_to_hex(colors),
            "weeks": variable_weeks,
            "latest_week": latest_week,
            "latest_date": display_date,
            "initial_count": int(len(col_df)),
            "max_pixels": max_pixels,
            "cloud_sensitive": cloud_sensitive,
            "sensor": sensor,
            "fg_name": fg.get_name(),
        }

    # Add ML anomaly scale to legend if ML dir exists
    ml_dir = os.path.join(os.path.dirname(csv_path), 'ml_weekly')
    if os.path.exists(ml_dir):
        legend_html += """
        <div class='sh-legend__anomaly'>
            <div class='sh-legend__anomaly-head'>Anomaly Detection</div>
            <div class='sh-legend-row__bar'>
                <span class='sh-legend-vmin'>Normal</span>
                <div class='sh-legend-row__ramp'
                     style='background:linear-gradient(to right, blue, cyan, lime, yellow, orange, red);'></div>
                <span class='sh-legend-vmax'>Anomalous</span>
            </div>
            <div class='sh-legend__anomaly-foot'>Latest weekly analysis hotspots</div>
        </div>
        """

    # Custom Legend control. The chrome (surface, border, padding,
    # eyebrow rhythm) all comes from the `.sh-legend` CSS block
    # injected below, so this macro only mounts the control and
    # stops Leaflet from swallowing wheel + click events on the
    # scrollable legend body.
    class CustomLegend(MacroElement):
        _template = Template("""
            {% macro script(this, kwargs) %}
            var legend = L.control({position: 'topright'});
            legend.onAdd = function (map) {
                var div = L.DomUtil.create('div', 'sh-legend');
                L.DomEvent.disableClickPropagation(div);
                L.DomEvent.disableScrollPropagation(div);
                div.innerHTML = `{{ this.content }}`;
                return div;
            };
            legend.addTo({{ this._parent.get_name() }});
            {% endmacro %}
        """)

        def __init__(self, content):
            super().__init__()
            self._name = "CustomLegend"
            self.content = content

    # Add ML Weekly Clustering Layer (if available)
    ml_dir = os.path.join(os.path.dirname(csv_path), "ml_weekly")
    if os.path.exists(ml_dir):
        try:
            _add_ml_anomaly_heatmap_layer(m, ml_dir, df)
        except Exception as e:
            print(f"[Map] Could not add ML anomaly layer: {e}")

    # Close the `.sh-legend__body` wrapper opened above the per-row
    # legend entries, so the collapse animation has a single host.
    legend_html += "</div>"
    m.add_child(CustomLegend(legend_html))
    folium.LayerControl(position="topleft", collapsed=False).add_to(m)

    # Dark mode CSS for layer control. min-width is set slightly larger
    # than Leaflet's default so long labels (e.g. "Land Surface
    # Temperature (°C)") and the date-navigator widget sit comfortably.
    dark_css = """
    <style>
        /* Variables overlay panel — same shell + eyebrow + spacing
           tokens as `.sh-basemap` and `.sh-date-nav` so the three
           floating controls in the iframe stack at the top-left
           edge as one design family. `max-height` raised to 62vh
           and inter-panel gap tightened to 3 px so the typical 11
           variables fit without an inner scrollbar. Padding
           tightened (`6px 10px 8px`) to match the smaller basemap
           shell exactly. */
        .leaflet-control-layers.leaflet-control-layers-expanded {
            background: #25221C !important;
            color: #ECE4D2 !important;
            border: 1px solid #3A352A !important;
            border-radius: 6px !important;
            box-shadow: 0 10px 26px rgba(0, 0, 0, 0.65), 0 3px 8px rgba(0, 0, 0, 0.45) !important;
            padding: 6px 10px 8px !important;
            font-family: system-ui, -apple-system, "Helvetica Neue",
                         Helvetica, Arial, sans-serif !important;
            font-size: 11px !important;
            max-height: 62vh !important;
            width: 240px !important;
            box-sizing: border-box !important;
            overflow-y: auto !important;
            margin-bottom: 3px !important;
        }

        /* Eyebrow header — `::before` on the overlays section reads
           "Variables" with the same 0.22em letter-spacing + ochre
           muted colour as the other panels' heads. The `base` block
           is empty (basemaps moved to the dedicated bottom-left
           panel) so we hide it. */
        .leaflet-control-layers-base {
            display: none !important;
        }
        .leaflet-control-layers-overlays {
            display: block !important;
        }
        .leaflet-control-layers-overlays::before {
            content: "Variables";
            display: block;
            font-size: 9.5px;
            font-weight: 700;
            letter-spacing: 0.22em;
            text-transform: uppercase;
            color: #9C988B;
            text-align: center;
            padding-bottom: 6px;
            border-bottom: 1px solid #322E25;
            margin-bottom: 6px;
        }

        .leaflet-control-layers-overlays label {
            display: flex !important;
            align-items: center;
            gap: 7px;
            margin: 0 !important;
            padding: 2px 0;
            font-size: 11px !important;
            color: #C9C5B5 !important;
            font-weight: 500;
            line-height: 1.3;
            transition: color 150ms cubic-bezier(0.25, 1, 0.5, 1);
        }
        .leaflet-control-layers-overlays label:hover {
            color: #ECE4D2 !important;
        }
        .leaflet-control-layers-overlays label > span {
            flex: 1 1 auto;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .leaflet-control-layers-overlays input[type="checkbox"] {
            accent-color: #C09137;
            margin: 0;
            flex: 0 0 auto;
            cursor: pointer;
        }

        /* Missing-data ghost rows. Schema-declared variables whose
           values came back null end up appended below the active
           checkboxes with no input control; the small "no data" pill
           is the affordance ("not toggleable; the data is gone").
           The header has the same eyebrow rhythm as `.sh-basemap__head`
           but with russet tinting so it reads as a quiet warning. */
        .sh-vars-missing-head {
            margin-top: 8px !important;
            padding-top: 6px !important;
            border-top: 1px solid #322E25;
            font-size: 9px !important;
            font-weight: 700;
            letter-spacing: 0.18em;
            text-transform: uppercase;
            color: #9C7A7E;
            text-align: center;
        }
        .sh-vars-missing {
            display: flex !important;
            align-items: center;
            gap: 7px;
            padding: 3px 0;
            font-size: 11px !important;
            color: #6E6A60;
            cursor: help;
            opacity: 0.85;
        }
        .sh-vars-missing:hover { opacity: 1; }
        .sh-vars-missing__swatch {
            width: 10px;
            height: 10px;
            border-radius: 2px;
            background: repeating-linear-gradient(
                135deg,
                #322E25,
                #322E25 3px,
                transparent 3px,
                transparent 6px
            );
            border: 1px solid #322E25;
            flex: 0 0 auto;
        }
        .sh-vars-missing__label {
            flex: 1 1 auto;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .sh-vars-missing__pill {
            font-size: 9px;
            font-weight: 700;
            letter-spacing: 0.06em;
            text-transform: uppercase;
            color: #C77E83;
            background: rgba(199, 126, 131, 0.12);
            border: 1px solid rgba(199, 126, 131, 0.35);
            padding: 1px 5px;
            border-radius: 3px;
            flex: 0 0 auto;
        }

        /* Custom scrollbar matches the basemap panel — webkit only,
           but the fallback (default scrollbar) is fine on other
           engines. */
        .leaflet-control-layers::-webkit-scrollbar {
            width: 6px;
        }
        .leaflet-control-layers::-webkit-scrollbar-thumb {
            background: #322E25 !important;
            border-radius: 3px;
        }
        .leaflet-control-layers::-webkit-scrollbar-thumb:hover {
            background: #3A352A !important;
        }
        .leaflet-control-layers::-webkit-scrollbar-track {
            background: transparent;
        }

        /* Folium ships a tiny toggle <a> + "+" icon when the panel
           is collapsed. We always boot expanded (collapsed=False)
           so hide it. */
        .leaflet-control-layers-toggle {
            display: none !important;
        }
        /* Week navigator — adopts the same shell + eyebrow header
           + button language as the basemap panel so the three
           floating controls (Variables / Week / Maps) read as a
           single design family. Sits between Variables (above) and
           Maps (below) in the top-left auto-stack. */
        .sh-date-nav {
            /* Mounted as a Leaflet control at "topleft", below the
               Variables panel and above the basemap panel. Padding
               matches `.sh-basemap` (8/10/10) so all three panels
               share an identical inner rhythm; `margin-bottom: 6 px`
               leaves a thin gap so the panels read as distinct
               controls rather than one stacked block. */
            background: #25221C;
            color: #ECE4D2;
            border: 1px solid #3A352A;
            border-radius: 6px;
            box-shadow: 0 10px 26px rgba(0, 0, 0, 0.65), 0 3px 8px rgba(0, 0, 0, 0.45);
            padding: 6px 10px 8px;
            margin-bottom: 3px;
            font-family: system-ui, -apple-system, "Helvetica Neue",
                         Helvetica, Arial, sans-serif;
            font-size: 11px;
            width: 240px;
            box-sizing: border-box;
        }
        /* Eyebrow header — matches `.sh-basemap__head` exactly so
           the three panels share the same visual rhythm. */
        .sh-date-nav .sh-dn-label {
            font-size: 9.5px;
            font-weight: 700;
            letter-spacing: 0.22em;
            text-transform: uppercase;
            color: #9C988B;
            text-align: center;
            padding-bottom: 6px;
            border-bottom: 1px solid #322E25;
            margin-bottom: 6px;
        }
        .sh-date-nav .sh-dn-row {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 6px;
        }
        /* Arrow buttons — same surface / border / hover treatment
           as `.sh-basemap__btn`, just narrower. */
        .sh-date-nav .sh-dn-btn {
            appearance: none;
            background: #2C2820;
            color: #9C988B;
            border: 1px solid #322E25;
            border-radius: 4px;
            padding: 0;
            width: 26px;
            height: 24px;
            font-size: 12px;
            font-weight: 600;
            line-height: 1;
            cursor: pointer;
            transition:
                background 150ms cubic-bezier(0.25, 1, 0.5, 1),
                color 150ms cubic-bezier(0.25, 1, 0.5, 1),
                border-color 150ms cubic-bezier(0.25, 1, 0.5, 1),
                transform 200ms cubic-bezier(0.16, 1, 0.3, 1);
        }
        .sh-date-nav .sh-dn-btn:hover:not(:disabled) {
            color: #ECE4D2;
            border-color: #C09137;
            transform: translateY(-1px);
        }
        .sh-date-nav .sh-dn-btn:active:not(:disabled) {
            transform: translateY(0) scale(0.96);
        }
        .sh-date-nav .sh-dn-btn:disabled {
            opacity: 0.32;
            cursor: not-allowed;
        }
        /* Active week — the headline number of the panel. Slightly
           larger + tabular nums so the digits don't shimmy as the
           user pages forward and back. */
        .sh-date-nav .sh-dn-date {
            flex-grow: 1;
            text-align: center;
            font-variant-numeric: tabular-nums;
            font-weight: 700;
            font-size: 13px;
            color: #ECE4D2;
            letter-spacing: 0.02em;
        }
        /* Range, variable, count, cloud — secondary information,
           grouped below the arrows. Each line keeps its own colour
           role: range stays white-ish, variable picks up the
           ochre accent from the rest of the dashboard, count is
           muted, cloud sits in a soft slate. Same `prefers-reduced
           -motion` discipline as the basemap panel. */
        .sh-date-nav .sh-dn-range {
            font-size: 10px;
            color: #B4B4B4;
            text-align: center;
            margin-top: 3px;
            font-variant-numeric: tabular-nums;
        }
        .sh-date-nav .sh-dn-var {
            font-size: 9.5px;
            color: #C09137;
            text-align: center;
            margin-top: 5px;
            padding-top: 5px;
            border-top: 1px solid #322E25;
            text-transform: uppercase;
            letter-spacing: 0.12em;
            font-weight: 600;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .sh-date-nav .sh-dn-count {
            font-size: 10px;
            color: #9C988B;
            text-align: center;
            margin-top: 2px;
            font-variant-numeric: tabular-nums;
        }
        .sh-date-nav .sh-dn-cloud {
            font-size: 9.5px;
            color: #91ABBE;
            text-align: center;
            margin-top: 2px;
            font-variant-numeric: tabular-nums;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .sh-date-nav .sh-dn-empty {
            font-size: 10px;
            color: #7E7B6E;
            font-style: italic;
            text-align: center;
        }
        @media (prefers-reduced-motion: reduce) {
            .sh-date-nav .sh-dn-btn { transition-duration: 0.01ms; }
        }

        /* Statistics legend — top-right floating panel that mirrors
           the `Variables / Week / Maps` design language: dark linen
           surface, ochre 0.22 em eyebrow head, muted secondary
           subtitle, ochre `border-left` accent so the panel reads
           in dialogue with the popup card chrome. The per-row
           gradient bars keep their unique colour ramps (NDVI green,
           LST blue, etc.) — only the chrome around them is unified. */
        .sh-legend {
            background: #25221C;
            color: #ECE4D2;
            border: 1px solid #3A352A;
            border-left: 3px solid #C09137;
            border-radius: 6px;
            box-shadow: 0 10px 26px rgba(0, 0, 0, 0.65), 0 3px 8px rgba(0, 0, 0, 0.45);
            padding: 8px 12px 10px;
            font-family: system-ui, -apple-system, "Helvetica Neue",
                         Helvetica, Arial, sans-serif;
            font-size: 11px;
            width: 240px;
            max-height: 86vh;
            overflow-y: auto;
            box-sizing: border-box;
        }
        .sh-legend::-webkit-scrollbar { width: 6px; }
        .sh-legend::-webkit-scrollbar-thumb {
            background: #322E25;
            border-radius: 3px;
        }
        .sh-legend::-webkit-scrollbar-thumb:hover {
            background: #3A352A;
        }
        .sh-legend::-webkit-scrollbar-track { background: transparent; }

        .sh-legend__head {
            font-size: 9.5px;
            font-weight: 700;
            letter-spacing: 0.22em;
            text-transform: uppercase;
            color: #9C988B;
            text-align: center;
            padding-bottom: 4px;
        }
        .sh-legend__sub {
            font-size: 9.5px;
            color: #C09137;
            text-align: center;
            text-transform: uppercase;
            letter-spacing: 0.12em;
            font-weight: 600;
            padding-bottom: 6px;
            border-bottom: 1px solid #322E25;
            margin-bottom: 8px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .sh-legend-row {
            margin-bottom: 6px;
        }
        .sh-legend-row:last-child {
            margin-bottom: 0;
        }
        .sh-legend-row__label {
            font-weight: 600;
            font-size: 10px;
            color: #ECE4D2;
            margin-bottom: 2px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .sh-legend-row__bar {
            display: flex;
            align-items: center;
            gap: 4px;
        }
        .sh-legend-row__ramp {
            flex-grow: 1;
            height: 6px;
            border-radius: 2px;
            border: 1px solid #322E25;
        }
        .sh-legend-vmin,
        .sh-legend-vmax {
            font-size: 8.5px;
            color: #9C988B;
            font-variant-numeric: tabular-nums;
            font-weight: 500;
            min-width: 38px;
            flex-shrink: 0;
        }
        .sh-legend-vmax { text-align: right; }

        /* Anomaly Detection sub-section — same eyebrow rhythm as the
           main head but indented inside the legend with a divider on
           top so it reads as a related-but-separate block. The "Normal
           / Anomalous" labels reuse the vmin/vmax slot so they sit
           tight against the gradient bar. */
        .sh-legend__anomaly {
            margin-top: 8px;
            padding-top: 8px;
            border-top: 1px solid #322E25;
        }
        .sh-legend__anomaly-head {
            font-size: 9.5px;
            font-weight: 700;
            letter-spacing: 0.22em;
            text-transform: uppercase;
            color: #C09137;
            margin-bottom: 4px;
        }
        .sh-legend__anomaly .sh-legend-vmin,
        .sh-legend__anomaly .sh-legend-vmax {
            font-size: 9px;
            color: #B4B4B4;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.04em;
        }
        .sh-legend__anomaly-foot {
            font-size: 9px;
            color: #6E6A60;
            margin-top: 4px;
            font-style: italic;
        }
    </style>
    """
    m.get_root().html.add_child(folium.Element(dark_css))

    # SmartHarvest popup cards. The `_SH_POPUP_CSS` block doubles as
    # the carrier of the `__SH_POPUP_CARDS` self-heal sentinel.
    m.get_root().html.add_child(folium.Element(_SH_POPUP_CSS))

    # Inject order matters: Leaflet stacks controls in the corner in
    # the order their `.addTo(map)` runs. We want the top-left column
    # to read Variables → Week → Maps, so the date-navigator script
    # (Week) is injected BEFORE the basemap switcher (Maps); the
    # Variables panel itself comes from Folium's own LayerControl,
    # which always lands first.

    # Variables a healthy SmartHarvest run is *expected* to ship.
    # If a column appears in `numeric_stats` (i.e. the schema knows
    # about it AND it lives in the merged CSV) but didn't make it
    # into `variable_index` (because every row was null), we want
    # the iframe Variables panel to show it as a "data missing"
    # ghost row instead of silently omitting it — the cormor_2 case
    # was confusing because the user's S2 indices simply vanished.
    missing_variables = []
    present_cols = {entry["col"] for entry in variable_index.values()}
    for col in numeric_stats:
        if col in present_cols:
            continue
        # `numeric_stats` only contains columns the schema declares
        # AND that exist in the CSV, so by definition the user
        # expects this column to carry data. Reaching this branch
        # means every row was null — surface it.
        missing_variables.append({
            "col": col,
            "label": schema.COLUMN_LABELS.get(col, col),
            "sensor": schema.COLUMN_SATELLITE.get(col),
        })

    # Date-navigator: only makes sense when we know the API origin
    # (which the Flask route supplies via project_name). Even when
    # there are zero present variables (the rare all-null case), we
    # still want to ship the nav so the missing-variables ghost rows
    # render correctly.
    if project_name and (variable_index or missing_variables):
        config = {
            "project": project_name,
            "variables": variable_index,
            "missing_variables": missing_variables,
        }
        # `__SH_LAZY_LAYERS` is also the self-heal sentinel checked
        # by `app.py` `/map/<project>` and `/ml_map/<project>` so it
        # lives at the very top of the embed where a 32 KB head-scan
        # is guaranteed to find it.
        nav_script = (
            "<script>\n"
            "window.__SH_LAZY_LAYERS = true; window.__SH_POPUP_CARDS = true; window.__SH_WEEKLY_NAV = true; window.__SH_WEEKLY_LEGEND = true; window.__SH_LEGEND_ADAPT = true; window.__SH_LEGEND_BULK = true; window.__SH_MAXPX_FIX = true; window.__SH_VARS_GHOST = true;\n"
            "window.__SH_MAP_CONFIG = " + json.dumps(config) + ";\n"
            + _DATE_NAV_JS
            + "\n</script>\n"
        )
        m.get_root().html.add_child(folium.Element(nav_script))

    # Basemap selection lives in its own floating panel — Folium's
    # layer control now only carries the Variables checkboxes, so the
    # user gets three visually distinct overlays. Injected last so
    # it stacks at the bottom of the top-left column.
    from tools.basemap_switcher import basemap_switcher_html, panel_collapse_html

    switcher = basemap_switcher_html(mapbox_token, default="satellite")
    if switcher:
        m.get_root().html.add_child(folium.Element(switcher))

    # Shared collapse toggle + ochre `border-left` for all four
    # floating panels. Injected last so the bootstrap finds every
    # panel already mounted in the DOM.
    m.get_root().html.add_child(
        folium.Element(panel_collapse_html(layers_label="Variables"))
    )

    m.save(output_file)
    print(f"Map saved to {output_file}")
    return output_file


if __name__ == "__main__":
    create_verification_map(
        "output/New_Vineyard/SmartHarvest_New_Vineyard.csv",
        "output/New_Vineyard/Map_New_Vineyard.html",
    )
