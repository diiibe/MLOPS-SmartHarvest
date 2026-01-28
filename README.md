# MLOPS-SmartHarvest  
**End-to-End Multi-Satellite ML Pipeline for Precision Agriculture Monitoring**

---

## Executive Summary

This project implements an **end-to-end machine learning pipeline** for satellite-based monitoring in precision agriculture, designed following **industrial best practices**.

The system focuses on **precision-first anomaly detection** over multi-satellite time series, integrating data quality management, reproducibility, CI/CD compatibility, and continuous monitoring as **core architectural components**.

The pipeline processes heterogeneous geospatial data sources (optical, radar, thermal, climatic, topographic) and is built to be **robust, auditable, and maintainable**, reflecting how machine learning systems are developed and operated in a company environment.

---

## Project Scope

The project is developed with a **production-oriented mindset**, treating the pipeline as a long-lived system rather than a one-off analysis.

Key priorities include:
- robust handling of data quality issues,
- deterministic and reproducible execution,
- CI/CD-compatible pipeline design,
- monitoring of data, pipeline health, and outputs,
- clear separation between configuration, processing logic, and validation.

These principles guide both the architectural decisions and the level of rigor applied throughout the repository.

---

## Problem Definition

Each agricultural parcel (AOI) is represented as a **multivariate time series** built from satellite-derived and environmental variables.

The core task is **time-series anomaly detection**, aimed at identifying deviations from the expected temporal behavior of a parcel.

A critical requirement is **minimizing false positives**, as spurious alerts caused by observational artifacts directly reduce trust in the system and its operational usefulness.  
For this reason, the system adopts a **precision-first strategy**, where missing data is preferred over contaminated or unstable observations.

---

## Data Sources and Rationale

The pipeline integrates multiple data sources to improve robustness, interpretability, and resilience to sensor-specific artifacts:

- **Sentinel-2 (Optical)**  
  Vegetation vigor, chlorophyll, and moisture-related indices.

- **Sentinel-1 (SAR Radar)**  
  Cloud-independent structural and moisture information, used as a robustness and cross-validation signal.

- **Landsat / ECOSTRESS (Thermal)**  
  Land Surface Temperature (LST) as a proxy for thermal and water stress.

- **ERA5-Land**  
  Climate and water balance variables (temperature, rainfall, evapotranspiration, deficit).

- **SRTM**  
  Topographic context (elevation, slope, aspect) to explain structural differences between parcels.

The **multi-source design** reduces dependency on any single sensor and improves discrimination between real anomalies and observation-driven artifacts.

---

## Variables Overview

The pipeline operates on a curated set of variables derived from the sources above.

Rather than focusing on individual indices, variables are organized into functional categories reflecting underlying physical processes:

- **Vegetation vigor and nutrition**  
  Optical and red-edge indicators capturing biomass, chlorophyll content, and phenological dynamics.

- **Structural and water-related dynamics**  
  Radar- and water-sensitive variables used to detect changes in canopy structure and moisture conditions.

- **Thermal and environmental context**  
  Land surface temperature and climate variables supporting interpretation of stress-related anomalies.

- **Topographic context**  
  Static variables providing structural explanation of long-term differences between parcels.

A detailed description of individual variables and indices is provided in the project documentation and in the final report.

---

## Quality Assurance as a Core Design Component

Data quality is treated as a **first-class requirement** of the system.

### Pixel-Level Quality Assurance
Optical data is filtered using an **ensemble QA strategy**, combining scene classification, probabilistic cloud detection, and continuous cloud confidence scores.  
A conservative decision rule is applied: a pixel is considered valid **only if it passes all QA checks**.

### Parcel-Level Reliability Gating
Each timestep is evaluated based on valid pixel coverage and minimum pixel counts.  
Timesteps that do not meet reliability thresholds are explicitly marked as **not observable** and excluded from downstream processing.

---

## Mixed Pixel Mitigation

At 10 m spatial resolution, mixed pixels are a structural issue.

Mitigation is achieved through:
1. **Negative buffering** of parcel geometries (core parcel),
2. **Robust aggregation statistics** (median, percentiles),
3. **Coverage- and count-based gating** at timestep level.

This prevents spatial artifacts from propagating into temporal patterns that could trigger false anomalies.

---

## Temporal Processing Strategy

The pipeline enforces a strict processing order:
1. Quality assurance and observability gating  
2. Temporal compositing on a regular grid (weekly)  
3. Interpolation and smoothing applied **only to indices**, never to raw bands  
4. Computation of derived temporal features (Mean, Delta, Drop)

Observed and reconstructed values are always kept **explicitly distinct**, together with quality metadata, ensuring traceability and auditability.

---

## Feature Engineering

The anomaly detection stage relies on a **restricted set of strategic features**, selected for:
- robustness to observational noise,
- agronomic interpretability,
- transferability across parcels and seasons.

Derived features are computed **after temporal stabilization**, reducing sensitivity to residual noise.

---

## CI/CD and Pipeline Automation

The project is designed with a **CI/CD-oriented architecture**:
- deterministic, configuration-driven execution,
- modular pipeline stages (ingestion, QA, feature generation),
- compatibility with automated and scheduled runs.

The repository includes:
- an **offline CI runner** to validate pipeline logic without live access to external services,
- a **Docker-based environment** to ensure reproducibility across systems.

CI/CD design considerations and automation strategies are documented in the `Per_Andrea/` directory.

---

## Monitoring and System Health

Monitoring is treated as an integral part of the system.

### Data Quality Monitoring
Indicators include valid pixel coverage, observed vs reconstructed ratios, and temporal availability by source.

### Pipeline Health Monitoring
The deterministic structure enables detection of abnormal missing data rates, distribution shifts, and run-to-run inconsistencies.

### Output Monitoring
Anomaly scores and alert frequency are tracked to detect alert inflation, support threshold calibration, and identify silent failures.


## Project Structure

```text
MLOPS-SmartHarvest/
├── satellites/             # Modules for specific satellite data extraction
├── modules/                # Core logic, statistics, and main extraction routines
├── database/               # Local database or storage for processed data
├── tests/                  # Unit and integration tests
├── config.py               # Main configuration (ROI, dates, thresholds)
├── Dockerfile              # Docker container definition
├── docker-compose.yml      # Docker Compose configuration (if applicable)
├── requirements.txt        # Python dependencies
└── utils.py                # Utility functions (filtering, transforms)
```

## Prerequisites

-   **Google Earth Engine (GEE)**: An active GEE account is required.
    -   You must authenticate locally or provide service account credentials.
-   **Python 3.9+**: If running locally.
-   **Docker**: If running via container.

## Installation

### Local Setup

1.  **Clone the repository**:
    ```bash
    git clone https://github.com/your-username/MLOPS-SmartHarvest.git
    cd MLOPS-SmartHarvest
    ```

2.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

3.  **Authenticate with GEE**:
    ```bash
    earthengine authenticate
    ```

### Docker Setup

1.  **Build the image**:
    ```bash
    docker build -t smartharvest-app .
    ```

2.  **Run the container**:
    ```bash
    docker run -it smartharvest-app
    ```
    *Note: For full GEE access, you may need to mount credentials or pass tokens.*

## Configuration

The main configuration is located in `config.py`. Key parameters include:

-   **ROI_TEST**: List of coordinates defining the Region of Interest (can also be loaded from `roi.json`).
-   **Time Windows**:
    -   `T1_START`, `T1_END`: Vegetative Development phase.
    -   `T2_START`, `T2_END`: Maturation phase.
-   **Thresholds**:
    -   `CLOUD_THRESH`: Max cloud coverage percentage for Sentinel-2.
    -   `CLOUD_THRESH_LANDSAT`: Max cloud coverage for Landsat.
-   **Sampling**: `SAMPLING_SCALE` (default 10m).

## Usage

### Running Tests / CI Offline Runner
To verify the setup without connecting to GEE (using mocks), run:
```bash
python tests/ci_offline_runner.py
```
This script simulates the pipeline and generates artifacts in the `output/` directory, such as `data_quality_report.csv` and `clusters.geojson`.

### Main Execution
(Add instructions here for the main entry point, e.g., `main.py` if implemented, or specific module execution)

```bash
# Example
python modules/satellites_data_extraction.py
```

## Modules Overview

-   **satellites_data_extraction**: Handles GEE API calls for various sensors.
-   **satellites_statistics**: Computes temporal aggregations and phenological metrics.
-   **check_data**: (If available) Runs data quality checks on exported datasets.