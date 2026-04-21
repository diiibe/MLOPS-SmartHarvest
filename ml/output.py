"""
STEP 7: Weekly Output - Save images and tables
"""

import os
import numpy as np
import pandas as pd
import json
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from datetime import datetime


def save_weekly_outputs(
    week_id,
    frame,
    cluster_labels,
    outlier_scores,
    track_ids,
    output_dir,
    coord_cols,
    tracking_info=None,
):
    """
    Save weekly clustering results as images and tables.

    Outputs:
        - cluster_map_{week_id}.csv: pixel-level cluster labels
        - outlier_map_{week_id}.csv: pixel-level outlier scores
        - cluster_image_{week_id}.png: visual cluster map (if gridded)
        - outlier_image_{week_id}.png: visual outlier heatmap
    """
    week_dir = os.path.join(output_dir, "weekly", week_id)
    os.makedirs(week_dir, exist_ok=True)

    # Add results to frame
    result_frame = frame.copy()
    result_frame["cluster_label"] = cluster_labels
    result_frame["outlier_score"] = outlier_scores
    result_frame["track_id"] = [track_ids.get(c, -1) for c in cluster_labels]

    # Add cluster status (new/continued/lost)
    if tracking_info and "cluster_status" in tracking_info:
        cluster_status_map = tracking_info["cluster_status"]
        result_frame["cluster_status"] = [
            cluster_status_map.get(c, "unknown") for c in cluster_labels
        ]
    else:
        result_frame["cluster_status"] = "unknown"

    # Save pixel-level table
    cluster_csv = os.path.join(week_dir, f"cluster_map_{week_id}.csv")
    result_frame.to_csv(cluster_csv, index=False)

    # Outlier table (only high scores)
    outlier_csv = os.path.join(week_dir, f"outlier_map_{week_id}.csv")
    outlier_frame = result_frame[
        result_frame["outlier_score"] > np.percentile(outlier_scores, 90)
    ]
    outlier_frame.to_csv(outlier_csv, index=False)

    # Try to create images if we have lat/lon
    if "lat" in coord_cols and "lon" in coord_cols:
        _create_cluster_image(result_frame, week_id, week_dir)
        _create_outlier_image(result_frame, week_id, week_dir)

    print(f"[Output] Saved weekly results to {week_dir}")

    return {
        "cluster_csv": cluster_csv,
        "outlier_csv": outlier_csv,
        "week_dir": week_dir,
    }


def _create_cluster_image(df, week_id, output_dir):
    """Create visual cluster map."""
    try:
        fig, ax = plt.subplots(figsize=(10, 8), facecolor="#1a1a1a")

        # Scatter plot colored by cluster
        unique_clusters = df["cluster_label"].unique()
        colors = plt.cm.tab20(np.linspace(0, 1, len(unique_clusters)))

        for i, cluster in enumerate(unique_clusters):
            cluster_df = df[df["cluster_label"] == cluster]
            label = f"Cluster {cluster}" if cluster != -1 else "Noise"
            ax.scatter(
                cluster_df["lon"],
                cluster_df["lat"],
                c=[colors[i]],
                label=label,
                s=10,
                alpha=0.6,
            )

        ax.set_xlabel("Longitude", color="white")
        ax.set_ylabel("Latitude", color="white")
        ax.set_title(f"Cluster Map - {week_id}", color="white", fontsize=14)
        ax.set_facecolor("#2d2d2d")
        ax.tick_params(colors="white")
        ax.spines["bottom"].set_color("white")
        ax.spines["left"].set_color("white")
        ax.spines["top"].set_color("#2d2d2d")
        ax.spines["right"].set_color("#2d2d2d")

        # Legend (limit to 20 items)
        if len(unique_clusters) <= 20:
            ax.legend(
                loc="upper right",
                facecolor="#1a1a1a",
                edgecolor="white",
                labelcolor="white",
                fontsize=8,
            )

        plt.tight_layout()
        img_path = os.path.join(output_dir, f"cluster_image_{week_id}.png")
        plt.savefig(img_path, dpi=150, facecolor="#1a1a1a")
        plt.close()

    except Exception as e:
        print(f"[Output] Warning: Could not create cluster image: {e}")


def _create_outlier_image(df, week_id, output_dir):
    """Create visual outlier heatmap."""
    try:
        fig, ax = plt.subplots(figsize=(10, 8), facecolor="#1a1a1a")

        scatter = ax.scatter(
            df["lon"],
            df["lat"],
            c=df["outlier_score"],
            cmap="YlOrRd",
            s=10,
            alpha=0.7,
            vmin=0,
            vmax=df["outlier_score"].quantile(0.99),
        )

        cbar = plt.colorbar(scatter, ax=ax)
        cbar.set_label("Outlier Score", color="white")
        cbar.ax.yaxis.set_tick_params(color="white")
        plt.setp(plt.getp(cbar.ax.axes, "yticklabels"), color="white")

        ax.set_xlabel("Longitude", color="white")
        ax.set_ylabel("Latitude", color="white")
        ax.set_title(f"Outlier Map - {week_id}", color="white", fontsize=14)
        ax.set_facecolor("#2d2d2d")
        ax.tick_params(colors="white")
        ax.spines["bottom"].set_color("white")
        ax.spines["left"].set_color("white")
        ax.spines["top"].set_color("#2d2d2d")
        ax.spines["right"].set_color("#2d2d2d")

        plt.tight_layout()
        img_path = os.path.join(output_dir, f"outlier_image_{week_id}.png")
        plt.savefig(img_path, dpi=150, facecolor="#1a1a1a")
        plt.close()

    except Exception as e:
        print(f"[Output] Warning: Could not create outlier image: {e}")


def _convert_to_native(data):
    """
    Recursively convert numpy types to native Python types for JSON
    serialization. Also ensures dictionary keys are strings.
    """
    if isinstance(data, dict):
        return {str(k): _convert_to_native(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [_convert_to_native(i) for i in data]
    elif isinstance(data, np.integer):
        return int(data)
    elif isinstance(data, np.floating):
        return float(data)
    elif isinstance(data, np.ndarray):
        return _convert_to_native(data.tolist())
    else:
        return data


def save_tracking_state(
    week_id,
    track_ids,
    tracking_info,
    next_track_id,
    state_file,
    stats_history=None,
    anomaly_track_history=None,
):
    """
    Save persistent tracking state atomically.
    Ensures all data is JSON-compatible.

    `stats_history` (optional) is the rolling list of per-week feature
    means/stds used by the cross-week normalizer. Persisting it means an
    incremental run picks up the same reference the previous run was using,
    rather than re-fitting from scratch on whatever weeks happen to be
    reprocessed.

    `anomaly_track_history` (optional) is the rolling list of
    `set(track_id)` per week used by the persistence filter. Stored as a
    list of lists so JSON can serialize it.
    """
    serialized_anom_history = (
        [sorted(int(x) for x in window) for window in anomaly_track_history]
        if anomaly_track_history
        else []
    )
    state_raw = {
        "last_week": week_id,
        "track_ids": track_ids,
        "tracking_info": tracking_info,
        "next_track_id": next_track_id,
        "stats_history": stats_history or [],
        "anomaly_track_history": serialized_anom_history,
        "timestamp": datetime.now().isoformat(),
    }

    # Convert all to native types (including string keys)
    state = _convert_to_native(state_raw)

    os.makedirs(os.path.dirname(state_file), exist_ok=True)

    # Atomic write: write to temp file then rename
    temp_file = f"{state_file}.tmp"
    try:
        with open(temp_file, "w") as f:
            json.dump(state, f, indent=2)
        os.replace(temp_file, state_file)
        print(f"[State] Saved tracking state to {state_file} (atomic)")
    except Exception as e:
        if os.path.exists(temp_file):
            os.remove(temp_file)
        print(f"[State] Error saving state: {e}")


def load_tracking_state(state_file):
    """
    Load tracking state from previous run.
    Handles malformed or missing state files.
    """
    if not os.path.exists(state_file):
        return None

    try:
        with open(state_file, "r") as f:
            state = json.load(f)
        print(f"[State] Loaded tracking state from {state.get('last_week', 'unknown')}")
        return state
    except (json.JSONDecodeError, ValueError) as e:
        print(f"[State] Warning: Tracking state file is corrupted: {e}")
        return None
    except Exception as e:
        print(f"[State] Error loading state: {e}")
        return None


def get_processed_weeks(output_dir):
    """
    Get list of already processed weeks.
    """
    weekly_dir = os.path.join(output_dir, "weekly")
    if not os.path.exists(weekly_dir):
        return set()

    processed = set()
    for week_folder in os.listdir(weekly_dir):
        if week_folder.startswith("20"):  # Year-based week ID
            processed.add(week_folder)

    return processed


def load_previous_week_frame(output_dir, week_id):
    """
    Rehydrate (prev_frame, prev_labels) from a prior week's cluster_map CSV
    so that tracking survives across incremental pipeline runs.

    Returns (None, None) if the file is missing or malformed.
    """
    path = os.path.join(output_dir, "weekly", week_id, f"cluster_map_{week_id}.csv")
    if not os.path.exists(path):
        return None, None

    try:
        df = pd.read_csv(path)
    except Exception as e:
        print(f"[State] Could not load prev week '{week_id}': {e}")
        return None, None

    if "cluster_label" not in df.columns:
        return None, None

    labels = df["cluster_label"].to_numpy()
    frame = df.drop(
        columns=[
            c
            for c in ("cluster_label", "outlier_score", "track_id", "cluster_status")
            if c in df.columns
        ]
    )
    return frame, labels
