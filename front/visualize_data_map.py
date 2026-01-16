import pandas as pd
import folium
import json
import os
import branca.colormap as cm

def create_verification_map(csv_path='output/SmartHarvest_DataCube_Temporal.csv', output_file='output/SmartHarvest_Verification_Map.html'):
    if not os.path.exists(csv_path):
        print(f"Error: {csv_path} not found.")
        return None

    print(f"Loading {csv_path}...")
    df = pd.read_csv(csv_path)
    
    # ... (rest of the logic remains the same) ...
    
    # Extract coordinates from .geo column
    # Format: {"geodesic":false,"type":"Point","coordinates":[12.8295,46.1054]}
    def parse_coords(geo_str):
        try:
            data = json.loads(geo_str)
            return data['coordinates'] # [lon, lat]
        except:
            return [0, 0]

    df['coords'] = df['.geo'].apply(parse_coords)
    df['lon'] = df['coords'].apply(lambda x: x[0])
    df['lat'] = df['coords'].apply(lambda x: x[1])
    
    # Center map
    center_lat = df['lat'].mean()
    center_lon = df['lon'].mean()
    
    m = folium.Map(location=[center_lat, center_lon], zoom_start=16, tiles='Esri.WorldImagery')
    
    # Define layers to visualize
    # Define layers to visualize
    layers_config = [
        # Vigor & Stress
        {'name': 'NDVI Peak', 'col': 'NDVI_Peak', 'colors': ['red', 'yellow', 'green']},
        {'name': 'NDVI Delta', 'col': 'NDVI_Delta', 'colors': ['blue', 'white', 'red']}, # Blue=Growth, Red=Senescence
        {'name': 'NDMI Peak (Water)', 'col': 'NDMI_Peak', 'colors': ['red', 'yellow', 'blue']}, # Blue=High Moisture
        {'name': 'NDRE Peak (Nitrogen)', 'col': 'NDRE_Peak', 'colors': ['red', 'yellow', 'green']}, # Green=High Chlorophyll
        {'name': 'VH Drop (Structure)', 'col': 'VH_Drop', 'colors': ['green', 'yellow', 'red']}, # Red=High Drop
        
        # Topography & Hydrology
        {'name': 'TWI (Water)', 'col': 'TWI', 'colors': ['brown', 'yellow', 'blue']}, # Blue=Wet
        {'name': 'Solar Radiation', 'col': 'Solar_Rad', 'colors': ['blue', 'yellow', 'red']}, # Red=High Sun
        {'name': 'Slope', 'col': 'Slope', 'colors': ['green', 'yellow', 'brown']},
        # Northness/Eastness removed in v2.1
        
        # Phenology
        {'name': 'Time to Peak', 'col': 'Time_to_Peak', 'colors': ['green', 'yellow', 'red']},
        {'name': 'Green Up Rate', 'col': 'Green_Up', 'colors': ['brown', 'yellow', 'green']},
        {'name': 'Senescence Rate', 'col': 'Senescence', 'colors': ['green', 'yellow', 'brown']},
        
        # Texture
        {'name': 'Texture Entropy', 'col': 'Texture_Entropy', 'colors': ['black', 'gray', 'white']},
        {'name': 'Texture Contrast', 'col': 'Texture_Contrast', 'colors': ['white', 'gray', 'black']},
        
        # Thermal
        {'name': 'LST (Temp)', 'col': 'LST', 'colors': ['blue', 'yellow', 'red']},
        # LST Delta removed in v2.1
        {'name': 'LST Stability', 'col': 'LST_Stability', 'colors': ['green', 'yellow', 'red']} # Red=Unstable
    ]

    # Tooltips for layers
    layer_tooltips = {
        'Texture Entropy': 'Disorder. White=High Heterogeneity.',
        'Texture Contrast': 'Local Contrast. White=High.',
        'LST (Temp)': 'Surface Temp. Red=Hot.',
        # LST Delta removed
        'LST Stability': 'Temp Variability. Red=Unstable (Spikes).'
    }
    
    print("Adding layers to map...")
    
    # Generate Custom Legend Panel HTML content (inner part)
    legend_content = """
        <h4 style='margin-top: 0; margin-bottom: 15px; font-size: 14px; text-transform: uppercase; border-bottom: 1px solid #ccc; padding-bottom: 5px;'>Analysis Legend</h4>
    """
    
    for layer in layers_config:
        col_name = layer['col']
        if col_name not in df.columns:
            continue
            
        # Get min/max for labels
        vmin = df[col_name].min()
        vmax = df[col_name].max()
        
        # Create CSS Gradient
        colors = layer['colors']
        gradient_str = ", ".join(colors)
        
        legend_content += f"""
        <div style='margin-bottom: 6px;'> <!-- Reduced margin -->
            <div style='font-weight: 600; font-size: 10px; margin-bottom: 1px; color: #ddd;'>{layer['name']}</div> <!-- Reduced font -->
            <div style='display: flex; align-items: center; justify-content: space-between;'>
                <span style='font-size: 8px; color: #aaa; width: 20px;'>{vmin:.1f}</span>
                <div style='
                    flex-grow: 1; 
                    height: 6px; /* Thinner bar */
                    background: linear-gradient(to right, {gradient_str}); 
                    border-radius: 2px; 
                    margin: 0 4px;
                    border: 1px solid #555;
                '></div>
                <span style='font-size: 8px; color: #aaa; width: 20px; text-align: right;'>{vmax:.1f}</span>
            </div>
        </div>
        """
        
        # Add data to map (CircleMarkers) - Logic remains same
        fg = folium.FeatureGroup(name=layer['name'], show=(col_name == 'NDVI_Peak'))
        
        # Create a colormap object just for the color mapping logic
        colormap = cm.LinearColormap(colors=layer['colors'], vmin=vmin, vmax=vmax)
        
        for idx, row in df.iterrows():
            val = row[col_name]
            color = colormap(val)
            
            popup_text = f"""
            <b>{layer['name']}</b><br>
            Value: {val:.4f}<br>
            """
            
            folium.CircleMarker(
                location=[row['lat'], row['lon']],
                radius=4,
                color=color,
                fill=True,
                fill_color=color,
                fill_opacity=0.8,
                popup=folium.Popup(popup_text, max_width=200)
            ).add_to(fg)
            
        fg.add_to(m)

    # Define Custom Control using MacroElement
    from branca.element import MacroElement
    from jinja2 import Template

    class CustomLegend(MacroElement):
        _template = Template("""
            {% macro script(this, kwargs) %}
            var legend = L.control({position: 'topright'});
            legend.onAdd = function (map) {
                var div = L.DomUtil.create('div', 'info legend');
                div.innerHTML = `{{ this.content }}`;
                div.style.backgroundColor = 'rgba(30, 30, 30, 0.9)'; // Dark background
                div.style.color = '#eee'; // Light text
                div.style.padding = '10px'; /* Reduced padding */
                div.style.borderRadius = '8px';
                div.style.boxShadow = '0 0 15px rgba(0,0,0,0.5)';
                div.style.width = '240px';
                div.style.maxHeight = '95vh'; /* Extended height */
                div.style.overflowY = 'auto';
                div.style.fontSize = '10px'; /* Reduced font */
                div.style.fontFamily = "'Segoe UI', sans-serif";
                return div;
            };
            legend.addTo({{ this._parent.get_name() }});
            {% endmacro %}
        """)
        def __init__(self, content):
            super(CustomLegend, self).__init__()
            self._name = 'CustomLegend'
            self.content = content

    # Add Custom Legend Control FIRST
    m.add_child(CustomLegend(legend_content))

    # Add Layer Control to TOP LEFT (User request)
    folium.LayerControl(position='topleft', collapsed=False).add_to(m)
    
    # Inject CSS for Dark Mode Layer Control (No Tooltips)
    dark_mode_css = """
    <style>
        /* Compact Layer Control */
        .leaflet-control-layers {
            background-color: rgba(30, 30, 30, 0.9) !important;
            color: #eee !important;
            border: none !important;
            border-radius: 8px !important;
            box-shadow: 0 0 15px rgba(0,0,0,0.5) !important;
            padding: 6px !important; /* Reduced padding */
            font-family: 'Segoe UI', sans-serif !important;
            max-height: 70vh !important;
            overflow-y: auto !important;
        }
        .leaflet-control-layers-expanded {
            padding: 8px !important;
        }
        .leaflet-control-layers-separator {
            border-top: 1px solid #555 !important;
        }
        .leaflet-control-layers-base label, .leaflet-control-layers-overlays label {
            margin-bottom: 2px !important;
            display: flex !important;
            align-items: center !important;
            font-size: 10px !important; /* Reduced font */
        }
        .leaflet-control-layers-base input, .leaflet-control-layers-overlays input {
            margin-right: 6px !important;
        }
    </style>
    """
    m.get_root().html.add_child(folium.Element(dark_mode_css))
    
    m.save(output_file)
    print(f"Map saved to {output_file}")
    return output_file

if __name__ == "__main__":
    create_verification_map()
