# Screenshots

This folder holds the images referenced by `README.md` and `TECHNICAL_REPORT.md`.

## Files managed automatically

The following files are generated (copied from real pipeline runs) during the
portfolio uplift work and should not need manual intervention:

- **`ml-anomaly-heatmap-W45.png`** — Week-W45 outlier heatmap from the
  Fantinel37 vineyard. Used as the hero image in the main README.
- **`ml-cluster-map-W45.png`** — Week-W45 cluster map from the same vineyard.
  Used in the Architecture section of the main README.

## Placeholders that the author should replace

The following files are committed as placeholders. Replace each one with a
real PNG at the correct path:

- **`dashboard-home.png`** — Screenshot of the Flask dashboard landing page
  after `python app.py`, showing the project list and the option to create a
  new project.
- **`dashboard-roi-selection.png`** — Screenshot of the ROI drawing interface
  with a vineyard polygon being drawn on the interactive map.
- **`dashboard-analysis.png`** — Screenshot of the dashboard after running the
  ML analysis, showing the anomaly heatmap overlaid on the base map.
- **`demo.gif`** — Short (15-30 seconds) screen recording of
  `docker compose up demo` start-to-finish, or of the Flask dashboard
  demonstrating the end-to-end flow.

When you replace a placeholder, keep the exact filename so the README
references continue to work.

## Filename conventions

- All filenames use lowercase kebab-case except where they reference a
  specific week (e.g., `-W45`).
- PNGs are preferred over JPG for UI screenshots (lossless).
- GIFs under 5 MB render inline on GitHub; larger GIFs should be trimmed or
  linked externally.
