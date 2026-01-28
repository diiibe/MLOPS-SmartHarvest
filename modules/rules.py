def evaluate_observation_quality(valid_pixels: int, total_pixels: int, coverage_ratio: float, is_small_parcel: bool) -> str:
    """
    Evaluates the quality of a satellite observation based on business rules.
    Pure Python implementation: no Earth Engine dependencies.

    Rules:
    - Minimum Absolute Pixels: 25
    - Minimum Relative coverage: 30% of total possible pixels
    - Coverage Ratio Threshold: 
        - 60% for normal parcels
        - 50% for small parcels (< 60 pixels)
    - Small Parcel Relaxation:
        - If small, min absolute pixels drops to 15.

    Returns:
        str: 'SUCCESS', 'LOW_CONFIDENCE', or 'NO_DECISION' (reserved for missing data)
    """
    
    # 0. Sanity checks (No Decision)
    if total_pixels <= 0:
        return 'NO_DECISION'

    # 1. Define Thresholds
    MIN_ABSOLUTE_PIXELS = 25
    MIN_RELATIVE_PCT = 0.30
    
    if is_small_parcel:
        COVERAGE_THRESHOLD = 0.50
        # Relaxed minimum for small parcels
        # Matches logic: max(15, total * 0.30)
        min_pixel_threshold = max(15, total_pixels * MIN_RELATIVE_PCT)
    else:
        COVERAGE_THRESHOLD = 0.60
        # Standard minimum
        # Matches logic: max(25, total * 0.30)
        min_pixel_threshold = max(MIN_ABSOLUTE_PIXELS, total_pixels * MIN_RELATIVE_PCT)

    # 2. Evaluate
    has_enough_pixels = valid_pixels >= min_pixel_threshold
    has_enough_coverage = coverage_ratio >= COVERAGE_THRESHOLD

    if has_enough_pixels and has_enough_coverage:
        return 'SUCCESS'
    else:
        return 'LOW_CONFIDENCE'
