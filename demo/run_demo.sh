#!/usr/bin/env bash
set -euo pipefail

# SmartHarvest demo mode: runs the ML pipeline on a bundled Fantinel37
# vineyard snapshot without requiring Google Earth Engine authentication.

PROJECT="demo"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

export MPLBACKEND=Agg

echo ""
echo "🍇 SmartHarvest demo — running ML pipeline on bundled vineyard snapshot"
echo "======================================================================"
echo ""

mkdir -p "output/${PROJECT}"
cp -f "demo/data/Fantinel37.csv" "output/${PROJECT}/SmartHarvest_${PROJECT}.csv"

python run_ml_weekly.py "${PROJECT}"

python - <<'PY'
import json, os
import pandas as pd
from modules import reporting

project = "demo"
output_dir = os.path.join("output", project)
csv_path = os.path.join(output_dir, f"SmartHarvest_{project}.csv")
ml_dir = os.path.join(output_dir, "ml_weekly")

df = pd.read_csv(csv_path, usecols=["date", "spatial_id", "satellite"])
n_pixels = df["spatial_id"].nunique()
date_min, date_max = df["date"].min(), df["date"].max()

metadata = [
    {
        "source": "ROI Stats",
        "area_ha": round(n_pixels * 100 / 10000, 2),
        "area_sqm": n_pixels * 100,
        "analysis_range": f"{date_min} to {date_max}",
    },
    {
        "source": "Demo Dataset",
        "image_count": int(df["date"].nunique()),
        "date_range": f"{date_min} to {date_max}",
        "bands": ["NDVI", "NDWI", "MNDWI", "NDRE", "IRECI", "S2REP", "VH", "VV", "Ratio", "LST", "Slope"],
    },
]

metadata_path = os.path.join(output_dir, f"metadata_{project}.json")
with open(metadata_path, "w") as f:
    json.dump(metadata, f, indent=2)

report_path = os.path.join(output_dir, f"Report_{project}.md")
acq_log_path = os.path.join(output_dir, "acquisition_log.txt")
reporting.generate_report(
    metadata,
    csv_path=csv_path,
    output_path=report_path,
    acq_log_path=acq_log_path,
    ml_dir=ml_dir if os.path.exists(ml_dir) else None,
)
print(f"[OK] Report: {report_path}")
print(f"[OK] Metadata: {metadata_path}")
PY

echo ""
echo "✅ Demo complete."
echo ""
echo "   Weekly maps:       output/${PROJECT}/ml_weekly/weekly/"
echo "   Monitoring stats:  output/${PROJECT}/ml_weekly/monitoring_ml.json"
echo "   Tracking log:      output/${PROJECT}/ml_weekly/tracking_state.json"
echo "   Report:            output/${PROJECT}/Report_${PROJECT}.md"
echo ""
echo "   To explore interactively: python app.py"
echo ""
