"""
ML Report Utilities - Generate summary statistics for reporting
"""

import os
import pandas as pd
import numpy as np


def generate_ml_summary(ml_dir):
    """
    Generate ML summary statistics for inclusion in report.

    Args:
        ml_dir: Path to ml_weekly directory

    Returns:
        weekly_stats: DataFrame with weekly cluster statistics
        top_anomalies: DataFrame with top 5 anomalous clusters
    """
    weekly_dir = os.path.join(ml_dir, "weekly")

    if not os.path.exists(weekly_dir):
        return None, None

    week_folders = sorted([f for f in os.listdir(weekly_dir) if f.startswith("20")])

    if not week_folders:
        return None, None

    weekly_records = []
    all_anomalies = []

    for week_id in week_folders:
        week_path = os.path.join(weekly_dir, week_id)
        cluster_csv = os.path.join(week_path, f"cluster_map_{week_id}.csv")
        anomaly_csv = os.path.join(week_path, f"anomalies_{week_id}.csv")

        if not os.path.exists(cluster_csv):
            continue

        # Read cluster data
        cluster_df = pd.read_csv(cluster_csv)

        # Backward compatibility: add cluster_status if missing
        if "cluster_status" not in cluster_df.columns:
            cluster_df["cluster_status"] = "unknown"

        total_pixels = len(cluster_df)
        total_clusters = len(
            cluster_df[cluster_df["cluster_label"] != -1]["cluster_label"].unique()
        )

        # Anomalous clusters (outlier_score > 95th percentile)
        if "outlier_score" in cluster_df.columns:
            threshold = cluster_df["outlier_score"].quantile(0.95)
            anomalous_pixels = (cluster_df["outlier_score"] > threshold).sum()
            pixel_anomaly_pct = (
                (anomalous_pixels / total_pixels * 100) if total_pixels > 0 else 0
            )

            # Count anomalous clusters (clusters with mean outlier score > threshold)
            cluster_scores = (
                cluster_df[cluster_df["cluster_label"] != -1]
                .groupby("cluster_label")["outlier_score"]
                .mean()
            )
            anomalous_clusters = (cluster_scores > threshold).sum()
            anomaly_pct = (
                (anomalous_clusters / total_clusters * 100) if total_clusters > 0 else 0
            )
        else:
            anomalous_pixels = 0
            pixel_anomaly_pct = 0
            anomalous_clusters = 0
            anomaly_pct = 0

        weekly_records.append(
            {
                "week_id": week_id,
                "total_clusters": total_clusters,
                "anomalous_clusters": int(anomalous_clusters),
                "anomaly_pct": anomaly_pct,
                "total_pixels": total_pixels,
                "anomalous_pixels": anomalous_pixels,
                "pixel_anomaly_pct": pixel_anomaly_pct,
            }
        )

        # Collect anomalies for top list
        if os.path.exists(anomaly_csv):
            anom_df = pd.read_csv(anomaly_csv)
            anom_df["week_id"] = week_id
            all_anomalies.append(anom_df)

    if not weekly_records:
        return None, None

    weekly_stats = pd.DataFrame(weekly_records)

    # Top anomalies
    if all_anomalies:
        all_anom_df = pd.concat(all_anomalies, ignore_index=True)

        # Sort by outlier_score_mean descending
        if "outlier_score_mean" in all_anom_df.columns:
            top_anomalies = all_anom_df.nlargest(5, "outlier_score_mean")
        else:
            top_anomalies = all_anom_df.head(5)
    else:
        top_anomalies = pd.DataFrame()

    return weekly_stats, top_anomalies


def format_weekly_ml_table(weekly_stats):
    """
    Format weekly ML statistics as markdown table.

    Args:
        weekly_stats: DataFrame from generate_ml_summary

    Returns:
        str: Markdown table
    """
    if weekly_stats is None or len(weekly_stats) == 0:
        return "_No ML analysis data available._\n"

    table = "| Week | Total Clusters | Anomalous | Anomaly % | Total Pixels | Anomalous Pixels | Pixel Anomaly % |\n"
    table += "|------|----------------|-----------|-----------|--------------|------------------|------------------|\n"

    for _, row in weekly_stats.iterrows():
        table += (
            f"| {row['week_id']} | "
            f"{row['total_clusters']} | "
            f"{row['anomalous_clusters']} | "
            f"{row['anomaly_pct']:.1f}% | "
            f"{row['total_pixels']:,} | "
            f"{row['anomalous_pixels']:,} | "
            f"{row['pixel_anomaly_pct']:.1f}% |\n"
        )

    return table


def format_top_anomalies(top_anomalies):
    """
    Format top anomalous clusters as markdown list.

    Args:
        top_anomalies: DataFrame from generate_ml_summary

    Returns:
        str: Markdown list
    """
    if top_anomalies is None or len(top_anomalies) == 0:
        return "_No anomalous clusters detected._\n"

    output = ""
    for i, row in enumerate(top_anomalies.iterrows(), 1):
        _, r = row
        track_id = r.get("track_id", -1)
        cluster_label = r.get("cluster_label", -1)
        outlier_score = r.get("outlier_score_mean", 0)
        pixel_count = r.get("pixel_count", 0)
        week_id = r.get("week_id", "Unknown")

        # Get coordinates if available
        lat = r.get("centroid_lat", None)
        lon = r.get("centroid_lon", None)

        location_str = ""
        if lat is not None and lon is not None:
            location_str = f"{lat:.5f}°N, {lon:.5f}°E"
        else:
            location_str = "Coordinates unavailable"

        output += (
            f"{i}. **Week {week_id}, Cluster {cluster_label}** (Track ID: {track_id})\n"
            f"   - Outlier Score: {outlier_score:.3f}\n"
            f"   - Location: {location_str}\n"
            f"   - Pixels: {pixel_count}\n\n"
        )

    return output
