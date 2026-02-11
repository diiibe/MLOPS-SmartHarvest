import os
import ee
import config

from google.oauth2 import service_account
from modules import (
    sentinel2,
    srtm,
    sentinel1,
    landsat_thermal,
    assembly,
    reporting,
    monitoring,
)
from ml.pipeline import run_ml_pipeline


def create_conn_ee():
    cred = "google_cred.json"
    if os.path.exists(cred):
        print(f"Connecting to Earth Engine using service account: {cred}")
        credentials = service_account.Credentials.from_service_account_file(
            cred,
            scopes=[
                "https://www.googleapis.com/auth/drive",
                "https://www.googleapis.com/auth/earthengine",
            ],
        )
        ee.Initialize(credentials=credentials)
    else:
        print("Service account file not found. Falling back to browser-based authentication.")
        ee.Authenticate()
        ee.Initialize()


def run_pipeline(
    roi_coords=None,
    project_name="default",
    start_date="2024-06-01",
    end_date="2024-09-01",
    progress_callback=None,
):
    """
    Run the SmartHarvest temporal pipeline.

    Args:
        roi_coords: GeoJSON polygon coordinates [[lon, lat], ...]
        project_name: Name for this analysis project
        start_date: Start of the analysis window (YYYY-MM-DD)
        end_date: End of the analysis window (YYYY-MM-DD)
        progress_callback: Optional callable(str) for progress messages
    Returns:
        dict with output paths, or None on failure
    """

    def log(message):
        print(message)
        if progress_callback:
            progress_callback(message)

    project_name_safe = project_name.replace(" ", "_")
    log(f"Initializing Pipeline for project: {project_name} ({project_name_safe})...")

    monitor = monitoring.PipelineMonitor(project_name_safe, "CORE")

    try:
        create_conn_ee()
        # ee.Initialize()

        # Set ROI
        if roi_coords:
            config.ROI = ee.Geometry.Polygon(roi_coords)
        else:
            config.ROI = ee.Geometry.Polygon(config.ROI_COORDS)

        area_sqm = config.ROI.area().getInfo()
        area_ha = area_sqm / 10000.0
        log(f"ROI Area: {area_ha:.2f} ha ({area_sqm:.0f} m²)")

        # Set analysis window
        config.START_DATE = start_date
        config.END_DATE = end_date
        log(f"Analysis Window: {config.START_DATE} to {config.END_DATE}")

        output_dir = os.path.join("output", project_name_safe)
        os.makedirs(output_dir, exist_ok=True)

    except Exception as e:
        log("Authentication failed. Please check GEE credentials.")
        print(f"Error: {e}")
        return None

    log("Starting SmartHarvest Temporal Pipeline...")
    all_metadata = []

    try:
        # 1. Sentinel-2
        log("Processing Sentinel-2 (Master Layer)...")
        monitor.start_step("Sentinel-2")
        s2_col, master_crs, s2_meta = sentinel2.get_sentinel2_data()
        monitor.stop_step("Sentinel-2", {"image_count": s2_meta.get("image_count", 0)})
        all_metadata.append(s2_meta)
        log(f"  -> {s2_meta['image_count']} S2 images found.")

        # 2. SRTM (static topo)
        log("Processing SRTM (Topography)...")
        monitor.start_step("SRTM")
        srtm_img, srtm_meta = srtm.get_srtm_data(master_crs)
        monitor.stop_step("SRTM")
        all_metadata.append(srtm_meta)

        # 3. Sentinel-1
        log("Processing Sentinel-1 (Radar)...")
        monitor.start_step("Sentinel-1")
        s1_col, s1_meta = sentinel1.get_sentinel1_data(master_crs)
        monitor.stop_step("Sentinel-1", {"image_count": s1_meta.get("image_count", 0)})
        all_metadata.append(s1_meta)
        log(f"  -> {s1_meta['image_count']} S1 images found.")

        # 4. Landsat Thermal
        log("Processing Landsat Thermal...")
        monitor.start_step("Landsat")
        l8_col, l8_meta = landsat_thermal.get_landsat_thermal(master_crs)
        monitor.stop_step("Landsat", {"image_count": l8_meta.get("image_count", 0)})
        all_metadata.append(l8_meta)
        log(f"  -> {l8_meta['image_count']} Landsat images found.")

        # 5. Create temporal FeatureCollections (GEE-side sampling)
        log("Creating temporal sample collections...")
        monitor.start_step("Assembly-Sampling")
        s2_fc, s1_fc, l8_fc, srtm_fc = assembly.create_temporal_samples(s2_col, s1_col, l8_col, srtm_img)
        monitor.stop_step("Assembly-Sampling")

        # 6. Download each satellite's data separately
        log("Downloading satellite data (separate per sensor)...")
        monitor.start_step("Download")
        csv_paths = assembly.download_satellite_data(s2_fc, s1_fc, l8_fc, srtm_fc, output_dir, project_name_safe)
        monitor.stop_step("Download")

        # 7. Merge into final temporal CSV
        log("Merging temporal CSV...")
        monitor.start_step("Merge")
        final_csv_name = f"SmartHarvest_{project_name_safe}.csv"
        final_csv_path = os.path.join(output_dir, final_csv_name)

        merged_path = assembly.build_temporal_csv(csv_paths, final_csv_path)
        monitor.stop_step("Merge")

        if merged_path:
            log(f"[OK] Temporal dataset assembled: {merged_path}")
        else:
            log("Warning: Could not assemble full temporal dataset. Some satellite data may be missing.")

        # 8. Generate map
        if merged_path and os.path.exists(merged_path):
            log("Generating verification map...")
            monitor.start_step("Map")
            try:
                from tools import visualize_data_map

                map_filename = f"Map_{project_name_safe}.html"
                map_path = os.path.join(output_dir, map_filename)
                visualize_data_map.create_verification_map(merged_path, map_path)
                log(f"[OK] Map saved to: {map_path}")
            except Exception as e:
                log(f"Warning: Map generation failed: {e}")
            monitor.stop_step("Map")

        # 9. Run ML Anomaly Detection (Integrated)
        if merged_path and os.path.exists(merged_path):
            log("Running ML Anomaly Detection...")
            monitor.start_step("ML-Analysis")
            try:
                ml_result = run_ml_pipeline(merged_path, output_dir)
                if ml_result.get("success"):
                    log(f"[OK] ML Analysis complete for {ml_result['latest_week']}")
                else:
                    log(f"Warning: ML Analysis failed: {ml_result.get('error')}")
            except Exception as e:
                log(f"Warning: ML Analysis error: {e}")
            monitor.stop_step("ML-Analysis")

        # 9. Generate map
        if merged_path and os.path.exists(merged_path):
            log("Generating verification map...")
            monitor.start_step("Map")
            try:
                from tools import visualize_data_map

                map_filename = f"Map_{project_name_safe}.html"
                map_path = os.path.join(output_dir, map_filename)
                visualize_data_map.create_verification_map(merged_path, map_path)
                log(f"[OK] Map saved to: {map_path}")
            except Exception as e:
                log(f"Warning: Map generation failed: {e}")
            monitor.stop_step("Map")

        # 10. Generate acquisition log and report
        log("Generating Acquisition Log and Report...")
        area_stats = {
            "source": "ROI Stats",
            "area_ha": area_ha,
            "area_sqm": area_sqm,
            "analysis_range": f"{config.START_DATE} to {config.END_DATE}",
        }
        all_metadata.insert(0, area_stats)

        report_filename = f"Report_{project_name_safe}.md"
        report_path = os.path.join(output_dir, report_filename)
        acq_log_path = os.path.join(output_dir, "acquisition_log.txt")
        ml_dir = os.path.join(output_dir, "ml_weekly")

        monitor.start_step("Report")
        saved_report_path = reporting.generate_report(
            all_metadata,
            csv_path=merged_path,
            output_path=report_path,
            acq_log_path=acq_log_path,
            ml_dir=ml_dir if os.path.exists(ml_dir) else None,
        )
        monitor.stop_step("Report")
        log(f"[OK] Report saved to: {saved_report_path}")

        # 11. Save metadata JSON
        import json

        metadata_filename = f"metadata_{project_name_safe}.json"
        metadata_path = os.path.join(output_dir, metadata_filename)
        with open(metadata_path, "w") as f:
            json.dump(all_metadata, f, indent=4)

        # 12. Validate pipeline output
        log("Running validation checks...")
        monitor.start_step("Validation")
        try:
            from tools.validate_pipeline import PipelineValidator

            validator = PipelineValidator(project_name_safe)
            validation_success = validator.run_validation()
            if not validation_success:
                log("⚠️  Validation found issues - check output above")
        except Exception as e:
            log(f"Warning: Validation check failed: {e}")
        monitor.stop_step("Validation")

        # Save Monitoring Log
        monitor.save(output_dir)

        return {
            "csv_path": merged_path or final_csv_path,
            "report_path": saved_report_path,
            "output_dir": output_dir,
            "metadata_path": metadata_path,
            "metadata": all_metadata,
            "project_name_safe": project_name_safe,
            "available_dates": _get_available_dates(merged_path),
        }

    except Exception as e:
        print(f"An error occurred during pipeline execution: {e}")
        import traceback

        traceback.print_exc()
        raise e


def _get_available_dates(csv_path):
    """Extract sorted list of unique dates from the temporal CSV."""
    if not csv_path or not os.path.exists(csv_path):
        return []
    try:
        import pandas as pd

        df = pd.read_csv(csv_path, usecols=["date"])
        return sorted(df["date"].dropna().unique().tolist())
    except Exception:
        return []


if __name__ == "__main__":
    run_pipeline()
