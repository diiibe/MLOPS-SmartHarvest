import ee
import config


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
    }

    return topo_resampled, metadata
