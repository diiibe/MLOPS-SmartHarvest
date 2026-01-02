import ee
import config
from utils import retrieve_sensor_data, filter_hour

def get_sentinel2_data():

    try:
        s2_full = retrieve_sensor_data('COPERNICUS/S2_SR_HARMONIZED', config.ROI, config.DATE_T1_START, config.DATE_T2_END, # Using specific dates
            cloud_max=config.CLOUD_THRESH
        )
    
    except Exception as e:
        print(f"Warning: sentinel2 data not found or error loading collection ({e}). Using dummy data.")
    
    return s2_full
