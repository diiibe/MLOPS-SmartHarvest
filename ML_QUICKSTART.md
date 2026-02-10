# ML Weekly Analysis - Quick Start Guide

## Installation

Install ML dependencies:

```bash
pip install hdbscan scikit-learn
```

(pandas, numpy, matplotlib already installed)

## Usage

### 1. Run ML Pipeline on Existing Project

```bash
# Process your latest project
python run_ml_weekly.py Fntinel37

# Or force reprocess all weeks
python run_ml_weekly.py Fntinel37 --force
```

### 2. View Results

**Cluster Maps (Images)**:
```bash
ls output/Fntinel37/ml_weekly/weekly/
open output/Fntinel37/ml_weekly/weekly/2025-W*/cluster_image_*.png
```

**Cluster Data (CSV)**:
```bash
# Latest week clusters
cat output/Fntinel37/ml_weekly/weekly/2025-W*/cluster_map_*.csv | tail -20

# Processing summary
cat output/Fntinel37/ml_weekly/processing_summary.csv
```

### 3. View on Dashboard Map

1. Open dashboard: `http://127.0.0.1:5000/dashboard/Fntinel37`
2. Go to "Interactive Map" tab
3. Enable layer: "ML Clusters (2025-Wxx)" in layer control
4. **Interpretation**:
   - **Different colors** = different clusters
   - **Larger markers** = higher anomaly score
   - **Popup** = cluster info + track ID

### 4. Integrate with Pipeline

The ML analysis runs **automatically** after CSV generation in `main.py`:

```python
# In main.py, after CSV assembly:
from ml.pipeline import run_ml_pipeline

ml_result = run_ml_pipeline(
    csv_path=merged_path,
    output_base_dir=output_dir
)
```

## What You Get

### Per Week:
1. **cluster_map_YYYY-Wxx.csv**: Every pixel with cluster label, track ID, outlier score
2. **outlier_map_YYYY-Wxx.csv**: Only anomalous pixels (top 10%)
3. **anomalies_YYYY-Wxx.csv**: Anomalous clusters summary
4. **Images**: Visual maps (PNG)

### Global:
1. **tracking_state.json**: Persistent tracking between weeks
2. **processing_summary.csv**: Summary table of all weeks

## Typical Workflow

```
1. Run EO pipeline → CSV generated
2. Run ML pipeline → Weekly clusters + tracking
3. View dashboard → ML layer on map
4. Inspect anomalies → Check outlier_map CSV
5. New data arrives → Rerun → Only current week updated
```

## Example Output

```
Week 2025-W44:
- 14,320 pixels
- 8 clusters found
- 2 new, 5 continued, 1 lost
- 3 anomalous clusters detected
```

Map shows:
- 8 colored regions (clusters)
- Tracked clusters keep same color across weeks
- Anomalous areas have larger markers

## Troubleshooting

**"No S2 data found"**
→ CSV missing or no Sentinel-2 rows

**"No weeks found"**
→ Date column missing or malformed

**"Skipping week - insufficient data"**
→ Week has <10 pixels (normal for cloud-heavy weeks)

**Map layer not showing**
→ Run `python run_ml_weekly.py <project>` first
→ Refresh dashboard

## Advanced: Custom Parameters

Edit `ml/clustering.py` to tune:
- `max_microclusters`: Default 5000
- `min_cluster_size` (HDBSCAN): Default 10
- `target_micro`: Pixels per microcluster (~30)

Edit `ml/tracking.py`:
- `overlap_pct`: Matching threshold (30%)

## Performance

| ROI Size | Pixels | Time/Week | Full 12 Weeks |
|----------|--------|-----------|---------------|
| 50 ha    | 5K     | ~5s       | ~1 min        |
| 150 ha   | 15K    | ~15s      | ~3 min        |
| 500 ha   | 50K    | ~60s      | ~12 min       |

## Next Steps

- [ ] Add ML layer to dashboard by default
- [ ] Show anomaly timeline chart
- [ ] Export cluster statistics to report
- [ ] Email alerts for new anomalies

## Questions?

See full documentation: `ml/README.md`
