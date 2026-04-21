import ee
import config


# SRTM v3 (SRTMGL1_003) is the 1-arc-second global DEM. Its actual coverage
# is roughly 56°S to 60°N — polar regions fall outside. For ROIs outside
# this band Slope/Elevation will come back as fully masked (NaN); we warn
# the user so the silent feature-loss is visible.
_SRTM_LAT_MIN = -56.0
_SRTM_LAT_MAX = 60.0


def get_srtm_data(master_crs):
    """
    Process SRTM data to create topographic features.
    Returns a single static image with Slope (constant across all dates).

    Args:
        master_crs (ee.Projection): The projection to align to.
    Returns:
        image (ee.Image): Static image with Slope band.
        metadata (dict): Metadata about the data source.
    """
    available = True
    coverage_note = None
    try:
        bounds = config.ROI.bounds().coordinates().getInfo()[0]
        lats = [pt[1] for pt in bounds]
        lat_min, lat_max = min(lats), max(lats)
        if lat_max > _SRTM_LAT_MAX or lat_min < _SRTM_LAT_MIN:
            available = False
            coverage_note = (
                f"ROI latitude range [{lat_min:.2f}, {lat_max:.2f}] falls outside "
                f"SRTM coverage [{_SRTM_LAT_MIN}, {_SRTM_LAT_MAX}]. "
                "Slope will be NaN for pixels above/below this band."
            )
            print(f"[SRTM] WARNING: {coverage_note}")
    except Exception as exc:
        # bounds() failure is non-fatal — proceed without the warning.
        print(f"[SRTM] Could not compute ROI bounds for coverage check: {exc}")

    srtm = ee.Image("USGS/SRTMGL1_003")

    roi_buffer = config.ROI.buffer(100)
    srtm_clipped = srtm.clip(roi_buffer)

    elevation = srtm_clipped.select("elevation").rename("Elevation")
    slope = ee.Terrain.slope(elevation).rename("Slope")

    # Combine Elevation + Slope (Elevation useful for context in map tooltips)
    topo = ee.Image.cat([elevation, slope])

    # Resample to master CRS at 10m
    topo_resampled = topo.reproject(crs=master_crs, scale=config.TARGET_SCALE)

    metadata = {
        "source": "SRTM",
        "collection": "USGS/SRTMGL1_003",
        "image_count": "Static",
        "bands": ["Elevation", "Slope"],
        "available": available,
    }
    if coverage_note:
        metadata["reason"] = coverage_note

    return topo_resampled, metadata
