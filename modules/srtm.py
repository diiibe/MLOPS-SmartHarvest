"""
Topographic features for the SmartHarvest pipeline.

Historically this module wrapped SRTMGL1 (`USGS/SRTMGL1_003`), which
covers only ±60° latitude and shows visible voids over steep terrain.
The pipeline now defaults to Copernicus GLO-30 (`COPERNICUS/DEM/GLO30`),
the modern global DEM derived from the TanDEM-X mission — better
quality, fewer voids, full polar coverage. SRTM stays as a fallback
when the Copernicus mosaic over the ROI is empty (e.g. an asset
permission glitch).

The module name + entry point stay `get_srtm_data` for backward
compatibility with `main.py`; we just renamed the implementation.
"""

import ee
import config


# SRTM v3 (SRTMGL1_003) covers roughly 56°S to 60°N — the legacy
# fallback. Copernicus GLO-30 covers the whole globe, so this band
# only matters when we drop back to SRTM.
_SRTM_LAT_MIN = -56.0
_SRTM_LAT_MAX = 60.0


def _build_copernicus_dem(roi_buffer):
    """Mosaic the Copernicus GLO-30 tiles intersecting the ROI.

    Returns an `ee.Image` with a single `Elevation` band, or `None`
    if the mosaic comes back empty (no tiles intersect the ROI, or
    the asset is unavailable).
    """
    cop = (
        ee.ImageCollection("COPERNICUS/DEM/GLO30")
        .filterBounds(roi_buffer)
        .select("DEM")
    )
    try:
        size = cop.size().getInfo()
    except Exception as exc:
        print(f"[DEM] Copernicus availability check failed: {exc}")
        return None
    if not size:
        return None
    return cop.mosaic().rename("Elevation")


def _build_srtm(roi_buffer):
    """Legacy fallback. Same SRTMGL1 image we used to ship by default."""
    srtm = ee.Image("USGS/SRTMGL1_003")
    return srtm.clip(roi_buffer).select("elevation").rename("Elevation")


def get_srtm_data(master_crs):
    """
    Build a static topo image (Elevation + Slope) for the project.

    The function tries Copernicus GLO-30 first, then falls back to
    SRTMGL1 if Copernicus is empty or fails. The master CRS is the
    reference S2 projection so the topo image lines up with the rest
    of the temporal stack.

    Args:
        master_crs (ee.Projection): Projection to align the output to.
    Returns:
        image (ee.Image): Static image with `Elevation` + `Slope` bands.
        metadata (dict): Source description + coverage flags.
    """
    available = True
    coverage_note = None
    source_label = "Copernicus GLO-30"
    source_collection = "COPERNICUS/DEM/GLO30"

    roi_buffer = config.ROI.buffer(100)

    elevation = _build_copernicus_dem(roi_buffer)
    if elevation is None:
        # Fallback path — log explicitly so we don't silently regress.
        print("[DEM] Copernicus GLO-30 returned no data; falling back to SRTM v3.")
        try:
            bounds = config.ROI.bounds().coordinates().getInfo()[0]
            lats = [pt[1] for pt in bounds]
            lat_min, lat_max = min(lats), max(lats)
            if lat_max > _SRTM_LAT_MAX or lat_min < _SRTM_LAT_MIN:
                available = False
                coverage_note = (
                    f"ROI latitude range [{lat_min:.2f}, {lat_max:.2f}] falls outside "
                    f"SRTM coverage [{_SRTM_LAT_MIN}, {_SRTM_LAT_MAX}], and Copernicus "
                    "GLO-30 returned no data. Slope will be NaN."
                )
                print(f"[DEM] WARNING: {coverage_note}")
        except Exception as exc:
            print(f"[DEM] Could not compute ROI bounds for coverage check: {exc}")

        elevation = _build_srtm(roi_buffer)
        source_label = "SRTM v3 (fallback)"
        source_collection = "USGS/SRTMGL1_003"

    slope = ee.Terrain.slope(elevation).rename("Slope")
    topo = ee.Image.cat([elevation, slope])

    # Resample to master CRS at TARGET_SCALE so the topo grid matches
    # the temporal sample grid. Bicubic resample first to soften the
    # 30 m → 10 m step before reproject; without it the slope mosaic
    # shows hard tile seams when oversampled to 10 m.
    topo_resampled = (
        topo.resample("bicubic").reproject(crs=master_crs, scale=config.TARGET_SCALE)
    )

    metadata = {
        # Key kept as "SRTM" so the rest of the pipeline + UI rows
        # don't need to migrate to a new label. The `source` /
        # `collection` fields below carry the truthful provenance.
        "source": source_label,
        "collection": source_collection,
        "image_count": "Static",
        "bands": ["Elevation", "Slope"],
        "available": available,
    }
    if coverage_note:
        metadata["reason"] = coverage_note

    return topo_resampled, metadata
