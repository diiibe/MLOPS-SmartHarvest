"""
Reporting module: generates acquisition_log.txt and validation report.
"""

import os
import datetime
import collections

import pandas as pd
import config


def generate_acquisition_log(csv_path, acq_log_path, metadata_list=None):
    """
    Parse the temporal CSV and write an acquisition_log.txt.
    If metadata_list is provided, appends discarded image info.

    Format:
        YYYY-MM-DD: S2
        YYYY-MM-DD: S1
        YYYY-MM-DD: S2,L8
    """
    if not csv_path or not os.path.exists(csv_path):
        return None

    try:
        df = pd.read_csv(csv_path, usecols=["date", "satellite"])
        # Group by date and collect unique satellites
        log_entries = {}
        for date, group in df.groupby("date"):
            sats = sorted(
                set(
                    sat.strip()
                    for row in group["satellite"].dropna()
                    for sat in str(row).split(",")
                    if sat.strip()
                )
            )
            log_entries[date] = sats

        lines = []
        for date in sorted(log_entries):
            sats_str = ",".join(log_entries[date])
            lines.append(f"{date}: {sats_str}")

        if metadata_list:
            s2_meta = next(
                (m for m in metadata_list if m.get("source") == "Sentinel-2"), None
            )
            if s2_meta and "discarded_images" in s2_meta:
                lines.append(
                    f"\n# Discarded S2 images (clouds > {config.CLOUD_THRESHOLD_S2}%): {s2_meta['discarded_images']}"
                )

        with open(acq_log_path, "w") as f:
            f.write("\n".join(lines) + "\n")

        return acq_log_path, log_entries
    except Exception as e:
        print(f"Warning: Could not generate acquisition log: {e}")
        return None, {}


def _format_cloud_shadow_stats(metadata_list):
    """
    Format cloud and shadow coverage statistics as markdown.

    Args:
        metadata_list: List of metadata dicts

    Returns:
        str: Markdown formatted text
    """
    output = ""

    for meta in metadata_list:
        source = meta.get("source", "Unknown")

        # Sentinel-2: cloud + shadow
        if source == "Sentinel-2":
            cloud_cov = meta.get("cloud_coverage", {})
            shadow_cov = meta.get("shadow_coverage", {})

            output += f"**{source}**:\n"
            output += f"- Mean cloud coverage: {cloud_cov.get('mean', 0):.1f}%\n"
            output += f"- Max cloud coverage: {cloud_cov.get('max', 0):.1f}%\n"
            output += f"- Mean shadow coverage: {shadow_cov.get('mean', 0):.1f}%\n"
            output += f"- Max shadow coverage: {shadow_cov.get('max', 0):.1f}%\n\n"

        # Landsat: cloud + QA masked
        elif source == "Landsat 8/9":
            cloud_cov = meta.get("cloud_coverage", {})
            qa_masked = meta.get("qa_masked", {})

            output += f"**{source}**:\n"
            output += f"- Mean cloud coverage: {cloud_cov.get('mean', 0):.1f}%\n"
            output += f"- Max cloud coverage: {cloud_cov.get('max', 0):.1f}%\n"
            output += f"- Mean QA masked: {qa_masked.get('mean', 0):.1f}%\n"
            output += f"- Max QA masked: {qa_masked.get('max', 0):.1f}%\n\n"

    if not output:
        output = "_No cloud/shadow statistics available._\n\n"

    return output


def _format_threshold_sensitivity(metadata_list, thresholds=None):
    """
    Render a "what if we had used a different cloud threshold?" table.

    For each optical / thermal source that stashed `cloud_per_image_pct`
    during acquisition (Sentinel-2, Landsat 8/9), count how many scenes
    would have been kept at a range of hypothetical thresholds and
    compare against the one actually used. This turns an abstract knob
    ("we filter at 50%") into something concrete the user can calibrate
    against a real dataset.

    Args:
        metadata_list: list of metadata dicts produced by the acquisition
            modules. Entries without `cloud_per_image_pct` are skipped.
        thresholds: optional iterable of percentages to probe. Defaults
            to a pragmatic sweep from 10 to 100 in steps of 10.

    Returns:
        str: markdown text, or a short placeholder if no source exposes
        a per-image cloud array (e.g. runs that pre-date this feature).
    """
    if thresholds is None:
        thresholds = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]

    rows = []
    for meta in metadata_list:
        per_image = meta.get("cloud_per_image_pct")
        if not per_image:
            continue
        source = meta.get("source", "Unknown")
        used_threshold = meta.get("cloud_threshold_used")
        total = len(per_image)
        for threshold in thresholds:
            kept = sum(1 for p in per_image if p is not None and p < threshold)
            rows.append((source, threshold, kept, total, used_threshold))

    if not rows:
        return (
            "_No per-image cloud-coverage arrays were captured for this run — "
            "counterfactual sensitivity table not available._\n\n"
        )

    # Group by source so the table reads top-to-bottom per sensor.
    output = (
        "For each optical / thermal source, below is the number of scenes "
        "that would have passed the cloud filter at various thresholds "
        "(exclusive, as `CLOUDY_PIXEL_PERCENTAGE < threshold`). The "
        "*[used]* marker highlights the threshold applied to the run on "
        "disk; tightening it always keeps fewer scenes, loosening it keeps "
        "more, saturating at the total count in the window.\n\n"
    )

    by_source = {}
    for source, threshold, kept, total, used in rows:
        by_source.setdefault(source, {"rows": [], "total": total, "used": used})
        by_source[source]["rows"].append((threshold, kept))

    for source, payload in by_source.items():
        output += f"**{source}** — {payload['total']} scenes in the window\n\n"
        output += "| Threshold (%) | Kept | Discarded | Kept / Total |\n"
        output += "| ---: | ---: | ---: | :--- |\n"
        for threshold, kept in payload["rows"]:
            marker = " *[used]*" if threshold == payload["used"] else ""
            discarded = payload["total"] - kept
            pct = (kept / payload["total"] * 100) if payload["total"] else 0
            output += (
                f"| {threshold}{marker} | {kept} | {discarded} | "
                f"{pct:.0f}% |\n"
            )
        output += "\n"

    return output


def _format_discarded_images(metadata_list):
    """
    Format discarded images table as markdown.

    Args:
        metadata_list: List of metadata dicts

    Returns:
        str: Markdown table
    """
    table = "| Satellite | Total | Retained | Discarded | Discard Rate | Reason |\n"
    table += "|-----------|-------|----------|-----------|--------------|--------|\n"

    has_data = False

    for meta in metadata_list:
        source = meta.get("source", "Unknown")

        # Skip non-satellite sources
        if source in ["ROI Stats", "SRTM"]:
            continue

        total = meta.get("total_images", 0)
        retained = meta.get("image_count", 0)
        discarded = meta.get("discarded_images", 0)
        discard_rate = meta.get("discarded_pct", 0)
        reason = meta.get("discard_reason", "-")

        # Abbreviate source names
        source_abbrev = source.replace("Sentinel-", "S").replace("Landsat 8/9", "L8/9")

        table += (
            f"| {source_abbrev} | {total} | {retained} | {discarded} | "
            f"{discard_rate:.1f}% | {reason} |\n"
        )
        has_data = True

    if not has_data:
        return "_No discarded images data available._\n\n"

    table += "\n"
    return table


def _format_monitoring_log(output_dir):
    """
    Format monitoring logs from CORE and ML pipelines as markdown.
    """
    sections = []

    # Check for CORE monitoring
    core_path = os.path.join(output_dir, "monitoring_core.json")
    if os.path.exists(core_path):
        try:
            import json

            with open(core_path, "r") as f:
                data = json.load(f)

            section = "### Core Pipeline Performance\n\n"
            section += f"**Total Duration:** {data.get('duration_total_sec', 0):.2f} seconds\n\n"
            section += "| Step | Duration (s) | Metrics |\n"
            section += "| :--- | :--- | :--- |\n"
            for step in data.get("steps", []):
                metrics_str = ", ".join(
                    [f"{k}: {v}" for k, v in step.get("metrics", {}).items()]
                )
                section += f"| {step['name']} | {step['duration_sec']:.2f} | {metrics_str or '-'} |\n"
            sections.append(section)
        except Exception:
            pass

    # Check for ML monitoring
    ml_path = os.path.join(output_dir, "ml_weekly", "monitoring_ml.json")
    if os.path.exists(ml_path):
        try:
            import json

            with open(ml_path, "r") as f:
                data = json.load(f)

            section = "### ML Pipeline Performance\n\n"
            section += f"**Total Duration:** {data.get('duration_total_sec', 0):.2f} seconds\n\n"
            section += "| Step | Duration (s) | Metrics |\n"
            section += "| :--- | :--- | :--- |\n"
            for step in data.get("steps", []):
                metrics_val = step.get("metrics", {})
                if isinstance(metrics_val, dict):
                    metrics_str = ", ".join(
                        [f"{k}: {v}" for k, v in metrics_val.items()]
                    )
                else:
                    metrics_str = str(metrics_val)
                section += f"| {step['name']} | {step['duration_sec']:.2f} | {metrics_str or '-'} |\n"
            sections.append(section)
        except Exception:
            pass

    if not sections:
        return ""

    return "\n## 8. Performance & Monitoring\n\n" + "\n".join(sections)


def _validate_dataset(csv_path, log_entries):
    """
    Validate the dataset for grid consistency and sensor presence.
    Returns a dict with validation results.
    """
    if not csv_path or not os.path.exists(csv_path):
        return {}

    try:
        df = pd.read_csv(csv_path)
        total_rows = len(df)
        unique_dates = df["date"].nunique() if "date" in df.columns else 0

        # Grid consistency: rows per date should be stable
        rows_per_date = df.groupby("date").size()
        grid_ok = rows_per_date.std() < 1  # Allow ±0 variance (exact)
        grid_count = int(rows_per_date.median()) if len(rows_per_date) > 0 else 0

        # Sensor analysis per date
        sensor_analysis = []
        for date in sorted(log_entries):
            sats = log_entries[date]
            sensor_analysis.append((date, sats))

        return {
            "total_rows": total_rows,
            "unique_dates": unique_dates,
            "grid_ok": grid_ok,
            "grid_count": grid_count,
            "rows_per_date": rows_per_date.to_dict(),
            "sensor_analysis": sensor_analysis,
        }
    except Exception as e:
        print(f"Warning: Validation failed: {e}")
        return {}


def generate_report(
    metadata_list,
    csv_path=None,
    output_path="output/Report.md",
    acq_log_path=None,
    ml_dir=None,
):
    """
    Generate acquisition log and a validation report.

    Args:
        metadata_list: List of metadata dicts from pipeline modules.
        csv_path: Path to the assembled temporal CSV.
        output_path: Path to write the .md report.
        acq_log_path: Path to write the acquisition_log.txt.
        ml_dir: Path to ml_weekly directory (optional, for ML analysis section).
    """
    output_dir = os.path.dirname(output_path)

    # 1. Generate acquisition log
    log_result = None
    log_entries = {}
    if csv_path and acq_log_path:
        result = generate_acquisition_log(csv_path, acq_log_path, metadata_list)
        if result and result[0]:
            log_result, log_entries = result
            print(f"[OK] Acquisition log saved: {acq_log_path}")

    # 2. Validate dataset
    validation = _validate_dataset(csv_path, log_entries) if csv_path else {}

    # 3. Extract metadata
    roi_stats = next((m for m in metadata_list if m.get("source") == "ROI Stats"), {})
    area_info = ""
    time_info = ""
    if roi_stats:
        area_info = f"**Area:** {roi_stats.get('area_ha', 0):.2f} ha"
        time_info = f"**Analysis Period:** {roi_stats.get('analysis_range', 'N/A')}"

    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    # 4. Build report
    report = f"""# SmartHarvest Analysis Report
**Generated on:** {now}

## 1. Analysis Overview

{area_info}
{time_info}

"""

    # 5. Global Statistics section
    if validation:
        grid_status = (
            "OK (Stable at {} rows per date)".format(validation["grid_count"])
            if validation["grid_ok"]
            else f"WARNING (Variable rows per date)"
        )

        report += f"""## 2. Dataset Statistics

- **Loading dataset:** `{csv_path or 'N/A'}`
- **Parsing acquisition log:** `{acq_log_path or 'N/A'}`

### Global Statistics
- **Total rows:** {validation['total_rows']}
- **Unique dates:** {validation['unique_dates']}

"""

    report += "\n"

    # 6. Sensor Analysis
    if validation.get("sensor_analysis"):
        report += "### Sensor Analysis\n\n"
        report += "| Date | Sensors |\n"
        report += "| :--- | :--- |\n"
        for date, sats in validation["sensor_analysis"]:
            sats_str = ", ".join(sats) if sats else "None"
            report += f"| {date} | {sats_str} |\n"
        report += "\n"

    # 7. Data Sources Table
    report += """## 3. Data Sources

| Source | Images | Date Range | Bands |
| :--- | :--- | :--- | :--- |
"""
    for item in metadata_list:
        if item.get("source") == "ROI Stats":
            continue
        source = item.get("source", "Unknown")
        count = item.get("image_count", "N/A")
        date_range = item.get("date_range", "N/A")
        bands = ", ".join(item.get("bands", [])) if item.get("bands") else "N/A"
        report += f"| **{source}** | {count} | {date_range} | {bands} |\n"

    # NEW SECTION 4: Cloud & Shadow Coverage
    report += "\n## 4. Cloud & Shadow Coverage\n\n"
    report += _format_cloud_shadow_stats(metadata_list)

    # NEW SECTION 5: Discarded Images
    report += "\n## 5. Discarded Images\n\n"
    report += _format_discarded_images(metadata_list)

    # NEW SECTION 5b: Cloud Threshold Sensitivity (counterfactual)
    report += "\n## 5.1 Cloud Threshold Sensitivity\n\n"
    report += _format_threshold_sensitivity(metadata_list)

    # NEW SECTION 6: ML Weekly Analysis (if available)
    if ml_dir and os.path.exists(ml_dir):
        try:
            from ml.report_utils import (
                generate_ml_summary,
                format_weekly_ml_table,
                format_top_anomalies,
            )

            weekly_stats, top_anomalies = generate_ml_summary(ml_dir)

            if weekly_stats is not None and len(weekly_stats) > 0:
                report += "\n## 6. ML Weekly Analysis\n\n"
                report += "### Weekly Cluster Statistics\n\n"
                report += format_weekly_ml_table(weekly_stats)
                report += "\n### Top Anomalous Clusters\n\n"
                report += format_top_anomalies(top_anomalies)
        except Exception as e:
            print(f"[Warning] Could not generate ML analysis section: {e}")

    report += """
## 7. Variable Reference

| Variable | Source | Description |
| :--- | :--- | :--- |
| NDVI | Sentinel-2 | Normalized Difference Vegetation Index |
| NDWI | Sentinel-2 | Water Index (McFeeters) |
| MNDWI | Sentinel-2 | Modified Water Index |
| NDRE | Sentinel-2 | Red-Edge Index |
| IRECI | Sentinel-2 | Inverted Red-Edge Chlorophyll Index |
| S2REP | Sentinel-2 | Red-Edge Position |
| VH | Sentinel-1 | Vertical-Horizontal Backscatter |
| VV | Sentinel-1 | Vertical-Vertical Backscatter |
| Ratio | Sentinel-1 | VH-VV Ratio |
| LST | Landsat 8/9 | Land Surface Temperature (°C) |
| Slope | SRTM | Terrain Slope (degrees) |
"""

    # 8. Performance Monitoring
    report += _format_monitoring_log(output_dir)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report)

    return output_path
