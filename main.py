import ee
import config
import os
from modules import sentinel2, srtm, sentinel1, landsat_thermal, assembly, reporting


def run_pipeline(roi_coords=None, project_name="default",
                 start_date="2024-06-01", end_date="2024-09-01",
                 progress_callback=None):
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

    try:
        ee.Initialize()

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

        output_dir = os.path.join('output', project_name_safe)
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
        s2_col, master_crs, s2_meta = sentinel2.get_sentinel2_data()
        all_metadata.append(s2_meta)
        log(f"  -> {s2_meta['image_count']} S2 images found.")

        # 2. SRTM (static topo)
        log("Processing SRTM (Topography)...")
        srtm_img, srtm_meta = srtm.get_srtm_data(master_crs)
        all_metadata.append(srtm_meta)

        # 3. Sentinel-1
        log("Processing Sentinel-1 (Radar)...")
        s1_col, s1_meta = sentinel1.get_sentinel1_data(master_crs)
        all_metadata.append(s1_meta)
        log(f"  -> {s1_meta['image_count']} S1 images found.")

        # 4. Landsat Thermal
        log("Processing Landsat Thermal...")
        l8_col, l8_meta = landsat_thermal.get_landsat_thermal(master_crs)
        all_metadata.append(l8_meta)
        log(f"  -> {l8_meta['image_count']} Landsat images found.")

        # 5. Create temporal FeatureCollections (GEE-side sampling)
        log("Creating temporal sample collections...")
        s2_fc, s1_fc, l8_fc, srtm_fc = assembly.create_temporal_samples(
            s2_col, s1_col, l8_col, srtm_img
        )

        # 6. Download each satellite's data separately
        log("Downloading satellite data (separate per sensor)...")
        csv_paths = assembly.download_satellite_data(
            s2_fc, s1_fc, l8_fc, srtm_fc, output_dir, project_name_safe
        )

        # 7. Merge into final temporal CSV
        final_csv_name = f'SmartHarvest_{project_name_safe}.csv'
        final_csv_path = os.path.join(output_dir, final_csv_name)

        merged_path = assembly.build_temporal_csv(csv_paths, final_csv_path)

        if merged_path:
            log(f"[OK] Temporal dataset assembled: {merged_path}")
        else:
            log("Warning: Could not assemble full temporal dataset. Some satellite data may be missing.")

        # 8. Generate map
        if merged_path and os.path.exists(merged_path):
            log("Generating verification map...")
            try:
                from tools import visualize_data_map
                map_filename = f'Map_{project_name_safe}.html'
                map_path = os.path.join(output_dir, map_filename)
                visualize_data_map.create_verification_map(merged_path, map_path)
                log(f"[OK] Map saved to: {map_path}")
            except Exception as e:
                log(f"Warning: Map generation failed: {e}")

        # 10. Generate acquisition log and report
        log("Generating Acquisition Log and Report...")
        area_stats = {
            'source': 'ROI Stats',
            'area_ha': area_ha,
            'area_sqm': area_sqm,
            'analysis_range': f"{config.START_DATE} to {config.END_DATE}"
        }
        all_metadata.insert(0, area_stats)

        report_filename = f'Report_{project_name_safe}.md'
        report_path = os.path.join(output_dir, report_filename)
        acq_log_path = os.path.join(output_dir, 'acquisition_log.txt')
        ml_dir = os.path.join(output_dir, 'ml_weekly')

        saved_report_path = reporting.generate_report(
            all_metadata,
            csv_path=merged_path,
            output_path=report_path,
            acq_log_path=acq_log_path,
            ml_dir=ml_dir if os.path.exists(ml_dir) else None
        )
        log(f"[OK] Report saved to: {saved_report_path}")

        # 11. Save metadata JSON
        import json
        metadata_filename = f'metadata_{project_name_safe}.json'
        metadata_path = os.path.join(output_dir, metadata_filename)
        with open(metadata_path, 'w') as f:
            json.dump(all_metadata, f, indent=4)

        # 12. Validate pipeline output
        log("Running validation checks...")
        try:
            from tools.validate_pipeline import PipelineValidator
            validator = PipelineValidator(project_name_safe)
            validation_success = validator.run_validation()
            if not validation_success:
                log("⚠️  Validation found issues - check output above")
        except Exception as e:
            log(f"Warning: Validation check failed: {e}")

        return {
            'csv_path': merged_path or final_csv_path,
            'report_path': saved_report_path,
            'output_dir': output_dir,
            'metadata_path': metadata_path,
            'metadata': all_metadata,
            'project_name_safe': project_name_safe,
            'available_dates': _get_available_dates(merged_path)
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
        df = pd.read_csv(csv_path, usecols=['date'])
        return sorted(df['date'].dropna().unique().tolist())
    except Exception:
        return []


if __name__ == "__main__":
    run_pipeline()
