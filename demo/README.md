# SmartHarvest Demo Mode

This folder contains everything needed to run a live SmartHarvest demo on a
stranger's machine **without** a Google Earth Engine account.

## What the demo does

1. Copies the bundled `demo/data/Fantinel37.csv` — a stratified subsample of
   a real 14-week pipeline output from a Friuli vineyard — into the
   `output/demo/` directory.
2. Runs `python run_ml_weekly.py demo`, which executes the weekly clustering
   pipeline on the copied data: microclustering (MiniBatchKMeans), HDBSCAN,
   outlier scoring, inter-week tracking.
3. Writes cluster map PNGs, outlier heatmap PNGs, and monitoring JSON to
   `output/demo/ml_weekly/`.

## How to run it

### Option A — Docker (recommended)

From the repository root:

```bash
docker compose up demo
```

Outputs land in your local `output/demo/` directory thanks to a volume
mount. The container exits on its own when the pipeline finishes (takes
approximately 30 seconds on a modern laptop).

### Option B — Directly (no Docker)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
bash demo/run_demo.sh
```

## What to expect

After completion you should see this output layout:

    output/demo/
    ├── SmartHarvest_demo.csv          # copied snapshot
    └── ml_weekly/
        ├── monitoring_ml.json          # pipeline stats
        ├── tracking_state.json         # inter-week cluster tracking
        ├── weekly/
        │   ├── 2025-W33/
        │   │   ├── cluster_image_2025-W33.png
        │   │   └── outlier_image_2025-W33.png
        │   ├── 2025-W34/
        │   ├── ...
        │   └── 2025-W46/
        └── ml_map_2025-W*.html         # interactive per-week maps

## Dataset provenance

The bundled `data/Fantinel37.csv` is a stratified random subsample of a real
pipeline output from the Fantinel37 vineyard in Friuli, Italy. All 14 weeks
(2025-W33 through 2025-W46) are preserved; 5,000 pixels are sampled per week
(70,000 rows total, seed = 42). The full source dataset (~740k rows ≈ 207 MB)
is too large to commit to Git.

The subsample is sufficient to demonstrate the pipeline's behavior end-to-end
but produces slightly lower-density cluster and anomaly maps than the
full-resolution outputs shown in the main `README.md`.

## Running on your own vineyard

The demo mode uses a bundled CSV; to run SmartHarvest on a different area
you need Google Earth Engine access. See the "Full Mode" section of the main
`README.md` for instructions.
