"""
STEP 8-9: Temporal Tracking + Anomaly Detection
"""

import numpy as np
import pandas as pd
from scipy.spatial.distance import cdist


def track_clusters_simple(
    current_frame, prev_frame, current_labels, prev_labels, prev_track_ids, coord_cols
):
    """
    STEP 8: Simple tracking between consecutive weeks.

    Strategy: Match clusters by pixel overlap (majority vote).

    Args:
        current_frame: current week pixel data
        prev_frame: previous week pixel data
        current_labels: cluster labels for current week
        prev_labels: cluster labels for previous week
        prev_track_ids: track IDs from previous week
        coord_cols: coordinate column names

    Returns:
        track_ids: persistent track ID for each current cluster
        tracking_info: dict with tracking statistics
    """
    if prev_frame is None or len(prev_frame) == 0:
        # First week - assign new track IDs
        unique_clusters = [c for c in np.unique(current_labels) if c != -1]
        track_ids = {
            c: c for c in unique_clusters
        }  # cluster_id = track_id for first week
        cluster_status = {c: "new" for c in unique_clusters}
        next_track_id = max(unique_clusters) + 1 if unique_clusters else 0

        print(f"[Tracking] First week: {len(unique_clusters)} new tracks")

        tracking_info = {
            "new": len(unique_clusters),
            "continued": 0,
            "lost": 0,
            "cluster_status": cluster_status,
        }

        return track_ids, tracking_info, next_track_id

    # Find spatial overlap between weeks
    # Use spatial_id or lat/lon for matching
    if "spatial_id" in coord_cols:
        match_col = "spatial_id"
    else:
        # Create temp pixel ID
        current_frame["_pixel_id"] = (
            current_frame["lat"].round(6).astype(str)
            + "_"
            + current_frame["lon"].round(6).astype(str)
        )
        prev_frame["_pixel_id"] = (
            prev_frame["lat"].round(6).astype(str)
            + "_"
            + prev_frame["lon"].round(6).astype(str)
        )
        match_col = "_pixel_id"

    # Build mapping: pixel -> cluster for both weeks
    current_pixel_cluster = dict(zip(current_frame[match_col], current_labels))
    prev_pixel_cluster = dict(zip(prev_frame[match_col], prev_labels))
    prev_pixel_track = dict(
        zip(prev_frame[match_col], [prev_track_ids.get(c, -1) for c in prev_labels])
    )

    # Find overlapping pixels
    overlap_pixels = set(current_pixel_cluster.keys()) & set(prev_pixel_cluster.keys())

    # Pre-compute prev track sizes (for IoU denominator)
    prev_track_sizes = {}
    for track_id in prev_pixel_track.values():
        if track_id != -1:
            prev_track_sizes[track_id] = prev_track_sizes.get(track_id, 0) + 1

    # For each current cluster, find best match with previous clusters using IoU
    unique_current = [c for c in np.unique(current_labels) if c != -1]
    track_ids = {}
    # Score each (curr_cluster, prev_track) candidate, then greedy-assign best-first
    # to prevent two current clusters from claiming the same prev track (split bug).
    candidates = []  # (iou, curr_cluster, prev_track)

    for curr_cluster in unique_current:
        curr_pixels = [p for p, c in current_pixel_cluster.items() if c == curr_cluster]
        curr_size = len(curr_pixels)
        curr_overlap = [p for p in curr_pixels if p in overlap_pixels]

        if len(curr_overlap) == 0:
            continue

        prev_tracks_overlap = [
            prev_pixel_track[p] for p in curr_overlap if prev_pixel_track[p] != -1
        ]
        if not prev_tracks_overlap:
            continue

        # Count overlap per prev track; compute IoU = inter / (|curr| + |prev_track| - inter)
        prev_track_counts = pd.Series(prev_tracks_overlap).value_counts()
        for prev_track, inter in prev_track_counts.items():
            prev_sz = prev_track_sizes.get(prev_track, 0)
            denom = curr_size + prev_sz - inter
            if denom <= 0:
                continue
            iou = inter / denom
            candidates.append((iou, curr_cluster, int(prev_track)))

    # Greedy: highest IoU first, each curr_cluster and each prev_track matched at most once
    candidates.sort(key=lambda x: (-x[0], x[1], x[2]))
    matched_prev_tracks = set()
    IOU_THRESHOLD = 0.30
    for iou, curr_cluster, prev_track in candidates:
        if iou < IOU_THRESHOLD:
            break
        if curr_cluster in track_ids:
            continue
        if prev_track in matched_prev_tracks:
            continue
        track_ids[curr_cluster] = prev_track
        matched_prev_tracks.add(prev_track)

    # Unmatched current clusters (no IoU >= threshold or prev_track already taken)
    for curr_cluster in unique_current:
        if curr_cluster not in track_ids:
            track_ids[curr_cluster] = None

    # Assign new track IDs for unmatched clusters
    next_track_id = (
        max(
            max(prev_track_ids.values()) if prev_track_ids else 0,
            max([t for t in track_ids.values() if t is not None], default=0),
        )
        + 1
    )

    # Track cluster status (new/continued/lost)
    cluster_status = {}
    new_tracks = 0

    for cluster, track_id in track_ids.items():
        if track_id is None:
            # Assign new track ID
            track_ids[cluster] = next_track_id
            cluster_status[cluster] = "new"
            next_track_id += 1
            new_tracks += 1
        elif track_id in matched_prev_tracks:
            cluster_status[cluster] = "continued"
        else:
            # Edge case: track_id assigned but not in matched_prev_tracks
            cluster_status[cluster] = "new"

    # Statistics
    continued_tracks = len([s for s in cluster_status.values() if s == "continued"])
    lost_tracks = len(
        [t for t in prev_track_ids.values() if t not in track_ids.values() and t != -1]
    )

    print(
        f"[Tracking] Continued: {continued_tracks}, New: {new_tracks}, Lost: {lost_tracks}"
    )

    tracking_info = {
        "new": new_tracks,
        "continued": continued_tracks,
        "lost": lost_tracks,
        "cluster_status": cluster_status,  # cluster_label -> 'new'/'continued'
    }

    return track_ids, tracking_info, next_track_id


def detect_anomalies(
    frame, cluster_labels, outlier_scores, track_ids, micro_outlier_scores=None
):
    """
    STEP 9: Simple anomaly detection based on outlier scores.

    Threshold source:
      - If `micro_outlier_scores` is provided, the 95th percentile is computed
        on microcluster-level scores (unduplicated). This avoids the bias where
        large microclusters dominate the pixel-level distribution and crowd out
        genuine small-cluster outliers.
      - Otherwise, fall back to the per-pixel `outlier_scores`.

    Returns:
        anomalies, anomaly_summary: two DataFrames (possibly empty).
    """
    scores_for_threshold = (
        np.asarray(micro_outlier_scores)
        if micro_outlier_scores is not None
        else np.asarray(outlier_scores)
    )

    # Degenerate inputs: constant scores or all-zero → no meaningful anomalies
    if scores_for_threshold.size == 0 or np.allclose(
        scores_for_threshold, scores_for_threshold.flat[0]
    ):
        print("[Anomaly Detection] Scores are constant — no anomalies detected")
        return pd.DataFrame(), pd.DataFrame()

    score_threshold = np.percentile(scores_for_threshold, 95)

    # Use >= so ties at the 95th percentile still trigger; avoids "no anomalies
    # detected" when the top 5 % is tied (common with propagated micro-scores).
    anomaly_mask = np.asarray(outlier_scores) >= score_threshold

    if anomaly_mask.sum() == 0:
        print("[Anomaly Detection] No anomalies detected")
        return pd.DataFrame(), pd.DataFrame()

    # Build anomaly dataframe
    anomalies = frame[anomaly_mask].copy()
    anomalies["cluster_label"] = cluster_labels[anomaly_mask]
    anomalies["outlier_score"] = np.asarray(outlier_scores)[anomaly_mask]
    anomalies["track_id"] = [track_ids.get(c, -1) for c in anomalies["cluster_label"]]

    # Group by cluster/track
    anomaly_summary = (
        anomalies.groupby("track_id")
        .agg({"outlier_score": "mean", "cluster_label": "first"})
        .reset_index()
    )

    anomaly_summary = anomaly_summary[
        anomaly_summary["track_id"] != -1
    ]  # Exclude noise

    print(f"[Anomaly Detection] Found {len(anomaly_summary)} anomalous clusters")

    return anomalies, anomaly_summary
