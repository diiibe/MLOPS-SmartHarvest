"""
STEP 1-3: Data Loading and Weekly Frame Construction
"""

import pandas as pd
import numpy as np


def load_and_filter_s2(csv_path):
    """
    STEP 1: Load CSV and filter for Sentinel-2 data.

    Returns:
        df: Filtered dataframe with S2 observations
        columns: dict with identified column types
    """
    df = pd.read_csv(csv_path)

    # Identify columns
    date_col = "date"
    sat_col = "satellite" if "satellite" in df.columns else None

    # Coordinate columns
    coord_cols = []
    if "spatial_id" in df.columns:
        coord_cols.append("spatial_id")
    if "lat" in df.columns and "lon" in df.columns:
        coord_cols.extend(["lat", "lon"])

    # Feature columns: explicit whitelist from config (avoids accidentally
    # feeding the clustering with structurally-NaN columns like S1/L8 bands
    # that only have values on rare concurrent-acquisition dates).
    try:
        import config as _app_config

        whitelist = list(getattr(_app_config, "ML_FEATURES", []))
    except Exception:
        whitelist = []

    numeric_cols = [
        c
        for c in df.select_dtypes(include=[np.number]).columns
        if c not in ("lat", "lon") and not c.startswith(".")
    ]
    if whitelist:
        feature_cols = [c for c in whitelist if c in numeric_cols]
        # If nothing from the whitelist is present (e.g. external CSV), fall
        # back to the auto-detected numeric columns so tests on minimal CSVs
        # still work.
        if not feature_cols:
            feature_cols = numeric_cols
    else:
        feature_cols = numeric_cols

    # Filter for S2 (main timeline)
    if sat_col:
        # Keep rows that have S2 acquisition
        s2_df = df[df[sat_col].str.contains("S2", na=False)].copy()
    else:
        # No satellite column - use all data
        s2_df = df.copy()

    # Convert date to datetime
    s2_df[date_col] = pd.to_datetime(s2_df[date_col])

    # Filter out rows with all NaN features (cloud-masked)
    s2_df = s2_df[s2_df[feature_cols].notna().any(axis=1)]

    columns = {
        "date": date_col,
        "satellite": sat_col,
        "coords": coord_cols,
        "features": feature_cols,
    }

    print(f"[Data Loader] Loaded {len(s2_df):,} S2 observations")
    print(
        f"[Data Loader] Date range: {s2_df[date_col].min()} to {s2_df[date_col].max()}"
    )
    print(f"[Data Loader] Features: {', '.join(feature_cols[:5])}...")

    return s2_df, columns


def define_weeks(df, date_col="date"):
    """
    STEP 2: Define weekly timeline from S2 observations.

    Returns:
        weeks: list of (week_id, start_date, end_date) tuples
    """
    df = df.copy()

    # True ISO 8601 week (Mon–Sun, week 1 contains the first Thursday of the year).
    # %G is the ISO year (differs from %Y around Jan 1), %V is the ISO week
    # zero-padded. Previously %U was used (US convention, Sun-start) which
    # both misaligned with the README's claim of "ISO week" and produced W00
    # at year boundaries that broke alphabetical sorting.
    df["week_id"] = df[date_col].dt.strftime("%G-W%V")
    # Pandas default "W" alias = "W-SUN" = weeks ending Sunday → start_time is
    # Monday, which matches ISO. (Using W-MON would start weeks on Tuesday.)
    df["week_start"] = df[date_col].dt.to_period("W").dt.start_time

    # Get unique weeks sorted
    week_info = (
        df.groupby("week_id")
        .agg({"week_start": "first", date_col: ["min", "max", "count"]})
        .reset_index()
    )

    week_info.columns = ["week_id", "week_start", "date_min", "date_max", "obs_count"]
    week_info = week_info.sort_values("week_start")

    weeks = [
        (row["week_id"], row["week_start"], row["date_max"], row["obs_count"])
        for _, row in week_info.iterrows()
    ]

    print(f"[Weekly Timeline] Found {len(weeks)} weeks")
    print(f"[Weekly Timeline] Latest week: {weeks[-1][0]} ({weeks[-1][3]} obs)")

    return weeks, df


def build_weekly_frame(df, week_id, coord_cols, feature_cols, date_col="date"):
    """
    STEP 3: Build single weekly frame (one row per pixel).

    Strategy: Take most recent observation per pixel in the week.

    Returns:
        frame: DataFrame with pixel + features for this week
    """
    # Filter to this week
    week_df = df[df["week_id"] == week_id].copy()

    if len(week_df) == 0:
        return None

    # Group by pixel (spatial_id or lat/lon)
    if "spatial_id" in coord_cols:
        group_col = "spatial_id"
    else:
        # Create temp pixel id from lat/lon
        week_df["pixel_id"] = (
            week_df["lat"].round(6).astype(str)
            + "_"
            + week_df["lon"].round(6).astype(str)
        )
        group_col = "pixel_id"

    # Aggregate features with the nanmedian across all acquisitions in the
    # week, not just the most recent one. Median is robust to cloud/haze
    # outliers and to the occasional SCL misclassification that slips past
    # the upstream masking. Coords and spatial_id are taken from the first
    # row in the group (they are pixel-constant within a week).
    present_features = [c for c in feature_cols if c in week_df.columns]
    # Do not re-include group_col in coord_present — otherwise the merge below
    # creates duplicate "spatial_id" columns and later `.notna()` lookups fail.
    coord_present = [
        c for c in coord_cols if c in week_df.columns and c != group_col
    ]

    grouped = week_df.groupby(group_col, as_index=False, sort=False)
    first_view = grouped.first()
    keep_for_coords = [group_col] + [c for c in coord_present if c in first_view.columns]
    coords_frame = first_view[keep_for_coords]
    if present_features:
        feat_frame = grouped[present_features].median(numeric_only=True)
        frame = coords_frame.merge(feat_frame, on=group_col, how="left")
    else:
        frame = coords_frame

    # Drop pixels with all NaN features
    if present_features:
        frame = frame[frame[present_features].notna().any(axis=1)]

    print(f"[Weekly Frame] {week_id}: {len(frame):,} pixels")

    return frame
