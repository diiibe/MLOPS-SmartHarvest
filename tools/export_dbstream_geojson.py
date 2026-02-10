import argparse
import json
import os
import re

import numpy as np
import pandas as pd

import schema


def find_latest_anomalies(pattern_prefix: str) -> str:
    candidates = []
    for root, _, files in os.walk("output"):
        for f in files:
            if f.startswith(pattern_prefix) and f.endswith(".csv"):
                candidates.append(os.path.join(root, f))
    if not candidates:
        raise FileNotFoundError(f"No {pattern_prefix}*.csv found under output/")
    return max(candidates, key=os.path.getmtime)


def extract_lat_lon(df: pd.DataFrame) -> pd.DataFrame:
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


def infer_project_name(path: str) -> str:
    base = os.path.basename(path)
    m = re.match(r"dbstream_(anomalies|zone_summary)_(.*)\.csv", base)
    if m:
        return m.group(2)
    return "default"


def main():
    parser = argparse.ArgumentParser(description="Export DBStream anomalies to GeoJSON")
    parser.add_argument("--input", dest="input_path", default=None, help="CSV input path")
    parser.add_argument("--zone", action="store_true", default=False, help="Use zone summary CSV")
    parser.add_argument("--min-score", type=float, default=None, help="Minimum score filter")
    parser.add_argument("--only-anomalies", action="store_true", default=False, help="Keep only anomalies (dbstream_anomaly==1)")
    parser.add_argument("--output", dest="output_path", default=None, help="GeoJSON output path")
    args = parser.parse_args()

    if args.zone:
        input_path = args.input_path or find_latest_anomalies("dbstream_zone_summary_")
    else:
        input_path = args.input_path or find_latest_anomalies("dbstream_anomalies_")

    if not os.path.exists(input_path):
        raise FileNotFoundError(input_path)

    df = pd.read_csv(input_path)
    df = schema.normalize_columns(df)
    df.replace(-9999, np.nan, inplace=True)
    df = extract_lat_lon(df)

    if args.only_anomalies and "dbstream_anomaly" in df.columns:
        df = df[df["dbstream_anomaly"] == 1]

    if args.min_score is not None and "dbstream_score" in df.columns:
        df = df[df["dbstream_score"] >= args.min_score]

    # Drop rows without coordinates
    df = df.dropna(subset=["lat", "lon"])

    features = []
    for _, row in df.iterrows():
        props = row.to_dict()
        lat = props.pop("lat")
        lon = props.pop("lon")
        geom = {"type": "Point", "coordinates": [float(lon), float(lat)]}
        features.append({"type": "Feature", "geometry": geom, "properties": props})

    geojson = {"type": "FeatureCollection", "features": features}

    project = infer_project_name(input_path)
    if args.output_path:
        output_path = args.output_path
    else:
        suffix = "zone" if args.zone else "pixel"
        output_path = os.path.join(os.path.dirname(input_path), f"dbstream_anomalies_{project}_{suffix}.geojson")

    with open(output_path, "w") as f:
        json.dump(geojson, f)

    print(f"Saved GeoJSON: {output_path}")


if __name__ == "__main__":
    main()
