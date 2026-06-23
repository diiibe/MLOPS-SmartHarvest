# Data Analysis tab — production-grade redesign

**Date**: 2026-05-03
**Branch**: `claude/landslide-design-language`
**Status**: in-progress (phase 1)

## Context

The dashboard's Data Analysis tab today is a flat vertical list of
~11 Plotly sections with one `?` info icon per section. Content is
solid (acquisition timeline, cloud-cover scatter, index trends,
overlays, distributions, correlations, NDVI-by-slope, glossary)
but the structure does not scale: more charts make the page longer
and harder to navigate, and there is no information hierarchy to
guide the user from "state today" to "deep statistical analysis".

The user asks for a redesign that:

1. keeps every chart that exists today
2. adds production-quality companions (phenology, sub-cell, change
   detection, data completeness, KPI strip)
3. organises the section into themed **sub-tabs** rather than a
   single scroll
4. improves the hover info on every chart
5. uses motion + frontend-design treatment in line with the rest of
   the dashboard's wine-house aesthetic

## Architecture

A new sub-tab strip mounts inside `#analysis-view`, before the
chart sections. Each sub-tab is a `<div data-subtab="…">` block;
the active block is shown via `[hidden]` toggling so the chart
HTML still parses on first paint (Plotly figures already shipped
inline survive a tab switch with no re-render cost).

Switching is a 3-step animation: outgoing tab fades + slides up
8 px (180 ms), DOM swap, incoming tab fades in with a 40 ms
stagger between sections (max 4 stagger steps, then everything
together to avoid a long settle). Hover on the segmented-control
rail moves an animated pill underneath the active tab.

## Sub-tabs

### 1. Overview — "state of the vineyard at a glance"

- **KPI strip** (4 tiles): latest-week ROI mean NDVI + delta vs
  prior week, latest-week S2 cloud %, latest-week scene count,
  weekly hot-spot anomaly count from the ML pipeline.
- **NDVI sparkline** (12 weeks rolling) — minimal axis, accent
  trend, dot for the latest point.
- **Latest-week heatmap strip** — pixel grid coloured by NDVI for
  the most recent week, no map, just the heatmap.
- **Recent acquisitions** — last 5 acquisitions with sensor +
  cloud %.

### 2. Temporal — "how the vineyard moves through time"

Existing: index_trends, canopy_overlay, water_overlay,
radar_overlay, thermal_vs_vigour.

New (phase 2): phenology curve with greening / peak / senescence
markers, climatology band (when ≥ 2 prior years available).

### 3. Spatial — "how the vineyard varies in space"

Existing: distributions, correlation, ndvi_by_slope.

New (phase 1): change-detection summary card — ΔNDVI between the
last 30 days and the prior 30 days, broken into "improved /
stable / declined" pixel counts.

New (phase 2): per-pixel time-series sampler, sub-cell aggregation
heatmap (e.g. 50 m blocks with NDVI mean + variance), Moran's I
spatial autocorrelation.

### 4. Quality & Provenance — "is the input data trustworthy?"

Existing: acquisition timeline, cloud_coverage.

New (phase 1): data-completeness matrix — week × variable, cell
shaded by % of pixels with valid data; surfaces missing-band cases
like the cormor_2 S2 regression at a glance.

New (phase 2): masking budget breakdown (by cause), sensor health
card (latency, max gap, next expected acquisition).

## Hover info improvements

The `?` icon already carries `data-tooltip` text. The redesign:

- bumps tooltip width to 320 px so longer explanations breathe
- bolds the first sentence as the headline ("What this shows")
- adds a "How to read it" 2-3 line micro-list rendered via simple
  `<br>•` separators inside the tooltip text
- links variable codes inside the tooltip to the glossary entry
  via `data-glossary-link="<code>"` so clicking the chip scrolls
  the glossary into view

## Glossary placement

The glossary stays as a sticky / dismissible panel reachable from
every sub-tab via a small "Variables ↗" link in the sub-tab strip
(no longer a vertical section at the bottom of one specific
sub-tab — it belongs to all of them).

## Animation budget

- Tab switch: 180 ms ease-out-quint outgoing, 220 ms ease-out-quint
  incoming, 40 ms stagger between sections within the incoming
  tab (capped at 4 steps).
- KPI tile entrance: scale 0.96 → 1, opacity 0 → 1, 240 ms.
- `prefers-reduced-motion: reduce` collapses every transition to
  10 ms.

## Phase plan

**Phase 1 (this session)**: sub-tab system, re-grouping, KPI strip
+ sparkline + recent-acquisitions Overview, ΔNDVI summary in
Spatial, data-completeness matrix in Quality, hover treatment
upgrade, glossary as dismissible panel, motion treatment.

**Phase 2 (next session)**: phenology curve, sub-cell heatmap,
per-pixel sampler, Moran's I, masking budget breakdown.

## Acceptance

- All 11 existing charts still render exactly as before.
- The four sub-tabs are reachable without scrolling.
- Tab switch animates without layout jump and stays smooth on a
  cold-cache reload of `/dashboard/Cormor`.
- Hover on any `?` icon explains both what the chart shows and how
  to read it, in ≤ 80 words.
- Tests stay green (44/44) and `make check` passes (when applicable).

## Risk / non-goals

- We do NOT redo the chart toolkit (still Plotly).
- We do NOT migrate to React or any SPA framework.
- We do NOT touch the Map / Anomaly / Report tabs.
- The sub-cell analysis itself is phased: phase 1 only ships the
  ΔNDVI count summary; the heatmap + Moran's I land in phase 2.
