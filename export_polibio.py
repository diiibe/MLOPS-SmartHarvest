"""
Enhanced Multi-Sensor Export with Polibio Step 2 Integration

This script exports data from multiple sensors with preserved acquisition dates.
"""

import ee
import config
import pandas as pd
import requests
import os
from modules.satellites_data_extraction import (
    get_sentinel2_data,
    get_landsat_thermal_data,
    get_sentinel1_data
)
from modules.s2cleaning import (
    get_adaptive_core, 
    extract_parcel_stats,
    validate_parcel_observation
)
from utils import create_conn_ee, indicesanddate, despeckle

def export_with_step2(
    ROI=config.ROI_TEST,
    start_date=config.T1_START,
    end_date=config.T2_END,
    output_file='output/multi_sensor_polibio.csv',
    use_erosion=True
):
    """
    Export Multi-Sensor data (S2, S1, Landsat) with Polibio Step 1+2 cleaning.
    """
    
    create_conn_ee()
    
    print(f"Exporting Multi-Sensor data with Polibio cleaning...")
    print(f"Period: {start_date} to {end_date}")
    print(f"Erosion: {'Enabled' if use_erosion else 'Disabled'}")
    print("="*60)
    
    # --- 1. S2 COLLECTION ---
    print("\n1. Processing Sentinel-2...")
    s2_col = get_sentinel2_data(ROI, start_date, end_date)
    s2_col = s2_col.map(lambda img: indicesanddate(ee.Image(img)).set('sensor', 'S2'))
    
    # --- 2. LANDSAT THERMAL (LST) ---
    print("2. Processing Landsat Thermal (LST)...")
    l_raw = get_landsat_thermal_data(ROI, start_date, end_date)
    
    def process_landsat(img):
        image = ee.Image(img)
        lst = image.select('ST_B10').multiply(0.00341802).add(149.0).subtract(273.15).rename('LST')
        qa = image.select('QA_PIXEL')
        mask = qa.bitwiseAnd(1 << 3).eq(0).And(qa.bitwiseAnd(1 << 4).eq(0))
        # Masked update and resample
        return lst.updateMask(mask).resample('bilinear').reproject(
            crs='EPSG:4326', scale=config.SAMPLING_SCALE
        ).copyProperties(image, ['system:time_start']).set('sensor', 'Landsat')
    
    lst_col = l_raw.map(process_landsat)

    # --- 3. SENTINEL-1 (VV, VH, VHRATIO) ---
    print("3. Processing Sentinel-1 (SAR)...")
    s1_raw = get_sentinel1_data(ROI, start_date, end_date)
    
    def process_s1(img):
        image = ee.Image(img)
        image_clean = ee.Image(despeckle(image))
        vhratio = image_clean.select('VH').divide(image_clean.select('VV')).rename('VHRATIO')
        return image_clean.addBands(vhratio).copyProperties(image, ['system:time_start']).set('sensor', 'S1')
    
    s1_col = s1_raw.map(process_s1)

    # --- 4. HARMONIZE AND MERGE ---
    print("4. Harmonizing bands and merging collections...")
    
    s2_indices = ['NDVI', 'EVI', 'GNDVI', 'IRECI', 'NDMI', 'NDRE']
    landsat_bands = ['LST']
    s1_bands = ['VV', 'VH', 'VHRATIO']
    all_bands = s2_indices + landsat_bands + s1_bands

    # Create a single constant image with all bands as -999 (unmasked)
    # This acts as a background to ensure all images have all bands for sampling.
    blank_bands = ee.Image.constant([-999] * len(all_bands)).rename(all_bands)

    def harmonize_bands(img):
        image = ee.Image(img)
        # By adding blank bands to 'image' (overwrite=False), we keep 'image' as the primary object.
        # This inherently preserves its system:time_start, id, and other metadata.
        return image.addBands(blank_bands, overwrite=False)

    s2_final = s2_col.map(harmonize_bands)
    lst_final = lst_col.map(harmonize_bands)
    s1_final = s1_col.map(harmonize_bands)
    
    merged_col = s2_final.merge(lst_final).merge(s1_final).sort('system:time_start')
    
    # --- 5. ADAPTIVE EROSION (Polibio Step 2) ---
    if use_erosion:
        core_result = get_adaptive_core(ROI, sampling_scale=config.SAMPLING_SCALE)
        roi_to_use = core_result['core_geometry']
    else:
        roi_to_use = ee.Geometry.Polygon(ROI) if isinstance(ROI, list) else ROI

    # --- 6. SAMPLING ---
    print("6. Extracting pixel data...")
    
    def sample_with_metadata(img):
        image = ee.Image(img)
        date_str = image.date().format('YYYY-MM-dd')
        sensor_name = image.get('sensor')
        
        # Stats for QA
        stats = extract_parcel_stats(image, roi_to_use, sampling_scale=config.SAMPLING_SCALE)
        is_valid = validate_parcel_observation(stats, is_small_parcel=0) # simplified for debug
        
        # Sample bands
        sampled = image.select(all_bands).sample(
            region=roi_to_use,
            scale=config.SAMPLING_SCALE,
            geometries=True
        )
        
        def set_feat_props(feat):
            return feat.set({
                'date': date_str,
                'sensor': sensor_name,
                'valid_pixels': stats.get('valid_pixel_count'),
                'coverage_ratio': stats.get('coverage_ratio'),
                'observation_valid': is_valid
            })
            
        return sampled.map(set_feat_props)
    
    features = merged_col.map(sample_with_metadata).flatten()
    
    # --- 7. EXPORT ---
    print("7. Generating download URL...")
    selectors = ['date', 'sensor'] + all_bands + [
        'valid_pixels', 'coverage_ratio', 'observation_valid', '.geo'
    ]
    
    try:
        url = features.getDownloadURL(
            filetype='CSV',
            selectors=selectors,
            filename='multi_sensor_polibio'
        )
        
        response = requests.get(url)
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        with open(output_file, 'wb') as f:
            f.write(response.content)
        
        df = pd.read_csv(output_file)
        if len(df) > 0:
            print(f"✅ Export complete: {len(df)} rows")
        else:
            print("⚠️ Warning: Exported dataset is empty.")
        return df
        
    except Exception as e:
        print(f"❌ Error during export: {e}")
        return None

if __name__ == "__main__":
    export_with_step2(
        ROI=config.ROI_TEST,
        start_date='2024-05-01',
        end_date='2024-09-30',
        output_file='output/vineyard_multi_sensor_2024.csv',
        use_erosion=True
    )
