import argparse
import json
import os

import pandas as pd
import folium
import branca.colormap as cm

import schema


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


def find_latest_anomalies() -> str:
    candidates = []
    for root, _, files in os.walk("output"):
        for f in files:
            if f.startswith("dbstream_anomalies_") and f.endswith(".csv"):
                candidates.append(os.path.join(root, f))
    if not candidates:
        raise FileNotFoundError("No dbstream_anomalies_*.csv found under output/")
    return max(candidates, key=os.path.getmtime)


def main():
    parser = argparse.ArgumentParser(description="Visualize DBStream anomalies on a map")
    parser.add_argument("--input", dest="input_path", default=None, help="dbstream_anomalies_*.csv")
    parser.add_argument("--output", dest="output_path", default=None, help="HTML output path")
    parser.add_argument("--only-anomalies", action="store_true", default=False)
    parser.add_argument("--sample-size", type=int, default=None)
    args = parser.parse_args()

    input_path = args.input_path or find_latest_anomalies()
    if not os.path.exists(input_path):
        raise FileNotFoundError(input_path)

    df = pd.read_csv(input_path)
    df = schema.normalize_columns(df)
    df.replace(-9999, pd.NA, inplace=True)
    df = extract_lat_lon(df)

    if args.only_anomalies and "dbstream_anomaly" in df.columns:
        df = df[df["dbstream_anomaly"] == 1]

    if args.sample_size:
        df = df.sample(n=min(args.sample_size, len(df)), random_state=42)

    df = df.dropna(subset=["lat", "lon"])
    if df.empty:
        raise ValueError("No rows with coordinates to plot")

    center_lat = df["lat"].mean()
    center_lon = df["lon"].mean()
    m = folium.Map(location=[center_lat, center_lon], zoom_start=16, tiles="Esri.WorldImagery")

    score_col = "dbstream_score" if "dbstream_score" in df.columns else None
    if score_col:
        vmin = float(df[score_col].min())
        vmax = float(df[score_col].max())
    else:
        vmin, vmax = 0.0, 1.0

    colormap = cm.LinearColormap(["green", "yellow", "red"], vmin=vmin, vmax=vmax)

    fg = folium.FeatureGroup(name="DBStream Score", show=True)
    for _, row in df.iterrows():
        score = float(row[score_col]) if score_col else 0.0
        color = colormap(score)
        popup = (
            f"Score: {score:.3f}<br>Cluster: {row.get('dbstream_cluster', '')}<br>Anomaly: {row.get('dbstream_anomaly', '')}"
        )
        folium.CircleMarker(
            location=[row["lat"], row["lon"]],
            radius=4,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.8,
            popup=folium.Popup(popup, max_width=200),
        ).add_to(fg)
    fg.add_to(m)

    colormap.caption = "DBStream Anomaly Score"
    colormap.add_to(m)

    folium.LayerControl(position="topleft", collapsed=False).add_to(m)

    if args.output_path:
        output_path = args.output_path
    else:
        base = os.path.basename(input_path).replace(".csv", "_map.html")
        output_path = os.path.join(os.path.dirname(input_path), base)

    m.save(output_path)
    print(f"Map saved to {output_path}")


if __name__ == "__main__":
    main()
