import ee
import os
import json
import config
import requests
from utils import create_conn_ee, to_celsius, generate_metadata
from modules.satellites_data_extraction import get_ecostress_data

def get_ecostress(ROI=config.ROI_TEST, start_date=config.T1_START, end_date=config.T2_END, ROI_NAME="ROI_TEST"):

    create_conn_ee()
    eco_raw = get_ecostress_data(ROI, start_date, end_date)
    
    # Check if collection has data
    collection_size = eco_raw.size().getInfo()
    if collection_size == 0:
        print(f"No Ecostress data available for ROI in period {start_date} to {end_date}")
        # Still create empty output files to maintain consistency
        output_dir = f'raw_data/{ROI_NAME}/ecostress'
        os.makedirs(output_dir, exist_ok=True)
        output_file = f'{output_dir}/{start_date}_{end_date}.csv'
        with open(output_file, 'w') as f:
            f.write('date,LST_eco,.geo\n')  # Write header only
        
        # Generate metadata with 0 images
        metadata = generate_metadata(
            "Ecostress", 
            "NASA/ECOSTRESS/L2T_LSTE/V2", 
            0, 
            start_date, 
            end_date, 
            ['date', 'LST_eco', '.geo'], 
            config.runid
        )
        metadata_dir = f'metadata/{ROI_NAME}/ecostress'
        os.makedirs(metadata_dir, exist_ok=True)
        metadata_path = os.path.join(metadata_dir, f'{config.runid}.json')
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=4)
        return
    
    # Process images: Convert to Celsius and retain properties
    def process_image(img):
        # to_celsius for 'eco' returns just the band, so we must copy properties
        return to_celsius('eco', img).copyProperties(img, ['system:time_start'])
    
    eco = eco_raw.map(process_image)

    def sample_pixel(img):
        img = img.set('date_str', img.date().format('YYYY-MM-dd'))
        # Select band and sample
        # Ecostress L2 LSTE is 70m resolution
        return img.select(['LST_eco']).sample(
            region=ee.Geometry.Polygon(ROI),
            scale=70, 
            geometries=True, # Keep geometry
        ).map(lambda feat: feat.set('date', img.get('date_str'))) # Add date to each feature

    # Flatten collection to features
    features = eco.map(sample_pixel).flatten()

    try:
        # Request download URL
        # Define columns to export
        selectors = ['date', 'LST_eco', '.geo']
        
        url = features.getDownloadURL(
                filetype='CSV',
                selectors=selectors,
                filename='ecostress_data'
            )

        print(f"Downloading Ecostress data for {start_date} to {end_date}...")
        response = requests.get(url)
        
        # Create directory if it doesn't exist
        output_dir = f'raw_data/{ROI_NAME}/ecostress'
        os.makedirs(output_dir, exist_ok=True)
        
        output_file = f'{output_dir}/{start_date}_{end_date}.csv'
        with open(output_file, 'wb') as f:
            f.write(response.content)
            
        print(f"Saved to {output_file}")

    except Exception as e:
        print(f"Error generating URL or downloading: {e}")

    # Metadata generation
    metadata = generate_metadata(
        "Ecostress", 
        "NASA/ECOSTRESS/L2T_LSTE/V2", 
        eco_raw.size().getInfo(), 
        start_date, 
        end_date, 
        ['date', 'LST_eco', '.geo'], 
        config.runid
    )
    
    metadata_dir = f'metadata/{ROI_NAME}/ecostress'
    os.makedirs(metadata_dir, exist_ok=True)
    metadata_filename = f'{config.runid}.json'
    metadata_path = os.path.join(metadata_dir, metadata_filename)
    
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=4)

    return

if __name__ == "__main__":
    # Example usage for testing
    get_ecostress(
        ROI=config.ROI_TEST,
        start_date='2024-06-01',
        end_date='2024-06-30'
    )
