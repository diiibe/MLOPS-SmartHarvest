import argparse
import json
import os
import re

import numpy as np
import pandas as pd
from sklearn.preprocessing import RobustScaler

import config
import schema
from ml.dbstream import DBStream


def infer_project_name(path: str) -> str:
    base = os.path.basename(path)
    m = re.match(r"dbstream_features_(.*?)(?:_scaled)?\.csv", base)
    if m:
        return m.group(1)
    m = re.match(r"SmartHarvest_(.*)\.csv", base)
    if m:
        return m.group(1)
    return "default"


def find_latest_features() -> str:
    candidates = []
    for root, _, files in os.walk("output"):
        for f in files:
            if f.startswith("dbstream_features_") and f.endswith(".csv"):
                candidates.append(os.path.join(root, f))
    if not candidates:
        raise FileNotFoundError("No dbstream_features_*.csv found under output/")
    # Prefer scaled if present
    scaled = [p for p in candidates if p.endswith("_scaled.csv")]
    return max(scaled or candidates, key=os.path.getmtime)


def main():
    parser = argparse.ArgumentParser(
        description="[EXPERIMENTAL] Run DBStream anomaly detection on feature table (Alternative algorithm)"
    )
    parser.add_argument(
        "--features",
        dest="features_path",
        default=None,
        help="Path to dbstream_features_*.csv",
    )
    parser.add_argument("--epsilon", type=float, default=1.5)
    parser.add_argument("--mu", type=float, default=5.0)
    parser.add_argument("--lambda", dest="lambda_", type=float, default=0.0)
    parser.add_argument("--threshold", type=float, default=0.7)
    parser.add_argument("--shuffle", action="store_true", default=True)
    parser.add_argument("--no-shuffle", dest="shuffle", action="store_false")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--scale",
        action="store_true",
        default=False,
        help="Scale features if input is not scaled",
    )
    args = parser.parse_args()

    features_path = args.features_path or find_latest_features()
    if not os.path.exists(features_path):
        raise FileNotFoundError(features_path)

    project = infer_project_name(features_path)
    output_dir = os.path.dirname(features_path)

    print(f"Loading features: {features_path}")
    df = pd.read_csv(features_path)
    df = schema.normalize_columns(df)
    df.replace(-9999, np.nan, inplace=True)

    feature_cols = [
        c for c in getattr(config, "DBSTREAM_FEATURES", []) if c in df.columns
    ]
    if not feature_cols:
        raise ValueError("No DBStream features found in input")

    # Ensure lat/lon if available in .geo
    if "lat" not in df.columns or "lon" not in df.columns:
        if ".geo" in df.columns:

            def parse_geo(val):
                try:
                    geo = json.loads(val) if isinstance(val, str) else val
                    coords = geo.get("coordinates") if isinstance(geo, dict) else None
                    if coords and len(coords) >= 2:
                        return coords[1], coords[0]
                except Exception:
                    return None, None
                return None, None

            coords = df[".geo"].apply(parse_geo)
            df["lat"] = coords.apply(lambda x: x[0])
            df["lon"] = coords.apply(lambda x: x[1])

    # Drop rows with missing features
    df = df.dropna(subset=feature_cols)

    # Scale if requested or if file is not already scaled
    if args.scale or not features_path.endswith("_scaled.csv"):
        scaler = RobustScaler()
        df[feature_cols] = scaler.fit_transform(df[feature_cols])

    # Shuffle to simulate stream order
    if args.shuffle:
        df = df.sample(frac=1, random_state=args.seed).reset_index(drop=True)

    X = df[feature_cols].to_numpy(dtype=float)
    timestamps = np.arange(X.shape[0])

    model = DBStream(epsilon=args.epsilon, mu=args.mu, lambda_=args.lambda_)
    scores, labels, cluster_ids, dists = model.partial_fit_predict(
        X, timestamps, anomaly_threshold=args.threshold
    )

    df_out = df.copy()
    df_out["dbstream_score"] = scores
    df_out["dbstream_anomaly"] = labels
    df_out["dbstream_cluster"] = cluster_ids
    df_out["dbstream_dist"] = dists

    pixel_path = os.path.join(output_dir, f"dbstream_anomalies_{project}.csv")
    df_out.to_csv(pixel_path, index=False)
    print(f"Saved pixel-level anomalies: {pixel_path}")

    # Zone-level summary by microcluster id
    weights = [mc.weight for mc in model.microclusters]
    summary = (
        df_out.groupby("dbstream_cluster")
        .agg(
            count=("dbstream_cluster", "count"),
            anomaly_rate=("dbstream_anomaly", "mean"),
            mean_score=("dbstream_score", "mean"),
        )
        .reset_index()
    )

    if "lat" in df_out.columns and "lon" in df_out.columns:
        lat_lon = (
            df_out.groupby("dbstream_cluster")
            .agg(
                mean_lat=("lat", "mean"),
                mean_lon=("lon", "mean"),
            )
            .reset_index()
        )
        summary = summary.merge(lat_lon, on="dbstream_cluster", how="left")

    # Attach cluster weights
    summary["cluster_weight"] = summary["dbstream_cluster"].apply(
        lambda i: weights[i] if i < len(weights) else np.nan
    )

    zone_path = os.path.join(output_dir, f"dbstream_zone_summary_{project}.csv")
    summary.to_csv(zone_path, index=False)
    print(f"Saved zone summary: {zone_path}")


if __name__ == "__main__":
    main()
