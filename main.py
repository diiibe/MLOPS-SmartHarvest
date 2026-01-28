import config
import datetime
import calendar

from satellites.srtm import get_srtm
from satellites.sentinel1 import get_st1
from satellites.sentinel2 import get_st2
from utils import get_missing_partitions, create_partitioned_dataset
from dateutil.relativedelta import relativedelta
from satellites.landsat_thermal import get_landsat


def run_pipeline(roi_coords=config.ROI_TEST, start_date=config.START, end_date=config.END, progress_callback=None):
    # roi_coord will be a json file path?

    # set_run_id = currnet_timestamp()
    roi_coords_name = config.roi_name

    dates_to_be_downloaded = get_missing_partitions(start_date, end_date, f"database/{roi_coords_name}")
    if roi_coords:
        if dates_to_be_downloaded or end_date == datetime.date.today():

            get_srtm(roi_coords, roi_coords_name)

            for i in dates_to_be_downloaded:
                download_start_date = i
                if download_start_date == datetime.date.today().replace(day=1):
                    download_end_date = datetime.date.today()
                else:
                    download_end_date = i + relativedelta(months=1, days=-1)
                get_st1(roi_coords, download_start_date, download_end_date, roi_coords_name)
                get_st2(roi_coords, download_start_date, download_end_date, roi_coords_name)
                get_landsat(roi_coords, download_start_date, download_end_date, roi_coords_name)

    else:
        print(f"Roi Coords not defined, please define them. Roi coord used {roi_coords}")

    # else:
    #     # return report using existing data
    # --- TRACEABILITY & METADATA (Gate A) ---
    import json
    import hashlib
    import os
    from modules.exports import generate_all_exports

    # 1. Generate Run ID
    run_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # 2. Define Output Folder
    # Using 'output/runs/{run_id}' for traceability artifacts
    # (Data remains in raw_data/database as per logic, or could be moved here if desired)
    run_dir = os.path.join("output", "runs", run_id)
    os.makedirs(run_dir, exist_ok=True)
    
    print(f"Run ID: {run_id}")
    print(f"Run Traceability Directory: {run_dir}")

    # 3. Snapshot Configuration
    config_dict = {k: v for k, v in vars(config).items() if not k.startswith("__")}
    # Serialize non-serializable objects (like functions/classes) to string if needed
    # For now, assuming simple config.
    config_snapshot_path = os.path.join(run_dir, "config_snapshot.json")
    
    try:
        with open(config_snapshot_path, "w") as f:
            json.dump(config_dict, f, default=str, indent=4)
        
        # Calculate SHA256 of the snapshot
        with open(config_snapshot_path, "rb") as f:
            config_hash = hashlib.sha256(f.read()).hexdigest()
            
    except Exception as e:
        print(f"Warning: Could not save config snapshot: {e}")
        config_hash = "ERROR"

    # --- GATE B: EXPORTS ---
    # Trigger exports only if successful so far (which we assume if we are here)
    print("Generating Gate B Artifacts...")
    export_paths = generate_all_exports(run_dir, run_id, config_dict)
    
    # 4. Generate Run Manifest
    manifest = {
        "run_id": run_id,
        "status": "SUCCESS", # Assuming if we reached here, it didn't crash
        "timestamp": datetime.datetime.now().isoformat(),
        "config_snapshot_path": f"runs/{run_id}/config_snapshot.json",
        "config_snapshot_sha256": config_hash,
        "policy": {
            "confirmation": {
                "coherence_min": config.CONFIRM_COHERENCE_MIN,
                "persistence_min": config.CONFIRM_PERSISTENCE_MIN
            }
        },
        "stages": {
            "extraction": "SUCCESS", # Implicit
            "partitioning": "SUCCESS"
        },
        "artifacts": {
            "pdf_report": {
                "path": os.path.relpath(export_paths["pdf_report"], start="output"), 
                "type": "pdf"
            },
            "macro_anomaly_report": {
                "path": os.path.relpath(export_paths["macro_anomaly_report"], start="output"), 
                "type": "csv"
            },
            "anomaly_heatmap": {
                "path": os.path.relpath(export_paths["anomaly_heatmap"], start="output"), 
                "type": "geojson"
            },
            "coverage_reliability_report": {
                "path": os.path.relpath(export_paths["coverage_reliability_report"], start="output"), 
                "type": "csv"
            }
        }
    }
    
    manifest_path = os.path.join(run_dir, "run_manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=4)
        
    print(f"Run Manifest created: {manifest_path}")

if __name__ == "__main__":
    run_pipeline()
