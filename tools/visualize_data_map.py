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

import schema


def _parse_coords(geo_str):
    """Parse .geo GeoJSON string to [lon, lat]."""
    try:
        data = json.loads(geo_str) if isinstance(geo_str, str) else geo_str
        return data['coordinates']  # [lon, lat]
    except Exception:
        return [0, 0]


def get_available_dates(csv_path):
    """Return sorted list of unique dates in the temporal CSV."""
    if not os.path.exists(csv_path):
        return []
    try:
        df = pd.read_csv(csv_path, usecols=['date'])
        return sorted(df['date'].dropna().unique().tolist())
    except Exception:
        return []


def _add_ml_cluster_layer(m, ml_dir, df):
    """
    Add ML weekly clustering layer to map.
    Shows clusters from latest processed week.
    """
    # Find latest week folder
    weekly_dir = os.path.join(ml_dir, 'weekly')
    if not os.path.exists(weekly_dir):
        return

    week_folders = [f for f in os.listdir(weekly_dir) if f.startswith('20')]
    if not week_folders:
        return

    latest_week = sorted(week_folders)[-1]
    cluster_csv = os.path.join(weekly_dir, latest_week, f'cluster_map_{latest_week}.csv')

    if not os.path.exists(cluster_csv):
        return

    # Load cluster data
    cluster_df = pd.read_csv(cluster_csv)

    # Merge with main df to get coordinates if needed
    if 'lat' not in cluster_df.columns or 'lon' not in cluster_df.columns:
        if 'spatial_id' in cluster_df.columns and 'spatial_id' in df.columns:
            # Merge on spatial_id
            coords_df = df[['spatial_id', 'lat', 'lon']].drop_duplicates('spatial_id')
            cluster_df = cluster_df.merge(coords_df, on='spatial_id', how='left')

    # Create cluster layer
    fg = folium.FeatureGroup(name=f'ML Clusters ({latest_week})', show=False)

    # Color palette for clusters
    unique_clusters = cluster_df['cluster_label'].unique()
    unique_clusters = [c for c in unique_clusters if c != -1]  # Exclude noise
    colors_palette = ['#e74c3c', '#3498db', '#2ecc71', '#f39c12', '#9b59b6',
                     '#1abc9c', '#e67e22', '#34495e', '#16a085', '#c0392b']

    cluster_colors = {}
    for i, c in enumerate(unique_clusters):
        cluster_colors[c] = colors_palette[i % len(colors_palette)]
    cluster_colors[-1] = '#7f8c8d'  # Gray for noise

    # Add markers
    for _, row in cluster_df.iterrows():
        if pd.isna(row.get('lat')) or pd.isna(row.get('lon')):
            continue

        cluster_label = row['cluster_label']
        track_id = row.get('track_id', -1)
        outlier_score = row.get('outlier_score', 0)

        color = cluster_colors.get(cluster_label, '#7f8c8d')

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
            location=[row['lat'], row['lon']],
            radius=marker_size,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.7,
            weight=1,
            popup=folium.Popup(popup_text, max_width=220)
        ).add_to(fg)

    fg.add_to(m)
    print(f"[Map] Added ML cluster layer: {latest_week} ({len(cluster_df)} pixels, {len(unique_clusters)} clusters)")


def create_verification_map(csv_path, output_file, selected_date=None):
    """
    Create a Folium map with one layer per statistic.

    Args:
        csv_path: Path to the temporal SmartHarvest CSV.
        output_file: Path for the output HTML map.
        selected_date: Date string (YYYY-MM-DD) to display.
                      If None, each variable uses its own latest date with data.
    Returns:
        str: Path to the output HTML file, or None on error.
    """
    if not os.path.exists(csv_path):
        print(f"Error: {csv_path} not found.")
        return None

    print(f"Loading {csv_path}...")
    df = pd.read_csv(csv_path)

    # Parse coordinates for all rows
    df['coords'] = df['.geo'].apply(_parse_coords)
    df['lon'] = df['coords'].apply(lambda x: x[0])
    df['lat'] = df['coords'].apply(lambda x: x[1])

    center_lat = df['lat'].mean()
    center_lon = df['lon'].mean()

    m = folium.Map(location=[center_lat, center_lon], zoom_start=16,
                   tiles='Esri.WorldImagery')

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

    for col in numeric_stats:
        if col not in df.columns:
            continue

        # Filter data for this column
        if selected_date:
            # Use specified date for all columns
            col_df = df[df['date'] == selected_date][['lat', 'lon', '.geo', 'date', col]].copy()
            display_date = selected_date
        else:
            # Use latest date with data for this column
            col_data_df = df[df[col].notna()].copy()
            if col_data_df.empty:
                continue
            display_date = col_data_df['date'].max()
            col_df = col_data_df[col_data_df['date'] == display_date][['lat', 'lon', '.geo', 'date', col]].copy()

        # Average if multiple points same location same day
        col_df = col_df.groupby(['.geo', 'lat', 'lon'], as_index=False)[col].mean()

        col_data = col_df[col].dropna()
        if col_data.empty:
            continue

        vmin = float(col_data.min())
        vmax = float(col_data.max())
        if np.isnan(vmin) or np.isnan(vmax) or vmin == vmax:
            continue

        label = schema.COLUMN_LABELS.get(col, col)
        colors = schema.COLUMN_COLORS.get(col, ['red', 'yellow', 'green'])
        colormap = cm.LinearColormap(colors=colors, vmin=vmin, vmax=vmax)

        gradient_str = ', '.join(colors)
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
        show = (col == 'NDVI')
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
                location=[row['lat'], row['lon']],
                radius=4,
                color=color,
                fill=True,
                fill_color=color,
                fill_opacity=0.85,
                popup=folium.Popup(popup_text, max_width=220)
            ).add_to(fg)

        fg.add_to(m)

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
            self._name = 'CustomLegend'
            self.content = content

    # Add ML Weekly Clustering Layer (if available)
    ml_dir = os.path.join(os.path.dirname(csv_path), 'ml_weekly')
    if os.path.exists(ml_dir):
        try:
            _add_ml_cluster_layer(m, ml_dir, df)
        except Exception as e:
            print(f"[Map] Could not add ML cluster layer: {e}")

    m.add_child(CustomLegend(legend_html))
    folium.LayerControl(position='topleft', collapsed=False).add_to(m)

    # Dark mode CSS for layer control
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
            max-height: 65vh !important;
            overflow-y: auto !important;
        }
        .leaflet-control-layers-base label,
        .leaflet-control-layers-overlays label {
            margin-bottom: 2px !important;
            font-size: 10px !important;
        }
    </style>
    """
    m.get_root().html.add_child(folium.Element(dark_css))

    m.save(output_file)
    print(f"Map saved to {output_file}")
    return output_file


if __name__ == "__main__":
    create_verification_map(
        'output/New_Vineyard/SmartHarvest_New_Vineyard.csv',
        'output/New_Vineyard/Map_New_Vineyard.html'
    )
