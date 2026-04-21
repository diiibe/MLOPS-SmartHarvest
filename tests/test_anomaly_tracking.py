"""Regression tests for the fixes in ml/tracking.py."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ml.tracking import detect_anomalies, track_clusters_simple


# ---------------------------------------------------------------------------
# detect_anomalies: must always return a 2-tuple, even when degenerate.
# ---------------------------------------------------------------------------

def test_detect_anomalies_returns_tuple_when_empty_scores():
    frame = pd.DataFrame({"lat": [46.0], "lon": [13.0], "spatial_id": ["a"]})
    result = detect_anomalies(frame, np.array([0]), np.array([0.0]), {0: 0})
    assert isinstance(result, tuple) and len(result) == 2


def test_detect_anomalies_returns_tuple_on_constant_scores():
    # All pixels share the same outlier score → no threshold can pick a "top 5%".
    # Previous code returned a single DataFrame here, which blew up pipeline.py
    # when it tried to unpack.
    frame = pd.DataFrame({"lat": [46.0] * 10, "lon": [13.0] * 10})
    labels = np.zeros(10, dtype=int)
    scores = np.full(10, 0.5)
    anomalies, summary = detect_anomalies(frame, labels, scores, {0: 0})
    assert isinstance(anomalies, pd.DataFrame)
    assert isinstance(summary, pd.DataFrame)
    assert len(summary) == 0


def test_detect_anomalies_threshold_is_inclusive():
    # Scores with ties at the 95th percentile should still flag pixels (>=, not >).
    frame = pd.DataFrame({"lat": [46.0] * 20, "lon": [13.0] * 20})
    labels = np.zeros(20, dtype=int)
    scores = np.array([0.0] * 19 + [1.0])  # p95 ≈ 1.0, only one pixel at that score
    _, summary = detect_anomalies(frame, labels, scores, {0: 10})
    assert len(summary) >= 1, "inclusive threshold should catch top-of-range ties"


# ---------------------------------------------------------------------------
# track_clusters_simple: split case must not collapse two current clusters
# onto the same prev track id.
# ---------------------------------------------------------------------------

def test_track_clusters_dedup_on_split():
    # Previous week: one big cluster covering 20 pixels, track_id = 7.
    prev_frame = pd.DataFrame({"spatial_id": [f"p{i}" for i in range(20)]})
    prev_labels = np.zeros(20, dtype=int)
    prev_track_ids = {0: 7}

    # Current week: the cluster "splits" into two. Same 20 pixels, now labelled
    # 0 (first 10) and 1 (last 10).
    current_frame = pd.DataFrame({"spatial_id": [f"p{i}" for i in range(20)]})
    current_labels = np.array([0] * 10 + [1] * 10)

    track_ids, info, _ = track_clusters_simple(
        current_frame,
        prev_frame,
        current_labels,
        prev_labels,
        prev_track_ids,
        coord_cols=["spatial_id"],
    )

    # Exactly one current cluster keeps the heritage track id; the other must
    # receive a fresh id — IoU against the prev track is 0.5 for both, so the
    # tie-break is deterministic but either winner is acceptable; what matters
    # is that the two ids are distinct.
    assert track_ids[0] != track_ids[1], (
        "split clusters should not share the same track_id"
    )
