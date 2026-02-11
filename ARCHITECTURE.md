# SmartHarvest MLOps - Architecture & Usage Guide

Complete guide to understanding and using the SmartHarvest vineyard analysis pipeline.

---

## 📋 Table of Contents

1. [Quick Start](#quick-start)
2. [Architecture Overview](#architecture-overview)
3. [Pipeline Flow](#pipeline-flow)
4. [Module Reference](#module-reference)
5. [Data Schemas](#data-schemas)
6. [Usage Examples](#usage-examples)
7. [Extending the Pipeline](#extending-the-pipeline)
8. [Troubleshooting](#troubleshooting)

---

## 🚀 Quick Start

### Installation
```bash
# Clone repository
git clone <your-repo-url>
cd MLOps

# Install dependencies
pip install -r requirements.txt

# Authenticate Google Earth Engine
earthengine authenticate
```

### Run Basic Pipeline
```bash
# 1. Configure your vineyard ROI in config.py
# 2. Run pipeline
python main.py

# 3. View results
open output/<project_name>/Map_<project_name>.html
```

### Run Web Interface
```bash
# Start Flask app
python app.py

# Open browser
open http://127.0.0.1:5000
```

---

## 🏗️ Architecture Overview

### System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      USER INTERFACE                         │
│  ┌──────────────┐              ┌──────────────┐            │
│  │   Web App    │              │  CLI Script  │            │
│  │   (app.py)   │              │  (main.py)   │            │
│  └──────┬───────┘              └──────┬───────┘            │
└─────────┼──────────────────────────────┼───────────────────┘
          │                              │
          └──────────────┬───────────────┘
                         │
┌────────────────────────▼───────────────────────────────────┐
│                   CORE PIPELINE                             │
│                   (main.py)                                 │
│                                                             │
│  1. Initialize GEE                                          │
│  2. Configure ROI & Dates                                   │
│  3. Process Satellite Data                                  │
│  4. Assemble Temporal Dataset                               │
│  5. Generate Outputs                                        │
└────────────────────────┬───────────────────────────────────┘
                         │
          ┌──────────────┼──────────────┐
          │              │              │
          ▼              ▼              ▼
┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│  SATELLITE  │  │  ASSEMBLY   │  │   OUTPUT    │
│   MODULES   │  │   MODULE    │  │  MODULES    │
│             │  │             │  │             │
│ sentinel2   │  │ assembly.py │  │ reporting   │
│ sentinel1   │  │             │  │ visualize   │
│ landsat     │  │             │  │ charts      │
│ srtm        │  │             │  │ validate    │
└─────────────┘  └─────────────┘  └─────────────┘
      │                 │                 │
      ▼                 ▼                 ▼
┌─────────────────────────────────────────────────────────────┐
│              GOOGLE EARTH ENGINE API                         │
│  • Sentinel-2 (Optical)                                      │
│  • Sentinel-1 (Radar)                                        │
│  • Landsat 8/9 (Thermal)                                     │
│  • SRTM (Topography)                                         │
└─────────────────────────────────────────────────────────────┘
```

### Component Hierarchy

```
SmartHarvest MLOps/
│
├── 🎯 ENTRYPOINTS
│   ├── app.py              # Web UI (Flask)
│   ├── main.py             # Pipeline CLI
│   └── run_ml_weekly.py    # ML anomaly detection
│
├── ⚙️ CONFIGURATION
│   ├── config.py           # Global settings (ROI, dates, thresholds)
│   └── schema.py           # Column definitions & labels
│
├── 📦 SATELLITE MODULES (modules/)
│   ├── sentinel2.py        # Optical vegetation indices
│   ├── sentinel1.py        # Radar backscatter
│   ├── landsat_thermal.py  # Land surface temperature
│   ├── srtm.py            # Topography (slope, aspect)
│   ├── assembly.py         # Data merging & export
│   └── reporting.py        # Report generation
│
├── 🛠️ TOOLS (tools/)
│   ├── visualize_data_map.py     # Interactive Folium maps
│   ├── visualize_ml_map.py       # ML anomaly maps
│   ├── charts.py                 # Plotly dashboard charts
│   ├── validate_pipeline.py      # Data quality checks
│   ├── analyze_temporal_data.py  # Statistical analysis
│   └── [ml tools...]           # Clustering utilities
│
├── 🤖 ML PIPELINE (ml/)
│   ├── pipeline.py         # ML orchestration
│   ├── data_loader.py      # CSV preprocessing
│   ├── clustering.py       # HDBSCAN clustering
│   ├── tracking.py         # Temporal cluster tracking
│   ├── output.py           # Result export
│   └── report_utils.py     # ML report sections
│
├── 🌐 WEB INTERFACE
│   ├── templates/          # HTML templates (Jinja2)
│   └── static/             # CSS/JS assets
│
└── 📊 OUTPUTS (output/)
    └── <project_name>/
        ├── SmartHarvest_<project>.csv      # Main temporal dataset
        ├── Map_<project>.html              # Interactive map
        ├── Report_<project>.md             # Metadata report
        ├── metadata_<project>.json         # JSON metadata
        ├── acquisition_log.txt             # Image acquisition log
        └── ml_weekly/                      # ML analysis results
```

---

## 🔄 Pipeline Flow

### Main Pipeline Execution (`main.py`)

```
START
  │
  ├─► 1. INITIALIZE
  │     ├── ee.Initialize()
  │     ├── Load config.ROI
  │     ├── Set START_DATE / END_DATE
  │     └── Calculate ROI area
  │
  ├─► 2. PROCESS SENTINEL-2 (Master Layer)
  │     ├── Query ImageCollection
  │     ├── Filter by ROI, date, cloud cover
  │     ├── Calculate indices (NDVI, NDWI, MNDWI, NDRE, IRECI, S2REP)
  │     ├── Extract master CRS
  │     └── Return: (collection, master_crs, metadata)
  │
  ├─► 3. PROCESS SRTM (Static Topography)
  │     ├── Query SRTM DEM
  │     ├── Calculate Slope (degrees)
  │     ├── Reproject to master_crs
  │     └── Return: (image, metadata)
  │
  ├─► 4. PROCESS SENTINEL-1 (Radar)
  │     ├── Query ImageCollection (VH+VV)
  │     ├── Filter by ROI, date
  │     ├── Calculate Ratio (VH-VV in dB)
  │     ├── Reproject to master_crs
  │     └── Return: (collection, metadata)
  │
  ├─► 5. PROCESS LANDSAT THERMAL
  │     ├── Query Landsat 8/9
  │     ├── Filter by ROI, date
  │     ├── Convert ST_B10 to Celsius
  │     ├── Reproject to master_crs
  │     └── Return: (collection, metadata)
  │
  ├─► 6. CREATE TEMPORAL SAMPLES
  │     ├── Sample each ImageCollection at ROI points
  │     ├── Create FeatureCollections with date stamps
  │     └── Return: (s2_fc, s1_fc, l8_fc, srtm_fc)
  │
  ├─► 7. DOWNLOAD SATELLITE DATA
  │     ├── Export S2 → _tmp_S2_<project>.csv
  │     ├── Export S1 → _tmp_S1_<project>.csv
  │     ├── Export L8 → _tmp_L8_<project>.csv
  │     ├── Export SRTM → _tmp_SRTM_<project>.csv
  │     └── Return: {csv_paths}
  │
  ├─► 8. MERGE TEMPORAL CSV
  │     ├── Load all _tmp_*.csv files
  │     ├── Merge on (date, lat, lon)
  │     ├── Add 'satellite' column
  │     ├── Sort by date
  │     └── Save: SmartHarvest_<project>.csv
  │
  ├─► 9. GENERATE VISUALIZATION
  │     ├── Create Folium map
  │     ├── Add satellite imagery basemap
  │     ├── Plot points colored by variables
  │     ├── Add **ML Anomaly Heatmap** layer (weighted by outlier_score)
  │     ├── Add date selector
  │     └── Save: Map_<project>.html
  │
  ├─► 10. GENERATE REPORT
  │     ├── Collect metadata from all modules
  │     ├── Generate acquisition log
  │     ├── Create markdown report
  │     └── Save: Report_<project>.md
  │
  └─► 11. VALIDATE OUTPUT
        ├── Check CSV schema
        ├── Verify data ranges
        ├── Count missing values
        └── Print validation summary
  │
END ✓
```

### ML Weekly Pipeline (`run_ml_weekly.py`)

```
START
  │
  ├─► 1. LOAD TEMPORAL DATA
  │     └── Read: SmartHarvest_<project>.csv
  │
  ├─► 2. SPLIT BY WEEK
  │     ├── Group data by ISO week (YYYY-Wxx)
  │     └── Create weekly feature tables
  │
  ├─► 3. HDBSCAN CLUSTERING (per week)
  │     ├── Normalize features (NDVI, NDWI, VH, VV, LST, Slope)
  │     ├── Microclustering (MiniBatchKMeans)
  │     ├── Run HDBSCAN (density-based clustering)
  │     ├── Calculate outlier scores
  │     └── Assign cluster labels
  │
  ├─► 4. TEMPORAL TRACKING
  │     ├── Match clusters across weeks
  │     ├── Assign persistent track_ids
  │     ├── Detect status changes (new/stable/fading/lost)
  │     └── Save: tracking_state.json
  │
  ├─► 5. DETECT ANOMALIES
  │     ├── Flag high outlier scores (threshold: 0.7)
  │     ├── Filter persistent anomalies (2+ weeks)
  │     └── Save: anomalies_<week>.csv
  │
  ├─► 6. GENERATE OUTPUTS
  │     ├── cluster_map_<week>.csv (cluster assignments)
  │     ├── outlier_map_<week>.csv (outlier scores)
  │     ├── cluster_image_<week>.png (spatial plot)
  │     └── outlier_image_<week>.png (heatmap)
  │
  └─► 7. UPDATE SUMMARY
        ├── processing_summary.csv (all weeks)
        └── Update report with ML section
  │
END ✓
```

---

## 📦 Module Reference

### Satellite Processing Modules

#### `modules/sentinel2.py`
**Purpose**: Process Sentinel-2 optical imagery for vegetation indices.

**Function**: `get_sentinel2_data() -> (collection, master_crs, metadata)`

**Output Bands**:
- `NDVI` - Normalized Difference Vegetation Index
- `NDWI` - Normalized Difference Water Index (McFeeters formula)
- `MNDWI` - Modified NDWI
- `NDRE` - Normalized Difference Red-Edge
- `IRECI` - Inverted Red-Edge Chlorophyll Index
- `S2REP` - Sentinel-2 Red-Edge Position

**Configuration**:
```python
config.ROI              # Region of Interest
config.START_DATE       # Start date (YYYY-MM-DD)
config.END_DATE         # End date
config.CLOUD_THRESHOLD_S2  # Max cloud cover (default: 20%)
config.TARGET_SCALE     # Spatial resolution (default: 10m)
```

---

#### `modules/sentinel1.py`
**Purpose**: Process Sentinel-1 SAR imagery for radar backscatter.

**Function**: `get_sentinel1_data(master_crs) -> (collection, metadata)`

**Output Bands**:
- `VH` - VH polarization backscatter (dB)
- `VV` - VV polarization backscatter (dB)
- `Ratio` - VH-VV ratio (dB)

**Notes**: Uses IW mode, descending orbit, preprocessed GRD product.

---

#### `modules/landsat_thermal.py`
**Purpose**: Process Landsat 8/9 thermal imagery for land surface temperature.

**Function**: `get_landsat_thermal(master_crs) -> (collection, metadata)`

**Output Bands**:
- `LST` - Land Surface Temperature (°C)

**Conversion**: `LST = ST_B10 * 0.00341802 + 149.0 - 273.15`

---

#### `modules/srtm.py`
**Purpose**: Process SRTM digital elevation model for topography.

**Function**: `get_srtm_data(master_crs) -> (image, metadata)`

**Output Bands**:
- `Slope` - Terrain slope (degrees)

**Notes**: Static layer, no temporal component.

---

#### `modules/assembly.py`
**Purpose**: Assemble and merge satellite data into temporal dataset.

**Key Functions**:

```python
# Sample ImageCollections at ROI points
create_temporal_samples(s2, s1, l8, srtm)
  → (s2_fc, s1_fc, l8_fc, srtm_fc)

# Download FeatureCollections as CSV
download_satellite_data(s2_fc, s1_fc, l8_fc, srtm_fc, output_dir, project_name)
  → {s2: path, s1: path, l8: path, srtm: path}

# Merge CSVs into final temporal dataset
build_temporal_csv(csv_paths, output_path)
  → merged_csv_path
```

**Output Schema**: See [Data Schemas](#data-schemas)

---

#### `modules/reporting.py`
**Purpose**: Generate metadata reports and acquisition logs.

**Function**: `generate_report(metadata, csv_path, output_path, acq_log_path, ml_dir)`

**Outputs**:
- `Report_<project>.md` - Markdown summary with:
  - ROI statistics
  - Acquisition dates per sensor
  - Data coverage summary
  - ML analysis results (if available)
- `acquisition_log.txt` - Detailed acquisition dates

---

### Tools Reference

#### `tools/visualize_data_map.py`
**Purpose**: Create interactive Folium maps for data exploration.

**Function**: `create_verification_map(csv_path, output_path, selected_date=None)`

**Features**:
- Satellite basemap (Esri WorldImagery)
- Point markers colored by variable values
- Variable selector (NDVI, NDWI, VH, LST, etc.)
- Date selector (filter by acquisition date)
- Legend with color scale

**Usage**:
```python
from tools import visualize_data_map
visualize_data_map.create_verification_map(
    csv_path='output/MyVineyard/SmartHarvest_MyVineyard.csv',
    output_path='output/MyVineyard/Map_MyVineyard.html',
    selected_date='2025-08-15'  # Optional
)
```

---

#### `tools/charts.py`
**Purpose**: Generate Plotly charts for dashboard.

**Functions**:
```python
create_histograms(df) -> str  # Returns HTML
# Creates distribution plots for all variables
```

**Usage**: Called automatically by `app.py` dashboard route.

---

#### `tools/validate_pipeline.py`
**Purpose**: Validate pipeline output data quality.

**Class**: `PipelineValidator(project_name)`

**Checks**:
- CSV file exists and is readable
- Required columns present
- Data types correct
- Value ranges plausible (e.g., NDVI in [-1, 1])
- Missing value counts
- Date format valid

**Usage**:
```python
from tools.validate_pipeline import PipelineValidator
validator = PipelineValidator('MyVineyard')
success = validator.run_validation()
```

---

### ML Pipeline Reference

#### `ml/pipeline.py`
**Purpose**: Orchestrate weekly ML anomaly detection.

**Function**: `run_ml_pipeline(csv_path, output_dir, force_reprocess=False)`

**Returns**:
```python
{
    'success': True,
    'weeks_processed': 12,
    'latest_week': '2025-W44',
    'latest_cluster_map': 'path/to/cluster_map_2025-W44.csv',
    'ml_dir': 'output/MyVineyard/ml_weekly/'
}
```

---

#### `ml/clustering.py`
**Purpose**: HDBSCAN density-based clustering with microclustering.

**Function**: `hdbscan_clustering(micro_centroids, micro_sizes, min_cluster_size=10)`

**Methods**:
```python
normalize_features(frame, feature_cols)  # Normalize inputs
microclustering(X_scaled, frame)         # Reduce dimensionality
hdbscan_clustering(...)                  # Run HDBSCAN on microclusters
```

---

#### `ml/tracking.py`
**Purpose**: Track cluster evolution across weeks.

**Class**: `ClusterTracker()`

**Methods**:
```python
update(week_id, cluster_data, features) -> tracked_data
# Assigns persistent track_ids and status labels
```

**Status Labels**:
- `new` - First appearance
- `stable` - Consistent for 2+ weeks
- `fading` - Decreasing size
- `lost` - Disappeared

---

## 📊 Data Schemas

### Temporal CSV Schema (`SmartHarvest_<project>.csv`)

| Column | Type | Source | Description | Range |
|--------|------|--------|-------------|-------|
| `date` | str | All | Acquisition date (YYYY-MM-DD) | - |
| `lat` | float | ROI | Latitude (WGS84) | -90 to 90 |
| `lon` | float | ROI | Longitude (WGS84) | -180 to 180 |
| `.geo` | str | ROI | GeoJSON point | - |
| `satellite` | str | Meta | Sensor(s) for this row | S2,S1,L8,SRTM |
| `NDVI` | float | S2 | Vegetation index | -1 to 1 |
| `NDWI` | float | S2 | Water index | -1 to 1 |
| `MNDWI` | float | S2 | Modified water index | -1 to 1 |
| `NDRE` | float | S2 | Red-edge index | -1 to 1 |
| `IRECI` | float | S2 | Chlorophyll index | 0 to 10 |
| `S2REP` | float | S2 | Red-edge position | 700-780 nm |
| `VH` | float | S1 | Radar VH backscatter | -30 to 0 dB |
| `VV` | float | S1 | Radar VV backscatter | -30 to 0 dB |
| `Ratio` | float | S1 | VH-VV difference | -10 to 10 dB |
| `LST` | float | L8 | Land surface temperature | -20 to 60 °C |
| `Slope` | float | SRTM | Terrain slope | 0 to 90° |

**Notes**:
- One row per (date × point × satellite) combination
- `satellite` column indicates which sensors contributed data for that row
- Static variables (Slope) repeated across all dates
- Missing values represented as `NaN`

---

### ML Cluster Map Schema (`cluster_map_<week>.csv`)

| Column | Type | Description |
|--------|------|-------------|
| `date` | str | ISO week (YYYY-Wxx) |
| `lat` | float | Latitude |
| `lon` | float | Longitude |
| `cluster_label` | int | Cluster ID (-1 = noise) |
| `outlier_score` | float | Anomaly score (0-1) |
| `track_id` | int | Persistent cluster ID |
| `cluster_status` | str | new/stable/fading/lost |
| `NDVI` | float | Feature values... |
| `NDWI` | float | |
| ... | | (all temporal features) |

---

## 💡 Usage Examples

### Example 1: Basic Pipeline Run

```python
# main.py
from modules import sentinel2, sentinel1, landsat_thermal, srtm, assembly, reporting
import config
import ee

# Initialize
ee.Initialize()
config.ROI = ee.Geometry.Polygon([
    [10.0, 45.0], [10.1, 45.0], [10.1, 45.1], [10.0, 45.1]
])
config.START_DATE = '2025-06-01'
config.END_DATE = '2025-09-01'

# Process satellites
s2_col, master_crs, s2_meta = sentinel2.get_sentinel2_data()
s1_col, s1_meta = sentinel1.get_sentinel1_data(master_crs)
l8_col, l8_meta = landsat_thermal.get_landsat_thermal(master_crs)
srtm_img, srtm_meta = srtm.get_srtm_data(master_crs)

# Assemble
s2_fc, s1_fc, l8_fc, srtm_fc = assembly.create_temporal_samples(
    s2_col, s1_col, l8_col, srtm_img
)

# Download
csv_paths = assembly.download_satellite_data(
    s2_fc, s1_fc, l8_fc, srtm_fc, 'output/test', 'test'
)

# Merge
final_csv = assembly.build_temporal_csv(
    csv_paths, 'output/test/SmartHarvest_test.csv'
)

print(f"✓ Temporal dataset: {final_csv}")
```

---

### Example 2: Custom Web Interface Route

```python
# app.py
from flask import Flask, jsonify
import pandas as pd

app = Flask(__name__)

@app.route('/api/ndvi_stats/<project_name>')
def ndvi_stats(project_name):
    """Custom API endpoint for NDVI statistics."""
    csv_path = f'output/{project_name}/SmartHarvest_{project_name}.csv'
    df = pd.read_csv(csv_path)

    stats = {
        'mean': float(df['NDVI'].mean()),
        'std': float(df['NDVI'].std()),
        'min': float(df['NDVI'].min()),
        'max': float(df['NDVI'].max())
    }

    return jsonify(stats)
```

---

### Example 3: Custom Visualization

```python
# custom_viz.py
import pandas as pd
import folium

def create_ndvi_heatmap(csv_path, output_path):
    """Create NDVI heatmap for latest date."""
    df = pd.read_csv(csv_path)

    # Get latest date
    latest_date = df['date'].max()
    df_latest = df[df['date'] == latest_date]

    # Create map
    center_lat = df_latest['lat'].mean()
    center_lon = df_latest['lon'].mean()
    m = folium.Map(location=[center_lat, center_lon], zoom_start=15)

    # Add heatmap
    from folium.plugins import HeatMap
    heat_data = [[row['lat'], row['lon'], row['NDVI']]
                 for _, row in df_latest.iterrows()]
    HeatMap(heat_data).add_to(m)

    m.save(output_path)
    print(f"✓ Heatmap saved: {output_path}")

# Usage
create_ndvi_heatmap(
    'output/MyVineyard/SmartHarvest_MyVineyard.csv',
    'output/MyVineyard/ndvi_heatmap.html'
)
```

---

## 🔧 Extending the Pipeline

### Adding a New Satellite Data Source

**1. Create module** (`modules/new_satellite.py`):
```python
import ee
import config

def get_new_satellite_data(master_crs):
    """
    Process new satellite data.

    Args:
        master_crs: Projection to align to (from Sentinel-2)

    Returns:
        tuple: (ee.ImageCollection, metadata_dict)
    """
    # Query collection
    collection = ee.ImageCollection('NEW/COLLECTION') \
        .filterBounds(config.ROI) \
        .filterDate(config.START_DATE, config.END_DATE)

    # Calculate indices/bands
    def add_index(image):
        index = image.expression(
            'B1 - B2',
            {'B1': image.select('B1'), 'B2': image.select('B2')}
        ).rename('NEW_INDEX')
        return image.addBands(index)

    collection = collection.map(add_index)

    # Reproject to master CRS
    collection = collection.map(
        lambda img: img.reproject(crs=master_crs, scale=config.TARGET_SCALE)
    )

    # Metadata
    metadata = {
        'source': 'New Satellite',
        'image_count': collection.size().getInfo(),
        'bands': ['NEW_INDEX']
    }

    return collection, metadata
```

**2. Update `schema.py`**:
```python
TEMPORAL_COLUMNS = [
    # ... existing columns ...
    'NEW_INDEX',  # Add new column
]

COLUMN_LABELS = {
    # ... existing labels ...
    'NEW_INDEX': 'New Index Description',
}

COLUMN_SATELLITE = {
    # ... existing mappings ...
    'NEW_INDEX': 'NEW',
}
```

**3. Integrate in `main.py`**:
```python
from modules import new_satellite

# In run_pipeline():
new_col, new_meta = new_satellite.get_new_satellite_data(master_crs)
all_metadata.append(new_meta)

# Update assembly call:
s2_fc, s1_fc, l8_fc, srtm_fc, new_fc = assembly.create_temporal_samples(
    s2_col, s1_col, l8_col, srtm_img, new_col  # Add new collection
)
```

**4. Update `assembly.py`** to handle new collection:
```python
def create_temporal_samples(s2, s1, l8, srtm, new=None):
    # ... existing code ...

    if new:
        new_fc = new.map(lambda img: sample_image(img, ['NEW_INDEX']))
        return s2_fc, s1_fc, l8_fc, srtm_fc, new_fc

    return s2_fc, s1_fc, l8_fc, srtm_fc
```

---

### Adding Custom Analysis Tools

**Example**: Create a NDVI anomaly detector:

```python
# tools/ndvi_anomaly_detector.py
import pandas as pd
import numpy as np

def detect_ndvi_anomalies(csv_path, threshold_std=2.0):
    """
    Detect NDVI anomalies using z-score method.

    Args:
        csv_path: Path to temporal CSV
        threshold_std: Number of std deviations for anomaly

    Returns:
        DataFrame with anomaly flags
    """
    df = pd.read_csv(csv_path)

    # Calculate z-scores per point
    df['NDVI_zscore'] = df.groupby(['lat', 'lon'])['NDVI'].transform(
        lambda x: (x - x.mean()) / x.std()
    )

    # Flag anomalies
    df['NDVI_anomaly'] = np.abs(df['NDVI_zscore']) > threshold_std

    # Filter anomalies
    anomalies = df[df['NDVI_anomaly']].copy()

    print(f"✓ Found {len(anomalies)} NDVI anomalies")
    return anomalies

# Usage
anomalies = detect_ndvi_anomalies(
    'output/MyVineyard/SmartHarvest_MyVineyard.csv',
    threshold_std=2.5
)
anomalies.to_csv('output/MyVineyard/ndvi_anomalies.csv', index=False)
```

---

## 🐛 Troubleshooting

### Common Issues

#### 1. **Google Earth Engine Authentication Error**
```
Error: Please authorize access to Earth Engine
```

**Solution**:
```bash
earthengine authenticate
# Follow browser authentication flow
```

---

#### 2. **Empty Image Collections**
```
Warning: 0 images found for Sentinel-2
```

**Causes**:
- Date range outside growing season
- Cloud cover threshold too strict
- ROI outside satellite coverage

**Solutions**:
```python
# Check ROI coverage
print(config.ROI.bounds().getInfo())

# Relax cloud threshold
config.CLOUD_THRESHOLD_S2 = 50  # Default: 20

# Expand date range
config.START_DATE = '2025-05-01'  # Earlier
config.END_DATE = '2025-10-01'    # Later
```

---

#### 3. **Memory Error During Export**
```
Error: Export too large
```

**Solutions**:
```python
# Reduce ROI area
config.ROI = config.ROI.buffer(-100)  # Shrink by 100m

# Increase scale (coarser resolution)
config.TARGET_SCALE = 20  # Default: 10m

# Reduce date range
# Process in smaller time windows
```

---

#### 4. **Missing Values in CSV**
```
Warning: 45% of NDVI values are NaN
```

**Causes**:
- Cloud masking removed too many pixels
- Satellite orbits didn't cover ROI on those dates
- Data gaps in source collections

**Check**:
```python
import pandas as pd
df = pd.read_csv('output/MyVineyard/SmartHarvest_MyVineyard.csv')

# Check coverage per satellite
print(df.groupby('satellite')['NDVI'].count())

# Check coverage per date
print(df.groupby('date').size())
```

---

#### 5. **Map Not Loading**
```
Map_MyVineyard.html shows blank page
```

**Solutions**:
```python
# Check CSV has data
df = pd.read_csv('output/MyVineyard/SmartHarvest_MyVineyard.csv')
print(len(df))  # Should be > 0

# Regenerate map
from tools import visualize_data_map
visualize_data_map.create_verification_map(
    'output/MyVineyard/SmartHarvest_MyVineyard.csv',
    'output/MyVineyard/Map_MyVineyard.html'
)
```

---

### Performance Optimization

#### Speed Up Exports

```python
# In assembly.py, increase maxWorkers
ee.batch.Export.table.toDrive(
    collection=fc,
    description='export',
    fileFormat='CSV',
    maxWorkers=16  # Default: 1
).start()
```

#### Cache Frequent Queries

```python
# Save intermediate results
s2_col.getInfo()  # Slow
# vs
with open('cache_s2.json', 'w') as f:
    json.dump(s2_col.getInfo(), f)
```

---

## 📚 Additional Resources

- [Google Earth Engine Docs](https://developers.google.com/earth-engine)
- [Sentinel-2 User Guide](https://sentinel.esa.int/web/sentinel/user-guides/sentinel-2-msi)
- [Sentinel-1 User Guide](https://sentinel.esa.int/web/sentinel/user-guides/sentinel-1-sar)
- [HDBSCAN Paper](https://jlmelville.github.io/hdbscan/hdbscan.pdf)

---

## 🤝 Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on:
- Code style
- Testing procedures
- Pull request process

---

## 📄 License

MIT License - see [LICENSE](LICENSE) file for details.

---

**Last Updated**: 2026-02-10
**Version**: 1.0.0
