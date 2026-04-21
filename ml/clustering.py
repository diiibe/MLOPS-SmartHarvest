"""
STEP 4-6: Normalization, Microclustering, and HDBSCAN
"""

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import MiniBatchKMeans
import hdbscan


def normalize_features(frame, feature_cols, reference_stats=None):
    """
    STEP 4: Feature normalization.

    If `reference_stats` is provided (a dict of `{col: (mean, std)}`), the
    features are centred/scaled against those rolling statistics instead of
    being re-fit on this week alone. This keeps feature coordinates
    comparable across weeks so the same vineyard block doesn't flip between
    "anomalous" and "normal" only because a rainy week shifted the local
    mean. Falls back to a per-week StandardScaler when no reference is
    available (first week) or when a reference column's std is zero.

    Returns:
        frame_norm: DataFrame with `<col>_norm` columns added
        scaler: fitted StandardScaler (per-week fit, always returned for
            inverse_transform convenience)
        X_scaled: ndarray of shape (n, len(feature_cols))
    """
    X = frame[feature_cols].values.astype(float, copy=True)

    # Fill NaN with column median (fallback 0 if the entire column is NaN)
    for i in range(X.shape[1]):
        median_val = np.nanmedian(X[:, i])
        if np.isnan(median_val):
            median_val = 0.0
        X[np.isnan(X[:, i]), i] = median_val

    # Always fit a per-week scaler so callers that want inverse_transform
    # (or a fresh baseline) still get one.
    scaler = StandardScaler().fit(X)

    if reference_stats:
        means = np.array(
            [reference_stats.get(c, (scaler.mean_[i], scaler.scale_[i]))[0]
             for i, c in enumerate(feature_cols)]
        )
        stds = np.array(
            [reference_stats.get(c, (scaler.mean_[i], scaler.scale_[i]))[1]
             for i, c in enumerate(feature_cols)]
        )
        # Guard against zero-variance reference columns (would divide by 0)
        stds = np.where(stds > 1e-12, stds, 1.0)
        X_scaled = (X - means) / stds
    else:
        X_scaled = scaler.transform(X)

    frame_norm = frame.copy()
    for i, col in enumerate(feature_cols):
        frame_norm[f"{col}_norm"] = X_scaled[:, i]

    return frame_norm, scaler, X_scaled


def compute_feature_stats(frame, feature_cols):
    """Return `{col: (mean, std)}` from a single weekly frame.

    Used to build the rolling reference the next week normalizes against.
    NaNs are ignored; constant columns get `std=0` which the normalizer
    then fences off. Kept separate from `normalize_features` so the
    pipeline can accumulate a stats history without touching the scaled
    output format.
    """
    stats = {}
    for col in feature_cols:
        if col not in frame.columns:
            continue
        vals = frame[col].to_numpy(dtype=float, copy=True)
        vals = vals[~np.isnan(vals)]
        if len(vals) == 0:
            stats[col] = (0.0, 0.0)
            continue
        stats[col] = (float(vals.mean()), float(vals.std(ddof=0)))
    return stats


def merge_reference_stats(history, feature_cols):
    """Aggregate a list of per-week `{col: (mean, std)}` dicts into a single
    reference, using the mean of means and RMS of stds. This is a rough
    approximation to pooling statistics across weeks without storing every
    raw observation; exact pooling would require also knowing per-week
    sample counts. Good enough for the "stabilize cluster boundaries"
    goal — the clustering is density-based, not parametric."""
    if not history:
        return None
    merged = {}
    for col in feature_cols:
        means = [h[col][0] for h in history if col in h]
        stds = [h[col][1] for h in history if col in h]
        if not means:
            continue
        merged[col] = (
            float(np.mean(means)),
            float(np.sqrt(np.mean(np.square(stds)))),
        )
    return merged or None


def microclustering(X_scaled, frame, max_microclusters=5000):
    """
    STEP 5: Microclustering to reduce noise and dimensionality.

    Auto-adjusts k to keep microcluster count reasonable.

    Returns:
        micro_labels: array of microcluster labels per pixel
        micro_centroids: centroids of microclusters
        micro_sizes: size of each microcluster
    """
    n_samples = len(X_scaled)

    # Auto-select k: aim for ~20-50 pixels per microcluster.
    # Clamp to n_samples so MiniBatchKMeans never receives n_clusters > n_samples
    # (which would raise), and cast to int explicitly for safety.
    target_micro = min(max_microclusters, max(50, n_samples // 30))
    target_micro = int(min(n_samples, target_micro))

    # Use MiniBatchKMeans for speed
    kmeans = MiniBatchKMeans(
        n_clusters=target_micro, random_state=42, batch_size=1024, max_iter=100
    )

    micro_labels = kmeans.fit_predict(X_scaled)
    micro_centroids = kmeans.cluster_centers_

    # Compute microcluster sizes
    unique_labels, counts = np.unique(micro_labels, return_counts=True)
    micro_sizes = {label: count for label, count in zip(unique_labels, counts)}

    print(
        f"[Microclustering] Created {len(unique_labels)} microclusters from {n_samples:,} pixels"
    )
    print(
        f"[Microclustering] Avg size: {n_samples / len(unique_labels):.1f} pixels/micro"
    )

    return micro_labels, micro_centroids, micro_sizes


def hdbscan_clustering(
    micro_centroids,
    micro_sizes,
    min_cluster_size=10,
    target_min_pixels=50,
):
    """
    STEP 6: HDBSCAN on microcluster centroids.

    `micro_sizes` (dict {label: pixel_count}) is used to translate a
    user-meaningful "cluster must cover at least N pixels" threshold into the
    microcluster-space `min_cluster_size` that HDBSCAN consumes. This prevents
    singleton microclusters from dominating when the microcluster population
    is uneven — the previous implementation accepted `micro_sizes` but never
    used it.

    min_samples is also scaled with microcluster count (was hardcoded to 5).

    Returns:
        cluster_labels: final cluster label per microcluster (-1 = noise)
        outlier_scores: outlier score per microcluster (higher = more outlier)
    """
    n_micro = len(micro_centroids)

    # Average pixels per microcluster (fallback 1 if sizes missing/empty)
    if micro_sizes:
        avg_micro_px = max(1.0, float(sum(micro_sizes.values())) / len(micro_sizes))
    else:
        avg_micro_px = 1.0

    # How many microclusters add up to `target_min_pixels` pixels on average
    size_from_pixels = max(2, int(round(target_min_pixels / avg_micro_px)))
    adjusted_min_size = max(
        2, min(min_cluster_size, size_from_pixels, max(2, n_micro // 20))
    )

    # min_samples scales with density: enough to suppress single-point noise
    # without being so strict that sparse microcluster sets collapse to all-noise.
    adjusted_min_samples = max(2, min(10, n_micro // 50))

    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=adjusted_min_size,
        min_samples=adjusted_min_samples,
        metric="euclidean",
        cluster_selection_method="eom",  # Excess of Mass
        core_dist_n_jobs=1,  # single-thread → reproducible run-to-run
        approx_min_span_tree=False,  # exact MST → deterministic
    )

    cluster_labels = clusterer.fit_predict(micro_centroids)
    outlier_scores = clusterer.outlier_scores_

    n_clusters = len(set(cluster_labels)) - (1 if -1 in cluster_labels else 0)
    n_noise = (cluster_labels == -1).sum()

    print(
        f"[HDBSCAN] Found {n_clusters} clusters + {n_noise} noise microclusters "
        f"(min_cluster_size={adjusted_min_size}, min_samples={adjusted_min_samples}, "
        f"avg_micro_px={avg_micro_px:.1f})"
    )

    return cluster_labels, outlier_scores, clusterer


def propagate_to_pixels(micro_labels, cluster_labels, outlier_scores):
    """
    Propagate microcluster results to pixel level.

    Returns:
        pixel_cluster_labels: cluster label per pixel
        pixel_outlier_scores: outlier score per pixel
    """
    pixel_cluster_labels = np.array([cluster_labels[m] for m in micro_labels])
    pixel_outlier_scores = np.array([outlier_scores[m] for m in micro_labels])

    return pixel_cluster_labels, pixel_outlier_scores
