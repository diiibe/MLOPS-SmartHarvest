import config
import datetime
import calendar

from satellites.srtm import get_srtm
from satellites.sentinel1 import get_st1
from satellites.sentinel2 import get_st2
from utils import get_missing_partitions
from dateutil.relativedelta import relativedelta
from satellites.landsat_thermal import get_landsat



def run_pipeline(roi_coords=config.ROI_TEST, start_date=config.START, end_date=config.END, progress_callback=None):
    # roi_coord will be a json file path?

    # set_run_id = currnet_timestamp()
    roi_coords_name = config.roi_name
    
    dates_to_be_downloaded = get_missing_partitions(start_date, end_date, f'database/{roi_coords_name}')
    if roi_coords:
        if dates_to_be_downloaded or end_date == datetime.current():
    
            get_srtm(roi_coords, roi_coords_name)
            
            for i in dates_to_be_downloaded:
                download_start_date = i
                download_end_date = i + relativedelta(months=1, days=-1)
                get_st1(roi_coords, download_start_date, download_end_date, roi_coords_name)
                get_st2(roi_coords, download_start_date, download_end_date, roi_coords_name)
                get_landsat(roi_coords, download_start_date, download_end_date, roi_coords_name)

    else:
         print(f"Roi Coords not defined, please define them. Roi coord used {roi_coords}")

    # else:
    #     # return report using existing data


if __name__ == "__main__":
    run_pipeline()

