"""Unit tests for the cloud-threshold counterfactual table in the report."""
from __future__ import annotations

from modules.reporting import _format_threshold_sensitivity


def test_no_metadata_returns_placeholder():
    out = _format_threshold_sensitivity([])
    assert "counterfactual" in out.lower() or "not available" in out.lower()


def test_metadata_without_per_image_array_falls_back_to_placeholder():
    meta = [
        {"source": "Sentinel-2", "cloud_coverage": {"mean": 12.0}},
        {"source": "Landsat 8/9", "cloud_coverage": {"mean": 40.0}},
    ]
    out = _format_threshold_sensitivity(meta)
    assert "not available" in out.lower()


def test_kept_counts_are_cumulative_and_marker_is_applied():
    # Hand-crafted: five scenes with cloud % 5, 25, 35, 55, 85
    # At threshold 30 (strict `<`), scenes with 5 and 25 pass → kept = 2
    # At threshold 60, scenes 5/25/35/55 pass → kept = 4
    # At threshold 100, every scene passes → kept = 5
    meta = [
        {
            "source": "Sentinel-2",
            "cloud_per_image_pct": [5, 25, 35, 55, 85],
            "cloud_threshold_used": 50,
        }
    ]
    out = _format_threshold_sensitivity(meta, thresholds=[30, 50, 60, 100])

    # Sanity: source header + scene total
    assert "Sentinel-2" in out
    assert "5 scenes in the window" in out

    # Kept values
    lines = [ln for ln in out.splitlines() if ln.startswith("|")]
    # Header + divider + 4 data rows
    assert len(lines) == 6
    # The [used] marker should land on the 50% row exactly
    used_row = [ln for ln in lines if "[used]" in ln]
    assert len(used_row) == 1
    assert "| 50" in used_row[0]

    # Pull numeric columns from the 4 data rows (skip header/divider)
    data_rows = [ln for ln in lines[2:]]

    def kept(row):
        # format: "| 30 | 2 | 3 | 40% |"
        return int(row.split("|")[2].strip())

    assert [kept(r) for r in data_rows] == [2, 3, 4, 5]


def test_multiple_sources_each_get_their_own_table():
    meta = [
        {
            "source": "Sentinel-2",
            "cloud_per_image_pct": [10, 20, 30],
            "cloud_threshold_used": 50,
        },
        {
            "source": "Landsat 8/9",
            "cloud_per_image_pct": [40, 60, 80, 90],
            "cloud_threshold_used": 80,
        },
    ]
    out = _format_threshold_sensitivity(meta, thresholds=[50, 80])
    assert out.count("scenes in the window") == 2
    assert "Sentinel-2" in out and "Landsat 8/9" in out
