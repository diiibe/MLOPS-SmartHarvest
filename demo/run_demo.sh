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

echo ""
echo "✅ Demo complete."
echo ""
echo "   Weekly maps:       output/${PROJECT}/ml_weekly/weekly/"
echo "   Monitoring stats:  output/${PROJECT}/ml_weekly/monitoring_ml.json"
echo "   Tracking log:      output/${PROJECT}/ml_weekly/tracking_state.json"
echo ""
echo "   To explore interactively: python app.py"
echo ""
