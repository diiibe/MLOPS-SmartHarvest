import ee
import config
from utils import retrieve_sensor_data, filter_hour
from s2cleaning import s2cleancollection

def get_ecostress_data(ROI=config.ROI_TEST, start_date=config.START, end_date=config.END):

    roi = ee.Geometry.Polygon(ROI)
    try:
        eco = retrieve_sensor_data('NASA/ECOSTRESS/LT_LSTE', roi, start_date, end_date)
        # 'NASA/ECOSTRESS/L2T_LSTE/V2'
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

def get_era5_data(ROI=config.ROI_TEST, start_date=config.START, end_date=config.END):

    try:
        roi = ee.Geometry.Polygon(ROI)
        era5 = retrieve_sensor_data('ECMWF/ERA5_LAND/HOURLY', roi, start_date, end_date,
        seasonal_months=(config.SEASONAL_START_MONTH, config.SEASONAL_END_MONTH)
        )

    except Exception as e:
        print(f"Warning: era5 data not found or error loading collection ({e}). Using dummy data.")

    return era5

def get_landsat_thermal_data(ROI=config.ROI_TEST, start_date=config.START, end_date=config.END):

    roi = ee.Geometry.Polygon(ROI)
    try:
        # Try Landsat 9 first (newer)
        l9 = retrieve_sensor_data('LANDSAT/LC09/C02/T1_L2', roi, start_date, end_date,
            cloud_max=config.CLOUD_THRESH_LANDSAT
        )

        l8 = retrieve_sensor_data('LANDSAT/LC08/C02/T1_L2', roi, start_date, end_date,
            cloud_max=config.CLOUD_THRESH_LANDSAT
        )

        # Merge both collections
        landsat = l9.merge(l8)

    except Exception as e:
        print(f"Warning: Error processing Landsat thermal data ({e}). Using dummy data.")


    return landsat

def get_sentinel1_data(ROI=config.ROI_TEST, start_date=config.T1_START, end_date=config.T2_END):

    roi = ee.Geometry.Polygon(ROI)
    try:
        # 1. Query & Filter (Full Range)
        s1_full = retrieve_sensor_data('COPERNICUS/S1_GRD', roi, start_date, end_date, # Using specific dates
            s1_pol=['VV', 'VH'],
            s1_mode='IW',
            s1_orbit='ASCENDING'
        )

    except Exception as e:
        print(f"Warning: sentinel1 data not found or error loading collection ({e}). Using dummy data.")

    return s1_full

def get_sentinel2_data(ROI=config.ROI_TEST, start_date=config.T1_START, end_date=config.T2_END):

    roi = ee.Geometry.Polygon(ROI)
    try:
        s2_full = retrieve_sensor_data('COPERNICUS/S2_SR_HARMONIZED', roi, start_date, end_date, # Using specific dates
            cloud_max=config.CLOUD_THRESH
        )

    except Exception as e:
        print(f"Warning: sentinel2 data not found or error loading collection ({e}). Using dummy data.")

    return s2_full

def get_srtm_data(ROI=config.ROI_TEST):

    roi = ee.Geometry.Polygon(ROI)
    try:
        srtm = ee.Image('USGS/SRTMGL1_003')

        # Clip on ROI extended buffer (100m) to avoid edge effects
        roi_buffer = roi.buffer(100)
        srtm_clipped = srtm.clip(roi_buffer)

    except Exception as e:
        print(f"Warning: srtm data not found or error loading image ({e}). Using dummy data.")

    return srtm_clipped

def get_master_crs(ROI=config.ROI_TEST, start_date=config.T1_START, end_date=config.T2_END):

    roi = ee.Geometry.Polygon(ROI)

    try:
        s2_full = retrieve_sensor_data('COPERNICUS/S2_SR_HARMONIZED', roi, start_date, end_date, # Using specific dates
            cloud_max=config.CLOUD_THRESH
        )
        first_img = s2_full.first()
        master_crs = first_img.select('B4').projection()

    except Exception as e:
        print(f"Warning: sentinel2 data not found or error loading collection ({e}). Using dummy data.")

    return master_crs

def get_sentinel2_data(ROI=config.ROI_TEST, start_date=config.T1_START, end_date=config.T2_END):
    """
    Wrapper calling the Polibio cleaning pipeline.
    """
    # Note: s2cleancollection uses get_sentinel2_data from modules internally, 
    # so we must be careful not to create a recursion loop if modules imports this file.
    # Fortunately, modules/s2cleaning imports from modules.satellites_data_extraction directly.
    return s2cleancollection(config.ROI, start_date, end_date)