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
    ("Dark",      "dark-v11"),
    ("Satellite", "satellite-streets-v12"),
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
                control=True,
                overlay=False,
                max_zoom=22,
                tile_size=512,
                zoom_offset=-1,
            ).add_to(m)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        name="Esri Satellite",
        attr="Tiles &copy; Esri",
        control=True,
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

    /* --- Layer-control section titles --------------------------- */
    .sh-layer-section-title {
        font-size: 9.5px;
        font-weight: 700;
        letter-spacing: 0.22em;
        text-transform: uppercase;
        color: #9C988B;
        padding: 4px 0;
        margin-bottom: 4px;
    }
    .leaflet-control-layers-separator {
        border-top: 1px solid #322E25 !important;
        margin: 8px 0 !important;
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
window.__SH_POPUP_CARDS = true; window.__SH_WEEKLY_NAV = true;
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
            div.innerHTML =
                '<div class="sh-dn-label">Week</div>' +
                '<div class="sh-dn-row">' +
                '  <button class="sh-dn-btn sh-dn-prev" title="Previous week">&#9664;</button>' +
                '  <div class="sh-dn-date">—</div>' +
                '  <button class="sh-dn-btn sh-dn-next" title="Next week">&#9654;</button>' +
                '</div>' +
                '<div class="sh-dn-range"></div>' +
                '<div class="sh-dn-var"></div>' +
                '<div class="sh-dn-count"></div>' +
                '<div class="sh-dn-cloud"></div>';
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
            varEl.textContent = label + " · weekly mean";
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
                rows.forEach(function (p) {
                    var color = colorFor(p.value, meta);
                    var m = L.circleMarker([p.lat, p.lon], {
                        radius: 4,
                        color: color,
                        fillColor: color,
                        fillOpacity: 0.85,
                        weight: 1,
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
            }).catch(function (err) {
                console.error("[SH-date-nav] load failed", err);
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
        print("Adding layers with latest available date per variable...")

    # Build legend HTML
    if selected_date:
        legend_title = f"Statistics — {selected_date}"
    else:
        legend_title = "Statistics — Latest per Variable"

    legend_html = f"""
        <h4 style='margin-top:0;margin-bottom:10px;font-size:13px;
                   text-transform:uppercase;border-bottom:1px solid #555;
                   padding-bottom:5px;'>
            {legend_title}
        </h4>
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

        # Strict single-date filter for this variable's initial layer:
        # show every pixel observed on exactly `display_date`. No
        # subsampling, no forward-fill — matches the
        # `/api/variable_frame` endpoint so the Python-rendered layer
        # and the JS-fetched frames agree on pixel counts.
        if selected_date:
            col_df = df[df["date"] == selected_date][
                ["lat", "lon", ".geo", "date", col]
            ].copy()
            display_date = selected_date
        else:
            col_data_df = df[df[col].notna()].copy()
            if col_data_df.empty:
                continue
            display_date = col_data_df["date"].max()
            col_df = col_data_df[col_data_df["date"] == display_date][
                ["lat", "lon", ".geo", "date", col]
            ].copy()

        # Dedupe tile-boundary duplicates at the same location on the
        # same day; does not reduce unique pixel coverage.
        col_df = col_df.groupby([".geo", "lat", "lon"], as_index=False)[col].mean()

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
        legend_html += f"""
        <div style='margin-bottom:5px;'>
            <div style='font-weight:600;font-size:10px;color:#ddd;'>{label}</div>
            <div style='display:flex;align-items:center;'>
                <span style='font-size:8px;color:#aaa;width:22px;'>{vmin:.2f}</span>
                <div style='flex-grow:1;height:6px;
                    background:linear-gradient(to right,{gradient_str});
                    border-radius:2px;margin:0 4px;border:1px solid #555;'></div>
                <span style='font-size:8px;color:#aaa;width:22px;text-align:right;'>{vmax:.2f}</span>
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
        block = df[df[col].notna()][["date", col]].copy()
        block["date_dt"] = pd.to_datetime(block["date"])
        # `%G-W%V` is the ISO 8601 year-week ("2025-W45"). It survives
        # the year boundary correctly (a Jan-1 in week 53 of the
        # previous year stays in that week's bucket).
        block["week"] = block["date_dt"].dt.strftime("%G-W%V")
        per_week_counts = block.groupby("week").size()
        variable_weeks = sorted(per_week_counts.index.tolist())
        # `max_pixels` is the largest single-week observation
        # footprint — used by the cloud-coverage hint as the
        # denominator. With weekly averaging the weekly count never
        # exceeds the number of unique pixels imaged in that week,
        # so this is the right scale.
        max_pixels = (
            int(per_week_counts.max()) if len(per_week_counts) else 0
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
        <div style='margin-top:10px; padding-top:10px; border-top:1px solid #444;'>
            <div style='font-weight:600;font-size:10px;color:#f39c12;'>ANOMALY DETECTION</div>
            <div style='display:flex;align-items:center;margin-top:4px;'>
                <span style='font-size:8px;color:#aaa;width:30px;'>Normal</span>
                <div style='flex-grow:1;height:6px;
                    background:linear-gradient(to right, blue, cyan, lime, yellow, orange, red);
                    border-radius:2px;margin:0 4px;border:1px solid #555;'></div>
                <span style='font-size:8px;color:#aaa;width:45px;text-align:right;'>Anomalous</span>
            </div>
            <div style='font-size:8px;color:#888;margin-top:2px;'>Latest weekly analysis hotspots</div>
        </div>
        """

    # Custom Legend control
    class CustomLegend(MacroElement):
        _template = Template("""
            {% macro script(this, kwargs) %}
            var legend = L.control({position: 'topright'});
            legend.onAdd = function (map) {
                var div = L.DomUtil.create('div', 'info legend');
                div.innerHTML = `{{ this.content }}`;
                div.style.backgroundColor = 'rgba(25,25,25,0.92)';
                div.style.color = '#eee';
                div.style.padding = '10px';
                div.style.borderRadius = '8px';
                div.style.boxShadow = '0 0 15px rgba(0,0,0,0.5)';
                div.style.width = '240px';
                div.style.maxHeight = '90vh';
                div.style.overflowY = 'auto';
                div.style.fontSize = '10px';
                div.style.fontFamily = "'Segoe UI', sans-serif";
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

    m.add_child(CustomLegend(legend_html))
    folium.LayerControl(position="topleft", collapsed=False).add_to(m)

    # Dark mode CSS for layer control. min-width is set slightly larger
    # than Leaflet's default so long labels (e.g. "Land Surface
    # Temperature (°C)") and the date-navigator widget sit comfortably.
    dark_css = """
    <style>
        .leaflet-control-layers {
            background-color: rgba(25,25,25,0.92) !important;
            color: #eee !important;
            border: none !important;
            border-radius: 8px !important;
            box-shadow: 0 0 15px rgba(0,0,0,0.5) !important;
            padding: 6px !important;
            font-family: 'Segoe UI', sans-serif !important;
            max-height: 85vh !important;
            min-width: 220px !important;
            overflow-y: auto !important;
        }
        .leaflet-control-layers-base label,
        .leaflet-control-layers-overlays label {
            margin-bottom: 2px !important;
            font-size: 10px !important;
        }
        /* Visible scrollbar so the ML Clusters entry at the bottom of the
           list is discoverable even on short viewports. */
        .leaflet-control-layers::-webkit-scrollbar {
            width: 8px;
        }
        .leaflet-control-layers::-webkit-scrollbar-thumb {
            background: rgba(255,255,255,0.25) !important;
            border-radius: 4px;
        }
        .leaflet-control-layers::-webkit-scrollbar-track {
            background: transparent;
        }
        /* Date navigator — sits just under the layer control, same width
           so the two feel like a single stacked panel. */
        .sh-date-nav {
            background-color: rgba(25,25,25,0.92);
            color: #eee;
            border-radius: 8px;
            box-shadow: 0 0 15px rgba(0,0,0,0.5);
            padding: 8px 10px;
            margin-top: 6px;
            font-family: 'Segoe UI', sans-serif;
            font-size: 11px;
            min-width: 220px;
        }
        .sh-date-nav .sh-dn-label {
            font-size: 9px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: #9aa;
            margin-bottom: 4px;
        }
        .sh-date-nav .sh-dn-row {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 6px;
        }
        .sh-date-nav .sh-dn-btn {
            background: rgba(255,255,255,0.08);
            color: #eee;
            border: 1px solid rgba(255,255,255,0.15);
            border-radius: 4px;
            cursor: pointer;
            width: 26px;
            height: 22px;
            font-size: 12px;
            line-height: 1;
            padding: 0;
        }
        .sh-date-nav .sh-dn-btn:hover:not(:disabled) {
            background: rgba(255,255,255,0.18);
        }
        .sh-date-nav .sh-dn-btn:disabled {
            opacity: 0.35;
            cursor: not-allowed;
        }
        .sh-date-nav .sh-dn-date {
            flex-grow: 1;
            text-align: center;
            font-variant-numeric: tabular-nums;
            font-weight: 600;
            font-size: 12px;
        }
        .sh-date-nav .sh-dn-var {
            font-size: 9px;
            color: #8ab4ff;
            text-align: center;
            margin-top: 3px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .sh-date-nav .sh-dn-empty {
            font-size: 10px;
            color: #888;
            font-style: italic;
            text-align: center;
        }
        .sh-date-nav .sh-dn-range {
            font-size: 10px;
            color: #b4b4b4;
            text-align: center;
            margin-top: 2px;
            font-variant-numeric: tabular-nums;
        }
        .sh-date-nav .sh-dn-count {
            font-size: 9px;
            color: #8c8c8c;
            text-align: center;
            margin-top: 2px;
            font-variant-numeric: tabular-nums;
        }
        .sh-date-nav .sh-dn-cloud {
            font-size: 9px;
            color: #c8d5ff;
            text-align: center;
            margin-top: 1px;
            font-variant-numeric: tabular-nums;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
    </style>
    """
    m.get_root().html.add_child(folium.Element(dark_css))

    # SmartHarvest popup cards + layer-control section titles. The
    # JS block sets `window.__SH_POPUP_CARDS = true` which doubles as
    # the self-heal sentinel checked by `app.py`.
    m.get_root().html.add_child(folium.Element(_SH_POPUP_CSS))
    m.get_root().html.add_child(folium.Element(_SH_LAYER_TITLES_JS))

    # Date-navigator: only makes sense when we know the API origin
    # (which the Flask route supplies via project_name).
    if project_name and variable_index:
        config = {
            "project": project_name,
            "variables": variable_index,
        }
        # `__SH_LAZY_LAYERS` is also the self-heal sentinel checked
        # by `app.py` `/map/<project>` and `/ml_map/<project>` so it
        # lives at the very top of the embed where a 32 KB head-scan
        # is guaranteed to find it.
        nav_script = (
            "<script>\n"
            "window.__SH_LAZY_LAYERS = true; window.__SH_POPUP_CARDS = true; window.__SH_WEEKLY_NAV = true;\n"
            "window.__SH_MAP_CONFIG = " + json.dumps(config) + ";\n"
            + _DATE_NAV_JS
            + "\n</script>\n"
        )
        m.get_root().html.add_child(folium.Element(nav_script))

    m.save(output_file)
    print(f"Map saved to {output_file}")
    return output_file


if __name__ == "__main__":
    create_verification_map(
        "output/New_Vineyard/SmartHarvest_New_Vineyard.csv",
        "output/New_Vineyard/Map_New_Vineyard.html",
    )
