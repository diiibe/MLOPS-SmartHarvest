import ee
import config


def get_sentinel2_data():
    """
    Process Sentinel-2 data to create per-image spectral indices.
    Returns a collection where each image has the computed indices,
    suitable for temporal sampling.

    Returns:
        collection (ee.ImageCollection): Per-image images with NDVI, NDWI, MNDWI, NDRE, IRECI, S2REP.
        master_crs (ee.Projection): Projection of the master layer (for aligning other data).
        metadata (dict): Metadata about the collection.
    """

    # 1. Query & Filter
    s2_raw = (
        ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
        .filterBounds(config.ROI)
        .filterDate(config.START_DATE, config.END_DATE)
    )

    total_count = s2_raw.size().getInfo()

    # Calculate cloud coverage statistics BEFORE filtering
    print("[S2] Calculating cloud coverage statistics...")
    cloud_stats = s2_raw.aggregate_stats('CLOUDY_PIXEL_PERCENTAGE').getInfo()

    # Calculate shadow coverage statistics from SCL band
    print("[S2] Calculating shadow coverage statistics...")
    def compute_shadow_coverage(image):
        scl = image.select('SCL')
        # Shadow classes: SCL 2=Dark areas, 3=Cloud shadows
        shadow_mask = scl.eq(2).Or(scl.eq(3))

        # Compute fraction of shadow pixels in ROI
        stats = shadow_mask.reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=config.ROI,
            scale=60,  # Coarser scale for speed
            maxPixels=1e9,
            bestEffort=True
        )

        shadow_val = stats.get('SCL')
        shadow_fraction = ee.Number(ee.Algorithms.If(shadow_val, ee.Number(shadow_val).multiply(100), 0))
        return image.set('shadow_coverage', shadow_fraction)

    s2_with_shadow = s2_raw.map(compute_shadow_coverage)
    shadow_stats = s2_with_shadow.aggregate_stats('shadow_coverage').getInfo()

    s2_full = s2_raw.filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', config.CLOUD_THRESHOLD_S2))

    count = s2_full.size().getInfo()
    discarded_count = total_count - count

    if count == 0:
        raise Exception(
            "Sentinel-2 Collection is empty after filtering. "
            "Check dates or cloud threshold."
        )

    # 2. Cloud Masking (SCL-based)
    def mask_s2_clouds(image):
        scl = image.select('SCL')
        # Keep: 4=Vegetation, 5=Not Vegetated, 6=Water, 7=Unclassified
        mask = scl.gte(4).And(scl.lte(7))
        return image.updateMask(mask)

    s2_masked = s2_full.map(mask_s2_clouds)

    # 3. Index Computation per image
    def add_indices(image):
        b4_proj = image.select('B4').projection()

        def get_band(b_name):
            return image.select(b_name).resample('bicubic').reproject(crs=b4_proj, scale=10)

        green = get_band('B3')
        red = get_band('B4')
        re1 = get_band('B5')
        re2 = get_band('B6').rename('RE2')
        re3 = get_band('B7').rename('RE3')
        nir = get_band('B8')
        swir1 = get_band('B11')

        # NDVI = (NIR - Red) / (NIR + Red)
        ndvi = nir.subtract(red).divide(nir.add(red)).rename('NDVI')

        # NDWI (McFeeters) = (Green - NIR) / (Green + NIR)
        ndwi = green.subtract(nir).divide(green.add(nir)).rename('NDWI')

        # MNDWI = (Green - SWIR1) / (Green + SWIR1)
        mndwi = green.subtract(swir1).divide(green.add(swir1)).rename('MNDWI')

        # NDRE = (NIR - RE1) / (NIR + RE1)
        ndre = nir.subtract(re1).divide(nir.add(re1)).rename('NDRE')

        # IRECI = (RE3 - Red) / (RE1 / RE2)
        ireci = re3.subtract(red).divide(re1.divide(re2)).rename('IRECI')

        # S2REP = 705 + 35 * ((Red + RE3)/2 - RE1) / (RE2 - RE1)
        s2rep = (
            red.add(re3).divide(2).subtract(re1)
            .divide(re2.subtract(re1))
            .multiply(35).add(705)
            .rename('S2REP')
        )

        return image.addBands([ndvi, ndwi, mndwi, ndre, ireci, s2rep])

    s2_with_indices = s2_masked.map(add_indices)

    # 4. Select only the index bands (drop raw spectral bands for export)
    index_bands = ['NDVI', 'NDWI', 'MNDWI', 'NDRE', 'IRECI', 'S2REP']
    collection = s2_with_indices.select(index_bands)

    # 5. Save master projection from first image
    first_img = s2_full.first()
    master_crs = first_img.select('B4').projection()

    metadata = {
        'source': 'Sentinel-2',
        'collection': 'COPERNICUS/S2_SR_HARMONIZED',
        'image_count': count,
        'total_images': total_count,
        'discarded_images': discarded_count,
        'discarded_pct': (discarded_count / total_count * 100) if total_count > 0 else 0,
        'discard_reason': f'Cloud threshold (>{config.CLOUD_THRESHOLD_S2}%)',
        'date_range': f"{config.START_DATE} to {config.END_DATE}",
        'bands': index_bands,
        'cloud_coverage': {
            'mean': cloud_stats.get('mean', 0),
            'min': cloud_stats.get('min', 0),
            'max': cloud_stats.get('max', 0),
            'stddev': cloud_stats.get('stdDev', 0)
        },
        'shadow_coverage': {
            'mean': shadow_stats.get('mean', 0),
            'min': shadow_stats.get('min', 0),
            'max': shadow_stats.get('max', 0),
            'stddev': shadow_stats.get('stdDev', 0)
        }
    }

    return collection, master_crs, metadata
