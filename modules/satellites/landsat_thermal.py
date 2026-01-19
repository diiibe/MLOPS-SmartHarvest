import ee
import config
from utils import retrieve_sensor_data, filter_hour

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