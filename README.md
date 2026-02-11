# SmartHarvest - Vineyard Monitoring & Zonation Pipeline


A modular MLOps pipeline for precision viticulture, combining Google Earth Engine (GEE) satellite data acquisition with advanced ML-based anomaly detection and temporal tracking.


## Key Features


*   **Multi-Source Data Fusion**: Integrates Sentinel-2 (Optical), Sentinel-1 (Radar), Landsat (Thermal), and SRTM (Topo).
*   **Weekly ML Analysis**: Automatic weekly clustering using **HDBSCAN** with microclustering (MiniBatchKMeans).
*   **Anomaly Heatmaps**: Weighted visualization of `outlier_score` to identify "hotspots" of stress or vigor anomalies.
*   **Interactive Web Dashboard**: Flask-based UI for ROI selection, analysis execution, and full-screen temporal map visualization.
*   **Zonation Integration**: ML anomaly heatmaps are integrated as a layer in the main interactive map for cross-sensor correlation.
*   **Automated Monitoring**: Built-in instrumentation for pipeline performance and data quality metrics.


## Project Structure


```
MLOPS-SmartHarvest/
├── app.py                  # Web application & Dashboard entry point
├── main.py                 # Core satellite pipeline orchestrator
├── run_ml_weekly.py        # Standalone ML pipeline runner
├── config.py               # Global settings & GEE configuration
├── schema.py               # Data validation & column normalization
│
├── modules/                # Core processing logic
│   ├── sentinel2.py        # Optical indices (NDVI, NDRE, etc.)
│   ├── sentinel1.py        # Radar backscatter (VH, VV)
│   ├── landsat_thermal.py  # Surface Temperature (LST)
│   ├── srtm.py             # Topography (Slope, Aspect)
│   ├── assembly.py         # Data cube construction & sampling
│   ├── reporting.py        # Automated PDF/MD report generation
│   └── monitoring.py       # Performance & metrics tracking
│
├── ml/                     # Machine Learning Kernel
│   ├── pipeline.py         # Weekly clustering orchestrator
│   ├── clustering.py       # HDBSCAN & Microclustering logic
│   ├── tracking.py         # Inter-week cluster association
│   └── data_loader.py      # S2-specific temporal filtering
│
├── tools/                  # Visualization & Utility scripts
│   ├── visualize_ml_map.py # Weekly anomaly map generation
│   ├── validate_pipeline.py# Integrity & consistency checks
│   └── charts.py           # Statistical plots for dashboard
│
├── templates/ & static/    # Flask UI components
└── output/                 # Project-specific output directories
```


## Installation & Setup


### 1. Environment Setup
It is recommended to use a virtual environment to manage dependencies.


#### macOS/Linux
```bash
# Create virtual environment
python3 -m venv .venv


# Activate virtual environment
source .venv/bin/activate
```


#### Windows
```bash
# Create virtual environment
python -m venv .venv


# Activate virtual environment
.venv\Scripts\activate
```


### 2. Install Requirements
Ensure your virtual environment is activated, then install the dependencies:
```bash
pip install -r requirements.txt
```


### 3. GEE Authentication
With the virtual environment activated, authenticate with Google Earth Engine:
```bash
earthengine authenticate
```


## Usage


### Web Interface (Recommended)
Launch the interactive dashboard to manage projects and view maps:
```bash
python app.py
```
Open `http://localhost:5000` to draw your ROI and start the analysis.


> [!NOTE]
> **Project Names**: Spaces in project names are automatically converted to underscores (e.g., "Mio Campo" becomes "Mio_Campo") for file system compatibility, but are restored in the UI for readability.


### Command Line
Run the core pipeline for a project (uses settings in `config.py` by default):
```bash
python main.py
```
Or run the ML analysis separately on existing data (requires project name):
```bash
python run_ml_weekly.py --project MyVineyard
```


## Monitoring & Quality Control


The pipeline now generates detailed performance logs in the project output directory:
- `monitoring_core.json`: Execution times and sensor counts for data acquisition.
- `ml_weekly/monitoring_ml.json`: Performance metrics for clustering, tracking, and anomaly detection.
- Dashboard views provide real-time status during execution.


## Documentation
For in-depth technical details, see:
*   **[ARCHITECTURE.md](ARCHITECTURE.md)**: System design, module reference, and algorithm details.
*   **[ml/README.md](ml/README.md)**: Deep dive into the clustering and tracking kernel.
