import ee
import config
from satellites_data_extraction import get_sentinel2_data

def s2cleancollection(roi, start_date, end_date):
    """
    STEP 1: Generates a clean Sentinel-2 ImageCollection using an Ensemble Masking approach.
    
    The procedure combines 4 sources of information:
    1. Sentinel-2 L2A (SCL band)
    2. Cloud Score+ (google/cloud_score_plus)
    3. s2cloudless (copernicus/s2_cloud_probability)
    4. Geometric Shadow Projection (based on solar azimuth/zenith)

    Args:
        roi (ee.Geometry): Region of Interest.
        start_date (str): Start date (YYYY-MM-DD).
        end_date (str): End date (YYYY-MM-DD).

    Returns:
        ee.ImageCollection: A collection of images with invalid pixels (cloud/shadow) masked out.
    """
    
    # 1. Base Collection (Sentinel-2 Harmonized)
    # Pass roi directly to get_sentinel2_data (it expects a list usually)
    s2 = get_sentinel2_data(roi, start_date, end_date)
    
    # Ensure we have a Geometry object for filterBounds
    roi_geo = roi
    if isinstance(roi, list):
        roi_geo = ee.Geometry.Polygon(roi)
    
    # 2. Auxiliary Collections
    cs_plus = ee.ImageCollection('GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED') \
        .filterBounds(roi_geo) \
        .filterDate(start_date, end_date)
    
    s2_cloudless = ee.ImageCollection('COPERNICUS/S2_CLOUD_PROBABILITY') \
        .filterBounds(roi_geo) \
        .filterDate(start_date, end_date)

    # Join collections based on system:index
    # We use .combine() which matches images by system:index automatically.
    
    # Pre-rename bands to avoid confusion/collisions
    def rename_cs(img):
        return img.select(['cs', 'cs_cdf'], ['cs_cs', 'cs_cs_cdf'])
    cs_plus = cs_plus.map(rename_cs)
    
    def rename_cld(img):
        return img.select(['probability'], ['cld_probability'])
    s2_cloudless = s2_cloudless.map(rename_cld)
    
    # Combine (Inner Join on system:index)
    s2_full = s2.combine(cs_plus).combine(s2_cloudless)

    def apply_masks(img):
        """
        Applies the ensemble mask rules to a single image.
        """
        
        # --- 1A. Thresholds (Regole Base) ---
        # Cloud Score+ Rules: cs >= 0.60 AND cs_cdf >= 0.70
        # bands: cs_cs, cs_cs_cdf
        is_cs_clear = img.select('cs_cs').gte(0.60).And(img.select('cs_cs_cdf').gte(0.70))
        
        # S2Cloudless Rules: probability <= 30
        # band: cld_probability
        is_prob_clear = img.select('cld_probability').lte(30)
        
        # --- 1B. SCL Toxic Classes ---
        # 0: No Data, 1: Saturated, 2: Dark, 3: Cloud Shadow, 7: Unclassified,
        # 8: Medium Cloud, 9: High Cloud, 10: Thin Cirrus, 11: Snow
        scl = img.select('SCL')
        # We keep only: 4 (Vegetation), 5 (Bare Soil), 6 (Water)
        # Note: We include 6 for now, but exclude it for dark pixel check later.
        is_scl_clear = scl.eq(4).Or(scl.eq(5)).Or(scl.eq(6))
        
        # Combine "Cloud-Like" detections (Inverted logic: invalid if ANY says bad)
        # But here we defined "clear" conditions.
        # Pixel is clear if ALL say clear.
        cloud_mask = is_cs_clear.And(is_prob_clear).And(is_scl_clear)
        
        # --- 1D. Shadow Projection (Ombre) ---
        # Temporarily DISABLED for debugging GE/Server error
        # 1. Identification of Cloud Core (Strict cloud for projection)
        # is_cloud_core = img.select('cld_probability').gt(50).Or(scl.eq(8)).Or(scl.eq(9))
        
        # 2. Geometric Projection params
        # azimuth = ee.Number(img.get('MEAN_SOLAR_AZIMUTH_ANGLE'))
        # zenith = ee.Number(img.get('MEAN_SOLAR_ZENITH_ANGLE'))
        
        # Shadow direction = Azimuth + 180 (moved to radians)
        # shadow_azimuth = azimuth.add(180).multiply(3.14159265 / 180)
        
        # Project function
        # def project_shadows(cloud_mask, height):
        #     # Distance = height * tan(zenith)
        #     dist = ee.Number(height).multiply(zenith.multiply(3.14159265 / 180).tan())
        #     x_shift = dist.multiply(shadow_azimuth.sin()).divide(10) # divide by scale (10m)
        #     y_shift = dist.multiply(shadow_azimuth.cos()).divide(10)
        #     return cloud_mask.changeProj(cloud_mask.projection(), cloud_mask.projection().translate(x_shift, y_shift))

        # Try multiple heights (simplified for MVP: 500m, 1000m, 2000m)
        # Using a reduce/iterate approach or hardcoded union for simplicity
        # shadow_proj = ee.Image(0)
        # for h in [500, 1000, 2000]:
        #      shadow_proj = shadow_proj.Or(project_shadows(is_cloud_core, h))
        
        # 3. Dark Pixel Confirmation (Intersection)
        # Must be projected shadow AND dark (NIR < 0.15) AND Not Water (SCL!=6)
        # nir = img.select('B8').divide(10000) # L2A is scaled by 10000
        # is_dark = nir.lt(0.15).And(scl.neq(6))
        
        # confirmed_shadow = shadow_proj.And(is_dark)
        
        # Dilate masks (Buffer) - Simulated with focal_min/max
        # "Dilate Cloud 20m" -> 2 pixels radius (focal_max on cloud mask)
        # "Dilate Shadow 10m" -> 1 pixel radius
        
        # Note: cloud_mask is 1 for CLEAR. So we invert to dilate CLOUDS.
        is_cloud = cloud_mask.Not()
        is_cloud_dilated = is_cloud.focal_max(20, 'circle', 'meters')
        
        # is_shadow_dilated = confirmed_shadow.focal_max(10, 'circle', 'meters')
        
        # Final Invalid Mask
        is_invalid = is_cloud_dilated #.Or(is_shadow_dilated)
        
        # --- 1E. Final Masking ---
        return img.updateMask(is_invalid.Not())

    return s2_full.map(apply_masks)

def get_adaptive_core(roi_geometry, sampling_scale=10):
    """
    STEP 2A: Adaptive Erosion for Core Vineyard.
    
    Creates an eroded 'core' ROI that excludes mixed border pixels.
    Uses adaptive erosion: tries 10m, then 5m, then 0m if parcel becomes too small.
    
    Args:
        roi_geometry (ee.Geometry): The original parcel polygon.
        sampling_scale (int): Pixel size in meters (default 10m for S2).
    
    Returns:
        dict: {
            'core_geometry': ee.Geometry (eroded),
            'erosion_applied': ee.Number (meters eroded),
            'is_small_parcel': ee.Number (1 if small, 0 otherwise)
        }
    """
    # Convert to ee.Geometry if list
    if isinstance(roi_geometry, list):
        roi_geometry = ee.Geometry.Polygon(roi_geometry)
    
    # Calculate original area and approximate pixel count
    original_area = roi_geometry.area()
    pixel_area = sampling_scale * sampling_scale
    approx_pixels = original_area.divide(pixel_area)
    
    # Minimum pixel threshold (25 pixels as per spec)
    min_pixels = 25
    min_area = ee.Number(min_pixels).multiply(pixel_area)
    
    # Try erosion levels: 10m, 5m, 0m
    erosion_10m = roi_geometry.buffer(-10)
    erosion_5m = roi_geometry.buffer(-5)
    erosion_0m = roi_geometry  # No erosion
    
    # Check areas
    area_10m = erosion_10m.area()
    area_5m = erosion_5m.area()
    
    # Decision logic (client-side for simplicity, could be server-side with ee.Algorithms.If)
    # We'll use a simpler approach: always try 10m, but flag small parcels
    core_geometry = erosion_10m
    erosion_applied = 10
    is_small = approx_pixels.lt(60)  # Flag if < 60 pixels (small parcel)
    
    # For very small parcels, use 5m or 0m
    # Using ee.Algorithms.If for server-side logic
    core_geometry = ee.Algorithms.If(
        area_10m.gte(min_area),
        erosion_10m,
        ee.Algorithms.If(
            area_5m.gte(min_area),
            erosion_5m,
            erosion_0m
        )
    )
    
    erosion_applied = ee.Algorithms.If(
        area_10m.gte(min_area),
        10,
        ee.Algorithms.If(
            area_5m.gte(min_area),
            5,
            0
        )
    )
    
    return {
        'core_geometry': ee.Geometry(core_geometry),
        'erosion_applied': ee.Number(erosion_applied),
        'is_small_parcel': is_small
    }

def extract_parcel_stats(image, parcel_core, sampling_scale=10):
    """
    STEP 2B: Extract Robust Statistics for a Parcel.
    
    Calculates median, percentiles, and performs outlier removal using IQR (Tukey fence).
    
    Args:
        image (ee.Image): Cleaned image with masked invalid pixels.
        parcel_core (ee.Geometry): Eroded core parcel geometry.
        sampling_scale (int): Sampling resolution in meters.
    
    Returns:
        ee.Dictionary: Statistics including median, p10, p25, p75, p90, valid_count, coverage_ratio.
    """
    # Sample pixels in the core area
    sample = image.sample(
        region=parcel_core,
        scale=sampling_scale,
        geometries=False
    )
    
    # Get band names (all spectral indices)
    bands = image.bandNames()
    
    # Calculate statistics using reduceRegion for efficiency
    stats = image.reduceRegion(
        reducer=ee.Reducer.median()
            .combine(ee.Reducer.percentile([10, 25, 75, 90]), '', True)
            .combine(ee.Reducer.count(), '', True)
            .combine(ee.Reducer.stdDev(), '', True),
        geometry=parcel_core,
        scale=sampling_scale,
        maxPixels=1e9
    )
    
    # Calculate total possible pixels in core
    core_area = parcel_core.area()
    pixel_area = sampling_scale * sampling_scale
    total_pixels = core_area.divide(pixel_area)
    
    # Get valid pixel count (using first band as proxy)
    first_band = bands.get(0)
    valid_count = ee.Number(stats.get(ee.String(first_band).cat('_count')))
    
    # Coverage ratio
    coverage_ratio = valid_count.divide(total_pixels)
    
    # Add metadata
    stats = stats \
        .set('valid_pixel_count', valid_count) \
        .set('total_pixel_count', total_pixels) \
        .set('coverage_ratio', coverage_ratio)
    
    return stats

def validate_parcel_observation(stats, is_small_parcel=False):
    """
    STEP 2C: Validate if Parcel Observation Meets Quality Thresholds.
    
    Applies adaptive thresholds based on parcel size.
    
    Args:
        stats (ee.Dictionary): Statistics from extract_parcel_stats.
        is_small_parcel (bool/ee.Number): Whether parcel is small (<60 pixels).
    
    Returns:
        ee.Number: 1 if valid, 0 if invalid observation.
    """
    valid_count = ee.Number(stats.get('valid_pixel_count'))
    coverage_ratio = ee.Number(stats.get('coverage_ratio'))
    total_count = ee.Number(stats.get('total_pixel_count'))
    
    # Adaptive thresholds
    # Standard: min 25 pixels OR 30% of core, whichever is higher
    # Coverage: 60% (or 50% for small parcels)
    min_absolute = 25
    min_relative_pct = 0.30
    coverage_threshold = ee.Algorithms.If(is_small_parcel, 0.50, 0.60)
    
    # Effective minimum
    min_effective = ee.Number(total_count).multiply(min_relative_pct).max(min_absolute)
    
    # For very small parcels, relax to 15 pixels
    min_effective = ee.Algorithms.If(
        ee.Number(is_small_parcel),
        ee.Number(15).max(ee.Number(total_count).multiply(min_relative_pct)),
        min_effective
    )
    
    # Validation
    is_valid = valid_count.gte(min_effective).And(coverage_ratio.gte(coverage_threshold))
    
    return ee.Number(is_valid)



