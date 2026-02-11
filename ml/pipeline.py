"""
STEP 10: ML Pipeline Orchestrator - Weekly Clustering with Tracking
"""

import os
import pandas as pd
import numpy as np
from datetime import datetime

from . import data_loader, clustering, tracking, output
from modules import monitoring


def run_ml_pipeline(csv_path, output_base_dir, force_reprocess=False):
    """
    Main ML pipeline entrypoint.

    Args:
        csv_path: Path to SmartHarvest CSV
        output_base_dir: Base directory for ML outputs
        force_reprocess: If True, reprocess all weeks

    Returns:
        results: dict with summary of processing
    """
    print("\n" + "=" * 70)
    print("SMARTHARVEST ML KERNEL - WEEKLY CLUSTERING & TRACKING")
    print("=" * 70 + "\n")

    monitor = monitoring.PipelineMonitor(os.path.basename(output_base_dir), "ML")

    # STEP 1: Load and filter data
    print("\n[STEP 1] Loading CSV and filtering S2 data...")
    monitor.start_step("Data-Loading")
    df, columns = data_loader.load_and_filter_s2(csv_path)
    monitor.stop_step("Data-Loading", {"rows": len(df)})

    if len(df) == 0:
        print("[ERROR] No S2 data found in CSV!")
        return {"success": False, "error": "No S2 data"}

    # STEP 2: Define weekly timeline
    print("\n[STEP 2] Defining weekly timeline...")
    monitor.start_step("Timeline-Definition")
    weeks, df = data_loader.define_weeks(df, columns["date"])
    monitor.stop_step("Timeline-Definition", {"weeks_count": len(weeks)})

    if len(weeks) == 0:
        print("[ERROR] No weeks found in data!")
        return {"success": False, "error": "No weeks"}

    # Define ML output directory and state file
    ml_dir = os.path.join(output_base_dir, 'ml_weekly')
    state_file = os.path.join(ml_dir, 'tracking_state.json')

    # Load previous state (for tracking)
    prev_state = output.load_tracking_state(state_file) if not force_reprocess else None
    processed_weeks = (
        output.get_processed_weeks(ml_dir) if not force_reprocess else set()
    )

    # Determine which weeks to process
    # Always reprocess current week (last week in timeline)
    weeks_to_process = []
    for week_id, week_start, week_end, obs_count in weeks:
        if force_reprocess or week_id not in processed_weeks or week_id == weeks[-1][0]:
            weeks_to_process.append((week_id, week_start, week_end, obs_count))

    print(
        f"\n[Pipeline] Processing {len(weeks_to_process)} weeks (of {len(weeks)} total)"
    )

    # Initialize tracking
    prev_frame = None
    prev_labels = None
    prev_track_ids = {}
    next_track_id = prev_state["next_track_id"] if prev_state else 0

    if prev_state and not force_reprocess:
        prev_track_ids = {int(k): v for k, v in prev_state["track_ids"].items()}
        print(f"[Tracking] Resuming from week {prev_state['last_week']}")

    # Process weeks in chronological order
    results_summary = []

    for week_id, week_start, week_end, obs_count in weeks_to_process:
        print(f"\n{'='*70}")
        print(f"PROCESSING WEEK: {week_id} ({obs_count} observations)")
        print(f"{'='*70}")

        try:
            # STEP 3: Build weekly frame
            print(f"\n[STEP 3] Building weekly frame...")
            monitor.start_step(f"Week-{week_id}")
            frame = data_loader.build_weekly_frame(
                df, week_id, columns["coords"], columns["features"], columns["date"]
            )

            if frame is None or len(frame) < 10:
                print(f"[WARNING] Skipping {week_id} - insufficient data")
                continue

            # STEP 4: Normalize features
            print(f"\n[STEP 4] Normalizing features...")
            frame_norm, scaler, X_scaled = clustering.normalize_features(
                frame, columns["features"]
            )

            # STEP 5: Microclustering
            print(f"\n[STEP 5] Microclustering...")
            micro_labels, micro_centroids, micro_sizes = clustering.microclustering(
                X_scaled, frame
            )

            # STEP 6: HDBSCAN on microclusters
            print(f"\n[STEP 6] Running HDBSCAN...")
            cluster_labels_micro, outlier_scores_micro, clusterer = (
                clustering.hdbscan_clustering(micro_centroids, micro_sizes)
            )

            # Propagate to pixels
            cluster_labels, outlier_scores = clustering.propagate_to_pixels(
                micro_labels, cluster_labels_micro, outlier_scores_micro
            )

            # STEP 8: Tracking
            print(f"\n[STEP 8] Tracking clusters...")
            track_ids, tracking_info, next_track_id = tracking.track_clusters_simple(
                frame,
                prev_frame,
                cluster_labels,
                prev_labels,
                prev_track_ids,
                columns["coords"],
            )

            # STEP 9: Anomaly detection
            print(f"\n[STEP 9] Detecting anomalies...")
            anomalies, anomaly_summary = tracking.detect_anomalies(
                frame, cluster_labels, outlier_scores, track_ids
            )

            # STEP 7: Save outputs
            print(f"\n[STEP 7] Saving weekly outputs...")
            output_paths = output.save_weekly_outputs(
                week_id,
                frame,
                cluster_labels,
                outlier_scores,
                track_ids,
                ml_dir,
                columns["coords"],
                tracking_info,
            )

            # Save anomalies
            if len(anomaly_summary) > 0:
                anomaly_path = os.path.join(
                    output_paths["week_dir"], f"anomalies_{week_id}.csv"
                )
                anomaly_summary.to_csv(anomaly_path, index=False)

            # Save tracking state
            output.save_tracking_state(
                week_id, track_ids, tracking_info, next_track_id, state_file
            )

            monitor.stop_step(
                f"Week-{week_id}",
                {
                    "pixels": len(frame),
                    "clusters": len(set(cluster_labels))
                    - (1 if -1 in cluster_labels else 0),
                    "anomalies": len(anomaly_summary),
                },
            )

            # Store results
            results_summary.append(
                {
                    "week_id": week_id,
                    "pixels": len(frame),
                    "clusters": len(set(cluster_labels))
                    - (1 if -1 in cluster_labels else 0),
                    "noise_pixels": (cluster_labels == -1).sum(),
                    "anomalies": len(anomaly_summary),
                    "tracking": tracking_info,
                    "output_dir": output_paths["week_dir"],
                }
            )

            # Update prev state for next iteration
            prev_frame = frame
            prev_labels = cluster_labels
            prev_track_ids = track_ids

            print(f"\n[DONE] Week {week_id} completed successfully")

        except Exception as e:
            print(f"\n[ERROR] Failed to process week {week_id}: {e}")
            import traceback

            traceback.print_exc()
            continue

    # Final summary
    print("\n" + "=" * 70)
    print("PIPELINE COMPLETE")
    print("=" * 70)
    print(f"\nProcessed {len(results_summary)} weeks:")
    for r in results_summary:
        print(f"  {r['week_id']}: {r['clusters']} clusters, {r['anomalies']} anomalies")

    # Save summary
    summary_df = pd.DataFrame(results_summary)
    summary_path = os.path.join(ml_dir, "processing_summary.csv")
    summary_df.to_csv(summary_path, index=False)
    print(f"\nSummary saved to: {summary_path}")

    # Save Monitor
    monitor.save(ml_dir)

    # Return latest week result for integration
    if results_summary:
        latest = results_summary[-1]
        latest_cluster_csv = os.path.join(
            latest["output_dir"], f"cluster_map_{latest['week_id']}.csv"
        )

        return {
            "success": True,
            "weeks_processed": len(results_summary),
            "latest_week": latest["week_id"],
            "latest_cluster_map": latest_cluster_csv,
            "ml_dir": ml_dir,
            "summary": results_summary,
        }
    else:
        return {"success": False, "error": "No weeks were successfully processed"}
