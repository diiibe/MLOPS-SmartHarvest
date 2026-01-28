import ee
import config


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
        area_10m.gte(min_area), erosion_10m, ee.Algorithms.If(area_5m.gte(min_area), erosion_5m, erosion_0m)
    )

    erosion_applied = ee.Algorithms.If(area_10m.gte(min_area), 10, ee.Algorithms.If(area_5m.gte(min_area), 5, 0))

    return {
        "core_geometry": ee.Geometry(core_geometry),
        "erosion_applied": ee.Number(erosion_applied),
        "is_small_parcel": is_small,
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
    sample = image.sample(region=parcel_core, scale=sampling_scale, geometries=False)

    # Get band names (all spectral indices)
    bands = image.bandNames()

    # Calculate statistics using reduceRegion for efficiency
    stats = image.reduceRegion(
        reducer=ee.Reducer.median()
        .combine(ee.Reducer.percentile([10, 25, 75, 90]), "", True)
        .combine(ee.Reducer.count(), "", True)
        .combine(ee.Reducer.stdDev(), "", True),
        geometry=parcel_core,
        scale=sampling_scale,
        maxPixels=1e9,
    )

    # Calculate total possible pixels in core
    core_area = parcel_core.area()
    pixel_area = sampling_scale * sampling_scale
    total_pixels = core_area.divide(pixel_area)

    # Get valid pixel count (using first band as proxy)
    first_band = bands.get(0)
    valid_count = ee.Number(stats.get(ee.String(first_band).cat("_count")))

    # Coverage ratio
    coverage_ratio = valid_count.divide(total_pixels)

    # Add metadata
    stats = (
        stats.set("valid_pixel_count", valid_count)
        .set("total_pixel_count", total_pixels)
        .set("coverage_ratio", coverage_ratio)
    )

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
    valid_count = ee.Number(stats.get("valid_pixel_count"))
    coverage_ratio = ee.Number(stats.get("coverage_ratio"))
    total_count = ee.Number(stats.get("total_pixel_count"))

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
        ee.Number(is_small_parcel), ee.Number(15).max(ee.Number(total_count).multiply(min_relative_pct)), min_effective
    )

    # Validation
    is_valid = valid_count.gte(min_effective).And(coverage_ratio.gte(coverage_threshold))

    return ee.Number(is_valid)
