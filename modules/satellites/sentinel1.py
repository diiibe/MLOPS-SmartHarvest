import ee
import config
from utils import retrieve_sensor_data, filter_hour

def get_sentinel1_data():

    try:
        # 1. Query & Filter (Full Range)
        s1_full = retrieve_sensor_data('COPERNICUS/S1_GRD', config.ROI, config.T1_START, config.T2_END, 
            s1_pol=['VV', 'VH'],
            s1_mode='IW',
            s1_orbit='ASCENDING'
        )

    except Exception as e:
        print(f"Warning: sentinel1 data not found or error loading collection ({e}). Using dummy data.")
    
    return s1_full
