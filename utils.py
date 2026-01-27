import os
import ee
import glob
import config
import pandas as pd

from functools import reduce
from pathlib import Path
from datetime import datetime
from google.oauth2 import service_account
from dateutil.relativedelta import relativedelta

def create_conn_ee():
    cred = 'google_cred.json'
    if os.path.exists(cred):
        print(f"Connecting to Earth Engine using service account: {cred}")
        credentials = service_account.Credentials.from_service_account_file(cred, scopes=["https://www.googleapis.com/auth/drive",
                                                                                          "https://www.googleapis.com/auth/earthengine"])
        ee.Initialize(credentials=credentials)
    else:
        print("Service account file not found. Falling back to browser-based authentication.")
        ee.Authenticate()
        ee.Initialize()

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

# def cloudmask(image):
#     """
#     Function for cloud masking in Sentinel-2 using the QA60 band to identify clouds.
#     """
#     qa = image.select('QA60')
#     cloudbit = 1 << 10
#     cirrusbit = 1 << 11
#     mask = qa.bitwiseAnd(cloudbit).eq(0).And(qa.bitwiseAnd(cirrusbit).eq(0))

#     return image.updateMask(mask)

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

from datetime import datetime
from dateutil.relativedelta import relativedelta
from pathlib import Path

from datetime import datetime
from dateutil.relativedelta import relativedelta
from pathlib import Path

from datetime import datetime
from dateutil.relativedelta import relativedelta
from pathlib import Path

def get_missing_partitions(start_date, end_date, base_dir):
    """
    Returns a list of dates (partitions) that are MISSING data.
    Matches format: .../year=YYYY/month=M (no zero padding for single digit months)
    Do not allow dates bigger than current month.
    """
    # 1. Standardize inputs
    fmt = "%Y-%m-%d"
    if isinstance(start_date, str):
        start_date = datetime.strptime(start_date, fmt)
    if isinstance(end_date, str):
        end_date = datetime.strptime(end_date, fmt)

    base_path = Path(base_dir)
    missing_dates = []
    
    # Initialize iteration at the first of the start month
    current_date = start_date.replace(day=1)
    
    # Get the actual current time (Right Now)
    now = datetime.now()

    while current_date <= end_date:
        # --- NEW CHECK: Stop if we go beyond the current real-world month ---
        # Since current_date is always day 1, comparing it to 'now' works perfectly.
        # Example: if current_date is Nov 1st and now is Oct 25th, this breaks.
        if current_date > now:
            break
        # --------------------------------------------------------------------

        # 2. Construct path EXACTLY as shown in your example
        year_part = f"year={current_date.year}"
        month_part = f"month={current_date.month}" 
        
        target_path = base_path / year_part / month_part
        
        data_found = False
        
        # 3. Check if folder exists AND contains files
        if target_path.exists() and target_path.is_dir():
            # Get list of files, ignoring hidden system files like .DS_Store
            valid_files = [
                f for f in target_path.iterdir() 
                if f.is_file() and not f.name.startswith('.')
            ]
            
            if len(valid_files) > 0:
                data_found = True

        if not data_found:
            missing_dates.append(current_date)
        
        # Move to next month
        current_date += relativedelta(months=1)

    return missing_dates


# Calculates GDD for ERA5 as (T - 283.15) / 24
def gdd(image):
    t_base = 283.15
    gdd = image.select('temperature_2m').subtract(t_base).max(0).divide(24).rename('GDD')
    return image.addBands(gdd)

# Calculates NDVI for Sentinel-2 Harmonized
def ndvi(image):
    ndvi = image.normalizedDifference(['B8', 'B4']).rename('NDVI')
    return image.addBands(ndvi)

# Calculates NDVI for Sentinel-2 Harmonized
def evi(image):
    EVI = image.expression(
        '2.5 * ((NIR - RED) / (NIR + 6 * RED - 7.5 * BLUE + 1))', {
            'NIR': image.select('B8').divide(10000),
            'RED': image.select('B4').divide(10000),
            'BLUE': image.select('B2').divide(10000)
    }).rename("EVI")

    return image.addBands(EVI)

# Calculates GNDVI for Sentinel-2 Harmonized
def gndvi(image):
    gndvi = image.normalizedDifference(['B8', 'B3']).rename('GNDVI')
    return image.addBands(gndvi)

# Calculates GNDVI for Sentinel-2 Harmonized
def ireci(image):
    b4_proj = image.select('B4').projection()
    b4 = image.select('B4')
    b5 = image.select('B11').resample('bicubic').reproject(crs=b4_proj, scale=10)
    b6 = image.select('B11').resample('bicubic').reproject(crs=b4_proj, scale=10) # SWIR for NDMI
    b7 = image.select('B5').resample('bicubic').reproject(crs=b4_proj, scale=10)

    ireci = (b7.subtract(b4)).divide((b5.divide(b6))).rename('IRECI')
    return image.addBands(ireci)

# Calculates NDMI for Sentinel-2 Harmonized as (NIR - SWIR) / (NIR + SWIR)
def ndmi(image):
    ndmi = image.normalizedDifference(['B8', 'B11']).rename('NDMI')
    return image.addBands(ndmi)

# Calculates MNDWI for Sentinel-2 Harmonized as (Green – SWIR) / (Green + SWIR)
def mndwi(image):
    ndre = image.normalizedDifference(['B3', 'B11']).rename('NDRE')
    return image.addBands(ndre)

# Calculates NDRE for Sentinel-2 Harmonized as (NIR - RE) / (NIR + RE)
def ndre(image):
    ndre = image.normalizedDifference(['B8', 'B5']).rename('NDRE')
    return image.addBands(ndre)

def cirededge(image):
    b4_proj = image.select('B4').projection()
    b5 = image.select('B11').resample('bicubic').reproject(crs=b4_proj, scale=10)
    b7 = image.select('B5').resample('bicubic').reproject(crs=b4_proj, scale=10)

    cirededge = (b7.divide(b5)-1).rename('CIREDEDGE')
    return image.addBands(cirededge)

    # S2REP
# Adds time bands for linear regression since days are needed
# def timebands(image):
#     time_start = image.get('system:time_start')
#     start_millis = ee.Date(config.START).millis()
#     t = ee.Number(time_start).subtract(start_millis).divide(1000 * 60 * 60 * 24)
#     return image.addBands(ee.Image.constant(t).rename('t').float()).addBands(ee.Image.constant(1).rename('constant').float())

# Calculates LST for Landsat 8/9 as (ST_B10 * 0.00341802 + 149.0) - 273.15
def lstbands(image):

    lst = image.select('ST_B10').multiply(0.00341802).add(149.0).subtract(273.15).rename('LST')
    return image.addBands(lst)

def indicesanddate(image):
    img = ndvi(image)
    img = evi(img)
    img = gndvi(img)
    img = ireci(img)
    img = ndmi(img)
    img = mndwi(img)
    img = ndre(img)
    date_band = ee.Image.constant(image.get('system:time_start')).rename('date').toDouble()

    return img.addBands(date_band)

def despeckle(image):
    # Simple BoxCar 5x5
    return ee.Image(image.focal_mean(radius=2.5, units='pixels', iterations=1).copyProperties(image, ['system:time_start']))

def vv(image):
    return image.select('VV')

def vh(image):
    return image.select('VH')

def rariovhvv(image):
    vv = image.select('VV')
    vh = image.select('VH')
    rariovhvv = vh.divide(vv).rename('RATIOVHVV')

    return image.addBands(rariovhvv)

def indicesst1(image):
    img = vv(image)
    img = vh(image)
    img = rariovhvv(image)
    date_band = ee.Image.constant(image.get('system:time_start')).rename('date').toDouble()

    return img.addBands(date_band)

# Helper to converting Wind Speed 10m to 2m (FAO-56 approximation: multiply by 0.748)
def wind_10m_to_2m(u10, v10):
    ws10 = u10.hypot(v10)
    return ws10.multiply(0.748).rename('wind_speed_2m')

def process_era5(image):
    # Convert units
    temp_k = image.select('temperature_2m')
    temp_c = temp_k.subtract(273.15).rename('temp_c')
    dew_k = image.select('dewpoint_temperature_2m')
    dew_c = dew_k.subtract(273.15).rename('dew_c')
    precip = image.select('total_precipitation_hourly').rename('precip') # in meters
    pet = image.select('potential_evaporation').rename('pet')
    aet = image.select('evaporation_from_vegetation_transpiration').rename('aet') # Or total_evaporation

    # Solar Radiation (J/m^2) -> W/m^2 -> MJ/m^2/day (later) or accumulation
    # ERA5 accumulation is J/m^2 per hour.
    rad_j = image.select('surface_net_solar_radiation').max(0) # Avoid negative at night? Net can be negative.
    # FAO PM needs Net Radiation (Rn) in MJ/m2/day for daily. We have hourly.
    # Let's trust Net Radiation provided by ERA5.

    u10 = image.select('u_component_of_wind_10m')
    v10 = image.select('v_component_of_wind_10m')
    ws2 = wind_10m_to_2m(u10, v10)

    # --- ETo Calculation (Hourly logic simplified) ---
    # FAO-56 Penman-Monteith is typically Daily. Hourly is possible but complex (Gsc).
    # We will approximate Daily ETo by aggregating bands first or use simplified Hargreaves if PM is too heavy?
    # User requested Penman-Monteith. We will try a simplified daily aggregation approach.
    # But here we are mapping over hourly images.
    # Let's just prepare the bands for daily aggregation.

    return image.addBands([temp_c, dew_c, precip, pet, aet, ws2])

# b5 = image.select('B5').resample('bicubic').reproject(crs=b4_proj, scale=10)
# b11 = image.select('B11').resample('bicubic').reproject(crs=b4_proj, scale=10) # SWIR for NDMI

def generate_metadata(source, collection, image_count, start_date, end_date, bands, roi, runid):

    metadata = {
        'run_id': runid,
        'created_at': str(datetime.now()),
        'status': '',
        'source': source,
        'provider': collection,
        'image_count': image_count,
        'date_range': f"{start_date} to {end_date}",
        'bands_description': bands,
        'roi_coords': roi,
    }

    return metadata

import pandas as pd
import os
import glob
from functools import reduce

def create_partitioned_dataset(input_path, output_path="dataset"):
    """
    1. Groups files by their parent folder (e.g., sentinel_1, sentinel_2).
    2. Concatenates (stacks) files within the same folder vertically.
    3. Merges the resulting DataFrames from different folders horizontally.
    4. Writes the result to a Hive-partitioned dataset.
    """
    # 1. Find all CSV files
    all_files = glob.glob(os.path.join(input_path, "**/*.csv"), recursive=True)
    
    if not all_files:
        print("No CSV files found.")
        return

    # Dictionary to hold lists of DataFrames by their folder name
    # structure: { 'sentinel_1': [df1, df2], 'sentinel_2': [df3, df4] }
    files_by_source = {}

    print("Reading and grouping files...")
    
    for file in all_files:
        # Get the parent folder name to use as the "Source ID"
        parent_folder = os.path.basename(os.path.dirname(file))
        
        try:
            df = pd.read_csv(file)
            df.columns = df.columns.str.strip()
            
            # Only process if it has a date (ignore SRTM/static files)
            if 'date' in df.columns and '.geo' in df.columns:
                df['date'] = pd.to_datetime(df['date'])
                
                if parent_folder not in files_by_source:
                    files_by_source[parent_folder] = []
                files_by_source[parent_folder].append(df)
            else:
                print(f"Skipping static file: {os.path.basename(file)}")
                
        except Exception as e:
            print(f"Error reading {file}: {e}")

    # 2. Concatenate files from the SAME source (Vertical Stack)
    # This prevents the "Duplicate Columns" error
    consolidated_dfs = []
    
    for source, df_list in files_by_source.items():
        print(f"Stacking {len(df_list)} files for source: {source}")
        # Stack rows (e.g. Jan + Dec)
        stacked_df = pd.concat(df_list, ignore_index=True)
        consolidated_dfs.append(stacked_df)

    # 3. Merge different sources (Horizontal Join)
    if consolidated_dfs:
        print("Merging different sources (Outer Join)...")
        final_df = reduce(
            lambda left, right: pd.merge(
                left, 
                right, 
                on=['date', '.geo'], 
                how='outer'
            ), 
            consolidated_dfs
        )
    else:
        print("No valid time-series data found.")
        return

    # 4. Create Partitions and Write
    print("Generating partitions and writing to disk...")
    final_df['year'] = final_df['date'].dt.year
    final_df['month'] = final_df['date'].dt.month

    final_df.to_parquet(
        output_path,
        partition_cols=['year', 'month'],
        engine='pyarrow',
        compression='snappy',
        index=False
    )
    print(f"Success! Data written to: {output_path}")

# --- Usage ---
# create_partitioned_dataset_grouped("raw_data/ROI_TEST")