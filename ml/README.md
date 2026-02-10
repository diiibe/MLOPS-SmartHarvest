# SmartHarvest ML Weekly Kernel

## Overview

Automated weekly clustering and anomaly detection for Sentinel-2 Earth Observation data.

## Features

- **Weekly Timeline**: Processes S2 observations week-by-week
- **Microclustering**: Reduces salt-and-pepper noise via Mini-Batch K-Means
- **HDBSCAN Clustering**: Density-based clustering for robust pattern detection
- **Temporal Tracking**: Links clusters across weeks (birth, continuation, death)
- **Anomaly Detection**: Identifies outlier clusters based on HDBSCAN scores
- **Visual Outputs**: Cluster maps and outlier heatmaps per week
- **Incremental Updates**: Only processes new/updated weeks

## Usage

### Command Line

```bash
# Process latest week
python run_ml_weekly.py <project_name>

# Reprocess all weeks
python run_ml_weekly.py <project_name> --force

# Example
python run_ml_weekly.py Fntinel37
```

### Python API

```python
from ml.pipeline import run_ml_pipeline

result = run_ml_pipeline(
    csv_path='output/MyProject/SmartHarvest_MyProject.csv',
    output_base_dir='output/MyProject',
    force_reprocess=False
)

if result['success']:
    print(f"Latest week: {result['latest_week']}")
    print(f"Cluster map: {result['latest_cluster_map']}")
```

## Output Structure

```
output/<project>/ml_weekly/
├── weekly/
│   ├── 2025-W44/
│   │   ├── cluster_map_2025-W44.csv       # Pixel-level cluster labels
│   │   ├── outlier_map_2025-W44.csv       # High outlier pixels
│   │   ├── anomalies_2025-W44.csv         # Anomalous clusters
│   │   ├── cluster_image_2025-W44.png     # Visual cluster map
│   │   └── outlier_image_2025-W44.png     # Visual outlier heatmap
│   └── 2025-W45/
│       └── ...
├── tracking_state.json                     # Persistent tracking state
└── processing_summary.csv                  # Summary of all processed weeks
```

## Pipeline Steps

1. **Load & Filter**: Read CSV, filter S2 observations
2. **Weekly Timeline**: Define weeks (ISO week format)
3. **Weekly Frame**: One observation per pixel per week (most recent)
4. **Normalization**: StandardScaler per week
5. **Microclustering**: MiniBatchKMeans to reduce noise
6. **HDBSCAN**: Density-based clustering on microclusters
7. **Tracking**: Match clusters week-to-week (majority overlap)
8. **Anomaly Detection**: Flag high outlier scores (>95th percentile)
9. **Output**: Save CSVs, images, and state

## Map Integration

The latest week's clusters are automatically displayed on the dashboard map as a layer:
- **Layer Name**: "ML Clusters (YYYY-Wxx)"
- **Colors**: Different color per cluster
- **Size**: Larger markers = higher outlier score (more anomalous)
- **Popup**: Shows cluster label, track ID, outlier score, coordinates

To toggle the layer, use the layer control in the top-left of the map.

## Parameters

Default parameters (tuned for vineyard monitoring):
- **Microclustering**: ~30 pixels per microcluster
- **HDBSCAN min_cluster_size**: 10 (or auto-adjusted)
- **Tracking overlap threshold**: 30%
- **Anomaly threshold**: 95th percentile outlier score

## Robustness

- **Idempotent**: Running twice without new data does nothing
- **Incremental**: Only processes new weeks + current week
- **Fault-tolerant**: Skips weeks with insufficient data (<10 pixels)
- **State persistence**: Tracking state saved after each week
- **No .getInfo() calls**: Fully client-side after CSV download

## Dependencies

```
pandas
numpy
scikit-learn
hdbscan
matplotlib
```

Install:
```bash
pip install pandas numpy scikit-learn hdbscan matplotlib
```

## Examples

### Check Processing Summary

```bash
cat output/Fntinel37/ml_weekly/processing_summary.csv
```

### View Cluster Map

```bash
open output/Fntinel37/ml_weekly/weekly/2025-W45/cluster_image_2025-W45.png
```

### Load Cluster Data

```python
import pandas as pd

df = pd.read_csv('output/Fntinel37/ml_weekly/weekly/2025-W45/cluster_map_2025-W45.csv')
print(df.groupby('cluster_label').size())
```

## Troubleshooting

**No weeks processed**
- Check CSV has S2 data: `satellite` column contains 'S2'
- Check date range: at least one full week of data

**Empty cluster maps**
- Insufficient data for that week (<10 pixels after filtering)
- All features NaN (cloud-masked)

**Tracking not working**
- Delete `tracking_state.json` and rerun with `--force`
- Ensures fresh tracking from first week

**Map layer not showing**
- Run ML pipeline first: `python run_ml_weekly.py <project>`
- Check `ml_weekly/weekly/` folder exists
- Regenerate map: reopen dashboard

## Performance

Typical processing time (143 ha vineyard, 14K pixels):
- **Single week**: ~10-30 seconds
- **Full 3-month timeline (12 weeks)**: ~3-5 minutes
- **Incremental update (1 new week)**: ~10 seconds

## Future Enhancements

- [ ] Split/merge tracking (currently: new birth on split)
- [ ] Multi-temporal features (velocity, acceleration)
- [ ] Per-cluster statistics export
- [ ] Anomaly severity ranking
- [ ] Integration with dashboard charts
