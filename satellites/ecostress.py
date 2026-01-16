from utils import create_conn_ee
from modules.satellites_data_extraction import get_ecostress_data

def get_ecostress(ROI=config.ROI_TEST, start_date=config.T1_START, end_date=config.T2_END):

    create_conn_ee()
    ecostress_data = get_ecostress_data(start_date='2018-01-01', end_date='2026-01-15')

    return ecostress_data
