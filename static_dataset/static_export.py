import ee
import os
import sys
import pandas as pd

import config
from utils import create_conn_ee
from modules.satellites import sentinel1, sentinel2, landsat_thermal, srtm
import stats

# Add parent directory to sys.path to import modules and config
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

def staticexport():
    
    # 1. Connection initialization
    print("Connecting to Earth Engine")
    create_conn_ee()
    
    # 2. ROI initialization
    config.ROI = ee.Geometry.Polygon(config.ROI_TEST)
    print("ROI initialized")

    # 3. Data Retrieval
    print("Loading data from satellites")
    s2_col = sentinel2.get_sentinel2_data()
    s1_col = sentinel1.get_sentinel1_data()
    lst_col = landsat_thermal.get_landsat_thermal()
    elevation = srtm.get_srtm_data()

    # 4. Calculate Statistics
    print("Calculating S2 statistics")
    s2_stats = stats.s2stats(s2_col)
    print("Calculating S1 statistics")
    s1_stats = stats.s1stats(s1_col)
    print("Calculating Landsat statistics")
    lst_stats = stats.landsatstats(lst_col)
    print("Calculating terrain statistics")
    terrain_stats = stats.terrainstats(elevation)

    # 5. Resampling 
    # Sentinel-2/1 are natively 10m and Landsat 8/9 is 30m so we resample it to 10m using bicubic interpolation
    lst_resampled = lst_stats.resample('bicubic').reproject(crs=s2_stats.projection(), scale=10)
    # Terrain is 30m so we resample it to 10m using bilinear interpolation
    terrain_resampled = terrain_stats.resample('bilinear').reproject(crs=s2_stats.projection(), scale=10)

    # 6. Stacking all bands onto each other
    final_stack = ee.Image.cat([
        s2_stats,
        s1_stats,
        lst_resampled,
        terrain_resampled
    ]).clip(config.ROI)
    
    # Any pixel that is masked in at least one band will be masked in all.
    total_mask = final_stack.mask().reduce(ee.Reducer.min())
    final_stack = final_stack.updateMask(total_mask)
    
    print("Bands combined and masks harmonized.")

    # 7. Extracting data from rasters
    print(f"Extracting pixels at {config.SAMPLING_SCALE}m scale...")
    
    # Creates a masked coordinate image and adds it to the stack
    coord_img = ee.Image.pixelLonLat().updateMask(total_mask)
    final_stack_with_coords = final_stack.addBands(coord_img)
    
    data_stack = final_stack_with_coords.reduceRegion(
        reducer=ee.Reducer.toList(), 
        geometry=config.ROI, # Filtering by area of interest
        scale=config.SAMPLING_SCALE, # Resampling scale
        maxPixels=1e9 # Maximum number of pixels to process
    ).getInfo()

    # 8. Formatting data into a dataset
    print("Formatting dataset")
    df = pd.DataFrame(data_stack)
    
    # Unique Point_ID identifier
    df.insert(0, 'Point_ID', range(1, len(df) + 1))
    
    # Adding .geo coordinates in json format as a column 
    if 'longitude' in df.columns and 'latitude' in df.columns:
        df['.geo'] = df.apply(lambda row: f"Point [{row['longitude']}, {row['latitude']}]", axis=1)
        df = df.drop(columns=['longitude', 'latitude'])
    
    # Colums order in the final dataset
    ordered_cols = [
        'Point_ID', 
        'NDVI', 'NDMI', 'NDRE',
        'NDVI_Peak', 'NDMI_Peak', 'NDRE_Peak',
        'Time_to_Peak',
        'Green_Up', 'Senescence', 'NDVI_Delta',
        'Entropy', 'Contrast',
        'VH_Late', 'VH_Drop',
        'LST', 'LST_Stability',
        'Elevation', 'Slope', 'TWI', 'Solar_Rad',
        '.geo'
    ]
    # Keep only columns that exist (in case of missing data)
    final_cols = [c for c in ordered_cols if c in df.columns]
    df = df[final_cols]
    
    # Save to CSV
    output_dir = os.path.join(os.path.dirname(__file__), '..', 'output')
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    output_file = os.path.join(output_dir, 'SmartHarvest_Static_Dataset.csv')
    df.to_csv(output_file, index=False)
    print(f"Dataset saved to {output_file}")
    print(f"Total rows: {len(df)}")
    print(f"Columns: {df.columns.tolist()}")

if __name__ == "__main__":
    staticexport()
