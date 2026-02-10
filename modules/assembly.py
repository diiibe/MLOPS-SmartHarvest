"""
Temporal Assembly Module

Samples each satellite image collection per-image over the ROI,
downloads data separately per satellite, then merges client-side
into a single temporal CSV with one row per (date, point).
"""

import os
import json
import io

import ee
import requests
import numpy as np
import pandas as pd

import config

# ---------------------------------------------------------------------------
# GEE-side: Create temporal FeatureCollections
# ---------------------------------------------------------------------------


def create_temporal_samples(s2_col, s1_col, l8_col, srtm_img):
    """
    Sample each satellite collection per-image over FIXED reference grid.

    Key optimizations vs old code:
    - tileScale=1 instead of 8 (8x faster)
    - NO server-side spatial_id calculation (compute client-side)
    - Still uses reduceRegions for fixed grid alignment

    Returns:
        s2_fc, s1_fc, l8_fc (ee.FeatureCollection): Temporal samples per satellite.
        srtm_fc (ee.FeatureCollection): Static topo samples.
    """
    print("Creating fixed reference grid (optimized)...")

    # Create reference grid from ROI at TARGET_SCALE
    roi_fc = ee.FeatureCollection([ee.Feature(config.ROI)])

    # Use first S2 image to establish reference pixel grid
    first_s2 = s2_col.first()
    ref_projection = first_s2.select("NDVI").projection()

    # Create pixel coordinate image
    coords = ee.Image.pixelLonLat().reproject(ref_projection, scale=config.TARGET_SCALE)

    # Sample ROI to get FIXED grid points (same for all satellites)
    reference_points = coords.sampleRegions(
        collection=roi_fc,
        scale=config.TARGET_SCALE,
        geometries=True,
        tileScale=1,  # ← REDUCED from 8 (major speedup)
    )

    print(f"Reference grid created at {config.TARGET_SCALE}m resolution")
    print("Note: spatial_id will be calculated client-side for speed")

    def sample_collection_at_fixed_grid(collection, bands, sat_code):
        """
        Sample collection at FIXED reference points.
        Uses reduceRegions to ensure all satellites align to same grid.
        """

        def sample_image(img):
            # Use reduceRegions to sample at exact reference points
            # This ensures perfect alignment across all satellites
            if isinstance(bands, list) and len(bands) > 1:
                # Multi-band: reducer preserves band names automatically
                reducer = ee.Reducer.first()
            else:
                # Single-band: explicitly name output
                band_name = bands[0] if isinstance(bands, list) else bands
                reducer = ee.Reducer.first().setOutputs([band_name])

            sampled = img.select(bands).reduceRegions(
                collection=reference_points,  # ← SAME fixed points for all!
                reducer=reducer,
                scale=config.TARGET_SCALE,
                tileScale=1,  # ← REDUCED from 8 (major speedup)
            )

            # Add temporal metadata
            return sampled.map(
                lambda f: f.set(
                    "date", img.date().format("YYYY-MM-dd"), "satellite", sat_code
                )
            )

        return collection.map(sample_image).flatten()

    # Sample all satellites at SAME reference points
    print("Sampling S2 at fixed grid...")
    s2_fc = sample_collection_at_fixed_grid(
        s2_col, ["NDVI", "NDWI", "MNDWI", "NDRE", "IRECI", "S2REP"], "S2"
    )

    print("Sampling S1 at fixed grid...")
    s1_fc = sample_collection_at_fixed_grid(s1_col, ["VH", "VV", "Ratio"], "S1")

    print("Sampling Landsat at fixed grid...")
    l8_fc = sample_collection_at_fixed_grid(l8_col, ["LST"], "L8")

    # SRTM: sample at reference points
    print("Sampling SRTM at fixed grid...")
    srtm_fc = srtm_img.select("Slope").reduceRegions(
        collection=reference_points,
        reducer=ee.Reducer.first().setOutputs(["Slope"]),
        scale=config.TARGET_SCALE,
        tileScale=1,  # ← REDUCED from 8
    )

    return s2_fc, s1_fc, l8_fc, srtm_fc


# ---------------------------------------------------------------------------
# Download helpers
# ---------------------------------------------------------------------------


def _download_fc_as_df(fc, label, timeout=300, max_retries=3):
    """
    Try getDownloadURL for a FeatureCollection; return DataFrame or None.

    Args:
        fc: FeatureCollection to download
        label: Label for logging
        timeout: Timeout in seconds
        max_retries: Number of attempts (1 = no retry, 3 = 2 retries)
    """
    import time

    # S2 has more bands, needs more time
    if "S2" in label:
        timeout = 600  # 10 minutes for S2

    for attempt in range(1, max_retries + 1):
        try:
            url = fc.getDownloadURL(filetype="csv")

            # Show different message for single attempt vs retries
            if max_retries == 1:
                print(f"[{label}] Downloading (timeout: {timeout}s)...")
            else:
                print(
                    f"[{label}] Attempt {attempt}/{max_retries} (timeout: {timeout}s)..."
                )

            response = requests.get(url, timeout=timeout)

            if response.status_code != 200:
                print(f"[{label}] Download failed (HTTP {response.status_code}).")
                if attempt < max_retries:
                    wait_time = 2**attempt  # Exponential backoff: 2, 4, 8 seconds
                    print(f"[{label}] Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                return None

            df = pd.read_csv(io.StringIO(response.text))
            print(f"[{label}] ✓ Downloaded {len(df)} rows.")
            return df

        except requests.exceptions.Timeout:
            print(f"[{label}] Timeout after {timeout}s.")
            if attempt < max_retries:
                wait_time = 2**attempt
                print(f"[{label}] Retrying in {wait_time}s...")
                time.sleep(wait_time)
                continue
            if max_retries > 1:
                print(f"[{label}] All {max_retries} attempts failed.")
            return None

        except Exception as e:
            print(f"[{label}] Download failed: {e}")
            if attempt < max_retries:
                wait_time = 2**attempt
                print(f"[{label}] Retrying in {wait_time}s...")
                time.sleep(wait_time)
                continue
            return None

    return None


def _download_fc_chunked(fc, label, chunk_days=None):
    """
    Download a FeatureCollection in date-based chunks.
    Automatically splits the date range if direct download fails.

    Args:
        fc: FeatureCollection to download
        label: Label for logging
        chunk_days: Number of days per chunk (None = auto-select based on satellite)
    Returns:
        DataFrame or None
    """
    from datetime import datetime, timedelta

    # Auto-select chunk size based on satellite
    if chunk_days is None:
        if "S2" in label:
            chunk_days = 7  # S2 has 6 bands + high frequency, smaller chunks
        else:
            chunk_days = 15  # S1/L8 can handle larger chunks

    print(
        f"[{label}] Attempting chunked download (splitting by {chunk_days}-day intervals)..."
    )

    try:
        # Get unique dates from the collection
        dates_array = fc.aggregate_array("date").distinct().sort().getInfo()

        if not dates_array or len(dates_array) == 0:
            print(f"[{label}] No dates found in collection.")
            return None

        print(
            f"[{label}] Found {len(dates_array)} unique dates: {dates_array[0]} to {dates_array[-1]}"
        )

        # Create date chunks
        start_date = datetime.strptime(dates_array[0], "%Y-%m-%d")
        end_date = datetime.strptime(dates_array[-1], "%Y-%m-%d")

        chunks = []
        current = start_date
        while current <= end_date:
            chunk_end = min(current + timedelta(days=chunk_days - 1), end_date)
            chunks.append(
                (current.strftime("%Y-%m-%d"), chunk_end.strftime("%Y-%m-%d"))
            )
            current = chunk_end + timedelta(days=1)

        print(f"[{label}] Splitting into {len(chunks)} chunks...")

        # Download each chunk (with retry logic)
        dfs = []
        for i, (chunk_start, chunk_end) in enumerate(chunks):
            # Filter to date range
            chunk_fc = fc.filter(
                ee.Filter.And(
                    ee.Filter.greaterThanOrEquals("date", chunk_start),
                    ee.Filter.lessThanOrEquals("date", chunk_end),
                )
            )

            print(
                f"[{label}] Chunk {i+1}/{len(chunks)}: {chunk_start} to {chunk_end}..."
            )
            # Chunks get 3 retry attempts (network/GEE glitches)
            df = _download_fc_as_df(chunk_fc, f"{label}-chunk{i+1}", max_retries=3)

            if df is not None and len(df) > 0:
                dfs.append(df)
            else:
                print(f"[{label}] Chunk {i+1} failed after all retries or empty.")
                # Continue with other chunks instead of failing entirely

        if dfs:
            merged = pd.concat(dfs, ignore_index=True)
            print(
                f"[{label}] Chunked download complete: {len(merged)} total rows from {len(dfs)} chunks."
            )
            return merged
        else:
            print(f"[{label}] All chunks failed.")
            return None

    except Exception as e:
        print(f"[{label}] Chunked download failed: {e}")
        return None


def _start_drive_export(fc, description):
    """Start a Google Drive export task and return the task object."""
    task = ee.batch.Export.table.toDrive(
        collection=fc, description=description, fileFormat="CSV"
    )
    task.start()
    return task


def _estimate_fc_size(fc, label):
    """Estimate FeatureCollection size to warn about potential download issues."""
    try:
        size = fc.size().getInfo()
        if size > 100000:
            print(
                f"⚠️  [{label}] Large dataset: ~{size:,} rows. Download may be slow or require chunking."
            )
        elif size > 50000:
            print(f"[{label}] Dataset size: ~{size:,} rows. May require chunking.")
        else:
            print(f"[{label}] Dataset size: ~{size:,} rows.")
        return size
    except Exception as e:
        print(f"[{label}] Could not estimate size: {e}")
        return None


def download_satellite_data(
    s2_fc, s1_fc, l8_fc, srtm_fc, output_dir, project_name_safe
):
    """
    Download all satellite FCs with automatic retry strategies:
    1. Try direct download via getDownloadURL
    2. If that fails, try chunked download (split by date)
    3. If that fails, fall back to Drive export

    Returns paths to the 4 CSV files.
    """
    print("\n" + "=" * 70)
    print("DOWNLOADING SATELLITE DATA")
    print("=" * 70)

    results = {}
    drive_tasks = {}

    for label, fc in [("S2", s2_fc), ("S1", s1_fc), ("L8", l8_fc), ("SRTM", srtm_fc)]:
        df = None

        # Estimate size first
        _estimate_fc_size(fc, label)

        # Strategy 1: Direct download (single attempt, no retry)
        print(f"[{label}] Attempting direct download...")
        df = _download_fc_as_df(fc, label, max_retries=1)

        # Strategy 2: Chunked download (for temporal data only, not SRTM)
        if df is None and label != "SRTM":
            print(f"[{label}] Direct download failed. Trying chunked download...")
            df = _download_fc_chunked(fc, label, chunk_days=None)

        # Strategy 3: Drive export fallback
        if df is not None and len(df) > 0:
            path = os.path.join(output_dir, f"_tmp_{label}_{project_name_safe}.csv")
            df.to_csv(path, index=False)
            results[label] = path
            print(f"[{label}] ✓ Download successful: {len(df)} rows saved to {path}")
        else:
            # Start Drive export as final fallback
            print(f"[{label}] All download strategies failed. Starting Drive export...")
            desc = f"SmartHarvest_{label}_{project_name_safe}"
            task = _start_drive_export(fc, desc)
            drive_tasks[label] = task.id
            results[label] = None

    if drive_tasks:
        print("\n" + "=" * 70)
        print("⚠️  MANUAL INTERVENTION REQUIRED")
        print("=" * 70)
        print("Some datasets exceeded GEE download limits.")
        print("Drive export tasks have been started in your GEE account:")
        print()
        for label, task_id in drive_tasks.items():
            print(f"  • {label}: Task ID '{task_id}'")
        print()
        print("Steps to complete:")
        print(f"  1. Go to: https://code.earthengine.google.com/tasks")
        print(f"  2. Wait for tasks to complete (status: COMPLETED)")
        print(f"  3. Download CSVs from your Google Drive")
        print(f"  4. Rename and place them in: {output_dir}")
        print(
            f"     File names: _tmp_S2_{project_name_safe}.csv, _tmp_S1_{project_name_safe}.csv, etc."
        )
        print(f"  5. Re-run the analysis to merge the data")
        print("=" * 70 + "\n")

    return results


# ---------------------------------------------------------------------------
# Client-side merge
# ---------------------------------------------------------------------------


def _parse_geo_to_latlon(geo_str):
    """Parse .geo JSON string to (lat, lon) tuple."""
    try:
        data = json.loads(geo_str) if isinstance(geo_str, str) else geo_str
        coords = data.get("coordinates", [0, 0])
        return coords[1], coords[0]  # lat, lon
    except Exception:
        return None, None


def build_temporal_csv(csv_paths, output_path):
    """
    Merge per-satellite temporal CSVs into a single temporal dataset.

    Each row in the output = one geographic point × one date.
    Columns from satellites not present on that date are NaN.

    Args:
        csv_paths (dict): {'S2': path_or_None, 'S1': ..., 'L8': ..., 'SRTM': ...}
        output_path (str): Path for the merged output CSV.
    Returns:
        str: Path to the output CSV, or None if insufficient data.
    """

    def add_spatial_id_clientside(df):
        """
        Calculate spatial_id client-side from .geo or longitude/latitude.
        Rounds to 6 decimals (~10cm) for stable alignment across satellites.
        """
        if "spatial_id" in df.columns:
            # Already has spatial_id from server-side (old code path)
            return df

        # Parse coordinates from .geo or direct columns
        if ".geo" in df.columns:

            def parse_coords(geo_str):
                try:
                    data = json.loads(geo_str) if isinstance(geo_str, str) else geo_str
                    coords = data.get("coordinates", [0, 0])
                    return coords[0], coords[1]  # lon, lat
                except Exception:
                    return None, None

            df[["lon", "lat"]] = df[".geo"].apply(lambda x: pd.Series(parse_coords(x)))

        # Round to 6 decimals and create spatial_id
        if "lat" in df.columns and "lon" in df.columns:
            df["lat_rounded"] = df["lat"].round(6)
            df["lon_rounded"] = df["lon"].round(6)
            df["spatial_id"] = (
                df["lat_rounded"].astype(str) + "_" + df["lon_rounded"].astype(str)
            )
            # Keep rounded as main lat/lon
            df["lat"] = df["lat_rounded"]
            df["lon"] = df["lon_rounded"]
            df.drop(columns=["lat_rounded", "lon_rounded"], inplace=True)

        return df

    # Load available dataframes
    dfs = {}
    for label, path in csv_paths.items():
        if path and os.path.exists(path):
            df = pd.read_csv(path)
            df.replace(-9999, np.nan, inplace=True)
            # Add spatial_id client-side for alignment
            df = add_spatial_id_clientside(df)
            dfs[label] = df

    if not dfs:
        print("Error: No satellite data available for assembly.")
        return None

    # --- Build SRTM lookup: spatial_id or .geo -> Slope ---
    srtm_slope = {}
    srtm_df = None
    if "SRTM" in dfs:
        srtm_df = dfs["SRTM"]
        # Prefer spatial_id for lookup
        if "spatial_id" in srtm_df.columns and "Slope" in srtm_df.columns:
            for _, row in srtm_df.iterrows():
                srtm_slope[row["spatial_id"]] = row["Slope"]
        elif "Slope" in srtm_df.columns and ".geo" in srtm_df.columns:
            for _, row in srtm_df.iterrows():
                srtm_slope[row[".geo"]] = row["Slope"]

    # --- Columns per satellite ---
    sat_columns = {
        "S2": ["NDVI", "NDWI", "MNDWI", "NDRE", "IRECI", "S2REP"],
        "S1": ["VH", "VV", "Ratio"],
        "L8": ["LST"],
    }

    # --- Concatenate dynamic satellite data ---
    dynamic_parts = []
    for label in ["S2", "S1", "L8"]:
        if label in dfs:
            df = dfs[label].copy()
            print(f"\n[{label}] Processing for merge:")
            print(f"  Rows: {len(df)}")
            print(f"  Columns: {list(df.columns)}")

            # Ensure required columns exist
            required_cols = (
                ["date", "spatial_id"]
                if "spatial_id" in df.columns
                else ["date", ".geo"]
            )
            if not all(c in df.columns for c in required_cols):
                print(f"  ✗ Missing required columns {required_cols}. Skipping.")
                continue
            if "satellite" not in df.columns:
                df["satellite"] = label

            # Check data columns
            available_data_cols = [
                c for c in sat_columns.get(label, []) if c in df.columns
            ]
            print(f"  Data columns: {available_data_cols}")
            for col in available_data_cols:
                non_null = df[col].notna().sum()
                print(
                    f"    {col}: {non_null} non-null values ({non_null/len(df)*100:.1f}%)"
                )

            # Keep only relevant columns
            if "spatial_id" in df.columns:
                keep_cols = [
                    "spatial_id",
                    ".geo",
                    "date",
                    "satellite",
                ] + available_data_cols
            else:
                keep_cols = [".geo", "date", "satellite"] + available_data_cols
            keep_cols = [c for c in keep_cols if c in df.columns]
            dynamic_parts.append(df[keep_cols])
            print(f"  ✓ Added to merge with columns: {keep_cols}")

    if not dynamic_parts:
        print("Error: No dynamic satellite data found.")
        return None

    all_dynamic = pd.concat(dynamic_parts, ignore_index=True, sort=False)

    # --- Check spatial_id overlap between satellites (DEBUG) ---
    if "spatial_id" in all_dynamic.columns and "satellite" in all_dynamic.columns:
        print(f"\n[SPATIAL ID CHECK]")
        for sat in ["S2", "S1", "L8"]:
            sat_data = all_dynamic[all_dynamic["satellite"] == sat]
            if len(sat_data) > 0:
                unique_ids = sat_data["spatial_id"].nunique()
                print(f"  {sat}: {unique_ids} unique spatial_ids")

        # Check overlap
        s2_ids = set(
            all_dynamic[all_dynamic["satellite"] == "S2"]["spatial_id"].unique()
        )
        l8_ids = set(
            all_dynamic[all_dynamic["satellite"] == "L8"]["spatial_id"].unique()
        )
        if s2_ids and l8_ids:
            overlap = len(s2_ids.intersection(l8_ids))
            print(
                f"  S2/L8 spatial_id overlap: {overlap}/{len(s2_ids)} ({overlap/len(s2_ids)*100:.1f}%)"
            )
            if overlap < len(s2_ids) * 0.9:  # Less than 90% overlap
                print(f"  ⚠️  WARNING: Poor spatial alignment between S2 and L8!")

    # --- Merge by (date, spatial_id) if available, else (date, .geo) ---
    use_spatial_id = "spatial_id" in all_dynamic.columns
    group_cols = ["date", "spatial_id"] if use_spatial_id else ["date", ".geo"]

    print(f"\nMerging data by: {group_cols}")

    result_rows = []

    for group_key, group in all_dynamic.groupby(group_cols):
        if use_spatial_id:
            date, spatial_id = group_key
            # Get .geo from first row in group
            geo = group[".geo"].iloc[0] if ".geo" in group.columns else None
            row = {
                "date": date,
                "spatial_id": spatial_id,
                ".geo": geo,
                "NDVI": np.nan,
                "NDWI": np.nan,
                "MNDWI": np.nan,
                "NDRE": np.nan,
                "IRECI": np.nan,
                "S2REP": np.nan,
                "VH": np.nan,
                "VV": np.nan,
                "Ratio": np.nan,
                "LST": np.nan,
            }
        else:
            date, geo = group_key
            row = {
                "date": date,
                ".geo": geo,
                "NDVI": np.nan,
                "NDWI": np.nan,
                "MNDWI": np.nan,
                "NDRE": np.nan,
                "IRECI": np.nan,
                "S2REP": np.nan,
                "VH": np.nan,
                "VV": np.nan,
                "Ratio": np.nan,
                "LST": np.nan,
            }

        satellites_present = []

        for _, r in group.iterrows():
            sat = r.get("satellite", "")
            satellites_present.append(sat)
            for col in sat_columns.get(sat, []):
                val = r.get(col)
                if val is not None and not (isinstance(val, float) and np.isnan(val)):
                    row[col] = val

        row["satellite"] = ",".join(sorted(set(s for s in satellites_present if s)))
        result_rows.append(row)

    if not result_rows:
        print("Error: No rows produced after merge.")
        return None

    result_df = pd.DataFrame(result_rows)

    # Debug: check LST in result
    if "LST" in result_df.columns:
        lst_count = result_df["LST"].notna().sum()
        print(
            f"\n[MERGE] After merge: LST has {lst_count} non-null values ({lst_count/len(result_df)*100:.1f}%)"
        )
    else:
        print(f"\n[MERGE] ✗ LST column missing after merge!")

    # --- Filter out rows where ALL satellite data is NaN (cloud-masked or QA-filtered images) ---
    data_cols = [
        "NDVI",
        "NDWI",
        "MNDWI",
        "NDRE",
        "IRECI",
        "S2REP",
        "VH",
        "VV",
        "Ratio",
        "LST",
    ]
    existing_data_cols = [c for c in data_cols if c in result_df.columns]

    # Keep only rows where at least ONE data column has a value
    rows_before = len(result_df)
    result_df = result_df[result_df[existing_data_cols].notna().any(axis=1)].copy()
    rows_after = len(result_df)

    if rows_before > rows_after:
        empty_rows = rows_before - rows_after
        print(
            f"\n[FILTER] Removed {empty_rows} empty rows (cloud-masked/QA-filtered images)"
        )
        print(f"         Remaining: {rows_after} rows with valid data")

    # --- Add Slope from SRTM (static, same for every date) ---
    if use_spatial_id and "spatial_id" in srtm_df.columns:
        # Map by spatial_id for perfect alignment
        srtm_map = dict(zip(srtm_df["spatial_id"], srtm_df["Slope"]))
        result_df["Slope"] = result_df["spatial_id"].map(srtm_map)
    else:
        # Fallback: map by .geo
        result_df["Slope"] = result_df[".geo"].map(srtm_slope)

    # --- Parse lat/lon from .geo ---
    coords = result_df[".geo"].apply(_parse_geo_to_latlon)
    result_df["lat"] = coords.apply(lambda x: x[0])
    result_df["lon"] = coords.apply(lambda x: x[1])

    # --- Reorder columns ---
    if use_spatial_id:
        col_order = [
            "date",
            "spatial_id",
            "lat",
            "lon",
            ".geo",
            "satellite",
            "NDVI",
            "NDWI",
            "MNDWI",
            "NDRE",
            "IRECI",
            "S2REP",
            "VH",
            "VV",
            "Ratio",
            "LST",
            "Slope",
        ]
    else:
        col_order = [
            "date",
            "lat",
            "lon",
            ".geo",
            "satellite",
            "NDVI",
            "NDWI",
            "MNDWI",
            "NDRE",
            "IRECI",
            "S2REP",
            "VH",
            "VV",
            "Ratio",
            "LST",
            "Slope",
        ]
    # Only include columns that exist
    col_order = [c for c in col_order if c in result_df.columns]
    result_df = result_df[col_order]

    # Sort by date then geo
    result_df.sort_values(["date", ".geo"], inplace=True)
    result_df.reset_index(drop=True, inplace=True)

    result_df.to_csv(output_path, index=False)
    print(
        f"[OK] Temporal CSV saved: {output_path} ({len(result_df)} rows, "
        f"{result_df['date'].nunique()} unique dates)"
    )

    return output_path
