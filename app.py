import os
import re
import json
import pandas as pd
import markdown
from flask import (
    Flask,
    render_template,
    request,
    jsonify,
    send_file,
    send_from_directory,
    abort,
)
import main
from tools import visualize_data_map, charts

app = Flask(__name__)

os.makedirs("output", exist_ok=True)

# Only allow letters, digits, dash, underscore, dot (without ".."). Anything
# else becomes an underscore so the name can be used in a filesystem path and
# in a URL without surprises.
_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]")


def _get_project_safe_name(project_name):
    """Sanitize a project name for filesystem paths.

    The previous implementation only replaced spaces, which left path-traversal
    sequences (`../`) and separators (`/`, `\\`) intact — allowing crafted
    `project_name` values to escape the `output/` directory when concatenated
    with `os.path.join`.
    """
    if not project_name:
        return "default"
    # Collapse path separators and ".." before the per-character filter.
    cleaned = project_name.replace("/", "_").replace("\\", "_").replace("..", "_")
    safe = _SAFE_NAME_RE.sub("_", cleaned).strip("._") or "default"
    return safe


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/rois", methods=["GET"])
def list_rois():
    rois = []
    if os.path.exists("rois"):
        for f in os.listdir("rois"):
            if f.endswith(".json"):
                rois.append(f.replace(".json", ""))
    return jsonify(rois)


@app.route("/rois/<name>", methods=["GET"])
def get_roi(name):
    safe = _get_project_safe_name(name)
    path = os.path.join("rois", f"{safe}.json")
    if os.path.exists(path):
        with open(path, "r") as f:
            return jsonify(json.load(f))
    return jsonify({"error": "ROI not found"}), 404


@app.route("/rois", methods=["POST"])
def save_roi():
    data = request.json
    name = data.get("name")
    geometry = data.get("geometry")
    if not name or not geometry:
        return jsonify({"success": False, "error": "Missing name or geometry"})
    # Sanitize to prevent writing outside rois/ via "../" or absolute paths.
    safe_name = _get_project_safe_name(name)
    os.makedirs("rois", exist_ok=True)
    path = os.path.join("rois", f"{safe_name}.json")
    with open(path, "w") as f:
        json.dump(geometry, f, indent=4)
    return jsonify({"success": True, "saved_as": safe_name})


@app.route("/projects", methods=["GET"])
def list_projects():
    """List all existing projects with available CSV data."""
    projects = []
    if os.path.exists("output"):
        for folder in os.listdir("output"):
            folder_path = os.path.join("output", folder)
            if os.path.isdir(folder_path):
                csv_path = os.path.join(folder_path, f"SmartHarvest_{folder}.csv")
                if os.path.exists(csv_path):
                    # Get metadata if available
                    metadata_path = os.path.join(folder_path, f"metadata_{folder}.json")
                    metadata = {}
                    if os.path.exists(metadata_path):
                        try:
                            with open(metadata_path, "r") as f:
                                meta_list = json.load(f)
                                # Extract relevant info
                                for item in meta_list:
                                    if (
                                        "source" in item
                                        and item["source"] == "ROI Stats"
                                    ):
                                        metadata["area_ha"] = item.get("area_ha", 0)
                                        metadata["analysis_range"] = item.get(
                                            "analysis_range", "N/A"
                                        )
                        except Exception:
                            pass

                    # Get CSV stats
                    try:
                        df = pd.read_csv(csv_path)
                        metadata["rows"] = len(df)
                        metadata["dates"] = (
                            df["date"].nunique() if "date" in df.columns else 0
                        )
                    except Exception:
                        pass

                    projects.append(
                        {"name": folder, "csv_exists": True, "metadata": metadata}
                    )
    return jsonify(projects)


@app.route("/reuse_project", methods=["POST"])
def reuse_project():
    """Regenerate map and report for an existing project without re-downloading data."""
    try:
        data = request.json
        project_name = data.get("project_name")

        if not project_name:
            return jsonify({"success": False, "error": "Missing project name"})

        project_name_safe = _get_project_safe_name(project_name)
        output_dir = os.path.join("output", project_name_safe)
        csv_path = os.path.join(output_dir, f"SmartHarvest_{project_name_safe}.csv")

        if not os.path.exists(csv_path):
            return jsonify(
                {"success": False, "error": f"Project CSV not found: {csv_path}"}
            )

        analysis_progress[project_name_safe] = {
            "status": "Regenerating outputs...",
            "percent": 50,
        }

        # Regenerate map
        map_path = os.path.join(output_dir, f"Map_{project_name_safe}.html")
        try:
            visualize_data_map.create_verification_map(csv_path, map_path)
            print(f"[OK] Map regenerated: {map_path}")
        except Exception as e:
            print(f"Warning: Map generation failed: {e}")

        # Get available dates
        available_dates = (
            visualize_data_map.get_available_dates(csv_path)
            if os.path.exists(csv_path)
            else []
        )

        analysis_progress[project_name_safe] = {"status": "Complete", "percent": 100}

        return jsonify(
            {
                "success": True,
                "project_name": project_name_safe,
                "available_dates": available_dates,
            }
        )

    except Exception as e:
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)})


# Global progress store
analysis_progress = {}


@app.route("/progress/<project_name>")
def get_progress(project_name):
    safe = _get_project_safe_name(project_name)
    return jsonify(
        analysis_progress.get(safe, {"status": "idle", "percent": 0})
    )


@app.route("/run_analysis", methods=["POST"])
def run_analysis():
    try:
        data = request.json
        project_name = data.get("project_name", "default")
        geometry = data.get("geometry")

        if not geometry or "coordinates" not in geometry:
            return jsonify({"success": False, "error": "Invalid geometry"})

        roi_coords = geometry["coordinates"]

        # Validate ROI before kicking off the pipeline — saves a GEE auth round
        # trip and gives the user an actionable error for malformed input.
        try:
            from modules.roi_validation import (
                ROIValidationError,
                validate_roi_coords,
            )
            import config as _cfg

            roi_coords = validate_roi_coords(
                roi_coords, max_area_ha=getattr(_cfg, "MAX_ROI_AREA_HA", 10_000)
            )
        except ROIValidationError as ve:
            return jsonify({"success": False, "error": f"Invalid ROI: {ve}"})

        # Use the sanitized name as the progress-dict key so the JS client,
        # which polls /progress/<safe_name>, always hits the same key the
        # pipeline is writing into.
        project_name = _get_project_safe_name(project_name)
        analysis_date = data.get("analysis_date")
        time_range_days = data.get("time_range_days", 90)  # Default 3 months

        if not analysis_date:
            from datetime import datetime

            analysis_date = datetime.now().strftime("%Y-%m-%d")

        # Calculate time window based on user selection
        from datetime import datetime, timedelta

        end_dt = datetime.strptime(analysis_date, "%Y-%m-%d")
        start_dt = end_dt - timedelta(days=time_range_days)
        start_date = start_dt.strftime("%Y-%m-%d")
        end_date = end_dt.strftime("%Y-%m-%d")

        analysis_progress[project_name] = {"status": "Starting...", "percent": 5}

        def update_progress(msg):
            current = analysis_progress.get(project_name, {"percent": 0})
            new_percent = min(current["percent"] + 10, 95)
            analysis_progress[project_name] = {"status": msg, "percent": new_percent}

        # Run Pipeline
        result = main.run_pipeline(
            roi_coords=roi_coords,
            project_name=project_name,
            start_date=start_date,
            end_date=end_date,
            progress_callback=update_progress,
        )

        if result:
            # Map is already generated by main.py pipeline
            project_name_safe = result["project_name_safe"]
            analysis_progress[project_name] = {"status": "Complete", "percent": 100}
            return jsonify(
                {
                    "success": True,
                    "project_name": project_name_safe,
                    "available_dates": result.get("available_dates", []),
                }
            )
        else:
            analysis_progress[project_name] = {"status": "Failed", "percent": 0}
            return jsonify({"success": False, "error": "Pipeline failed"})

    except Exception as e:
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)})


@app.route("/dashboard/<project_name>")
def dashboard(project_name):
    project_name_safe = _get_project_safe_name(project_name)
    output_dir = os.path.join("output", project_name_safe)
    csv_path = os.path.join(output_dir, f"SmartHarvest_{project_name_safe}.csv")
    report_path = os.path.join(output_dir, f"Report_{project_name_safe}.md")
    metadata_path = os.path.join(output_dir, f"metadata_{project_name_safe}.json")

    # Read Metadata Stats
    stats = []
    meta_list = []
    if os.path.exists(metadata_path):
        try:
            with open(metadata_path, "r") as f:
                meta_list = json.load(f)
                # Separate list for image counts to ensure specific ordering
                image_stats = []
                topo_stat = None

                for item in meta_list:
                    if "source" in item:
                        if item["source"] == "ROI Stats":
                            stats.append(
                                {
                                    "label": "Area (ha)",
                                    "value": f"{item.get('area_ha', 0):.2f}",
                                }
                            )
                            stats.append(
                                {
                                    "label": "Analysis Window",
                                    "value": item.get("analysis_range", "N/A"),
                                }
                            )
                        elif item["source"] == "SRTM":
                            topo_stat = {
                                "label": "Topography",
                                "value": "Static (SRTM)",
                            }
                        elif "image_count" in item:
                            image_stats.append(
                                {
                                    "label": f"{item['source']} Images",
                                    "value": str(item["image_count"]),
                                }
                            )

                # Append image stats
                stats.extend(image_stats)

                # Append Topography last
                if topo_stat:
                    stats.append(topo_stat)

        except Exception as e:
            print(f"Error reading metadata: {e}")

    # Fallback: read from CSV if no stats from metadata
    if not stats and os.path.exists(csv_path):
        try:
            df = pd.read_csv(csv_path)
            stats.append({"label": "Total Rows", "value": str(len(df))})
            if "date" in df.columns:
                stats.append(
                    {"label": "Unique Dates", "value": str(df["date"].nunique())}
                )
                stats.append(
                    {
                        "label": "Date Range",
                        "value": f"{df['date'].min()} to {df['date'].max()}",
                    }
                )
            if "satellite" in df.columns:
                sats = set()
                for val in df["satellite"].dropna():
                    sats.update(str(val).split(","))
                stats.append({"label": "Satellites", "value": ", ".join(sorted(sats))})
        except Exception as e:
            print(f"Error reading CSV for stats: {e}")

    # If still no stats, add placeholder
    if not stats:
        stats.append({"label": "Status", "value": "Data not yet available"})

    # Generate Charts
    charts_html = {}
    if os.path.exists(csv_path):
        try:
            df = pd.read_csv(csv_path)
            # charts_html['temporal_trends'] = charts.create_temporal_trends(df)  # Removed per user request
            charts_html["histograms"] = charts.create_histograms(df)
            # charts_html['correlation'] = charts.create_correlation_matrix(df)  # Removed per user request
        except Exception as e:
            print(f"Error generating charts: {e}")

    # Available dates for date selector
    available_dates = (
        visualize_data_map.get_available_dates(csv_path)
        if os.path.exists(csv_path)
        else []
    )

    # Read Time Series Data
    ts_path = os.path.join(output_dir, f"timeseries_{project_name_safe}.json")
    ts_data = {}
    if os.path.exists(ts_path):
        with open(ts_path, "r") as f:
            ts_data = json.load(f)

    # Read Report
    report_html = "<p>Report not found.</p>"
    if os.path.exists(report_path):
        with open(report_path, "r") as f:
            report_html = markdown.markdown(f.read(), extensions=["tables"])

    return render_template(
        "dashboard.html",
        project_name=project_name_safe,
        stats=stats,
        report_html=report_html,
        ts_data=ts_data,
        available_dates=available_dates,
        charts=charts_html,
    )


@app.route("/map/<project_name>")
def get_map(project_name):
    """
    Serve the map HTML. Generates it if it doesn't exist.
    """
    project_name_safe = _get_project_safe_name(project_name)
    output_dir = os.path.join("output", project_name_safe)
    csv_path = os.path.join(output_dir, f"SmartHarvest_{project_name_safe}.csv")
    map_filename = f"Map_{project_name_safe}.html"
    map_path = os.path.join(output_dir, map_filename)

    # Regenerate the map if:
    # - it doesn't exist yet, or
    # - `ml_weekly/` is newer than the cached map. This covers projects
    #   whose map was generated before the ML pipeline finished — those
    #   HTMLs are missing the "ML Clusters (<week>)" overlay entirely,
    #   and without this check they'd keep serving stale content.
    ml_dir = os.path.join(output_dir, "ml_weekly")
    needs_regen = os.path.exists(csv_path) and (
        not os.path.exists(map_path)
        or (
            os.path.exists(ml_dir)
            and os.path.getmtime(ml_dir) > os.path.getmtime(map_path)
        )
    )
    if needs_regen:
        print(f"Generating map for {project_name}...")
        try:
            visualize_data_map.create_verification_map(csv_path, map_path)
        except Exception as e:
            print(f"Error generating map: {e}")
            return (
                f"<html><body><h2>Error generating map</h2><pre>{e}</pre></body></html>",
                500,
            )

    # Check if map exists now
    if not os.path.exists(map_path):
        return (
            f"<html><body><h2>Map not available</h2><p>CSV: {os.path.exists(csv_path)}</p><p>Map path: {map_path}</p></body></html>",
            404,
        )

    return send_from_directory(output_dir, map_filename)


@app.route("/download/<project_name>")
def download_csv(project_name):
    project_name_safe = _get_project_safe_name(project_name)
    output_dir = os.path.join("output", project_name_safe)
    csv_filename = f"SmartHarvest_{project_name_safe}.csv"
    return send_from_directory(output_dir, csv_filename, as_attachment=True)


@app.route("/download_report/<project_name>")
def download_report(project_name):
    project_name_safe = _get_project_safe_name(project_name)
    output_dir = os.path.join("output", project_name_safe)
    report_filename = f"Report_{project_name_safe}.md"
    if os.path.exists(os.path.join(output_dir, report_filename)):
        return send_from_directory(output_dir, report_filename, as_attachment=True)
    else:
        return "Report not found", 404


# ========== ML Anomaly Detection Routes ==========


@app.route("/ml_map/<project_name>")
def ml_map(project_name):
    """
    Serve ML anomaly detection map for a specific week.
    Query param: ?week=YYYY-Wxx (default: latest)
    """
    from tools import visualize_ml_map

    project_name_safe = _get_project_safe_name(project_name)
    output_dir = os.path.join("output", project_name_safe)
    ml_dir = os.path.join(output_dir, "ml_weekly")

    if not os.path.exists(ml_dir):
        return (
            "<html><body><h2>ML Analysis Not Available</h2><p>Run ML pipeline first: <code>python run_ml_weekly.py "
            + project_name
            + "</code></p></body></html>",
            404,
        )

    # Get week_id from query param or use latest
    week_id = request.args.get("week", None)

    if not week_id:
        # Get latest week
        weekly_dir = os.path.join(ml_dir, "weekly")
        week_folders = sorted([f for f in os.listdir(weekly_dir) if f.startswith("20")])
        if not week_folders:
            return "<html><body><h2>No ML Weeks Found</h2></body></html>", 404
        week_id = week_folders[-1]

    map_filename = f"ml_map_{week_id}.html"
    map_path = os.path.join(ml_dir, map_filename)

    # Generate map if it doesn't exist
    if not os.path.exists(map_path):
        print(f"[ML Map] Generating map for {week_id}...")
        try:
            visualize_ml_map.create_ml_anomaly_map(ml_dir, week_id, map_path)
        except Exception as e:
            print(f"[ML Map] Error: {e}")
            import traceback

            traceback.print_exc()
            return (
                f"<html><body><h2>Error Generating ML Map</h2><pre>{e}</pre></body></html>",
                500,
            )

    if not os.path.exists(map_path):
        return "<html><body><h2>ML Map Not Available</h2></body></html>", 404

    return send_from_directory(ml_dir, map_filename)


@app.route("/api/ml_weeks/<project_name>")
def ml_weeks_api(project_name):
    """
    Return list of available weeks with metadata.
    """
    project_name_safe = _get_project_safe_name(project_name)
    output_dir = os.path.join("output", project_name_safe)
    ml_dir = os.path.join(output_dir, "ml_weekly")
    weekly_dir = os.path.join(ml_dir, "weekly")

    if not os.path.exists(weekly_dir):
        return jsonify({"weeks": []})

    week_folders = sorted([f for f in os.listdir(weekly_dir) if f.startswith("20")])

    weeks = []
    for week_id in week_folders:
        week_path = os.path.join(weekly_dir, week_id)
        cluster_csv = os.path.join(week_path, f"cluster_map_{week_id}.csv")
        anomaly_csv = os.path.join(week_path, f"anomalies_{week_id}.csv")

        if not os.path.exists(cluster_csv):
            continue

        try:
            df = pd.read_csv(cluster_csv)
            total_clusters = len(
                df[df["cluster_label"] != -1]["cluster_label"].unique()
            )

            anomalies_count = 0
            if os.path.exists(anomaly_csv):
                anom_df = pd.read_csv(anomaly_csv)
                anomalies_count = len(anom_df)

            weeks.append(
                {
                    "week_id": week_id,
                    "clusters_count": total_clusters,
                    "anomalies_count": anomalies_count,
                    "total_pixels": len(df),
                }
            )
        except Exception as e:
            print(f"[API] Error reading {week_id}: {e}")
            continue

    return jsonify({"weeks": weeks})


@app.route("/api/ml_cluster/<project_name>/<week_id>/<int:cluster_label>")
def ml_cluster_detail(project_name, week_id, cluster_label):
    """
    Return detailed info for a specific cluster (for sidebar).
    """
    project_name_safe = _get_project_safe_name(project_name)
    output_dir = os.path.join("output", project_name_safe)
    ml_dir = os.path.join(output_dir, "ml_weekly")
    cluster_csv = os.path.join(ml_dir, "weekly", week_id, f"cluster_map_{week_id}.csv")

    if not os.path.exists(cluster_csv):
        return jsonify({"error": "Cluster data not found"}), 404

    try:
        df = pd.read_csv(cluster_csv)

        # Backward compatibility: add cluster_status if missing
        if "cluster_status" not in df.columns:
            df["cluster_status"] = "unknown"

        cluster_data = df[df["cluster_label"] == cluster_label]

        if len(cluster_data) == 0:
            return jsonify({"error": "Cluster not found"}), 404

        track_id = int(cluster_data["track_id"].iloc[0])
        status = cluster_data["cluster_status"].iloc[0]
        pixel_count = len(cluster_data)
        outlier_score_mean = float(cluster_data["outlier_score"].mean())

        # Get tracking history
        history = _get_cluster_history(ml_dir, track_id, week_id)

        # Get feature values (mean per cluster)
        feature_cols = [
            c
            for c in cluster_data.columns
            if c
            not in [
                "cluster_label",
                "outlier_score",
                "track_id",
                "cluster_status",
                "lat",
                "lon",
                ".geo",
                "date",
                "satellite",
                "spatial_id",
            ]
        ]

        features = {}
        for col in feature_cols:
            if col in cluster_data.columns:
                features[col] = float(cluster_data[col].mean())

        return jsonify(
            {
                "track_id": track_id,
                "cluster_label": cluster_label,
                "status": status,
                "pixel_count": pixel_count,
                "outlier_score_mean": outlier_score_mean,
                "history": history,
                "features": features,
            }
        )

    except Exception as e:
        print(f"[API] Error: {e}")
        import traceback

        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


def _get_cluster_history(ml_dir, track_id, current_week_id):
    """
    Get tracking history for a cluster across weeks.

    Args:
        ml_dir: Path to ml_weekly directory
        track_id: Track ID to search for
        current_week_id: Current week ID

    Returns:
        list: History entries [{week_id, pixel_count, outlier_score, status}]
    """
    weekly_dir = os.path.join(ml_dir, "weekly")
    week_folders = sorted([f for f in os.listdir(weekly_dir) if f.startswith("20")])

    # Only include weeks up to current_week_id
    week_folders = [w for w in week_folders if w <= current_week_id]

    history = []
    for week_id in week_folders:
        cluster_csv = os.path.join(weekly_dir, week_id, f"cluster_map_{week_id}.csv")
        if not os.path.exists(cluster_csv):
            continue

        try:
            df = pd.read_csv(cluster_csv)
            track_data = df[df["track_id"] == track_id]

            if len(track_data) > 0:
                history.append(
                    {
                        "week_id": week_id,
                        "pixel_count": len(track_data),
                        "outlier_score": float(track_data["outlier_score"].mean()),
                        "status": track_data["cluster_status"].iloc[0],
                    }
                )
        except Exception:
            continue

    return history


if __name__ == "__main__":
    port = int(os.environ.get("SMARTHARVEST_PORT", 5001))
    print("SmartHarvest Web App Started")
    print(f"Open: http://127.0.0.1:{port}")
    app.run(debug=True, host="127.0.0.1", port=port)
