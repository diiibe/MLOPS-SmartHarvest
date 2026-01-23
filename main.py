import config
from satellites.sentinel1 import get_st1
from satellites.sentinel2 import get_st2
from utils import get_missing_partitions
from dateutil.relativedelta import relativedelta
from satellites.landsat_thermal import get_landsat

import datetime
import calendar


def run_pipeline(roi_coords=None, start_date=config.START, end_date=config.END, progress_callback=None):

    dates_to_be_downloaded = get_missing_partitions(start_date, end_date, 'database')
    if dates_to_be_downloaded:
        for i in dates_to_be_downloaded:
            download_start_date = i
            download_end_date = i + relativedelta(months=1, days=-1)

            get_st1(roi_coords, download_start_date, download_end_date)

            )
if __name__ == "__main__":
    run_pipeline()

