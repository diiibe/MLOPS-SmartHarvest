"""
Enhanced Sentinel-2 Export with Polibio Step 2 Integration

This script exports Sentinel-2 data with:
- Step 1: Ensemble cloud masking (Cloud Score+, S2Cloudless, SCL)
- Step 2: Adaptive parcel erosion, robust statistics, QA validation

Output: CSV with spectral indices + QA metadata (coverage_ratio, valid_pixels, erosion_applied)
"""

import ee
import config
import pandas as pd
import requests
from modules.satellites_data_extraction import get_sentinel2_data
from modules.s2cleaning import get_adaptive_core, extract_parcel_stats, validate_parcel_observation
from utils import create_conn_ee, indicesanddate


def export_with_step2(
    ROI=config.ROI_TEST,
    start_date=config.T1_START,
    end_date=config.T2_END,
    output_file="output/sentinel2_polibio.csv",
    use_erosion=True,
):
    """
    Export Sentinel-2 data with Polibio Step 1+2 cleaning.

    Args:
        ROI: Region of interest (list of coordinates or ee.Geometry)
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        output_file: Output CSV path
        use_erosion: Whether to apply Step 2 erosion (default True)

    Returns:
        pd.DataFrame: Exported data with QA columns
    """

    create_conn_ee()

    print(f"Exporting S2 data with Polibio cleaning...")
    print(f"Period: {start_date} to {end_date}")
    print(f"Erosion: {'Enabled' if use_erosion else 'Disabled'}")
    print("=" * 60)

    # Step 1: Get cleaned collection (ensemble masking)
    print("\n1. Applying ensemble cloud masking...")
    clean_col = get_sentinel2_data(ROI, start_date, end_date)

    # Add indices
    clean_col = clean_col.map(indicesanddate)

    count = clean_col.size().getInfo()
    print(f"   Found {count} clean images")

    if count == 0:
        print("   No images found. Exiting.")
        return None

    # Step 2: Apply adaptive erosion (if enabled)
    if use_erosion:
        print("\n2. Applying adaptive parcel erosion...")
        core_result = get_adaptive_core(ROI, sampling_scale=config.SAMPLING_SCALE)
        roi_to_use = core_result["core_geometry"]
        erosion_applied = core_result["erosion_applied"].getInfo()
        is_small = core_result["is_small_parcel"].getInfo()

        original_area = ee.Geometry.Polygon(ROI).area().getInfo() if isinstance(ROI, list) else ROI.area().getInfo()
        core_area = roi_to_use.area().getInfo()

        print(f"   Original area: {original_area:.0f} m²")
        print(f"   Core area: {core_area:.0f} m² ({((original_area - core_area) / original_area * 100):.1f}% reduction)")
        print(f"   Erosion applied: {erosion_applied}m")
        print(f"   Small parcel: {bool(is_small)}")
    else:
        roi_to_use = ee.Geometry.Polygon(ROI) if isinstance(ROI, list) else ROI
        erosion_applied = 0
        is_small = 0
        print("\n2. Erosion disabled, using full ROI")

    # Step 3: Extract data with QA metadata
    print("\n3. Extracting pixel data with QA metadata...")

    def sample_with_qa(img):
        """Sample pixels and add QA metadata per image."""
        img = img.set("date_str", img.date().format("YYYY-MM-dd"))

        # Extract statistics for QA
        stats = extract_parcel_stats(img, roi_to_use, sampling_scale=config.SAMPLING_SCALE)

        # Validate observation
        is_valid = validate_parcel_observation(stats, is_small_parcel=is_small)

        # Get QA values
        valid_count = stats.get("valid_pixel_count")
        total_count = stats.get("total_pixel_count")
        coverage = stats.get("coverage_ratio")

        # Sample pixels
        # Note: MNDWI is not available (bug in utils.py - mndwi function calculates NDRE instead)
        indices = ["NDVI", "EVI", "GNDVI", "IRECI", "NDMI", "NDRE"]
        sampled = img.select(indices).sample(region=roi_to_use, scale=config.SAMPLING_SCALE, geometries=True)

        # Add metadata to each feature
        def add_metadata(feat):
            return feat.set(
                {
                    "date": img.get("date_str"),
                    "valid_pixels": valid_count,
                    "total_pixels": total_count,
                    "coverage_ratio": coverage,
                    "observation_valid": is_valid,
                    "erosion_m": erosion_applied,
                    "is_small_parcel": is_small,
                }
            )

        return sampled.map(add_metadata)

    # Process all images
    features = clean_col.map(sample_with_qa).flatten()

    # Get download URL
    print("\n4. Generating download URL...")
    selectors = [
        "date",
        "NDVI",
        "EVI",
        "GNDVI",
        "IRECI",
        "NDMI",
        "NDRE",
        "valid_pixels",
        "total_pixels",
        "coverage_ratio",
        "observation_valid",
        "erosion_m",
        "is_small_parcel",
        ".geo",
    ]

    try:
        url = features.getDownloadURL(filetype="CSV", selectors=selectors, filename="sentinel2_polibio")

        print("   Downloading data...")
        response = requests.get(url)

        # Save to file
        import os

        os.makedirs(os.path.dirname(output_file), exist_ok=True)

        with open(output_file, "wb") as f:
            f.write(response.content)

        print(f"\n✅ Export complete: {output_file}")

        # Load and return as DataFrame
        df = pd.read_csv(output_file)

        print(f"\nDataset Summary:")
        print(f"   Total pixels: {len(df)}")
        print(f"   Date range: {df['date'].min()} to {df['date'].max()}")
        print(f"   Unique dates: {df['date'].nunique()}")
        print(f"   Avg coverage: {df['coverage_ratio'].mean():.2%}")
        print(f"   Valid observations: {df['observation_valid'].sum()} / {len(df['date'].unique())} dates")

        return df

    except Exception as e:
        print(f"\n❌ Error during export: {e}")
        return None


if __name__ == "__main__":
    # Example usage
    df = export_with_step2(
        ROI=config.ROI_TEST,
        start_date="2024-06-01",
        end_date="2024-07-31",
        output_file="output/sentinel2_polibio_june_july.csv",
        use_erosion=True,
    )

    if df is not None:
        print("\n" + "=" * 60)
        print("First few rows:")
        print(df.head())
