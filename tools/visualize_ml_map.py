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
        return data['coordinates']  # [lon, lat]
    except Exception:
        return [0, 0]


def create_ml_anomaly_map(ml_dir, week_id, output_file):
    """
    Create dedicated ML anomaly detection map for a specific week.

    Args:
        ml_dir: Path to ml_weekly directory
        week_id: Week ID (e.g., '2025-W45')
        output_file: Path for output HTML

    Returns:
        str: Path to output HTML, or None on error
    """
    week_dir = os.path.join(ml_dir, 'weekly', week_id)
    cluster_csv = os.path.join(week_dir, f'cluster_map_{week_id}.csv')
    outlier_csv = os.path.join(week_dir, f'outlier_map_{week_id}.csv')

    if not os.path.exists(cluster_csv):
        print(f"[ML Map] Error: {cluster_csv} not found")
        return None

    print(f"[ML Map] Loading {cluster_csv}...")
    df = pd.read_csv(cluster_csv)

    # Parse coordinates if needed
    if 'lat' not in df.columns or 'lon' not in df.columns:
        if '.geo' in df.columns:
            df['coords'] = df['.geo'].apply(_parse_coords)
            df['lon'] = df['coords'].apply(lambda x: x[0])
            df['lat'] = df['coords'].apply(lambda x: x[1])

    center_lat = df['lat'].mean()
    center_lon = df['lon'].mean()

    # Create base map
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=16,
        tiles='Esri.WorldImagery'
    )

    # Determine anomalous clusters (outlier_score > 95th percentile)
    outlier_threshold = df['outlier_score'].quantile(0.95)

    # Aggregate by cluster
    agg_dict = {
        'outlier_score': 'mean',
        'track_id': 'first',
        'lat': 'mean',
        'lon': 'mean'
    }

    # Add cluster_status if available (backward compatibility)
    if 'cluster_status' in df.columns:
        agg_dict['cluster_status'] = 'first'

    cluster_agg = df[df['cluster_label'] != -1].groupby('cluster_label').agg(agg_dict).reset_index()

    # Set default status if column doesn't exist
    if 'cluster_status' not in cluster_agg.columns:
        cluster_agg['cluster_status'] = 'unknown'

    cluster_agg['pixel_count'] = df[df['cluster_label'] != -1].groupby('cluster_label').size().values
    cluster_agg['is_anomalous'] = cluster_agg['outlier_score'] > outlier_threshold

    # Layer 1: Normal Clusters
    fg_normal = folium.FeatureGroup(name='Normal Clusters', show=True)

    normal_clusters = cluster_agg[~cluster_agg['is_anomalous']]

    for _, cluster in normal_clusters.iterrows():
        _add_cluster_marker(fg_normal, cluster, week_id, is_anomalous=False)

    fg_normal.add_to(m)

    # Layer 2: Anomalous Clusters
    fg_anomalous = folium.FeatureGroup(name='Anomalous Clusters', show=True)

    anomalous_clusters = cluster_agg[cluster_agg['is_anomalous']]

    for _, cluster in anomalous_clusters.iterrows():
        _add_cluster_marker(fg_anomalous, cluster, week_id, is_anomalous=True)

    fg_anomalous.add_to(m)

    # Layer 3: Outlier Heatmap
    if os.path.exists(outlier_csv):
        fg_heatmap = folium.FeatureGroup(name='Outlier Heatmap', show=False)

        outlier_df = pd.read_csv(outlier_csv)

        if 'lat' not in outlier_df.columns or 'lon' not in outlier_df.columns:
            if '.geo' in outlier_df.columns:
                outlier_df['coords'] = outlier_df['.geo'].apply(_parse_coords)
                outlier_df['lon'] = outlier_df['coords'].apply(lambda x: x[0])
                outlier_df['lat'] = outlier_df['coords'].apply(lambda x: x[1])

        heat_data = [
            [row['lat'], row['lon'], row['outlier_score']]
            for _, row in outlier_df.iterrows()
            if not pd.isna(row['lat']) and not pd.isna(row['lon'])
        ]

        if heat_data:
            HeatMap(
                heat_data,
                radius=15,
                blur=25,
                max_zoom=18,
                gradient={0.0: 'blue', 0.5: 'yellow', 0.75: 'orange', 1.0: 'red'}
            ).add_to(fg_heatmap)

        fg_heatmap.add_to(m)

    # Add layer control
    folium.LayerControl(position='topleft', collapsed=False).add_to(m)

    # Add legend
    legend_html = _create_legend(week_id, len(normal_clusters), len(anomalous_clusters))
    m.get_root().html.add_child(folium.Element(legend_html))

    # Dark mode CSS
    dark_css = """
    <style>
        .leaflet-control-layers {
            background-color: rgba(25,25,25,0.92) !important;
            color: #eee !important;
            border: none !important;
            border-radius: 8px !important;
            box-shadow: 0 0 15px rgba(0,0,0,0.5) !important;
        }
        .leaflet-control-layers-base label,
        .leaflet-control-layers-overlays label {
            color: #eee !important;
            font-size: 11px !important;
        }
    </style>
    """
    m.get_root().html.add_child(folium.Element(dark_css))

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
    cluster_label = cluster['cluster_label']
    track_id = cluster['track_id']
    status = cluster['cluster_status']
    outlier_score = cluster['outlier_score']
    pixel_count = cluster['pixel_count']
    lat = cluster['lat']
    lon = cluster['lon']

    # Color by status
    status_colors = {
        'new': '#FFD700',       # Gold
        'continued': '#1E90FF',  # DodgerBlue
        'unknown': '#808080'     # Gray
    }
    fill_color = status_colors.get(status, '#808080')

    # Border color by anomaly
    border_color = '#FF4500' if is_anomalous else '#32CD32'  # OrangeRed : LimeGreen

    # Size by pixel count (logarithmic scale)
    marker_size = 8 + int(np.log1p(pixel_count) * 2)

    # Popup HTML
    popup_html = f"""
    <div style="font-family: Arial; font-size: 12px; min-width: 200px;">
        <b style="font-size: 14px;">Cluster {cluster_label}</b><br>
        <hr style="margin: 5px 0;">
        <b>Week:</b> {week_id}<br>
        <b>Track ID:</b> {track_id}<br>
        <b>Status:</b> <span style="background-color: {fill_color}; padding: 2px 6px; border-radius: 3px; color: black; font-weight: bold;">{status.upper()}</span><br>
        <b>Anomalous:</b> {'Yes' if is_anomalous else 'No'}<br>
        <b>Outlier Score:</b> {outlier_score:.3f}<br>
        <b>Pixel Count:</b> {pixel_count}<br>
        <b>Location:</b> {lat:.5f}°N, {lon:.5f}°E<br>
        <hr style="margin: 5px 0;">
        <small style="color: #888;">Click for details in sidebar</small>
    </div>
    """

    folium.CircleMarker(
        location=[lat, lon],
        radius=marker_size,
        color=border_color,
        fill=True,
        fill_color=fill_color,
        fill_opacity=0.7,
        weight=2,
        popup=folium.Popup(popup_html, max_width=250),
        tooltip=f"Cluster {cluster_label} (Track {track_id})"
    ).add_to(feature_group)


def _create_legend(week_id, normal_count, anomalous_count):
    """Create legend HTML."""
    return f"""
    <div id="ml-legend" style="
        position: fixed;
        top: 10px;
        right: 10px;
        width: 220px;
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
            ML Clustering — {week_id}
        </h4>

        <div style="margin-bottom: 8px;">
            <b>Cluster Status:</b><br>
            <div style="margin-left: 10px; margin-top: 4px;">
                <span style="display: inline-block; width: 12px; height: 12px; background-color: #FFD700; border: 2px solid #fff; border-radius: 50%;"></span> NEW<br>
                <span style="display: inline-block; width: 12px; height: 12px; background-color: #1E90FF; border: 2px solid #fff; border-radius: 50%;"></span> CONTINUED
            </div>
        </div>

        <div style="margin-bottom: 8px;">
            <b>Cluster Type:</b><br>
            <div style="margin-left: 10px; margin-top: 4px;">
                <span style="display: inline-block; width: 12px; height: 12px; background-color: #aaa; border: 2px solid #32CD32; border-radius: 50%;"></span> Normal ({normal_count})<br>
                <span style="display: inline-block; width: 12px; height: 12px; background-color: #aaa; border: 2px solid #FF4500; border-radius: 50%;"></span> Anomalous ({anomalous_count})
            </div>
        </div>

        <div style="font-size: 9px; color: #888; margin-top: 10px; border-top: 1px solid #555; padding-top: 5px;">
            Size = Pixel count<br>
            Click marker for details
        </div>
    </div>
    """


if __name__ == '__main__':
    # Test
    create_ml_anomaly_map(
        'output/MyProject/ml_weekly',
        '2025-W45',
        'output/MyProject/ml_weekly/ml_map_2025-W45.html'
    )
