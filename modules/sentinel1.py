import ee
import config


def get_sentinel1_data(master_crs):
    """
    Process Sentinel-1 data to create per-image backscatter features.
    Returns a collection where each image has VH, VV, Ratio bands.

    Args:
        master_crs (ee.Projection): The projection to align to.
    Returns:
        collection (ee.ImageCollection): Per-image images with VH, VV, Ratio.
        metadata (dict): Metadata about the collection.
    """

    # 1. Query & Filter
    s1_raw = ee.ImageCollection("COPERNICUS/S1_GRD").filterBounds(config.ROI).filterDate(config.START_DATE, config.END_DATE)

    total_count = s1_raw.size().getInfo()

    s1_full = (
        s1_raw.filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VH"))
        .filter(ee.Filter.eq("instrumentMode", "IW"))
        .filter(ee.Filter.eq("orbitProperties_pass", "ASCENDING"))
    )

    count = s1_full.size().getInfo()
    discarded_count = total_count - count
    if count == 0:
        print("Warning: No Sentinel-1 data found. Returning empty collection.")
        empty = ee.ImageCollection(
            [
                ee.Image.constant([-9999, -9999, -9999])
                .rename(["VH", "VV", "Ratio"])
                .reproject(crs=master_crs, scale=config.TARGET_SCALE)
                .set("system:time_start", ee.Date(config.START_DATE).millis())
            ]
        )
        return empty, {
            "source": "Sentinel-1",
            "image_count": 0,
            "date_range": f"{config.START_DATE} to {config.END_DATE}",
            "bands": ["VH", "VV", "Ratio"],
        }

    # 2. Preprocessing: despeckle + add Ratio + reproject to master grid
    def process_image(image):
        # BoxCar despeckling 5x5
        # Note: focal_mean().copyProperties() returns ee.Element, so cast back to ee.Image
        despeckled = ee.Image(image.focal_mean(radius=2.5, units="pixels", iterations=1)).set(
            "system:time_start", image.date().millis()
        )
        vh = despeckled.select("VH")
        vv = despeckled.select("VV")
        ratio = vh.subtract(vv).rename("Ratio")
        return despeckled.select(["VH", "VV"]).addBands(ratio).reproject(crs=master_crs, scale=config.TARGET_SCALE)

    collection = s1_full.map(process_image)

    metadata = {
        "source": "Sentinel-1",
        "collection": "COPERNICUS/S1_GRD",
        "image_count": count,
        "total_images": total_count,
        "discarded_images": discarded_count,
        "discarded_pct": ((discarded_count / total_count * 100) if total_count > 0 else 0),
        "discard_reason": "Polarization/Mode/Orbit filters (VV+VH, IW, ASCENDING)",
        "date_range": f"{config.START_DATE} to {config.END_DATE}",
        "bands": ["VH", "VV", "Ratio"],
    }

    return collection, metadata
