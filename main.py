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
        print(
            "Service account file not found. Falling back to browser-based authentication."
        )
        ee.Authenticate()
        ee.Initialize()


def run_pipeline(
    roi_coords=None,
    project_name="default",
    start_date=None,
    end_date=None,
    progress_callback=None,
    cloud_threshold_s2=None,
    cloud_threshold_landsat=None,
    target_scale=None,
):
    """
    Run the SmartHarvest temporal pipeline.

    Args:
        roi_coords: GeoJSON polygon coordinates [[lon, lat], ...]
        project_name: Name for this analysis project
        start_date: Start of the analysis window (YYYY-MM-DD). If omitted,
            falls back to config.START_DATE — but callers are strongly
            encouraged to supply explicit dates. The default window in
            config is a Northern-hemisphere growing season (Jun–Sep) and
            is NOT appropriate for Southern-hemisphere or tropical ROIs.
        end_date: End of the analysis window (YYYY-MM-DD).
        progress_callback: Optional callable(str) for progress messages.
        cloud_threshold_s2: Override for config.CLOUD_THRESHOLD_S2 (%).
            Only scenes whose CLOUDY_PIXEL_PERCENTAGE is below this
            value make it past the download filter.
        cloud_threshold_landsat: Override for config.CLOUD_THRESHOLD_LANDSAT.
        target_scale: Override for config.TARGET_SCALE — master-grid cell
            size in metres (10 = Sentinel-2 native, 20 ≈ 4× fewer rows).
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

        # Validate and set ROI
        from modules.roi_validation import (
            ROIValidationError,
            validate_roi_coords,
        )

        try:
            raw_coords = roi_coords if roi_coords else config.ROI_COORDS
            validated = validate_roi_coords(
                raw_coords,
                max_area_ha=getattr(config, "MAX_ROI_AREA_HA", 10_000),
            )
            config.ROI = ee.Geometry.Polygon(validated)
        except ROIValidationError as ve:
            log(f"Invalid ROI: {ve}")
            raise

        area_sqm = config.ROI.area().getInfo()
        area_ha = area_sqm / 10000.0
        log(f"ROI Area: {area_ha:.2f} ha ({area_sqm:.0f} m²)")

        # Log centroid so users can sanity-check the geography in the report.
        try:
            centroid = config.ROI.centroid().coordinates().getInfo()
            log(f"ROI Centroid: lon={centroid[0]:.4f}, lat={centroid[1]:.4f}")
        except Exception:
            pass

        # Set analysis window (fall back to config defaults only if caller
        # supplied nothing — explicit is better than implicit).
        if start_date:
            config.START_DATE = start_date
        if end_date:
            config.END_DATE = end_date
        log(f"Analysis Window: {config.START_DATE} to {config.END_DATE}")

        # Per-run overrides for download-pipeline hyperparameters. The
        # sensor modules read these from the `config` module at call
        # time, so rebinding the attributes here is enough. We stash
        # the effective values so they get recorded in the metadata
        # alongside everything else about the run.
        if cloud_threshold_s2 is not None:
            config.CLOUD_THRESHOLD_S2 = int(cloud_threshold_s2)
        if cloud_threshold_landsat is not None:
            config.CLOUD_THRESHOLD_LANDSAT = int(cloud_threshold_landsat)
        if target_scale is not None:
            config.TARGET_SCALE = int(target_scale)
        log(
            "Hyperparameters: "
            f"cloud_s2={config.CLOUD_THRESHOLD_S2} "
            f"cloud_landsat={config.CLOUD_THRESHOLD_LANDSAT} "
            f"target_scale={config.TARGET_SCALE}m"
        )
        pipeline_hparams = {
            "source": "Hyperparameters",
            "cloud_threshold_s2": config.CLOUD_THRESHOLD_S2,
            "cloud_threshold_landsat": config.CLOUD_THRESHOLD_LANDSAT,
            "target_scale": config.TARGET_SCALE,
        }

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

        # Log the CRS so operators running the pipeline on new ROIs can see
        # which UTM zone GEE selected (useful when debugging cross-zone ROIs).
        try:
            crs_info = master_crs.getInfo()
            log(f"  -> Master CRS: {crs_info.get('crs', crs_info)}")
        except Exception:
            pass

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
        s2_fc, s1_fc, l8_fc, srtm_fc = assembly.create_temporal_samples(
            s2_col, s1_col, l8_col, srtm_img
        )
        monitor.stop_step("Assembly-Sampling")

        # 6. Download each satellite's data separately
        log("Downloading satellite data (separate per sensor)...")
        monitor.start_step("Download")
        csv_paths = assembly.download_satellite_data(
            s2_fc, s1_fc, l8_fc, srtm_fc, output_dir, project_name_safe
        )
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
            log(
                "Warning: Could not assemble full temporal dataset. Some satellite data may be missing."
            )

        # 8. Run ML Anomaly Detection (Integrated)
        # Must run BEFORE map generation so that
        # `create_verification_map` can pick up the `ml_weekly/` output
        # and register the "ML Clusters (<week>)" overlay in the map's
        # layer control. Otherwise a freshly-analysed project ends up
        # with no cluster layer in the dashboard map.
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
                visualize_data_map.create_verification_map(
                    merged_path, map_path, project_name=project_name_safe
                )
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
        # Persist the effective hyperparameters so the report / dashboard
        # can show what was actually used for this run (and so we have a
        # trail if the caller passes overrides via the Advanced panel).
        all_metadata.append(pipeline_hparams)

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
