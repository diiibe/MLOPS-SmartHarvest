import ee
import os
import json
import config
import requests
from utils import create_conn_ee, generate_metadata
from modules.satellites_data_extraction import get_landsat_thermal_data

def get_landsat(ROI=config.ROI_TEST, start_date=config.T1_START, end_date=config.T2_END, ROI_NAME="ROI_TEST"):
    """
    Extract Landsat 8/9 thermal data and convert to Land Surface Temperature (LST) in Celsius.
    
    Args:
        ROI: Region of interest coordinates
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        ROI_NAME: Name for organizing output files
    
    Returns:
        None (saves data to files)
    """
    create_conn_ee()
    landsat_raw = get_landsat_thermal_data(ROI, start_date, end_date)

    def process_thermal(image):
        # ST_B10 is the thermal band in Landsat Collection 2 Level 2
        # It's already in Kelvin, scaled by 0.00341802 + 149.0
        lst_kelvin = image.select('ST_B10').multiply(0.00341802).add(149.0)
        lst_celsius = lst_kelvin.subtract(273.15)
        
        # Apply QA mask to remove clouds and cloud shadows
        qa = image.select('QA_PIXEL')
        # Bit 3: Cloud
        # Bit 4: Cloud Shadow
        cloud_mask = qa.bitwiseAnd(1 << 3).eq(0).And(qa.bitwiseAnd(1 << 4).eq(0))
        
        return lst_celsius.updateMask(cloud_mask).rename('LST').copyProperties(image, ['system:time_start'])
    
    # Process all images
    landsat_processed = landsat_raw.map(process_thermal)

    def sample_pixel(img):
        img = img.set('date_str', img.date().format('YYYY-MM-dd'))
        # Select band and sample
        return img.select(['LST']).sample(
            region=ee.Geometry.Polygon(ROI) if isinstance(ROI, list) else ROI,
            scale=config.SAMPLING_SCALE,
            geometries=True,
        ).map(lambda feat: feat.set('date', img.get('date_str')))

    # Flatten collection to features
    features = landsat_processed.map(sample_pixel).flatten()

    try:
        # Define columns to export
        selectors = ['date', 'LST', '.geo']
        
        url = features.getDownloadURL(
            filetype='CSV',
            selectors=selectors,
            filename='landsat_thermal_data'
        )

        print(f"Downloading Landsat thermal data for {start_date} to {end_date}...")
        response = requests.get(url)
        
        # Create directory if it doesn't exist
        output_dir = f'raw_data/{ROI_NAME}/landsat_thermal'
        os.makedirs(output_dir, exist_ok=True)
        
        output_file = f'{output_dir}/{start_date}_{end_date}.csv'
        with open(output_file, 'wb') as f:
            f.write(response.content)
            
        print(f"Saved to {output_file}")

    except Exception as e:
        print(f"Error generating URL or downloading: {e}")

    # Metadata generation
    metadata = generate_metadata(
        "Landsat 8/9 Thermal", 
        "LANDSAT/LC08-09/C02/T1_L2", 
        landsat_raw.size().getInfo(), 
        start_date, 
        end_date, 
        selectors, 
        config.runid
    )
    
    metadata_dir = f'metadata/{ROI_NAME}/landsat_thermal'
    os.makedirs(metadata_dir, exist_ok=True)
    metadata_filename = f'{config.runid}.json'
    metadata_path = os.path.join(metadata_dir, metadata_filename)
    
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=4)

    return

if __name__ == "__main__":
    # Example usage for testing
    get_landsat(
        ROI=config.ROI_TEST,
        start_date='2024-06-01',
        end_date='2024-06-30',
        ROI_NAME="ROI_TEST"
    )
