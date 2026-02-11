import argparse
import os
import re

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import RobustScaler

import config
import schema


def find_latest_features() -> str:
    candidates = []
    for root, _, files in os.walk("output"):
        for f in files:
            if f.startswith("dbstream_features_") and f.endswith(".csv"):
                candidates.append(os.path.join(root, f))
    if not candidates:
        # fallback to SmartHarvest CSVs
        for root, _, files in os.walk("output"):
            for f in files:
                if (
                    f.startswith("SmartHarvest_")
                    and f.endswith(".csv")
                    and "ready_for_kmeans" not in f
                ):
                    candidates.append(os.path.join(root, f))
    if not candidates:
        raise FileNotFoundError(
            "No dbstream_features_*.csv or SmartHarvest_*.csv found under output/"
        )
    # prefer scaled
    scaled = [p for p in candidates if p.endswith("_scaled.csv")]
    return max(scaled or candidates, key=os.path.getmtime)


def infer_project_name(path: str) -> str:
    base = os.path.basename(path)
    m = re.match(r"dbstream_features_(.*?)(?:_scaled)?\.csv", base)
    if m:
        return m.group(1)
    m = re.match(r"SmartHarvest_(.*)\.csv", base)
    if m:
        return m.group(1)
    return "default"


def elbow_knee(y: np.ndarray) -> int:
    # Normalize curve to [0,1]
    x = np.linspace(0, 1, len(y))
    y_norm = (y - y.min()) / (y.max() - y.min() + 1e-9)
    # Line from first to last
    x1, y1 = 0.0, y_norm[0]
    x2, y2 = 1.0, y_norm[-1]
    # Distance from each point to line
    num = np.abs((y2 - y1) * x - (x2 - x1) * y_norm + x2 * y1 - y2 * x1)
    den = np.sqrt((y2 - y1) ** 2 + (x2 - x1) ** 2)
    dist = num / (den + 1e-9)
    return int(np.argmax(dist))


def main():
    parser = argparse.ArgumentParser(
        description="[EXPERIMENTAL] Estimate DBStream epsilon using k-distance curve (Alternative algorithm)"
    )
    parser.add_argument(
        "--input",
        dest="input_path",
        default=None,
        help="dbstream_features_*.csv or SmartHarvest_*.csv",
    )
    parser.add_argument("--k", type=int, default=5, help="k for k-distance (min 2)")
    parser.add_argument("--sample-fraction", type=float, default=0.3)
    parser.add_argument("--sample-size", type=int, default=None)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--scale",
        action="store_true",
        default=False,
        help="Scale features if input is not scaled",
    )
    args = parser.parse_args()

    input_path = args.input_path or find_latest_features()
    if not os.path.exists(input_path):
        raise FileNotFoundError(input_path)

    print(f"Loading: {input_path}")
    df = pd.read_csv(input_path)
    df = schema.normalize_columns(df)
    df.replace(-9999, np.nan, inplace=True)

    feature_cols = [
        c for c in getattr(config, "DBSTREAM_FEATURES", []) if c in df.columns
    ]
    if not feature_cols:
        raise ValueError("No DBStream features found in input")

    df = df.dropna(subset=feature_cols)

    # Sampling
    if args.sample_size is not None:
        df = df.sample(n=min(args.sample_size, len(df)), random_state=args.seed)
    elif args.sample_fraction is not None and 0 < args.sample_fraction < 1:
        df = df.sample(frac=args.sample_fraction, random_state=args.seed)

    X = df[feature_cols].to_numpy(dtype=float)

    # Scale if needed
    if args.scale or not input_path.endswith("_scaled.csv"):
        scaler = RobustScaler()
        X = scaler.fit_transform(X)

    k = max(int(args.k), 2)
    nn = NearestNeighbors(n_neighbors=k)
    nn.fit(X)
    distances, _ = nn.kneighbors(X)

    # k-distance: distance to k-th neighbor (index k-1)
    k_dist = np.sort(distances[:, k - 1])

    knee_idx = elbow_knee(k_dist)
    epsilon = float(k_dist[knee_idx])

    # Save plot
    project = infer_project_name(input_path)
    out_dir = os.path.dirname(input_path)
    plot_path = os.path.join(out_dir, f"dbstream_kdistance_{project}.png")

    plt.figure(figsize=(8, 4))
    plt.plot(k_dist, color="#2c3e50")
    plt.scatter([knee_idx], [epsilon], color="red", s=30, label=f"knee ~ {epsilon:.3f}")
    plt.title(f"k-distance curve (k={k})")
    plt.xlabel("Points (sorted)")
    plt.ylabel("Distance to k-th neighbor")
    plt.legend()
    plt.tight_layout()
    plt.savefig(plot_path, dpi=140)
    plt.close()

    print(f"Suggested epsilon: {epsilon:.4f}")
    print(f"Saved k-distance plot: {plot_path}")

    # Print some helpful quantiles
    for q in [0.90, 0.95, 0.99]:
        print(f"k-distance p{int(q*100)}: {np.quantile(k_dist, q):.4f}")


if __name__ == "__main__":
    main()
