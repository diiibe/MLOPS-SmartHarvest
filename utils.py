import os
import ee
import pandas as pd
from google.oauth2 import service_account

def create_conn_ee():
        cred = 'google_cred.json'
        credentials = service_account.Credentials.from_service_account_file(cred, scopes=["https://www.googleapis.com/auth/drive",
                                                                                          "https://www.googleapis.com/auth/earthengine"])
        ee.Initialize(credentials=credentials)

def retrieve_sensor_data(sensor_name, roi, start_date, end_date, **kwargs):
    """
    Generalized function to retrieve and filter Earth Engine ImageCollections.

    Args:
        sensor_name (str): The Earth Engine asset ID (e.g., 'LANDSAT/LC09/C02/T1_L2').
        roi (ee.Geometry): Region of Interest.
        start_date (str): Start date (YYYY-MM-DD).
        end_date (str): End date (YYYY-MM-DD).
        **kwargs: Optional filters:
            - cloud_max (int/float): Max cloud percentage. 
              (Automatically detects 'CLOUD_COVER' vs 'CLOUDY_PIXEL_PERCENTAGE' based on ID).
            - seasonal_months (tuple): (start_month, end_month) for seasonal filtering.
            - s1_pol (list): Sentinel-1 Polarizations (e.g., ['VV', 'VH']).
            - s1_mode (str): Sentinel-1 Instrument Mode (e.g., 'IW').
            - s1_orbit (str): Sentinel-1 Orbit Pass (e.g., 'ASCENDING').

    Returns:
        ee.ImageCollection: The filtered collection.
    """
    
    # 1. Base Initialization (Standard for all)
    col = ee.ImageCollection(sensor_name) \
        .filterBounds(roi) \
        .filterDate(start_date, end_date)

    # 2. Handle Cloud Filtering (distinguishes between Landsat and Sentinel-2)
    if 'cloud_max' in kwargs:
        cloud_pct = kwargs['cloud_max']
        # Determine correct metadata property
        if 'S2' in sensor_name or 'COPERNICUS/S2' in sensor_name:
            prop = 'CLOUDY_PIXEL_PERCENTAGE'
        else:
            # Default to Landsat standard
            prop = 'CLOUD_COVER'
        
        col = col.filter(ee.Filter.lt(prop, cloud_pct))

    # 3. Handle Seasonal Filtering (ERA5, etc.)
    if 'seasonal_months' in kwargs:
        start_m, end_m = kwargs['seasonal_months']
        col = col.filter(ee.Filter.calendarRange(start_m, end_m, 'month'))

    # 4. Handle Sentinel-1 Specifics
    # Polarization (List check)
    if 's1_pol' in kwargs:
        for pol in kwargs['s1_pol']:
            col = col.filter(ee.Filter.listContains('transmitterReceiverPolarisation', pol))
    
    # Instrument Mode (Exact match)
    if 's1_mode' in kwargs:
        col = col.filter(ee.Filter.eq('instrumentMode', kwargs['s1_mode']))
        
    # Orbit Pass (Exact match)
    if 's1_orbit' in kwargs:
        col = col.filter(ee.Filter.eq('orbitProperties_pass', kwargs['s1_orbit']))

    return col

def filter_hour(image):

    date = image.date()
    hour = date.get('hour')

    return image.set('hour', hour)

def cloudmask(image):
    """
    Function for cloud masking in Sentinel-2 using the QA60 band to identify clouds.
    """
    qa = image.select('QA60')
    cloudbit = 1 << 10
    cirrusbit = 1 << 11
    mask = qa.bitwiseAnd(cloudbit).eq(0).And(qa.bitwiseAnd(cirrusbit).eq(0))

    return image.updateMask(mask)

def to_celsius(satellite_module, image):
    """
    Function for for converting K to Celsius
    
    Args:
        satellite_module (str): only landsat or eco avaliable
        image (ee.ImageCollection)
    """
    if satellite_module == 'landsat':
        # needs to be separated because Landsat data is scaled
        lst = image.select('ST_B10').multiply(0.00341802).add(149.0).subtract(273.15)
        lst = lst.rename('LST').copyProperties(image, ['system:time_start'])

    elif satellite_module == 'eco':
        lst = image.select('LST').multiply(0.02).subtract(273.15).rename('LST_eco')

    else:
        raise Exception(f"Incorrect/Unknown satellite_module: {satellite_module}")

    return lst