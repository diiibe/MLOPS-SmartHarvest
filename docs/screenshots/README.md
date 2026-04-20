# Screenshots

This folder holds the images referenced by `README.md` and `TECHNICAL_REPORT.md`.

## Current inventory

All assets below are real captures from a full Fantinel37 run and are
referenced by `README.md` (and in some cases `TECHNICAL_REPORT.md`):

- **`ml-anomaly-heatmap-W45.png`** — Week-W45 outlier heatmap. Hero image.
- **`ml-cluster-map-W45.png`** — Week-W45 HDBSCAN cluster map.
- **`dashboard-home.png`** — Flask dashboard landing page with project list.
- **`dashboard-roi-selection.png`** — ROI polygon drawing on the interactive
  map.
- **`dashboard-analysis.png`** — Anomaly Detection tab with the outlier
  heatmap active by default.
- **`demo.gif`** — End-to-end walk-through: `docker compose up demo` plus
  the dashboard. Kept under 5 MB so it renders inline on GitHub.
- **`demo.mp4`** — HD (1920×) companion to `demo.gif`, linked as "Watch in
  HD" from the README.

If you re-record any of these, keep the exact filename so the README
references continue to work.

## Filename conventions

- All filenames use lowercase kebab-case except where they reference a
  specific week (e.g., `-W45`).
- PNGs are preferred over JPG for UI screenshots (lossless).
- GIFs under 5 MB render inline on GitHub; larger GIFs should be trimmed or
  linked externally.
