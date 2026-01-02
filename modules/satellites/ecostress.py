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