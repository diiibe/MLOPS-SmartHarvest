import ee
import os
import json
import config
import requests
from utils import create_conn_ee, generate_metadata
from modules.satellites_data_extraction import get_srtm_data


def get_srtm(ROI=config.ROI_TEST, ROI_NAME="ROI_TEST"):
    """
    Extract SRTM elevation data and compute terrain derivatives.

    Args:
        ROI: Region of interest coordinates
        ROI_NAME: Name for organizing output files

    Returns:
        None (saves data to files)
    """
    create_conn_ee()
    srtm = get_srtm_data(ROI)

    # Compute terrain derivatives
    elevation = srtm.select("elevation")
    slope = ee.Terrain.slope(elevation).rename("slope")
    aspect = ee.Terrain.aspect(elevation).rename("aspect")

    # Combine all bands
    terrain = elevation.addBands([slope, aspect])

    # Sample pixels from the terrain image
    roi_geometry = ee.Geometry.Polygon(ROI) if isinstance(ROI, list) else ROI

    sampled = terrain.sample(region=roi_geometry, scale=config.SAMPLING_SCALE, geometries=True)

    try:
        # Define columns to export
        selectors = ["elevation", "slope", "aspect", ".geo"]

        url = sampled.getDownloadURL(filetype="CSV", selectors=selectors, filename="srtm_data")

        print(f"Downloading SRTM data for {ROI_NAME}...")
        response = requests.get(url)

        # Create directory if it doesn't exist
        output_dir = f"raw_data/{ROI_NAME}/srtm"
        os.makedirs(output_dir, exist_ok=True)

        output_file = f"{output_dir}/srtm_data.csv"
        with open(output_file, "wb") as f:
            f.write(response.content)

        print(f"Saved to {output_file}")

    except Exception as e:
        print(f"Error generating URL or downloading: {e}")

    # Metadata generation
    metadata = generate_metadata(
        "SRTM",
        "USGS/SRTMGL1_003",
        1,  # Single image (not a collection)
        "static",  # No temporal range
        "static",
        selectors,
        ROI,
        config.runid,
    )

    metadata_dir = f"metadata/{ROI_NAME}/srtm"
    os.makedirs(metadata_dir, exist_ok=True)
    metadata_filename = f"{config.runid}.json"
    metadata_path = os.path.join(metadata_dir, metadata_filename)

    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=4)

    return
