"""
ML Anomaly Detection Map - Interactive visualization for weekly clustering

Creates a dedicated map showing:
- Normal clusters (blue/green layers)
- Anomalous clusters (red/orange layers)
- Outlier heatmap (top 10% anomalous pixels)
- Status badges (NEW/CONTINUED)
"""

import os
import json
import pandas as pd
import numpy as np
import folium
from folium.plugins import HeatMap
from branca.element import MacroElement
from jinja2 import Template


def _parse_coords(geo_str):
    """Parse .geo GeoJSON string to [lon, lat]."""
    try:
        data = json.loads(geo_str) if isinstance(geo_str, str) else geo_str
        return data["coordinates"]  # [lon, lat]
    except Exception:
        return [0, 0]


def create_ml_anomaly_map(ml_dir, week_id, output_file, mapbox_token=None):
    """
    Create dedicated ML anomaly detection map for a specific week.

    Args:
        ml_dir: Path to ml_weekly directory
        week_id: Week ID (e.g., '2025-W45')
        output_file: Path for output HTML
        mapbox_token: Public Mapbox token. When supplied the four
            landslide-app basemap styles + the panel switcher are
            injected; when omitted the hard-coded
            `Esri.WorldImagery` stays untouched.

    Returns:
        str: Path to output HTML, or None on error
    """
    week_dir = os.path.join(ml_dir, "weekly", week_id)
    cluster_csv = os.path.join(week_dir, f"cluster_map_{week_id}.csv")
    outlier_csv = os.path.join(week_dir, f"outlier_map_{week_id}.csv")

    if not os.path.exists(cluster_csv):
        print(f"[ML Map] Error: {cluster_csv} not found")
        return None

    print(f"[ML Map] Loading {cluster_csv}...")
    df = pd.read_csv(cluster_csv)

    # Parse coordinates if needed
    if "lat" not in df.columns or "lon" not in df.columns:
        if ".geo" in df.columns:
            df["coords"] = df[".geo"].apply(_parse_coords)
            df["lon"] = df["coords"].apply(lambda x: x[0])
            df["lat"] = df["coords"].apply(lambda x: x[1])

    # Fit the map to actual cluster bounds so ROIs outside Italy render
    # correctly (previously zoom=16 centered on the Fantinel vineyard
    # worked by accident).
    lat_min, lat_max = float(df["lat"].min()), float(df["lat"].max())
    lon_min, lon_max = float(df["lon"].min()), float(df["lon"].max())
    center_lat = (lat_min + lat_max) / 2
    center_lon = (lon_min + lon_max) / 2

    # Canvas renderer keeps the cluster + heatmap pass cheap when
    # the week is dense (~5 000 markers); SVG was creating thousands
    # of DOM nodes on every layer toggle. Initialise without a
    # built-in tile layer so the explicit base-layer registration
    # below puts every basemap into the same Folium layer control
    # as a single-active radio group.
    from tools.visualize_data_map import _add_basemap_layers

    m = folium.Map(
        location=[center_lat, center_lon],
        tiles=None,
        prefer_canvas=True,
    )
    _add_basemap_layers(m, mapbox_token)
    if lat_min != lat_max or lon_min != lon_max:
        m.fit_bounds([[lat_min, lon_min], [lat_max, lon_max]], padding=(20, 20))
    else:
        m.options["zoom"] = 16

    # Determine anomalous clusters (outlier_score > 95th percentile).
    # If the column is empty/all-NaN the quantile is NaN; fall back to +inf so
    # the subsequent `> threshold` comparison cleanly marks nothing as anomalous
    # instead of bubbling the NaN through pandas' boolean-coercion warnings.
    if df.empty or df["outlier_score"].notna().sum() == 0:
        outlier_threshold = float("inf")
    else:
        outlier_threshold = df["outlier_score"].quantile(0.95)
        if pd.isna(outlier_threshold):
            outlier_threshold = float("inf")

    # Aggregate by cluster
    agg_dict = {
        "outlier_score": "mean",
        "track_id": "first",
        "lat": "mean",
        "lon": "mean",
    }

    # Add cluster_status if available (backward compatibility)
    if "cluster_status" in df.columns:
        agg_dict["cluster_status"] = "first"

    cluster_agg = (
        df[df["cluster_label"] != -1]
        .groupby("cluster_label")
        .agg(agg_dict)
        .reset_index()
    )

    # Set default status if column doesn't exist
    if "cluster_status" not in cluster_agg.columns:
        cluster_agg["cluster_status"] = "unknown"

    cluster_agg["pixel_count"] = (
        df[df["cluster_label"] != -1].groupby("cluster_label").size().values
    )
    cluster_agg["is_anomalous"] = cluster_agg["outlier_score"] > outlier_threshold

    # Layer 1: Normal Clusters
    fg_normal = folium.FeatureGroup(name="Normal Clusters", show=False)

    normal_clusters = cluster_agg[~cluster_agg["is_anomalous"]]

    for _, cluster in normal_clusters.iterrows():
        _add_cluster_marker(fg_normal, cluster, week_id, is_anomalous=False)

    fg_normal.add_to(m)

    # Layer 2: Anomalous Clusters
    fg_anomalous = folium.FeatureGroup(name="Anomalous Clusters", show=False)

    anomalous_clusters = cluster_agg[cluster_agg["is_anomalous"]]

    for _, cluster in anomalous_clusters.iterrows():
        _add_cluster_marker(fg_anomalous, cluster, week_id, is_anomalous=True)

    fg_anomalous.add_to(m)

    # Layer 3: Outlier Heatmap
    if os.path.exists(outlier_csv):
        fg_heatmap = folium.FeatureGroup(name="Outlier Heatmap", show=True)

        outlier_df = pd.read_csv(outlier_csv)

        if "lat" not in outlier_df.columns or "lon" not in outlier_df.columns:
            if ".geo" in outlier_df.columns:
                outlier_df["coords"] = outlier_df[".geo"].apply(_parse_coords)
                outlier_df["lon"] = outlier_df["coords"].apply(lambda x: x[0])
                outlier_df["lat"] = outlier_df["coords"].apply(lambda x: x[1])

        heat_data = [
            [row["lat"], row["lon"], row["outlier_score"]]
            for _, row in outlier_df.iterrows()
            if not pd.isna(row["lat"]) and not pd.isna(row["lon"])
        ]

        if heat_data:
            HeatMap(
                heat_data,
                radius=15,
                blur=25,
                max_zoom=18,
                gradient={0.0: "blue", 0.5: "yellow", 0.75: "orange", 1.0: "red"},
            ).add_to(fg_heatmap)

        fg_heatmap.add_to(m)

    # Add layer control
    folium.LayerControl(position="topleft", collapsed=False).add_to(m)

    # Add legend
    legend_html = _create_legend(week_id)
    m.get_root().html.add_child(folium.Element(legend_html))

    # Layer panel — same shell + eyebrow + spacing tokens as the
    # data-map iframe and the basemap / week panels, with a
    # "Layers" eyebrow (the ML iframe's overlays are clusters +
    # heatmap, not variables, so the more generic word reads true).
    dark_css = """
    <style>
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
        .leaflet-control-layers-base { display: none !important; }
        .leaflet-control-layers-overlays { display: block !important; }
        .leaflet-control-layers-overlays::before {
            content: "Layers";
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
        .leaflet-control-layers-toggle { display: none !important; }
        .leaflet-control-layers::-webkit-scrollbar { width: 6px; }
        .leaflet-control-layers::-webkit-scrollbar-thumb {
            background: #322E25 !important;
            border-radius: 3px;
        }
        .leaflet-control-layers::-webkit-scrollbar-track {
            background: transparent;
        }
    </style>
    """
    m.get_root().html.add_child(folium.Element(dark_css))

    # SmartHarvest popup cards + layer-control section titles. Reuses
    # the same blocks the data-map iframe injects so the two iframes
    # stay visually identical.
    from tools.visualize_data_map import _SH_POPUP_CSS
    from tools.basemap_switcher import basemap_switcher_html, panel_collapse_html

    m.get_root().html.add_child(folium.Element(_SH_POPUP_CSS))
    # Same Map / Variables split as the data map: standalone floating
    # panel for the basemap, Folium's layer control for the cluster /
    # heatmap overlays.
    switcher = basemap_switcher_html(mapbox_token, default="satellite")
    if switcher:
        m.get_root().html.add_child(folium.Element(switcher))

    # Shared collapse toggle + ochre `border-left` accent on every
    # floating panel. The Folium LayerControl on this iframe carries
    # cluster / heatmap toggles, so the eyebrow reads "Layers"
    # instead of "Variables".
    m.get_root().html.add_child(
        folium.Element(panel_collapse_html(layers_label="Layers"))
    )

    # Self-heal sentinel — `app.py /ml_map` regenerates the cached
    # HTML when this string is missing from the head. Bumped to
    # `__SH_POPUP_CARDS` for the popup-restyle pass; the layer-titles
    # JS block already sets `window.__SH_POPUP_CARDS = true`, but we
    # also emit the literal here so a 32 KB head-scan reliably finds
    # it without depending on script parse order.
    m.get_root().html.add_child(folium.Element(
        "<script>window.__SH_LAZY_LAYERS = true; window.__SH_POPUP_CARDS = true; window.__SH_WEEKLY_NAV = true; window.__SH_WEEKLY_LEGEND = true; window.__SH_LEGEND_ADAPT = true; window.__SH_LEGEND_BULK = true; window.__SH_MAXPX_FIX = true; window.__SH_VARS_GHOST = true;</script>"
    ))

    # Save map
    m.save(output_file)
    print(f"[ML Map] Saved to {output_file}")

    return output_file


def _add_cluster_marker(feature_group, cluster, week_id, is_anomalous):
    """
    Add cluster marker to map.

    Args:
        feature_group: Folium FeatureGroup
        cluster: Row from cluster_agg DataFrame
        week_id: Week ID string
        is_anomalous: Boolean
    """
    cluster_label = cluster["cluster_label"]
    track_id = cluster["track_id"]
    status = cluster["cluster_status"]
    outlier_score = cluster["outlier_score"]
    pixel_count = cluster["pixel_count"]
    lat = cluster["lat"]
    lon = cluster["lon"]

    # Color by status
    status_colors = {
        "new": "#FFD700",  # Gold
        "continued": "#1E90FF",  # DodgerBlue
        "unknown": "#808080",  # Gray
    }
    fill_color = status_colors.get(status, "#808080")

    # Border color by anomaly
    border_color = "#FF4500" if is_anomalous else "#32CD32"  # OrangeRed : LimeGreen

    # Size by pixel count (logarithmic scale)
    marker_size = 8 + int(np.log1p(pixel_count) * 2)

    # Map cluster_status → SmartHarvest badge class
    status_key = (status or "unknown").lower()
    badge_cls = {
        "new": "sh-badge sh-badge--new",
        "continued": "sh-badge sh-badge--continued",
    }.get(status_key, "sh-badge sh-badge--unknown")
    status_label = (status or "unknown").upper()

    popup_html = (
        '<div class="sh-popup">'
        f'<div class="sh-popup__title">Cluster #{cluster_label}</div>'
        f'<div class="sh-popup__sub">Week {week_id} &middot; Track #{track_id}</div>'
        '<table class="sh-popup__kv">'
        f'<tr><td>Status</td><td><span class="{badge_cls}">{status_label}</span></td></tr>'
        f'<tr><td>Anomalous</td><td>{"Yes" if is_anomalous else "No"}</td></tr>'
        f'<tr><td>Outlier score</td><td>{outlier_score:.3f}</td></tr>'
        f'<tr><td>Pixel count</td><td>{int(pixel_count):,}</td></tr>'
        f'<tr><td>Lat / Lon</td><td>{lat:.5f}° / {lon:.5f}°</td></tr>'
        '</table>'
        '</div>'
    )

    folium.CircleMarker(
        location=[lat, lon],
        radius=marker_size,
        color=border_color,
        fill=True,
        fill_color=fill_color,
        fill_opacity=0.7,
        weight=2,
        popup=folium.Popup(popup_html, max_width=260),
        tooltip=f"Cluster {cluster_label} (Track {track_id})",
    ).add_to(feature_group)


def _create_legend(week_id):
    """Create legend HTML."""
    return f"""
    <div id="ml-legend" style="
        position: fixed;
        top: 10px;
        right: 10px;
        width: 180px;
        background-color: rgba(25,25,25,0.92);
        color: #eee;
        padding: 12px;
        border-radius: 8px;
        box-shadow: 0 0 15px rgba(0,0,0,0.5);
        font-family: Arial, sans-serif;
        font-size: 11px;
        z-index: 1000;
    ">
        <h4 style="margin: 0 0 10px 0; font-size: 13px; border-bottom: 1px solid #555; padding-bottom: 5px;">
            Anomaly Heatmap
        </h4>
        <div style="margin-bottom: 8px;">
            <b>Intensity Legend:</b><br>
            <div style="margin-top: 5px; height: 12px; width: 100%; background: linear-gradient(to right, blue, cyan, lime, yellow, orange, red); border-radius: 2px;"></div>
            <div style="display: flex; justify-content: space-between; margin-top: 4px; font-size: 9px; color: #aaa;">
                <span>Normal</span>
                <span>Anomalous</span>
            </div>
        </div>
        <div style="font-size: 9px; color: #888; margin-top: 10px; border-top: 1px solid #555; padding-top: 5px;">
            Week: {week_id}<br>
            Hotspots (Red) indicate high stress or vigor anomalies.
        </div>
    </div>
    """


if __name__ == "__main__":
    # Test
    create_ml_anomaly_map(
        "output/MyProject/ml_weekly",
        "2025-W45",
        "output/MyProject/ml_weekly/ml_map_2025-W45.html",
    )
