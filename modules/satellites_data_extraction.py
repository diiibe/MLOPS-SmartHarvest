import ee
import config
from utils import retrieve_sensor_data, filter_hour

def get_ecostress_data():

    try:
        eco = retrieve_sensor_data('NASA/ECOSTRESS/L2_LSTE', config.ROI, config.START_DATE, config.END_DATE)

        # Filter by hour (approximate local time, assuming UTC+1 or similar for Italy/Europe based on coords in example)
        # The example coords are 45.10, 10.20 (Italy). UTC+1/UTC+2.
        # Let's filter by UTC hours 9 to 15 (approx 10-16 local).
        # A more robust way is to use solar time or just filter by 'solar_zenith' if available, but hour is requested.
            
        eco = eco.map(filter_hour).filter(ee.Filter.rangeContains('hour', 9, 15))
        
        # Check if collection is empty
        count = eco.size().getInfo()

    except Exception as e:
        print(f"Warning: ECOSTRESS data not found or error loading collection ({e}). Using dummy data.")

    return eco

def get_era5_data():

    try:

        era5 = retrieve_sensor_data('ECMWF/ERA5_LAND/HOURLY', config.ROI, config.START_DATE, config.END_DATE,
        seasonal_months=(config.SEASONAL_START_MONTH, config.SEASONAL_END_MONTH)
        )

    except Exception as e:
        print(f"Warning: era5 data not found or error loading collection ({e}). Using dummy data.")

    return era5

def get_landsat_thermal():
 
    try:
        # Try Landsat 9 first (newer)
        l9 = retrieve_sensor_data('LANDSAT/LC09/C02/T1_L2', config.ROI, config.START, config.END,
            cloud_max=config.CLOUD_THRESH
        )

        l8 = retrieve_sensor_data('LANDSAT/LC08/C02/T1_L2', config.ROI, config.START, config.END,
            cloud_max=config.CLOUD_THRESH
        )
        
        # Merge both collections
        landsat = l9.merge(l8)

    except Exception as e:
        print(f"Warning: Error processing Landsat thermal data ({e}). Using dummy data.")

        
    return landsat

def get_sentinel1_data():

    try:
        # 1. Query & Filter (Full Range)
        s1_full = retrieve_sensor_data('COPERNICUS/S1_GRD', config.ROI, config.DATE_T1_START, config.DATE_T2_END, # Using specific dates
            s1_pol=['VV', 'VH'],
            s1_mode='IW',
            s1_orbit='ASCENDING'
        )

    except Exception as e:
        print(f"Warning: sentinel1 data not found or error loading collection ({e}). Using dummy data.")
    
    return s1_full

def get_sentinel2_data():

    try:
        s2_full = retrieve_sensor_data('COPERNICUS/S2_SR_HARMONIZED', config.ROI, config.DATE_T1_START, config.DATE_T2_END, # Using specific dates
            cloud_max=config.CLOUD_THRESH
        )
    
    except Exception as e:
        print(f"Warning: sentinel2 data not found or error loading collection ({e}). Using dummy data.")
    
    return s2_full

def get_srtm_data():

    try:
        srtm = ee.Image('USGS/SRTMGL1_003')
        
        # Clip on ROI extended buffer (100m) to avoid edge effects
        roi_buffer = config.ROI.buffer(100)
        srtm_clipped = srtm.clip(roi_buffer)
    
    except Exception as e:
        print(f"Warning: srtm data not found or error loading image ({e}). Using dummy data.")
    
    return srtm_clipped