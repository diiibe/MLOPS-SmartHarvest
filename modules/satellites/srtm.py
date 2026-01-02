import ee
import config
import math

def get_srtm_data():

    try:
        srtm = ee.Image('USGS/SRTMGL1_003')
        
        # Clip on ROI extended buffer (100m) to avoid edge effects
        roi_buffer = config.ROI.buffer(100)
        srtm_clipped = srtm.clip(roi_buffer)
    
    except Exception as e:
        print(f"Warning: srtm data not found or error loading image ({e}). Using dummy data.")
    
    return srtm_clipped