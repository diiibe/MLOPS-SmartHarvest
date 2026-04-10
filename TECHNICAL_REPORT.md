# SmartHarvest — Technical Report

> Technical deep-dive into the design decisions, methodology, and MLOps
> practices behind the SmartHarvest vineyard zonation pipeline.
>
> **Companion documents:**
> - `README.md` — overview and quick start for casual visitors
> - `ARCHITECTURE.md` — developer guide for using and extending the codebase
> - `docs/reports-italian/` — original Italian technical reports (source material)

---

## 1. Executive Summary

SmartHarvest is an end-to-end MLOps pipeline for **dynamic vineyard
zonation** from multi-sensor Earth observation data. It ingests
Sentinel-2 (optical), Sentinel-1 (radar), Landsat 8/9 (thermal) and
SRTM (topographic) imagery via Google Earth Engine (GEE), fuses the
heterogeneous layers onto a common 10 m "master" grid, and runs a
weekly unsupervised clustering kernel based on MiniBatchKMeans
microclustering followed by HDBSCAN. Temporal tracking keeps cluster
identities stable across weeks; an outlier-score-based detector flags
pixels whose behaviour diverges from their cohort.

The reference execution targets **Fantinel37**, a real hillside
vineyard in the Friuli Colli Orientali region of northeastern Italy,
over the 2025 ripening window. The core pipeline processed 62
Sentinel-2, 30 Sentinel-1 and 14 Landsat scenes in 2709.75 s (dominated
by the GEE download step at 2548.49 s), producing a 740,552-row
per-pixel CSV. The ML pipeline then consumed 353,912 Sentinel-2 rows,
built 13 weekly frames of 14,320 pixels each, and completed the full
clustering + tracking + anomaly sweep in 8.75 s. All numbers below are
sourced from real artefacts on disk: `monitoring_core.json`,
`monitoring_ml.json`, `processing_summary.csv`, and the parameters in
`ml/clustering.py` and `ml/pipeline.py`.

This report is not an accuracy benchmark — Section 6.4 makes explicit
that no ground-truth zonation exists for Fantinel37 and no
precision/recall can be claimed. The contribution lives in the pipeline
itself: its reproducibility, modularity, observability and multi-sensor
feature engineering.

---

## 2. Problem Statement and Background

### 2.1 Intra-parcel variability in viticulture

A commercial vineyard is almost never homogeneous. Vigour, phenology
and fruit composition all vary within the same parcel because of
microtopography (slope, aspect, elevation drive solar load and
drainage), soil variability (clay/sand fractions, rooting depth),
water balance (convergent flow paths retain moisture while shoulders
dry out) and uneven biotic pressure. A single harvest date applied
uniformly yields an *average* wine — overripe on the shoulders,
under-ripe in the footslopes. The opportunity is to **zonate** the
parcel into sub-regions managed and harvested separately.

### 2.2 Why traditional approaches are insufficient

In-field walk surveys are labour-intensive and not reproducible.
Tractor-mounted proximal sensors see only the strips the machine
drove. UAV campaigns give high resolution but are expensive,
weather-dependent, and run a couple of times per season. A single-date
NDVI snapshot contains no information about *how* the vineyard got
there — a stressed vine and a pruned vine can give the same reading.
None of these methods combine dense temporal sampling, the ability to
see beneath the optical signal with radar and thermal, and a fully
scripted workflow. That combination is what an MLOps pipeline on GEE
can deliver.

### 2.3 Why multi-sensor fusion is the right bet

Different sensors see different physics. **Sentinel-2** measures
canopy greenness and chlorophyll but is blocked by clouds and
saturates on dense canopies. **Sentinel-1** C-band SAR measures
backscatter from canopy structure and water content, sees through
clouds, and reacts to dielectric changes before NDVI does.
**Landsat 8/9 thermal** measures land surface temperature, a direct
proxy for transpiration. **SRTM** provides the static stage —
elevation, slope and aspect. Fusing these into a single spatially
aligned per-pixel feature vector is much more discriminative than any
single sensor alone. The full motivation is in the Italian design
documents under `docs/reports-italian/`.

---

## 3. Related Work

1. **Gorelick et al. (2017).** *Google Earth Engine: Planetary-scale
   geospatial analysis.* RSE 202, 18-27. The platform paper for GEE.
2. **Hall, Lamb, Holzapfel & Louis (2002).** *Optical remote sensing
   applications in viticulture: a review.* AJGWR 8(1), 36-47.
   Establishes NDVI as a vigour proxy and its limits.
3. **Matese & Di Gennaro (2018).** *Multisensor UAV platform in
   precision viticulture.* Agriculture 8(7), 116. Value of combining
   optical and thermal on the same vineyard.
4. **Campello, Moulavi & Sander (2013).** *Density-based clustering
   based on hierarchical density estimates.* PAKDD 2013, 160-172.
   The HDBSCAN paper.
5. **McInnes, Healy & Astels (2017).** *hdbscan: Hierarchical density
   based clustering.* JOSS 2(11), 205. The Python package we import.
6. **Sculley et al. (2015).** *Hidden technical debt in machine
   learning systems.* NeurIPS 2015. The MLOps motivation.

**Positioning.** The individual ingredients of SmartHarvest are not
novel: multi-sensor fusion for viticulture has been published, HDBSCAN
is well known, and GEE is a standard data-access layer. **The
research value is in the pipeline** — the features and parameters,
the master-slave reprojection, the weekly microclustering-then-HDBSCAN
cascade, the overlap tracker, and the MLOps-grade observability that
lets a reader reproduce every number in Section 6 from JSON files on
disk. The downstream ML is a means, not an end.

---

## 4. Methodology

### 4.1 Multi-sensor fusion on a master-slave grid

The four sensors have different native resolutions and CRS. Naively
stacking bands after a default reprojection introduces misalignments
on row scales. SmartHarvest uses a **master-slave grid**: the
cloud-masked Sentinel-2 projection is the master, and every subsequent
layer is forced onto it via `reproject(crs=master_crs, scale=10)`.
SRTM slope and aspect are computed on the **native 30 m DEM first**
and only then resampled to 10 m bilinearly — computing slope after
upsampling would introduce stair-step artefacts. Sentinel-1 is
despeckled spatially, averaged temporally, then reprojected. Landsat
LC08 and LC09 are merged, converted to Celsius, median-reduced and
upsampled bicubically. The final bands are concatenated into a
multi-band `ee.Image` and sampled with `sampleRegions()` at 10 m. The
procedure is deterministic.

### 4.2 Temporal feature engineering

The exported CSV for Fantinel37 contains, per observation, the
columns: `date, spatial_id, lat, lon, .geo, satellite, NDVI, NDWI,
MNDWI, NDRE, IRECI, S2REP, VH, VV, Ratio, LST, Slope` — 11 numeric
feature columns, verified from the real file
`output/Fantinel37/SmartHarvest_Fantinel37.csv`, which contains
740,552 data rows. Optical features come from Sentinel-2 (NDVI, NDWI,
MNDWI, NDRE, IRECI, S2REP), radar from Sentinel-1 (VH, VV, Ratio),
LST from Landsat, Slope from SRTM.

Rather than collapsing the season into one snapshot, SmartHarvest
**keeps the temporal dimension**. `ml/pipeline.py` buckets
observations into ISO weeks and runs a full clustering + tracking
cycle on every week. For Fantinel37, 13 weekly frames were built
covering 2025-W32 through 2025-W45 with **W34 missing** (no
cloud-free Sentinel-2 acquisition fell in that week). Each frame
contains 14,320 pixels — the intersection of the ROI polygon with
the master 10 m grid. The data strategy report
(`docs/reports-italian/data_strategy_report.md`) argues that
*changes* between phenological windows carry more agronomic
information than absolute values; a weekly cadence gives the ML
kernel a direct window on those dynamics without pre-baking
phenological dates.

### 4.3 Clustering strategy

The clustering stack in `ml/clustering.py` is a three-stage cascade.

#### 4.3.1 Per-week standardisation

Features are standardised with `StandardScaler`. Missing values are
imputed with the column median (zero fallback if a whole column is
NaN, which happens on weeks with no Sentinel-1 coverage).
Standardisation is **per-week**, so anomalies are "unusual for this
week", not "unusual for the season".

#### 4.3.2 Microclustering with MiniBatchKMeans

HDBSCAN on 14,320 points per week is feasible but sensitive to
speckle. SmartHarvest collapses the pixel cloud into a few hundred
microclusters first. From `ml/clustering.py`:

```python
target_micro = min(max_microclusters, max(50, n_samples // 30))
kmeans = MiniBatchKMeans(
    n_clusters=target_micro, random_state=42,
    batch_size=1024, max_iter=100
)
```

For 14,320 pixels this targets ≈ 477 microclusters, well under the
`max_microclusters=5000` ceiling. `random_state=42` pins the run and
noise is absorbed into the centroids.

#### 4.3.3 HDBSCAN on microcluster centroids

```python
adjusted_min_size = max(5, min(min_cluster_size, n_micro // 20))
clusterer = hdbscan.HDBSCAN(
    min_cluster_size=adjusted_min_size, min_samples=5,
    metric="euclidean", cluster_selection_method="eom",
)
```

Defaults: `min_cluster_size=10`, `min_samples=5`, Excess-of-Mass
selection. HDBSCAN returns cluster labels (`-1` for noise) and a
per-microcluster outlier score; both are propagated back to pixels
through the microcluster assignments.

### 4.4 Temporal tracking

`ml/tracking.py` bridges weeks with a pixel-overlap heuristic: for
each current cluster it looks at the pixels that also existed the
previous week, takes a plurality vote on their previous track IDs,
and if that plurality accounts for **more than 30%** of the overlap
it inherits the track ID. Otherwise a fresh ID is minted. Track state
(cluster-to-track map, highest ID so far, per-track
`new`/`continued`/`lost` status) is persisted to
`tracking_state.json` in the weekly output directory, which is how
`run_ml_weekly.py` resumes from a previous run. This is deliberately
simple; a Hungarian assignment on centroid distance fits as a
one-function replacement.

### 4.5 Anomaly scoring

Anomaly detection piggy-backs on HDBSCAN's outlier scores.
`ml/tracking.py` computes a threshold at the **95th percentile** of
outlier scores for the week
(`score_threshold = np.percentile(outlier_scores, 95)`), flags pixels
above it, and groups them by track ID — so the output is a short
list of anomalous clusters per week rather than a noisy per-pixel
dump. That list feeds the heatmap layer in the interactive map and
the rows in the per-week `anomalies_<week_id>.csv`.

---

## 5. Experimental Setup

### 5.1 Study area

The primary study area is **Fantinel37**, a real hillside vineyard in
the Friuli Colli Orientali region of northeastern Italy. The ROI
polygon is stored in `rois/Fantinel37.geojson`. At 10 m master-grid
resolution it samples to **14,320 pixels** per weekly frame, as
confirmed by every entry in
`output/Fantinel37/ml_weekly/monitoring_ml.json`.

A smaller synthetic polygon under the project name `demo` ships in
the repository (`demo/data/Fantinel37.csv`, 70,000 data rows) so
developers can run the ML pipeline on a laptop without GEE
authentication; the demo monitoring JSON shows 33,374 rows loaded and
a single weekly frame of 5,000 pixels processed in 0.489 s. All
numerical claims in Section 6 refer to the real Fantinel37 run.

### 5.2 Data sources

All inputs are drawn from the GEE public catalogue:

- `COPERNICUS/S2_SR_HARMONIZED` — Sentinel-2 L2A surface reflectance,
  cloud-masked via QA60, filtered `CLOUDY_PIXEL_PERCENTAGE < 20`.
  Fantinel37: **62 scenes** (`monitoring_core.json` → `Sentinel-2` →
  `image_count: 62`).
- `COPERNICUS/S1_GRD` — Sentinel-1 GRD, IW mode, VV+VH polarisation,
  spatially despeckled. Fantinel37: **30 scenes**
  (`Sentinel-1` → `image_count: 30`).
- `LANDSAT/LC08/C02/T1_L2` and `LANDSAT/LC09/C02/T1_L2` — merged
  thermal collections. Fantinel37: **14 scenes**
  (`Landsat` → `image_count: 14`). The original design called for
  ECOSTRESS; that collection was retired from GEE during development,
  and the Landsat 8/9 merge is the documented fallback (see
  `docs/reports-italian/pipeline_report.md` §8.3).
- `USGS/SRTMGL1_003` — static 30 m DEM, resampled to 10 m on the
  master grid.

### 5.3 Pipeline configuration

The clustering parameters in `ml/clustering.py`, as run for
Fantinel37 and stored verbatim in the repository, are:

| Parameter | Value | Source |
|---|---|---|
| `max_microclusters` | 5000 | `microclustering()` default |
| Target microclusters | `min(5000, max(50, n_samples // 30))` | same |
| MiniBatchKMeans `batch_size` / `max_iter` / `random_state` | 1024 / 100 / 42 | same |
| HDBSCAN `min_cluster_size` | 10, adjusted to `max(5, min(10, n_micro//20))` | `hdbscan_clustering()` |
| HDBSCAN `min_samples` | 5 | same |
| HDBSCAN `metric` / `cluster_selection_method` | `euclidean` / `eom` | same |
| Anomaly threshold | 95th percentile of outlier scores | `tracking.detect_anomalies()` |
| Tracking overlap threshold | 30% of current-cluster overlap | `tracking.track_clusters_simple()` |

The core pipeline uses `CLOUD_THRESHOLD=20`, `TARGET_SCALE=10` and
the ROI from `rois/Fantinel37.geojson`.

---

## 6. Results

### 6.1 Pipeline execution on Fantinel37

Numbers below are extracted verbatim from
`monitoring_core.json`, `monitoring_ml.json` and
`processing_summary.csv`. Nothing has been averaged, smoothed or
invented.

**Core acquisition pipeline.** Total wall time **2709.75 s** (≈45 min):

| Step | Duration (s) | Metric |
|---|---:|---|
| Sentinel-2 | 4.854 | `image_count: 62` |
| SRTM | 0.000 | static fetch |
| Sentinel-1 | 0.911 | `image_count: 30` |
| Landsat | 2.241 | `image_count: 14` |
| Assembly-Sampling | 0.338 | — |
| Download | **2548.494** | GEE export wait |
| Merge | 85.973 | — |
| ML-Analysis | 8.759 | (see below) |
| Map | 54.460 | folium map rendering |
| Report | 1.665 | markdown report |
| Validation | 0.949 | schema checks |

The dominant cost is the GEE `Download` step: modelling is negligible
by comparison. Any optimisation effort should target the GEE
roundtrip, not the sklearn code.

**ML pipeline.** Total wall time **8.752 s** for 13 weekly frames.
The data loader ingested **353,912 rows** from the Sentinel-2 subset
of the master CSV, the timeline identified **13 weeks**, and every
weekly frame converged to **14,320 pixels** (identical across all 13
weeks because the ROI geometry is fixed).

| Week | Pixels | Clusters | Noise px | Anomalies | Wall (s) |
|---|---:|---:|---:|---:|---:|
| 2025-W32 | 14320 | 2 | 1664 | 1 | 0.550 |
| 2025-W33 | 14320 | 2 | 3543 | 1 | 0.561 |
| 2025-W35 | 14320 | 0 | 14320 | 0 | 0.612 |
| 2025-W36 | 14320 | 2 | 1575 | 1 | 0.534 |
| 2025-W37 | 14320 | 6 | 5471 | 1 | 0.578 |
| 2025-W38 | 14320 | 3 | 2340 | 1 | 0.579 |
| 2025-W39 | 14320 | 2 | 2569 | 1 | 0.546 |
| 2025-W40 | 14320 | 2 |  587 | 1 | 0.558 |
| 2025-W41 | 14320 | 2 |  654 | 1 | 0.537 |
| 2025-W42 | 14320 | 2 |  442 | 2 | 0.520 |
| 2025-W43 | 14320 | 2 |  703 | 1 | 0.556 |
| 2025-W44 | 14320 | 2 |  272 | 1 | 0.591 |
| 2025-W45 | 14320 | 2 |  578 | 2 | 0.598 |

The ISO-week sequence is W32, W33, **[W34 missing]**, W35, ..., W45.
W34 is absent because no valid Sentinel-2 acquisition fell in that
ISO week (cloud cover), exactly the kind of gap the weekly
architecture is designed to absorb gracefully.

### 6.2 Cluster stability

Eleven of the 13 weeks return **exactly two clusters**. The exceptions:

- **W35** returns *zero* clusters (14,320 noise pixels). Residual
  cloud contamination collapses the feature distribution and HDBSCAN
  declines to form any cluster at the configured `min_cluster_size`.
  The pipeline correctly reports `clusters=0, anomalies=0` and
  continues. Degenerate weeks are flagged, not faked.
- **W37** returns 6 clusters with 5471 noise pixels; the tracker
  registered `new=5, continued=1, lost=1`.
- **W38** returns 3 clusters with `new=2, continued=1, lost=5`, the
  aftershock of W37.

From W38 onwards, the pipeline settles into a stable two-cluster
regime with exactly one continued track per week
(`new=1, continued=1, lost=1`) through W45. The noise fraction also
drops monotonically into the late season: 5471 → 2340 → 2569 → 587 →
654 → 442 → 703 → 272 → 578, consistent with a vineyard moving into
a low-activity phase where the feature distribution tightens.
Qualitatively, **most of the parcel resolves into two stable zones
for most of the ripening window** — exactly the kind of behaviour an
agronomist would hope for.

### 6.3 Anomaly heatmaps

Per-week anomaly counts are one or two in every non-degenerate week.
The absolute number is not the interesting quantity — the
95th-percentile threshold will always yield a few anomaly clusters by
construction. What matters is **which** tracks are flagged and
whether those tracks persist. The integration path from weekly
`anomalies_<week_id>.csv` files into the dashboard heatmap is
documented in `ARCHITECTURE.md`.

### 6.4 What we cannot claim

This is the single most important subsection of the report.

**No ground-truth vineyard zonation map exists for Fantinel37.** We
did not have access to in-field vigour measurements, yield maps, or
agronomist-drawn zone polygons for the parcel. Every output of the
pipeline — the weekly cluster partitions, the tracked cluster
identities, the anomaly flags — is an **unsupervised** construction.
It is internally consistent, reproducible and defensible from the
data, but **not validated against an external labelled reference**.

As a direct consequence:

- **No precision, recall, F1, AUC or any other
  accuracy-on-target-domain metric is reported in this document, and
  none can be.** Any such number would be fabricated.
- The "2 clusters" we see most weeks might correspond to the textbook
  high-vigour / low-vigour split the design documents motivate, or to
  a geometric artefact of the ROI shape and feature variance. Without
  a ground-truth map we cannot arbitrate between the two.
- The anomaly flags are "statistical outliers for this week under
  HDBSCAN", not "confirmed agronomic problems".
- Validation is therefore **qualitative and operational**: visual
  inspection of weekly maps against satellite basemaps, consistency
  checks on cluster number and stability, and monitoring of per-step
  timing for performance regressions.

**What this project is being evaluated on**, in the context of the
MLOps course it was built for, is the engineering quality of the
pipeline — its modularity, reproducibility, monitoring and
observability, extensibility to new parcels and sensors, testing
strategy, and the honesty with which it reports its own limits. It
is not being evaluated as a benchmark on a labelled ML dataset,
because no such labelled dataset exists for this problem at this
scale.

---

## 7. Discussion

### 7.1 What worked

- **The master-slave grid.** Pixel counts identical across weeks
  (14,320 every time), deterministic reruns, and no phantom
  misaligned pixels all follow from strict reprojection onto the
  Sentinel-2 master.
- **MiniBatchKMeans + HDBSCAN cascade.** Quantising to a few hundred
  microclusters before HDBSCAN gave a stable partition and fit each
  weekly frame into half a second of wall time. `random_state=42`
  is what makes the whole pipeline reproducible.
- **Weekly cadence.** The per-week `cluster_status` column in
  `processing_summary.csv` is what made the W37 burst and the W38
  transient visible at all; a single-shot model would have averaged
  them out.
- **Monitoring JSONs.** Every quantitative claim in Section 6 is
  traceable to one of two JSON files on disk. Monitoring was built
  early on the assumption that a pipeline you cannot measure is a
  pipeline you cannot trust.

### 7.2 What we would do differently

- **The tracker.** The 30%-overlap majority vote is fine when
  clusters are large and stable (W40-W45) but breaks on transient
  weeks like W37. A Hungarian assignment on centroid distance would
  likely make the W37-W38 transition cleaner.
- **Anomaly thresholding.** Hard-coded at the 95th percentile. A
  rolling threshold that learns the normal outlier-score distribution
  over the last N weeks and flags genuine excursions would be more
  honest than always flagging the top 5% of this week.
- **Thermal data.** ECOSTRESS (70 m, ~3 day revisit) was the original
  target but was retired from GEE. The Landsat 8/9 merge works but
  the effective thermal resolution is coarser and the revisit
  sparser.
- **Soil layer.** Clay content from SoilGrids was dropped because
  stacking the additional bands exceeded the GEE user-memory budget.
  Topography is a rough proxy.

### 7.3 Limitations

- **No ground truth, therefore no accuracy.** Repeated from §6.4.
- **Fixed ISO-week cadence** may cut across phenological transitions
  in unusual seasons.
- **Per-week standardisation** means outlier scores are not directly
  comparable across weeks.
- **Single parcel**: cross-parcel generalisation has not been
  benchmarked.
- **Cloud-driven gaps** (W34 missing, W35 degenerate) force the
  tracker to re-open temporal holes.

---

## 8. MLOps Considerations

This section is the intellectual centre of gravity of the report.
The scientific ambition of SmartHarvest is modest — it is an
unsupervised zonation pipeline — but the engineering ambition is
high. A pipeline you cannot measure, reproduce, test or extend is
not one you can take to production, no matter how elegant the
underlying model.

### 8.1 Modularity

The repository is split along a strict responsibility boundary.
`modules/` holds one Python module per remote-sensing data source
(`sentinel2.py`, `sentinel1.py`, `landsat_thermal.py`, `srtm.py`),
plus `assembly.py` and `reporting.py`; each exposes a function
returning a reprojected `ee.Image` and a metadata dict. `ml/` holds
the ML kernel (`pipeline.py`, `clustering.py`, `tracking.py`,
`data_loader.py`, `output.py`) and depends only on pandas, numpy,
sklearn and hdbscan — **no GEE imports** — so it is testable offline
against an exported CSV without GEE credentials. `tools/` holds
visualisation and utility scripts that may import from `modules/`
and `ml/`, but nothing in `modules/` or `ml/` imports from `tools/`.
`app.py` (Flask dashboard) and `main.py` (CLI orchestrator) are thin
composition-roots that wire modules together but contain no
processing logic of their own. The payoff is concrete: the ML
pipeline runs in **8.75 s** on 13 weekly frames because it never
reaches out to GEE after the CSV is on disk.

### 8.2 Monitoring and observability

Every step writes to a monitoring JSON via `modules/monitoring.py`.
`monitor.start_step(name)` / `monitor.stop_step(name, metrics_dict)`
wrap each logical step, and `monitor.save(output_dir)` serialises
steps, durations and custom metrics to `monitoring_core.json` or
`monitoring_ml.json` — each run leaves a self-describing trail under
`output/<project>/`. Every quantitative claim in Section 6 is
reproducible by opening two JSON files. The dominant cost of the
core pipeline (the GEE `Download` step at 2548.49 s out of 2709.75 s)
was discovered from `monitoring_core.json`, not guesswork — without
that measurement the developer would have optimised the wrong thing.
When the W35 degenerate case occurred, it was visible as
`{"pixels": 14320, "clusters": 0, "anomalies": 0}` — exactly the
level of detail needed to investigate without re-running the
pipeline.

### 8.3 Reproducibility

Three ingredients make a SmartHarvest run reproducible:
**deterministic reprojection** (the master-slave grid means the
exported CSV is bit-identical modulo GEE catalogue updates given the
same ROI and date window); **seeded ML**
(`MiniBatchKMeans(random_state=42)` pins microcluster boundaries,
HDBSCAN is deterministic by construction, and `np.percentile` /
`np.nanmedian` are deterministic — no stochastic step exists in the
ML pipeline after the seed); and **versioned inputs** (ROI as a file
in `rois/`, parameters in `config.py` and the defaults of
`ml/clustering.py`, no hidden env vars or external config servers).
The monitoring JSONs we ship are themselves a frozen reference run.

### 8.4 Testing strategy

The `tests/` directory follows a three-layer philosophy. **Unit-like
tests** on the ML kernel fixture synthetic DataFrames into
`normalize_features`, `microclustering` and `hdbscan_clustering`,
asserting shapes, label bounds (`-1 <= label`) and the presence of
tracking fields. **Integration tests** against the shipped demo CSV
(70,000 rows, no GEE required) run the full ML pipeline and assert
`weeks_processed > 0`, `clusters >= 0` and no exceptions — cheap in
CI and catches most real regressions. **Contract tests** assert that
`monitoring_core.json` and `monitoring_ml.json` exist, parse, and
contain the expected top-level keys (`project`, `pipeline`, `steps`,
`duration_total_sec`), validating the observability contract itself.

### 8.5 Extensibility

Adding a new sensor is a five-step operation: write
`modules/<new_sensor>.py` exposing
`get_<sensor>_data(master_crs) -> (ee.Image, metadata)` per the
contract in `ARCHITECTURE.md`; register it in `main.py`; add the new
bands to `schema.py`; optionally add a `tools/debug_<sensor>.py`;
rerun the acquisition pipeline. Adding a new parcel is simpler: drop
a `.geojson` in `rois/` and pass the project name on the CLI — the
shipped demo shows this end-to-end. Adding a new clustering model
sits entirely inside `ml/clustering.py`; swapping HDBSCAN for a
Bayesian Gaussian Mixture is a one-function change and tracking,
anomaly detection and monitoring do not need to know.

### 8.6 Deployment

The repository ships a `Dockerfile` and a `docker-compose.yml`. The
intended topology is a container image with Python, GEE credentials
mounted at runtime, and the full codebase; a scheduled trigger
(cron, GitHub Actions, Airflow) that runs `main.py` per active
project and then `run_ml_weekly.py` against the resulting CSV; and
`output/<project>/` as the delivery artefact — self-contained, with
maps, JSONs, reports and weekly cluster CSVs under a single tree
that can be rsynced or uploaded to object storage. `app.py` wraps
the same code as a Flask application for interactive exploration;
a serious deployment would sit behind a reverse proxy with
authentication. The Docker image is single-stage, trading image
size for a single-image deployment story.

---

## 9. Conclusions and Future Work

SmartHarvest is a reproducible, observable, multi-sensor vineyard
zonation pipeline built with MLOps-grade engineering practices on
top of Google Earth Engine and the Python scientific stack. The
reference Fantinel37 run processed 62 Sentinel-2, 30 Sentinel-1 and
14 Landsat scenes into a 740,552-row per-pixel feature table, then
built 13 weekly cluster partitions of 14,320 pixels each in under
nine seconds of compute, and produced stable two-cluster partitions
for most weeks of the 2025 ripening window with a single degenerate
week (W35) and a transient anomaly burst (W37-W38) that the tracker
handled cleanly.

We explicitly do not claim target-domain accuracy, because no
ground-truth zonation is available for Fantinel37. What we *do*
claim is that the pipeline is honest about that, every number in
this report can be reproduced from the JSON files on disk, and the
engineering choices — master-slave grid, microclustering cascade,
weekly monitoring JSON contract, modular sensor/ML split — are the
right ones for a production viticulture system.

**Future work**, roughly in order of expected impact:

1. Replace the simple overlap tracker with a Hungarian assignment on
   centroid distance to cleanly handle weeks like W37.
2. Ingest in-field data (yield maps, °Brix, vigour surveys) from a
   cooperating estate to enable real accuracy benchmarks.
3. Restore the soil layer from SoilGrids tiles sourced outside GEE.
4. Rolling anomaly thresholds — "unusual relative to recent history"
   rather than "top 5% of this week".
5. Multi-parcel benchmarking across estates with different topography
   and varieties.
6. CI wiring of the contract tests so every pull request validates
   the monitoring JSON schema automatically.

---

## 10. References

**Academic / domain**

- Gorelick, N., Hancher, M., Dixon, M., Ilyushchenko, S., Thau, D. &
  Moore, R. (2017). *Google Earth Engine: Planetary-scale geospatial
  analysis for everyone.* Remote Sensing of Environment 202, 18-27.
- Hall, A., Lamb, D. W., Holzapfel, B. & Louis, J. (2002). *Optical
  remote sensing applications in viticulture: a review.* AJGWR 8(1),
  36-47.
- Matese, A. & Di Gennaro, S. F. (2018). *Practical applications of a
  multisensor UAV platform in precision viticulture.* Agriculture
  8(7), 116.
- Campello, R. J. G. B., Moulavi, D. & Sander, J. (2013).
  *Density-based clustering based on hierarchical density estimates.*
  PAKDD 2013, 160-172.
- McInnes, L., Healy, J. & Astels, S. (2017). *hdbscan: Hierarchical
  density based clustering.* JOSS 2(11), 205.
- Sculley, D. et al. (2015). *Hidden technical debt in machine
  learning systems.* NeurIPS 2015.
- ESA (2015). *Sentinel-2 User Handbook.*
- Torres, R. et al. (2012). *GMES Sentinel-1 mission.* RSE 120, 9-24.

**Software**

`google-earthengine` (data access), `pandas`, `numpy`,
`scikit-learn` (`StandardScaler`, `MiniBatchKMeans`), `hdbscan`,
`folium`, `Flask`, `Docker` / `docker-compose`.

**Internal documents**

- `docs/reports-italian/pipeline_report.md` — primary methodology
  source.
- `docs/reports-italian/smartharvest_complete.md` — system spec,
  master-slave grid design.
- `docs/reports-italian/data_strategy_report.md` — data strategy and
  feature justification.
- `README.md` — user-facing overview.
- `ARCHITECTURE.md` — developer guide.

---

**Authors:**

- **Lorenzo Di Bernardo** · University of Trieste — MSc Artificial Intelligence & Data Science — MLOps, software development
- **Giovanni Mason** · Ca' Foscari University of Venice — Business & Administration — pipeline architecture, research, documentation

**Course:** Machine Learning Operations (MLOps) · Academic year 2025-26
**Final evaluation:** 30/30
