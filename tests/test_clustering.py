"""Unit tests for ml/clustering.py — normalize_features, microclustering, HDBSCAN path."""
from __future__ import annotations

import numpy as np
import pytest

from ml.clustering import hdbscan_clustering, microclustering, normalize_features


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_full_pipeline(df, feature_cols):
    """Run normalize -> microclustering -> hdbscan and return (cluster_labels, outlier_scores)."""
    frame_norm, scaler, X_scaled = normalize_features(df, feature_cols)
    micro_labels, micro_centroids, micro_sizes = microclustering(X_scaled, frame_norm)
    cluster_labels, outlier_scores, clusterer = hdbscan_clustering(micro_centroids, micro_sizes)
    return cluster_labels, outlier_scores, micro_labels


# ---------------------------------------------------------------------------
# Import smoke test
# ---------------------------------------------------------------------------

def test_clustering_module_imports_cleanly():
    """The module must import without side effects."""
    import ml.clustering as clustering_module
    assert clustering_module is not None


# ---------------------------------------------------------------------------
# normalize_features
# ---------------------------------------------------------------------------

def test_normalize_features_returns_three_items(synthetic_pixel_dataframe):
    """normalize_features must return (frame_norm, scaler, X_scaled)."""
    feature_cols = ["NDVI", "VH", "LST"]
    result = normalize_features(synthetic_pixel_dataframe, feature_cols)
    assert len(result) == 3, "Expected (frame_norm, scaler, X_scaled)"
    frame_norm, scaler, X_scaled = result
    assert X_scaled.shape == (len(synthetic_pixel_dataframe), len(feature_cols))


def test_normalize_features_adds_norm_columns(synthetic_pixel_dataframe):
    """normalize_features should add '<col>_norm' columns to the returned frame."""
    feature_cols = ["NDVI", "VH", "LST"]
    frame_norm, _, _ = normalize_features(synthetic_pixel_dataframe, feature_cols)
    for col in feature_cols:
        assert f"{col}_norm" in frame_norm.columns, f"Missing {col}_norm in frame_norm"


# ---------------------------------------------------------------------------
# Full pipeline on synthetic data
# ---------------------------------------------------------------------------

def test_hdbscan_finds_clusters_on_well_separated_data(synthetic_pixel_dataframe):
    """With three clearly separated blobs, the pipeline should discover at least 2 clusters."""
    feature_cols = ["NDVI", "VH", "LST"]
    cluster_labels, outlier_scores, micro_labels = _run_full_pipeline(
        synthetic_pixel_dataframe, feature_cols
    )
    unique_clusters = set(cluster_labels.tolist()) - {-1}
    assert len(unique_clusters) >= 2, (
        f"Expected at least 2 clusters on 3-blob synthetic data, got {len(unique_clusters)}"
    )


def test_hdbscan_is_deterministic_on_same_input(synthetic_pixel_dataframe):
    """Same input, same parameters => identical cluster labels across two runs."""
    feature_cols = ["NDVI", "VH", "LST"]
    _, _, X_scaled_a = normalize_features(synthetic_pixel_dataframe, feature_cols)
    _, _, X_scaled_b = normalize_features(synthetic_pixel_dataframe, feature_cols)

    _, micro_centroids_a, micro_sizes_a = microclustering(
        X_scaled_a, synthetic_pixel_dataframe
    )
    _, micro_centroids_b, micro_sizes_b = microclustering(
        X_scaled_b, synthetic_pixel_dataframe
    )

    labels_a, _, _ = hdbscan_clustering(micro_centroids_a, micro_sizes_a)
    labels_b, _, _ = hdbscan_clustering(micro_centroids_b, micro_sizes_b)

    assert np.array_equal(labels_a, labels_b), (
        "hdbscan_clustering produced different labels on identical inputs"
    )


def test_hdbscan_outlier_scores_shape(synthetic_pixel_dataframe):
    """outlier_scores must have the same length as micro_centroids."""
    feature_cols = ["NDVI", "VH", "LST"]
    _, _, X_scaled = normalize_features(synthetic_pixel_dataframe, feature_cols)
    _, micro_centroids, micro_sizes = microclustering(X_scaled, synthetic_pixel_dataframe)
    cluster_labels, outlier_scores, _ = hdbscan_clustering(micro_centroids, micro_sizes)

    assert len(outlier_scores) == len(micro_centroids), (
        "outlier_scores length must match number of microclusters"
    )
    assert len(cluster_labels) == len(micro_centroids), (
        "cluster_labels length must match number of microclusters"
    )


# ---------------------------------------------------------------------------
# Smoke test on bundled Fantinel data
# ---------------------------------------------------------------------------

def test_full_pipeline_smoke_on_fantinel(fantinel_sample_single_week):
    """Smoke test: full pipeline runs on a slice of the bundled demo data."""
    df = fantinel_sample_single_week
    feature_cols = [
        c for c in ["NDVI", "VH", "LST", "NDWI", "VV"]
        if c in df.columns and df[c].notna().sum() > 10
    ]
    if len(feature_cols) < 2:
        pytest.skip("Not enough usable feature columns in the bundled sample")

    if len(df) < 30:
        pytest.skip("Too few rows in the bundled sample for a clustering smoke test")

    cluster_labels, outlier_scores, micro_labels = _run_full_pipeline(df, feature_cols)

    # Basic sanity: every pixel has a micro-label, every micro-label is covered
    assert len(micro_labels) == len(df)
    assert len(cluster_labels) == len(set(micro_labels))
