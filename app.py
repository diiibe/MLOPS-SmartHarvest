import os
import time
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


# ---------------------------------------------------------------------------
# Per-project in-memory cache
# ---------------------------------------------------------------------------
#
# The Week navigator hits `/api/variable_week` and `/api/week_stats` on
# every prev / next click, and on a 740 k-row CSV (Fantinel scale)
# `pd.read_csv` alone burns 600-900 ms per call. We cache the parsed
# DataFrame keyed by project, with an mtime stamp so the next pipeline
# run cleanly invalidates the entry. A second-level cache stores
# already-computed per-(variable, week) frames so subsequent scrubs
# over the same data are O(1).
#
# Memory cost: a 750 k-row × 18-col DataFrame is ~120 MB in RAM. We
# evict the least-recently-used project once 5 are loaded so a
# multi-tab / multi-project session doesn't grow unbounded.
# ---------------------------------------------------------------------------

_PROJECT_CACHE: dict = {}
_PROJECT_CACHE_MAX = 5
_PROJECT_CACHE_LRU: list = []  # most-recent at the end


def _project_csv_path(project_name_safe: str) -> str:
    return os.path.join(
        "output", project_name_safe, f"SmartHarvest_{project_name_safe}.csv"
    )


def _evict_lru_if_full() -> None:
    while len(_PROJECT_CACHE_LRU) > _PROJECT_CACHE_MAX:
        oldest = _PROJECT_CACHE_LRU.pop(0)
        _PROJECT_CACHE.pop(oldest, None)


def _touch_lru(project_name_safe: str) -> None:
    if project_name_safe in _PROJECT_CACHE_LRU:
        _PROJECT_CACHE_LRU.remove(project_name_safe)
    _PROJECT_CACHE_LRU.append(project_name_safe)
    _evict_lru_if_full()


def _load_project_df(project_name_safe: str):
    """Return a parsed DataFrame for the project, cached + mtime-checked.

    Adds two derived columns we lean on in every API call (`date_dt`
    and `week`) so we don't recompute them per request.
    """
    csv_path = _project_csv_path(project_name_safe)
    if not os.path.exists(csv_path):
        return None
    mtime = os.path.getmtime(csv_path)
    cached = _PROJECT_CACHE.get(project_name_safe)
    if cached and cached["mtime"] == mtime:
        _touch_lru(project_name_safe)
        return cached["df"]
    df = pd.read_csv(csv_path)
    if "date" in df.columns:
        df["date_dt"] = pd.to_datetime(df["date"], errors="coerce")
        df["week"] = df["date_dt"].dt.strftime("%G-W%V")
    _PROJECT_CACHE[project_name_safe] = {
        "mtime": mtime,
        "df": df,
        # Sub-cache for already-computed (variable, week) aggregates.
        "frames": {},
        # Sub-cache for week_stats responses keyed by week_id.
        "week_stats": {},
    }
    _touch_lru(project_name_safe)
    return df


def _get_project_cache(project_name_safe: str):
    """Return the cache entry (loading it if needed). `None` if no CSV."""
    if _load_project_df(project_name_safe) is None:
        return None
    return _PROJECT_CACHE[project_name_safe]


def _get_weekly_frame(project_name_safe: str, variable: str, week_id: str):
    """Pre-compute (and cache) per-pixel weekly mean for `(variable, week)`.

    Returns the aggregated DataFrame with columns `[lat, lon, variable]`,
    or `None` when the slice is empty / the variable doesn't exist.
    """
    cache = _get_project_cache(project_name_safe)
    if cache is None:
        return None
    df = cache["df"]
    if variable not in df.columns:
        return None
    key = (variable, week_id)
    frames = cache["frames"]
    if key in frames:
        return frames[key]
    block = df[(df["week"] == week_id) & df[variable].notna()]
    if block.empty:
        frames[key] = None
        return None
    frame = block.groupby(["lat", "lon"], as_index=False)[variable].mean()
    # Also stash the obs_dates so the variable_week endpoint doesn't
    # iterate the original block twice.
    obs_dates = sorted(block["date"].dropna().unique().tolist())
    frames[key] = (frame, obs_dates)
    return frames[key]


def _to_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _analysis_window_stat(value):
    date_range = str(value or "N/A")
    start, end = None, None
    if " to " in date_range:
        start, end = date_range.split(" to ", 1)
    return {
        "label": "Analysis Window",
        "value": date_range,
        "kind": "window",
        "start": start,
        "end": end,
    }


def _sensor_class(source):
    return (
        str(source)
        .lower()
        .replace("/", "")
        .replace(" ", "-")
        .replace("sentinel-", "s")
        .replace("landsat-89", "landsat")
    )


def _sensor_stat(item):
    retained = _to_int(item.get("image_count"), 0)
    discarded = _to_int(item.get("discarded_images"), 0)
    total = _to_int(item.get("total_images"), retained + discarded)
    if total <= 0:
        total = retained + discarded

    retained_pct = (retained / total * 100) if total else 0
    discarded_pct = item.get("discarded_pct")
    if discarded_pct is None:
        discarded_pct = (discarded / total * 100) if total else 0

    return {
        "label": item["source"],
        "value": f"{retained} kept / {discarded} discarded",
        "kind": "sensor",
        "source_class": _sensor_class(item["source"]),
        "retained": retained,
        "discarded": discarded,
        "total": total,
        "retained_pct": f"{retained_pct:.0f}",
        "discarded_pct": f"{float(discarded_pct):.1f}",
    }


@app.route("/")
def index():
    # Pull the Mapbox token from the env so the New Project page can
    # offer Mapbox raster basemaps (Outdoors / Light / Satellite / Dark)
    # the same way landslide-app does. When no token is configured the
    # JS falls back to the original Esri / OSM tiles so the demo path
    # keeps working without any cloud account.
    mapbox_token = os.environ.get("MAPBOX_TOKEN") or os.environ.get(
        "SMARTHARVEST_MAPBOX_TOKEN", ""
    )
    return render_template("index.html", mapbox_token=mapbox_token)


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
            visualize_data_map.create_verification_map(
                csv_path,
                map_path,
                project_name=project_name_safe,
                mapbox_token=os.environ.get("MAPBOX_TOKEN")
                or os.environ.get("SMARTHARVEST_MAPBOX_TOKEN", ""),
            )
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

        # Optional per-run overrides for the download-pipeline knobs the
        # user can set from the "Advanced parameters" panel on the
        # index page. Only fields the client actually sent are passed
        # through; anything missing falls back to the config defaults.
        pipeline_config = data.get("pipeline_config") or {}
        pipeline_overrides = {}
        if "cloud_threshold_s2" in pipeline_config:
            try:
                pipeline_overrides["cloud_threshold_s2"] = int(
                    pipeline_config["cloud_threshold_s2"]
                )
            except (TypeError, ValueError):
                return jsonify({
                    "success": False,
                    "error": "cloud_threshold_s2 must be a number",
                })
        if "cloud_threshold_landsat" in pipeline_config:
            try:
                pipeline_overrides["cloud_threshold_landsat"] = int(
                    pipeline_config["cloud_threshold_landsat"]
                )
            except (TypeError, ValueError):
                return jsonify({
                    "success": False,
                    "error": "cloud_threshold_landsat must be a number",
                })
        if "target_scale" in pipeline_config:
            try:
                pipeline_overrides["target_scale"] = int(
                    pipeline_config["target_scale"]
                )
            except (TypeError, ValueError):
                return jsonify({
                    "success": False,
                    "error": "target_scale must be a number",
                })

        # Run Pipeline
        result = main.run_pipeline(
            roi_coords=roi_coords,
            project_name=project_name,
            start_date=start_date,
            end_date=end_date,
            progress_callback=update_progress,
            **pipeline_overrides,
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
                # Separate list for image counts to ensure specific ordering.
                # SRTM is intentionally NOT shown as a "Topography" row —
                # it's a static reference, listed under Sensors & Variables
                # already, and the user wanted it off this card.
                image_stats = []
                hparam_stats = []

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
                                _analysis_window_stat(item.get("analysis_range"))
                            )
                        elif item["source"] == "Hyperparameters":
                            # Show only the effective values the run used,
                            # rendered as a single compact row each so the
                            # sidebar stays dense.
                            if "cloud_threshold_s2" in item:
                                hparam_stats.append({
                                    "label": "Cloud threshold S2 (%)",
                                    "value": str(item["cloud_threshold_s2"]),
                                })
                            if "cloud_threshold_landsat" in item:
                                hparam_stats.append({
                                    "label": "Cloud threshold Landsat (%)",
                                    "value": str(item["cloud_threshold_landsat"]),
                                })
                            if "target_scale" in item:
                                hparam_stats.append({
                                    "label": "Grid resolution (m)",
                                    "value": str(item["target_scale"]),
                                })
                        elif "image_count" in item:
                            if item["source"] != "SRTM":
                                image_stats.append(_sensor_stat(item))

                # Append image stats below area/window, hyperparameters
                # at the very bottom.
                stats.extend(image_stats)
                stats.extend(hparam_stats)

        except Exception as e:
            print(f"Error reading metadata: {e}")

    # Per-sensor breakdown (used by the Sensors card in the sidebar).
    # Each group carries the variable codes the dashboard renders, the
    # accent token already wired into the rest of the UI, and the
    # `image_count` from the metadata when available — so the card
    # reads as a compact tally instead of a prose blurb.
    SENSOR_GROUPS_SPEC = [
        {
            "code": "S2",
            "label": "Sentinel-2",
            "accent": "russet",
            "variables": ["NDVI", "NDWI", "MNDWI", "NDRE", "IRECI", "S2REP"],
            "metadata_key": "Sentinel-2",
        },
        {
            "code": "S1",
            "label": "Sentinel-1",
            "accent": "sage",
            "variables": ["VH", "VV", "Ratio"],
            "metadata_key": "Sentinel-1",
        },
        {
            "code": "L8",
            "label": "Landsat 8/9",
            "accent": "ochre",
            "variables": ["LST"],
            "metadata_key": "Landsat 8/9",
        },
        {
            "code": "SRTM",
            "label": "SRTM Topography",
            "accent": "slate",
            "variables": ["Slope"],
            "metadata_key": "SRTM",
        },
    ]
    # Pre-compute "valid pixel count" per variable so we can flag a
    # sensor whose CSV columns came back entirely null. The cormor_2
    # case (S2 indices stripped by GEE, leaving 0 rows of valid NDVI)
    # was confusing in the UI: the Sensors card showed "Sentinel-2: 24
    # img" while the map had no S2 layers at all. The new
    # `data_missing` flag lets the template render an explicit
    # "no data" badge in that case.
    valid_per_var: dict = {}
    if os.path.exists(csv_path):
        try:
            cache = _get_project_cache(project_name_safe)
            if cache is not None:
                for col in cache["df"].columns:
                    valid_per_var[col] = int(cache["df"][col].notna().sum())
        except Exception as e:
            print(f"Error reading CSV for sensor validity: {e}")

    sensor_groups = []
    for spec in SENSOR_GROUPS_SPEC:
        meta = next(
            (m for m in meta_list if m.get("source") == spec["metadata_key"]),
            None,
        )
        # `data_missing` = the metadata says we ingested some images
        # but every variable column came back empty. That points at
        # an export-side regression (the cormor_2 / GEE case) rather
        # than a "this sensor isn't available" state, so we use a
        # different visual cue downstream.
        var_validity = {v: valid_per_var.get(v, 0) for v in spec["variables"]}
        any_valid = any(c > 0 for c in var_validity.values())
        ingested = bool(meta and meta.get("image_count"))
        sensor_groups.append({
            "code": spec["code"],
            "label": spec["label"],
            "accent": spec["accent"],
            "variables": spec["variables"],
            "image_count": (meta or {}).get("image_count"),
            "available": True if meta else None,
            # `valid_pixels` per variable so the template can show a
            # per-chip indicator if some indices ingested cleanly
            # while others did not.
            "var_validity": var_validity,
            "data_missing": ingested and not any_valid,
        })

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
                    _analysis_window_stat(f"{df['date'].min()} to {df['date'].max()}")
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
    # Order matters: `acquisition` renders first and carries the full
    # plotly.js payload via CDN; every subsequent chart embeds only
    # its own figure and reuses the already-loaded library. All
    # renderers return `None` when their input isn't available so the
    # template's `{% if charts.X %}` guard skips the section cleanly.
    charts_html = {}
    if os.path.exists(csv_path):
        try:
            df = pd.read_csv(csv_path)
            ml_dir_for_kpi = os.path.join(
                os.path.dirname(csv_path), "ml_weekly"
            )
            ml_dir_for_kpi = (
                ml_dir_for_kpi if os.path.exists(ml_dir_for_kpi) else None
            )
            # Overview tiles (no Plotly bundle hit — pure HTML).
            charts_html["kpi_strip"] = charts.create_kpi_strip(
                df, meta_list, ml_dir_for_kpi
            )
            charts_html["ndvi_sparkline"] = charts.create_ndvi_sparkline(df)
            charts_html["recent_acquisitions"] = charts.create_recent_acquisitions(df)
            # Existing charts (untouched).
            charts_html["acquisition"] = charts.create_acquisition_timeline(df)
            charts_html["cloud_coverage"] = charts.create_cloud_coverage(meta_list)
            charts_html["index_trends"] = charts.create_index_trends(df)
            charts_html["canopy_overlay"] = charts.create_canopy_overlay(df)
            charts_html["water_overlay"] = charts.create_water_overlay(df)
            charts_html["radar_overlay"] = charts.create_radar_overlay(df)
            charts_html["thermal_vs_vigour"] = charts.create_thermal_vs_vigour(df)
            charts_html["distributions"] = charts.create_distributions(df)
            charts_html["correlation"] = charts.create_correlation(df)
            charts_html["ndvi_by_slope"] = charts.create_ndvi_by_slope(df)
            # New phase-1 additions.
            charts_html["change_detection"] = charts.create_change_detection_summary(df)
            charts_html["completeness"] = charts.create_completeness_matrix(df)
            # Phase-2: phenology + sub-cell + Moran's I.
            charts_html["phenology"] = charts.create_phenology_curve(df)
            charts_html["subcell_heatmap"] = charts.create_subcell_heatmap(df)
            charts_html["morans_i"] = charts.create_morans_i_card(df)
        except Exception as e:
            print(f"Error generating charts: {e}")
            import traceback
            traceback.print_exc()

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
            report_html = markdown.markdown(
                f.read(),
                extensions=["tables", "fenced_code", "sane_lists"],
            )

    # Cache-buster for the map iframe: when the map HTML is regenerated
    # (e.g. because we just added the date-navigator feature) the mtime
    # changes, so Chrome fetches a fresh copy instead of reusing the
    # cached iframe it remembered from the previous dashboard visit.
    map_path = os.path.join(output_dir, f"Map_{project_name_safe}.html")
    if os.path.exists(map_path):
        map_cache_bust = int(os.path.getmtime(map_path))
    else:
        map_cache_bust = int(time.time())

    return render_template(
        "dashboard.html",
        project_name=project_name_safe,
        stats=stats,
        sensor_groups=sensor_groups,
        report_html=report_html,
        ts_data=ts_data,
        available_dates=available_dates,
        charts=charts_html,
        variable_glossary=charts.VARIABLE_GLOSSARY,
        map_cache_bust=map_cache_bust,
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
    # - `ml_weekly/` is newer than the cached map (covers projects whose
    #   map was generated before the ML pipeline finished — those are
    #   missing the "ML Clusters (<week>)" overlay), or
    # - the cached HTML pre-dates the date-navigator feature (the
    #   `__SH_MAP_CONFIG` marker embeds it; an old cache has no widget
    #   no matter how much the user hard-refreshes).
    ml_dir = os.path.join(output_dir, "ml_weekly")
    needs_regen = False
    if os.path.exists(csv_path):
        if not os.path.exists(map_path):
            needs_regen = True
        else:
            if (
                os.path.exists(ml_dir)
                and os.path.getmtime(ml_dir) > os.path.getmtime(map_path)
            ):
                needs_regen = True
            else:
                try:
                    # Feature-detect by the most recent embed sentinel.
                    # Bump the marker every time the embedded payload
                    # grows a field the client needs — currently
                    # `__SH_BASEMAP_CONFIG` (added for the Mapbox
                    # switcher injection). Older maps still carry
                    # `__SH_MAP_CONFIG` but lack the basemap config,
                    # so the panel never renders without a regen.
                    # 32 KB clears the leading CSS + the full embed
                    # without pulling in the ~50 MB of marker
                    # literals that follow.
                    with open(map_path, "r", encoding="utf-8", errors="ignore") as f:
                        head = f.read(32768)
                    if "__SH_LAYER_BADGE" not in head:
                        needs_regen = True
                except OSError:
                    needs_regen = True
    if needs_regen:
        print(f"Generating map for {project_name}...")
        try:
            visualize_data_map.create_verification_map(
                csv_path,
                map_path,
                project_name=project_name_safe,
                mapbox_token=os.environ.get("MAPBOX_TOKEN")
                or os.environ.get("SMARTHARVEST_MAPBOX_TOKEN", ""),
            )
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


@app.route("/api/variable_frame/<project_name>/<variable>/<date>")
def variable_frame(project_name, variable, date):
    """
    Return the raw (lat, lon, value) tuples for a specific variable on a
    specific date. Consumed by the map's date-navigator control to page
    through a layer's historical acquisitions without rebuilding the
    whole map HTML.

    Response shape:
        {"project": "...", "variable": "...", "date": "YYYY-MM-DD",
         "points": [{"lat": 46.xxxxx, "lon": 12.xxxxx, "value": 0.71}, ...]}
    """
    project_name_safe = _get_project_safe_name(project_name)
    output_dir = os.path.join("output", project_name_safe)
    csv_path = os.path.join(output_dir, f"SmartHarvest_{project_name_safe}.csv")
    if not os.path.exists(csv_path):
        return jsonify({"error": "CSV not found", "points": []}), 404

    try:
        df = pd.read_csv(csv_path, usecols=lambda c: c in (
            "date", "lat", "lon", ".geo", variable
        ))
    except ValueError:
        # Variable column missing from the CSV.
        return jsonify({"error": f"Unknown variable: {variable}", "points": []}), 404

    if variable not in df.columns:
        return jsonify({"error": f"Unknown variable: {variable}", "points": []}), 404

    # Backfill lat/lon from .geo if the column materialisation didn't
    # already produce them (matches visualize_data_map's own handling).
    if ("lat" not in df.columns or "lon" not in df.columns) and ".geo" in df.columns:
        import json as _json

        def _parse(g):
            try:
                data = _json.loads(g) if isinstance(g, str) else g
                return data["coordinates"]
            except Exception:
                return [None, None]

        coords = df[".geo"].apply(_parse)
        df["lon"] = coords.apply(lambda x: x[0])
        df["lat"] = coords.apply(lambda x: x[1])

    # Strict single-date filter: return every pixel observed on
    # exactly this date. No resampling, no per-pixel subsetting —
    # what you see is the full cloud/revisit footprint for the day.
    frame = df[(df["date"] == date) & df[variable].notna()]
    if len(frame):
        # Collapse tile-boundary duplicates (same pixel seen by two
        # overlapping tiles on the same pass) to avoid double-drawing
        # the same marker. This does not reduce unique pixel coverage.
        frame = frame.groupby(["lat", "lon"], as_index=False)[variable].mean()

    points = [
        {"lat": float(r["lat"]), "lon": float(r["lon"]), "value": float(r[variable])}
        for _, r in frame.iterrows()
        if pd.notna(r["lat"]) and pd.notna(r["lon"])
    ]
    return jsonify({
        "project": project_name_safe,
        "variable": variable,
        "date": date,
        "points": points,
    })


@app.route("/api/variable_week/<project_name>/<variable>/<week_id>")
def variable_week(project_name, variable, week_id):
    """
    Per-pixel weekly mean for one variable.

    The Interactive Map's date navigator now steps in ISO weeks, so
    a click on the prev / next arrow asks for an entire week's
    aggregate instead of a single acquisition. Pixels observed
    multiple times in the same week are averaged; pixels not
    observed at all in that week are simply absent — the user-
    visible effect is a stable "weekly view" that does not flicker
    when one of the dates inside the week is cloud-masked.

    `week_id` is the ISO 8601 year-week token, e.g. ``2025-W45``.

    Response shape:
        {"project": "...", "variable": "...", "week": "2025-W45",
         "date_range": "2025-11-03 to 2025-11-09",
         "obs_dates": ["2025-11-04", "2025-11-08"],
         "points": [{"lat": ..., "lon": ..., "value": ...}, ...]}
    """
    project_name_safe = _get_project_safe_name(project_name)
    if not os.path.exists(_project_csv_path(project_name_safe)):
        return jsonify({"error": "CSV not found", "points": []}), 404

    cache = _get_project_cache(project_name_safe)
    if cache is None:
        return jsonify({"error": "CSV not found", "points": []}), 404
    if variable not in cache["df"].columns:
        return jsonify({"error": f"Unknown variable: {variable}", "points": []}), 404

    cached_frame = _get_weekly_frame(project_name_safe, variable, week_id)
    if cached_frame is None:
        empty = jsonify({
            "project": project_name_safe,
            "variable": variable,
            "week": week_id,
            "date_range": "",
            "obs_dates": [],
            "points": [],
        })
        empty.headers["Cache-Control"] = "public, max-age=300"
        return empty

    frame, obs_dates = cached_frame

    # Vectorised dict-list construction is ~3x faster than `iterrows`
    # on 14 k+ rows. The output stays JSON-compatible.
    lat_arr = frame["lat"].to_numpy()
    lon_arr = frame["lon"].to_numpy()
    val_arr = frame[variable].to_numpy()
    points = [
        {"lat": float(lat_arr[i]), "lon": float(lon_arr[i]), "value": float(val_arr[i])}
        for i in range(len(frame))
        if pd.notna(lat_arr[i]) and pd.notna(lon_arr[i])
    ]

    if obs_dates:
        if obs_dates[0] == obs_dates[-1]:
            date_range = obs_dates[0]
        else:
            date_range = f"{obs_dates[0]} → {obs_dates[-1]}"
    else:
        date_range = ""

    if frame[variable].notna().any():
        vmin_week = float(frame[variable].min())
        vmax_week = float(frame[variable].max())
    else:
        vmin_week = vmax_week = None

    response = jsonify({
        "project": project_name_safe,
        "variable": variable,
        "week": week_id,
        "date_range": date_range,
        "obs_dates": obs_dates,
        "vmin": vmin_week,
        "vmax": vmax_week,
        "points": points,
    })
    # Cache for 5 minutes — the underlying CSV is mtime-checked, so a
    # pipeline rerun invalidates the server-side cache; this header
    # only keeps the browser from re-downloading the same week
    # while the user scrubs back and forth.
    response.headers["Cache-Control"] = "public, max-age=300"
    return response


@app.route("/api/week_stats/<project_name>/<week_id>")
def week_stats(project_name, week_id):
    """
    Per-variable vmin / vmax / count for a single ISO week.

    The map's date navigator scrubs the entire legend in lock-step
    with the active layer: when the user steps to a new week the
    JS calls this endpoint once and the legend's vmin / vmax labels
    re-write for every variable, even the ones currently hidden.
    Variables with no observation in that week come back as
    `{vmin: null, vmax: null, count: 0}` so the client can render
    a dash without making a separate "is this variable available?"
    call.
    """
    project_name_safe = _get_project_safe_name(project_name)
    if not os.path.exists(_project_csv_path(project_name_safe)):
        return jsonify({"error": "CSV not found", "variables": {}}), 404

    cache = _get_project_cache(project_name_safe)
    if cache is None:
        return jsonify({"error": "CSV not found", "variables": {}}), 404

    df = cache["df"]
    if "date" not in df.columns:
        return jsonify({"error": "CSV is missing date column", "variables": {}}), 500

    # Memoised — same week scrubbed twice is a single dict lookup.
    week_stats_cache = cache["week_stats"]
    if week_id in week_stats_cache:
        response = jsonify(week_stats_cache[week_id])
        response.headers["Cache-Control"] = "public, max-age=300"
        return response

    week_df = df[df["week"] == week_id]

    # Iterate the canonical schema list rather than column-introspect
    # so the response keys are stable even when a CSV happens to
    # carry an extra non-schema numeric column (e.g. spatial_id).
    import schema as _schema

    candidates = [c for c in _schema.STATS_COLUMNS if c in df.columns]
    out = {}
    for col in candidates:
        # Re-use the per-(variable, week) frame the variable_week
        # endpoint already computed when possible. On the typical
        # navigator path, variable_week fires for the active layer
        # right before week_stats fires for all layers — sharing
        # the cache here turns the second call into a near-free
        # min/max scan.
        cached_frame = _get_weekly_frame(project_name_safe, col, week_id)
        if cached_frame is None:
            out[col] = {"vmin": None, "vmax": None, "count": 0}
            continue
        avg, _obs = cached_frame
        if avg.empty or avg[col].notna().sum() == 0:
            out[col] = {"vmin": None, "vmax": None, "count": 0}
            continue
        vmin = float(avg[col].min())
        vmax = float(avg[col].max())
        # Constant week → null bounds so the client falls back to the
        # embedded global scale for colour mapping.
        if vmin == vmax:
            out[col] = {"vmin": None, "vmax": None, "count": int(len(avg))}
        else:
            out[col] = {
                "vmin": vmin,
                "vmax": vmax,
                "count": int(len(avg)),
            }

    payload = {
        "project": project_name_safe,
        "week": week_id,
        "variables": out,
    }
    week_stats_cache[week_id] = payload
    response = jsonify(payload)
    response.headers["Cache-Control"] = "public, max-age=300"
    return response


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

    # Generate or regenerate the map. The cached HTML is rebuilt when
    # it doesn't exist yet OR when it predates the basemap-switcher
    # embed (sentinel `__SH_BASEMAP_CONFIG`). Same logic the data-map
    # route uses so the two iframes stay feature-aligned.
    needs_regen = not os.path.exists(map_path)
    if not needs_regen:
        try:
            with open(map_path, "r", encoding="utf-8", errors="ignore") as f:
                head = f.read(32768)
            if "__SH_LAYER_BADGE" not in head:
                needs_regen = True
        except OSError:
            needs_regen = True

    if needs_regen:
        print(f"[ML Map] Generating map for {week_id}...")
        try:
            visualize_ml_map.create_ml_anomaly_map(
                ml_dir,
                week_id,
                map_path,
                mapbox_token=os.environ.get("MAPBOX_TOKEN")
                or os.environ.get("SMARTHARVEST_MAPBOX_TOKEN", ""),
            )
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
