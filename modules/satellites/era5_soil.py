import ee
import config
from utils import retrieve_sensor_data, filter_hour

def get_era5_data():

    try:

        era5 = retrieve_sensor_data('ECMWF/ERA5_LAND/HOURLY', config.ROI, config.START, config.END,
        seasonal_months=(config.SEASONAL_START_MONTH, config.SEASONAL_END_MONTH)
        )

    except Exception as e:
        print(f"Warning: era5 data not found or error loading collection ({e}). Using dummy data.")

    return era5
