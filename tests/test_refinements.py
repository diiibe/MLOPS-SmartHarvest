"""Tests for the post-audit refinements:
   - rolling cross-week normalization
   - combined relative + absolute anomaly threshold
   - persistence filter on anomalous track ids
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ml.clustering import (
    compute_feature_stats,
    merge_reference_stats,
    normalize_features,
)
from ml.tracking import detect_anomalies


# ---------------------------------------------------------------------------
# Rolling normalization
# ---------------------------------------------------------------------------

def test_compute_feature_stats_returns_mean_std_per_column():
    df = pd.DataFrame({"NDVI": [0.1, 0.5, 0.9], "NDWI": [0.0, 0.0, 0.0]})
    stats = compute_feature_stats(df, ["NDVI", "NDWI"])
    assert stats["NDVI"][0] == pytest_approx(0.5)
    assert stats["NDVI"][1] > 0
    assert stats["NDWI"][1] == 0.0  # constant column → std 0


def test_merge_reference_stats_averages_means_and_rms_stds():
    history = [
        {"NDVI": (0.5, 0.1)},
        {"NDVI": (0.7, 0.2)},
    ]
    merged = merge_reference_stats(history, ["NDVI"])
    # mean of means = 0.6, RMS of stds = sqrt((0.01 + 0.04)/2) ≈ 0.158
    assert merged["NDVI"][0] == pytest_approx(0.6)
    assert merged["NDVI"][1] == pytest_approx(np.sqrt(0.025), rel=1e-3)


def test_normalize_with_reference_uses_reference_not_local_stats():
    # Per-week scaler would center on 0.5, but the reference insists on
    # centering on 0.3 with std 0.2, so the scaled output must reflect that.
    frame = pd.DataFrame({"NDVI": [0.3, 0.5, 0.7]})
    ref = {"NDVI": (0.3, 0.2)}
    _, _, X_scaled = normalize_features(frame, ["NDVI"], reference_stats=ref)
    expected = (np.array([0.3, 0.5, 0.7]) - 0.3) / 0.2
    np.testing.assert_allclose(X_scaled[:, 0], expected)


def test_normalize_reference_handles_zero_std_without_divide_by_zero():
    frame = pd.DataFrame({"NDVI": [0.1, 0.2, 0.3]})
    # Reference reports std=0 (constant historical window) — must not NaN out.
    ref = {"NDVI": (0.2, 0.0)}
    _, _, X_scaled = normalize_features(frame, ["NDVI"], reference_stats=ref)
    assert np.isfinite(X_scaled).all()


# ---------------------------------------------------------------------------
# Absolute-threshold anomaly detection
# ---------------------------------------------------------------------------

def test_absolute_threshold_suppresses_quiet_week():
    # All scores well below min_absolute_score → nothing surfaces, even though
    # the 95th percentile is technically defined.
    frame = pd.DataFrame({"lat": [46.0] * 20, "lon": [13.0] * 20})
    labels = np.zeros(20, dtype=int)
    scores = np.linspace(0.01, 0.2, 20)  # all < 0.5
    _, summary = detect_anomalies(
        frame, labels, scores, {0: 5}, min_absolute_score=0.5
    )
    assert len(summary) == 0


def test_absolute_threshold_still_catches_real_outliers():
    frame = pd.DataFrame({"lat": [46.0] * 20, "lon": [13.0] * 20})
    labels = np.array([0] * 19 + [1])
    # Mostly quiet, one high-score outlier well above the absolute floor.
    scores = np.array([0.1] * 19 + [0.9])
    _, summary = detect_anomalies(
        frame, labels, scores, {0: 5, 1: 6}, min_absolute_score=0.5
    )
    assert len(summary) == 1
    assert int(summary.iloc[0]["track_id"]) == 6


# ---------------------------------------------------------------------------
# Persistence filter
# ---------------------------------------------------------------------------

def test_persistence_filter_drops_one_off_spike():
    frame = pd.DataFrame({"lat": [46.0] * 10, "lon": [13.0] * 10})
    labels = np.zeros(10, dtype=int)
    scores = np.array([0.1] * 9 + [0.99])
    history = [set(), set()]  # track_id 0 never appeared in prior weeks
    _, summary = detect_anomalies(
        frame,
        labels,
        scores,
        {0: 42},
        min_absolute_score=0.5,
        persistence_weeks=2,
        track_history=history,
    )
    assert len(summary) == 0, "one-off spike should be suppressed"


def test_persistence_filter_keeps_recurring_anomaly():
    frame = pd.DataFrame({"lat": [46.0] * 10, "lon": [13.0] * 10})
    labels = np.zeros(10, dtype=int)
    scores = np.array([0.1] * 9 + [0.99])
    history = [{42}, {42}]  # track_id 42 anomalous in both recent weeks
    _, summary = detect_anomalies(
        frame,
        labels,
        scores,
        {0: 42},
        min_absolute_score=0.5,
        persistence_weeks=2,
        track_history=history,
    )
    assert len(summary) == 1


# ---------------------------------------------------------------------------
# pytest approx shim (avoids importing the name when only used here)
# ---------------------------------------------------------------------------

def pytest_approx(value, rel=None, abs=None):  # noqa: D401 — tiny helper
    from pytest import approx

    kwargs = {}
    if rel is not None:
        kwargs["rel"] = rel
    if abs is not None:
        kwargs["abs"] = abs
    return approx(value, **kwargs)
