
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio

# Set default template for consistency with dark theme
pio.templates.default = "plotly_dark"

def create_temporal_trends(df):
    """
    Generate line chart for temporal monitoring.
    """
    if df is None or df.empty:
        return None
    
    # Filter for S2 variables
    s2_vars = ['NDVI', 'NDWI', 'MNDWI', 'NDRE', 'IRECI', 'S2REP']
    melted = df.melt(id_vars=['date'], value_vars=[c for c in s2_vars if c in df.columns], 
                     var_name='Index', value_name='Value')
    
    if melted.empty:
        return None

    fig = px.line(melted, x='date', y='Value', color='Index', 
                  title='Vegetation Indices Over Time',
                  color_discrete_sequence=px.colors.qualitative.Pastel)
    
    fig.update_layout(
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font_color='#ccc',
        hovermode="x unified"
    )
    return pio.to_html(fig, full_html=False, include_plotlyjs='cdn')

def create_histograms(df):
    """
    Generate histograms for key variables.
    """
    if df is None or df.empty:
        return None

    # Select relevant columns for user interest
    target_cols = ['NDVI', 'NDWI', 'MNDWI', 'NDRE', 'IRECI', 'S2REP', 
                   'VH', 'VV', 'Ratio', 'LST', 'Slope']
    
    # Check which actually exist in DF
    cols = [c for c in target_cols if c in df.columns]
    
    # Also include any other numeric columns if desired, but user said "make sense to be shown", 
    # so specific list is safer to avoid IDs/lat/lon.
    # But let's verify if they have ANY data (not all NaN)
    valid_cols = []
    for c in cols:
        if df[c].notna().any():
            valid_cols.append(c)
    
    if not valid_cols:
        return "<p>No numeric data available for histograms.</p>"

    # Calculate grid dimensions clearly
    import math
    n_plots = len(valid_cols)
    n_cols = 3  # Fixed number of columns for layout
    n_rows = math.ceil(n_plots / n_cols)
    
    from plotly.subplots import make_subplots
    fig = make_subplots(
        rows=n_rows, 
        cols=n_cols, 
        subplot_titles=valid_cols,
        vertical_spacing=0.1
    )
    
    error_list = []
    
    for i, col in enumerate(valid_cols):
        row = (i // n_cols) + 1
        col_idx = (i % n_cols) + 1
        
        try:
            fig.add_trace(
                go.Histogram(x=df[col], name=col, nbinsx=30),
                row=row, col=col_idx
            )
        except Exception as e:
            error_list.append(f"Error plotting {col}: {str(e)}")
            # Add annotation instead
            fig.add_annotation(
                text="Error",
                xref=f"x{i+1}", yref=f"y{i+1}",
                showarrow=False,
                row=row, col=col_idx
            )

    title_text = "Distributions"
    if error_list:
        title_text += " (Warnings: " + ", ".join(error_list) + ")"

    fig.update_layout(
        title_text=title_text,
        showlegend=False,
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font_color='#ccc',
        height=300 * n_rows,  # Adjust height based on rows
        hovermode="x"
    )
    return pio.to_html(fig, full_html=False, include_plotlyjs='cdn')

def create_correlation_matrix(df):
    """
    Generate correlation heatmap.
    """
    if df is None or df.empty:
        return None
        
    # Select numeric columns
    numeric_df = df.select_dtypes(include=['float64', 'int64'])
    # Drop geo columns
    cols = [c for c in numeric_df.columns if c not in ['lat', 'lon', '.geo', 'spatial_id']]
    
    if len(cols) < 2:
        return None
        
    corr = numeric_df[cols].corr()
    
    fig = px.imshow(corr, text_auto='.2f', aspect="auto",
                    color_continuous_scale='RdBu_r', zmin=-1, zmax=1,
                    title="Feature Correlation Matrix")
                    
    fig.update_layout(
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font_color='#ccc'
    )
    return pio.to_html(fig, full_html=False, include_plotlyjs=False)
