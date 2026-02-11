"""
EXPERIMENTAL: In-house DBStream implementation for batch/stream anomaly detection.
This is an alternative algorithm and is NOT used in the primary production pipeline (HDBSCAN).
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np


@dataclass
class MicroCluster:
    center: np.ndarray
    weight: float
    last_update: float

    def decay(self, t: float, lambda_: float) -> None:
        if lambda_ <= 0 or t <= self.last_update:
            self.last_update = max(self.last_update, t)
            return
        decay_factor = 2.0 ** (-lambda_ * (t - self.last_update))
        self.weight *= decay_factor
        self.last_update = t

    def update(self, x: np.ndarray, t: float, lambda_: float) -> None:
        self.decay(t, lambda_)
        self.weight += 1.0
        # Incremental mean update
        self.center = self.center + (x - self.center) / self.weight


class DBStream:
    def __init__(self, epsilon: float = 1.5, mu: float = 5.0, lambda_: float = 0.0) -> None:
        self.epsilon = float(epsilon)
        self.mu = float(mu)
        self.lambda_ = float(lambda_)
        self.microclusters: List[MicroCluster] = []

    def _nearest_cluster(self, x: np.ndarray) -> Tuple[int, float]:
        if not self.microclusters:
            return -1, float("inf")
        centers = np.stack([mc.center for mc in self.microclusters], axis=0)
        dists = np.linalg.norm(centers - x, axis=1)
        idx = int(np.argmin(dists))
        return idx, float(dists[idx])

    def partial_fit(self, X: np.ndarray, timestamps: Optional[np.ndarray] = None) -> None:
        if timestamps is None:
            timestamps = np.arange(X.shape[0])
        for x, t in zip(X, timestamps):
            idx, dist = self._nearest_cluster(x)
            if idx >= 0 and dist <= self.epsilon:
                self.microclusters[idx].update(x, float(t), self.lambda_)
            else:
                self.microclusters.append(MicroCluster(center=x.copy(), weight=1.0, last_update=float(t)))

    def score_point(self, x: np.ndarray, t: float) -> Tuple[float, int, float]:
        """Return (score, cluster_id, dist). Score in [0,1]."""
        if not self.microclusters:
            return 1.0, -1, float("inf")
        # Decay all clusters to current time
        for mc in self.microclusters:
            mc.decay(t, self.lambda_)
        idx, dist = self._nearest_cluster(x)
        if idx < 0 or dist > self.epsilon:
            return 1.0, -1, dist
        mc = self.microclusters[idx]
        density_ratio = min(mc.weight / self.mu, 1.0) if self.mu > 0 else 1.0
        dist_ratio = min(dist / self.epsilon, 1.0) if self.epsilon > 0 else 1.0
        score = 0.5 * dist_ratio + 0.5 * (1.0 - density_ratio)
        return float(score), idx, dist

    def partial_fit_predict(
        self,
        X: np.ndarray,
        timestamps: Optional[np.ndarray] = None,
        anomaly_threshold: float = 0.7,
    ):
        if timestamps is None:
            timestamps = np.arange(X.shape[0])
        scores = []
        labels = []
        cluster_ids = []
        dists = []
        for x, t in zip(X, timestamps):
            score, idx, dist = self.score_point(x, float(t))
            is_anom = 1 if (score >= anomaly_threshold) else 0
            # Update after scoring
            if idx >= 0 and dist <= self.epsilon:
                self.microclusters[idx].update(x, float(t), self.lambda_)
                assigned = idx
            else:
                self.microclusters.append(MicroCluster(center=x.copy(), weight=1.0, last_update=float(t)))
                assigned = len(self.microclusters) - 1
            scores.append(score)
            labels.append(is_anom)
            cluster_ids.append(assigned)
            dists.append(dist)
        return (
            np.array(scores),
            np.array(labels),
            np.array(cluster_ids),
            np.array(dists),
        )
