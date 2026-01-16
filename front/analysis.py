import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import json
import os

def generate_analysis_dashboard(project_name, output_dir):
    """
    Generates interactive Plotly charts for the dashboard.
    Returns a dictionary of HTML strings for each chart.
    """
    
    # Paths
    ts_path = os.path.join(output_dir, f'timeseries_{project_name}.json')
    csv_path = os.path.join(output_dir, f'SmartHarvest_{project_name}.csv')
    
    charts = {}
    
    # 1. Temporal Trends (Time Series)
    if os.path.exists(ts_path):
        with open(ts_path, 'r') as f:
            ts_data = json.load(f)
            
        s2_ts = pd.DataFrame(ts_data.get('sentinel2', []))
        s1_ts = pd.DataFrame(ts_data.get('sentinel1', []))
        phenology = ts_data.get('phenology', {})
        
        # Create Subplots (NDVI on top, VH on bottom)
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                            vertical_spacing=0.1,
                            subplot_titles=("Vegetation Health (NDVI)", "Structure/Moisture (VH Backscatter)"))
        
        # NDVI Trace
        if not s2_ts.empty:
            fig.add_trace(go.Scatter(x=s2_ts['date'], y=s2_ts['value'], 
                                     mode='lines+markers', name='NDVI',
                                     line=dict(color='#2ecc71', width=2)), row=1, col=1)
            
        # VH Trace
        if not s1_ts.empty:
            fig.add_trace(go.Scatter(x=s1_ts['date'], y=s1_ts['value'], 
                                     mode='lines+markers', name='VH (dB)',
                                     line=dict(color='#3498db', width=2)), row=2, col=1)
            
        # Add Phenological Windows (Shading)
        t1_start = phenology.get('T1', '').split(' to ')[0]
        t1_end = phenology.get('T1', '').split(' to ')[1]
        t2_start = phenology.get('T2', '').split(' to ')[0]
        t2_end = phenology.get('T2', '').split(' to ')[1]
        
        # Add shapes for T1 and T2
        shapes = []
        if t1_start and t1_end:
            shapes.append(dict(type="rect", xref="x", yref="paper",
                               x0=t1_start, y0=0, x1=t1_end, y1=1,
                               fillcolor="rgba(46, 204, 113, 0.1)", layer="below", line_width=0))
        if t2_start and t2_end:
            shapes.append(dict(type="rect", xref="x", yref="paper",
                               x0=t2_start, y0=0, x1=t2_end, y1=1,
                               fillcolor="rgba(231, 76, 60, 0.1)", layer="below", line_width=0))
            
        fig.update_layout(shapes=shapes, template="plotly_dark", height=600,
                          title_text="Temporal Dynamics & Phenological Phases")
        
        charts['temporal_trends'] = fig.to_html(full_html=False, include_plotlyjs='cdn')
        
    # 2. Distribution Analysis (Box Plots & Histograms)
    if os.path.exists(csv_path):
        df = pd.read_csv(csv_path)
        
        # Filter numeric columns only
        numeric_cols = df.select_dtypes(include=['float64', 'int64']).columns
        # Exclude coordinates if present
        cols_to_plot = [c for c in numeric_cols if c not in ['lon', 'lat', '.geo', 'system:index']]
        
        # A. Box Plot of Key Metrics (Updated for v2.0)
        fig_box = make_subplots(rows=1, cols=3, subplot_titles=("NDVI Delta", "VH Drop", "TWI"))
        
        if 'NDVI_Delta' in df.columns:
            fig_box.add_trace(go.Box(y=df['NDVI_Delta'], name='NDVI Delta', marker_color='#e74c3c'), row=1, col=1)
        if 'VH_Drop' in df.columns:
            fig_box.add_trace(go.Box(y=df['VH_Drop'], name='VH Drop', marker_color='#f39c12'), row=1, col=2)
        if 'TWI' in df.columns:
            fig_box.add_trace(go.Box(y=df['TWI'], name='TWI', marker_color='#3498db'), row=1, col=3)
            
        fig_box.update_layout(template="plotly_dark", height=400, title_text="Key Feature Distributions")
        charts['distributions'] = fig_box.to_html(full_html=False, include_plotlyjs=False)
        
        # B. Correlation Matrix (Heatmap)
        corr_matrix = df[cols_to_plot].corr()
        fig_corr = px.imshow(corr_matrix, text_auto=True, aspect="auto",
                             color_continuous_scale='RdBu_r', origin='lower',
                             title="Feature Correlation Matrix")
        fig_corr.update_layout(template="plotly_dark", height=600)
        charts['correlation'] = fig_corr.to_html(full_html=False, include_plotlyjs=False)
        
        # C. Histograms (All Stats)
        # We create a figure with many subplots
        num_vars = len(cols_to_plot)
        rows = (num_vars // 3) + 1
        fig_hist = make_subplots(rows=rows, cols=3, subplot_titles=cols_to_plot)
        
        for i, col in enumerate(cols_to_plot):
            row = (i // 3) + 1
            col_idx = (i % 3) + 1
            fig_hist.add_trace(go.Histogram(x=df[col], name=col, marker_color='#3498db'), row=row, col=col_idx)
            
        fig_hist.update_layout(template="plotly_dark", height=300*rows, title_text="Full Statistical Distributions", showlegend=False)
        charts['histograms'] = fig_hist.to_html(full_html=False, include_plotlyjs=False)
        
        # 3. Scatter Plot (NDVI Delta vs VH Drop) - Anomaly Detection
        if 'NDVI_Delta' in df.columns and 'VH_Drop' in df.columns:
            fig_scatter = px.scatter(df, x='NDVI_Delta', y='VH_Drop', 
                                     color='NDVI_Peak', title="Anomaly Detection: Vegetation vs Structure Change",
                                     labels={'NDVI_Delta': 'Vegetation Change (NDVI Delta)', 'VH_Drop': 'Structural Loss (VH Drop)'},
                                     template="plotly_dark")
            charts['scatter'] = fig_scatter.to_html(full_html=False, include_plotlyjs=False)
            
        # 4. 3D Scatter (LST vs NDVI vs TWI) - Updated for v2.0
        if 'LST' in df.columns and 'NDVI_Delta' in df.columns and 'TWI' in df.columns:
            fig_3d = px.scatter_3d(df, x='NDVI_Delta', y='LST', z='TWI',
                                   color='VH_Drop', title="Multi-Dimensional Analysis (NDVI vs LST vs TWI)",
                                   template="plotly_dark")
            fig_3d.update_layout(height=700)
            charts['scatter_3d'] = fig_3d.to_html(full_html=False, include_plotlyjs=False)
            
        # 5. TWI vs NDVI Scatter (New for v2.0)
        if 'TWI' in df.columns and 'NDVI_Peak' in df.columns:
            fig_twi = px.scatter(df, x='TWI', y='NDVI_Peak',
                                 color='Slope', title="Hydrology Analysis: TWI vs Peak Vigor",
                                 labels={'TWI': 'Topographic Wetness Index', 'NDVI_Peak': 'Max Vigor'},
                                 template="plotly_dark")
            charts['twi_scatter'] = fig_twi.to_html(full_html=False, include_plotlyjs=False)
            
    return charts
