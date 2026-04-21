"""
Map visualization for the temporal dataset.

Reads the SmartHarvest temporal CSV and creates a Folium map
showing the latest acquisition date's statistics as layers.
Supports date filtering via the `selected_date` parameter.
"""

import json
import os

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
        // `currentDate[label]` = date string currently displayed for that
        // variable. Seeded with the latest, which matches what Python
        // rendered into the initial FG.
        var currentDate = {};
        Object.keys(variables).forEach(function (k) {
            currentDate[k] = variables[k].latest;
        });

        // Stack of active overlay labels, most-recent-on-top. Used to
        // resolve "the last selected one" for the date display. Folium
        // renders a `show=True` overlay before this script runs so
        // `overlayadd` won't fire for it — prime the stack by walking
        // the map's current layers instead.
        var activeStack = [];
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
                '<div class="sh-dn-label">Acquisition date</div>' +
                '<div class="sh-dn-row">' +
                '  <button class="sh-dn-btn sh-dn-prev" title="Previous acquisition">&#9664;</button>' +
                '  <div class="sh-dn-date">—</div>' +
                '  <button class="sh-dn-btn sh-dn-next" title="Next acquisition">&#9654;</button>' +
                '</div>' +
                '<div class="sh-dn-var"></div>' +
                '<div class="sh-dn-count"></div>';
            return div;
        };
        control.addTo(map);

        var rootEl = control.getContainer();
        var dateEl = rootEl.querySelector(".sh-dn-date");
        var varEl = rootEl.querySelector(".sh-dn-var");
        var countEl = rootEl.querySelector(".sh-dn-count");
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
                varEl.textContent = "No layer active";
                varEl.classList.add("sh-dn-empty");
                countEl.textContent = "";
                prevBtn.disabled = true;
                nextBtn.disabled = true;
                return;
            }
            varEl.classList.remove("sh-dn-empty");
            var meta = variables[label];
            var date = currentDate[label];
            var idx = meta.dates.indexOf(date);
            dateEl.textContent = date || "—";
            varEl.textContent = label;
            var n = currentCount[label];
            countEl.textContent = (n == null)
                ? ""
                : n.toLocaleString() + " pixel" + (n === 1 ? "" : "s");
            prevBtn.disabled = idx <= 0;
            nextBtn.disabled = idx === -1 || idx >= meta.dates.length - 1;
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

        function loadFrame(label, date) {
            var meta = variables[label];
            var fg = window[meta.fg_name];
            if (!fg) return;

            var ticket = ++inflight;
            var url = "/api/variable_frame/" + encodeURIComponent(cfg.project) +
                      "/" + encodeURIComponent(meta.col) +
                      "/" + encodeURIComponent(date);
            fetch(url).then(function (r) {
                if (!r.ok) throw new Error("HTTP " + r.status);
                return r.json();
            }).then(function (payload) {
                if (ticket !== inflight) return;  // superseded
                fg.clearLayers();
                var rows = payload.points || [];
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
                        "<b>" + label + "</b><br>" +
                        "Value: " + (p.value != null ? p.value.toFixed(4) : "n/a") + "<br>" +
                        "Date: " + date + "<br>" +
                        "Lat: " + p.lat.toFixed(5) + ", Lon: " + p.lon.toFixed(5)
                    );
                    m.addTo(fg);
                });
                currentDate[label] = date;
                currentCount[label] = rows.length;
                render();
            }).catch(function (err) {
                console.error("[SH-date-nav] load failed", err);
            });
        }

        function step(direction) {
            var label = activeLabel();
            if (!label) return;
            var meta = variables[label];
            var idx = meta.dates.indexOf(currentDate[label]);
            if (idx === -1) return;
            var next = idx + direction;
            if (next < 0 || next >= meta.dates.length) return;
            loadFrame(label, meta.dates[next]);
        }

        prevBtn.addEventListener("click", function () { step(-1); });
        nextBtn.addEventListener("click", function () { step(1); });

        map.on("overlayadd", function (e) {
            if (variables[e.name]) {
                var i = activeStack.indexOf(e.name);
                if (i !== -1) activeStack.splice(i, 1);
                activeStack.push(e.name);
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

        popup_text = (
            f"<b>ML Cluster</b><br>"
            f"Week: {latest_week}<br>"
            f"Cluster: {cluster_label}<br>"
            f"Track ID: {track_id}<br>"
            f"Outlier Score: {outlier_score:.3f}<br>"
            f"Lat: {row['lat']:.5f}, Lon: {row['lon']:.5f}"
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
            popup=folium.Popup(popup_text, max_width=220),
        ).add_to(fg)

    fg.add_to(m)
    print(
        f"[Map] Added ML cluster layer: {latest_week} ({len(cluster_df)} pixels, {len(unique_clusters)} clusters)"
    )


def create_verification_map(
    csv_path, output_file, selected_date=None, project_name=None
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

    m = folium.Map(
        location=[center_lat, center_lon],
        tiles="Esri.WorldImagery",
    )
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

        # Default: show NDVI layer, hide others
        show = col == "NDVI"
        fg = folium.FeatureGroup(name=label, show=show)

        for _, row in col_df.iterrows():
            val = row.get(col)
            if pd.isna(val):
                continue
            color = colormap(val)
            popup_text = (
                f"<b>{label}</b><br>"
                f"Value: {val:.4f}<br>"
                f"Date: {display_date}<br>"
                f"Lat: {row['lat']:.5f}, Lon: {row['lon']:.5f}"
            )
            folium.CircleMarker(
                location=[row["lat"], row["lon"]],
                radius=4,
                color=color,
                fill=True,
                fill_color=color,
                fill_opacity=0.85,
                popup=folium.Popup(popup_text, max_width=220),
            ).add_to(fg)

        fg.add_to(m)

        # Record the timeline so the date-navigator can page through this
        # variable's acquisitions without a full map reload.
        variable_dates = sorted(
            df[df[col].notna()]["date"].dropna().unique().tolist()
        )
        variable_index[label] = {
            "col": col,
            "label": label,
            "vmin": vmin,
            "vmax": vmax,
            "colors": _resolve_to_hex(colors),
            "dates": variable_dates,
            "latest": display_date,
            "initial_count": int(len(col_df)),
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
        .sh-date-nav .sh-dn-count {
            font-size: 9px;
            color: #8c8c8c;
            text-align: center;
            margin-top: 2px;
            font-variant-numeric: tabular-nums;
        }
    </style>
    """
    m.get_root().html.add_child(folium.Element(dark_css))

    # Date-navigator: only makes sense when we know the API origin
    # (which the Flask route supplies via project_name).
    if project_name and variable_index:
        config = {
            "project": project_name,
            "variables": variable_index,
        }
        nav_script = (
            "<script>\n"
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
