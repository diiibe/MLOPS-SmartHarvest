"""Central schema and column definitions for the temporal pipeline."""

from typing import List

# Canonical column order in the temporal CSV
TEMPORAL_COLUMNS: List[str] = [
    'date',
    'lat',
    'lon',
    '.geo',
    'satellite',
    # Sentinel-2
    'NDVI',
    'NDWI',
    'MNDWI',
    'NDRE',
    'IRECI',
    'S2REP',
    # Sentinel-1
    'VH',
    'VV',
    'Ratio',
    # Landsat-8/9
    'LST',
    # Topography (SRTM - static)
    'Slope',
]

# Human-readable labels for UI/legend
COLUMN_LABELS = {
    'NDVI': 'Vegetation Index (NDVI)',
    'NDWI': 'Water Index (NDWI)',
    'MNDWI': 'Modified Water Index (MNDWI)',
    'NDRE': 'Red-Edge Index (NDRE)',
    'IRECI': 'Chlorophyll Index (IRECI)',
    'S2REP': 'Red-Edge Position (S2REP)',
    'VH': 'Radar VH Backscatter',
    'VV': 'Radar VV Backscatter',
    'Ratio': 'Radar VH/VV Ratio',
    'LST': 'Land Surface Temperature (°C)',
    'Slope': 'Slope (degrees)',
}

# Color ramps for map visualization (low -> high)
COLUMN_COLORS = {
    'NDVI': ['red', 'yellow', 'green'],
    'NDWI': ['red', 'yellow', 'blue'],
    'MNDWI': ['red', 'yellow', 'blue'],
    'NDRE': ['red', 'yellow', 'green'],
    'IRECI': ['red', 'yellow', 'green'],
    'S2REP': ['red', 'yellow', 'green'],
    'VH': ['red', 'yellow', 'blue'],
    'VV': ['red', 'yellow', 'blue'],
    'Ratio': ['red', 'yellow', 'blue'],
    'LST': ['blue', 'yellow', 'red'],
    'Slope': ['green', 'yellow', 'brown'],
}

# Which satellite provides each variable
COLUMN_SATELLITE = {
    'NDVI': 'S2',
    'NDWI': 'S2',
    'MNDWI': 'S2',
    'NDRE': 'S2',
    'IRECI': 'S2',
    'S2REP': 'S2',
    'VH': 'S1',
    'VV': 'S1',
    'Ratio': 'S1',
    'LST': 'L8',
    'Slope': 'SRTM',
}

# All measurable (non-positional) statistics columns
STATS_COLUMNS = ['NDVI', 'NDWI', 'MNDWI', 'NDRE', 'IRECI', 'S2REP',
                 'VH', 'VV', 'Ratio', 'LST', 'Slope']
