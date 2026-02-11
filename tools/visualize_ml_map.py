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

    # Layer 1: Anomaly Heatmap (weighted by outlier score)
    fg_heatmap = folium.FeatureGroup(name='Anomaly Heatmap', show=True)

    heat_data = [
        [row['lat'], row['lon'], row['outlier_score']]
        for _, row in df.iterrows()
        if not pd.isna(row['lat']) and not pd.isna(row['lon'])
    ]

    if heat_data:
        HeatMap(
            heat_data,
            radius=15,
            blur=20,
            min_opacity=0.3,
            gradient={
                0.0: 'blue',    # Normal
                0.3: 'cyan',
                0.5: 'lime',    # Medium
                0.7: 'yellow',
                0.85: 'orange',
                1.0: 'red'      # Anomalous
            }
        ).add_to(fg_heatmap)

    fg_heatmap.add_to(m)

    # Add layer control
    folium.LayerControl(position='topleft', collapsed=False).add_to(m)

    # Add legend
    legend_html = _create_legend(week_id)
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


    pass


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


if __name__ == '__main__':
    # Test
    create_ml_anomaly_map(
        'output/MyProject/ml_weekly',
        '2025-W45',
        'output/MyProject/ml_weekly/ml_map_2025-W45.html'
    )
