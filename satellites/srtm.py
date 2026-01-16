import ee
import config
import requests
from utils import create_conn_ee
from modules.satellites_data_extraction import get_srtm_data

def get_srtm(ROI=config.ROI_TEST, start_date=config.START, end_date=config.END):

    create_conn_ee()
    srtm = get_srtm_data(ROI, start_date, end_date)

    elevation = srtm.select('elevation')
    slope = ee.Terrain.slope(elevation).rename('Slope')
    aspect = ee.Terrain.aspect(elevation) # Keep for internal calc, don't export raw

    return srtm


