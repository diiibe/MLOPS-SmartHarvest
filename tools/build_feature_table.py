import argparse
import json
import os
import re

import numpy as np
import pandas as pd
from sklearn.preprocessing import RobustScaler

import config
import schema


def infer_project_name(csv_path: str) -> str:
    base = os.path.basename(csv_path)
    m = re.match(r"SmartHarvest_(.*)\.csv", base)
    if m:
        return m.group(1)
    return "default"


def find_latest_csv() -> str:
    candidates = []
    for root, _, files in os.walk("output"):
        for f in files:
            if f.startswith("SmartHarvest_") and f.endswith(".csv") and "ready_for_kmeans" not in f:
                candidates.append(os.path.join(root, f))
    if not candidates:
        raise FileNotFoundError("No SmartHarvest_*.csv found under output/")
    return max(candidates, key=os.path.getmtime)


def extract_lat_lon(df: pd.DataFrame) -> pd.DataFrame:
    # Keep lat/lon if available, otherwise extract from .geo (GeoJSON)
    if "lat" in df.columns and "lon" in df.columns:
        return df
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
    return df


def main():
    parser = argparse.ArgumentParser(description="Build DBStream feature table from SmartHarvest CSV")
    parser.add_argument("--csv", dest="csv_path", default=None, help="Path to SmartHarvest_*.csv")
    parser.add_argument(
        "--sample-fraction",
        type=float,
        default=None,
        help="Random sample fraction (0-1)",
    )
    parser.add_argument("--sample-size", type=int, default=None, help="Random sample size (rows)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for sampling")
    args = parser.parse_args()

    csv_path = args.csv_path or find_latest_csv()
    if not os.path.exists(csv_path):
        raise FileNotFoundError(csv_path)

    project = infer_project_name(csv_path)
    output_dir = os.path.dirname(csv_path)

    print(f"Loading CSV: {csv_path}")
    df = pd.read_csv(csv_path)
    df = schema.normalize_columns(df)
    df.replace(-9999, np.nan, inplace=True)
    df = extract_lat_lon(df)

    # Feature selection
    features = getattr(config, "DBSTREAM_FEATURES", [])
    if not features:
        features = [
            "NDVI_Mean",
            "NDVI_Delta",
            "NDVI_Stability",
            "IRECI_Mean",
            "S2REP_Mean",
            "MNDWI_Mean",
            "VH_Drop",
            "LST_Mean",
            "Elevation",
            "Slope",
            "Aspect",
        ]

    available = [c for c in features if c in df.columns]
    missing = [c for c in features if c not in df.columns]
    if missing:
        print(f"Warning: Missing features dropped: {missing}")

    # Keep only selected + coords
    keep_cols = [c for c in ["lat", "lon"] if c in df.columns] + available
    feat_df = df[keep_cols].dropna(subset=available)

    # Sampling
    if args.sample_size is not None:
        feat_df = feat_df.sample(n=min(args.sample_size, len(feat_df)), random_state=args.seed)
    elif args.sample_fraction is not None:
        feat_df = feat_df.sample(frac=args.sample_fraction, random_state=args.seed)

    raw_path = os.path.join(output_dir, f"dbstream_features_{project}.csv")
    feat_df.to_csv(raw_path, index=False)
    print(f"Saved raw features: {raw_path}")

    # Scale features
    scaler = RobustScaler()
    scaled = feat_df.copy()
    scaled_vals = scaler.fit_transform(scaled[available])
    scaled[available] = scaled_vals

    scaled_path = os.path.join(output_dir, f"dbstream_features_{project}_scaled.csv")
    scaled.to_csv(scaled_path, index=False)
    print(f"Saved scaled features: {scaled_path}")

    scaler_path = os.path.join(output_dir, f"dbstream_scaler_{project}.json")
    scaler_info = {
        "features": available,
        "center": scaler.center_.tolist(),
        "scale": scaler.scale_.tolist(),
    }
    with open(scaler_path, "w") as f:
        json.dump(scaler_info, f, indent=2)
    print(f"Saved scaler params: {scaler_path}")


if __name__ == "__main__":
    main()
