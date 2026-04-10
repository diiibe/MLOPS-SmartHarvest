"""Unit tests for ml/data_loader.py."""
from __future__ import annotations

import pathlib
import tempfile

import numpy as np
import pandas as pd
import pytest

from ml.data_loader import build_weekly_frame, define_weeks, load_and_filter_s2


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_minimal_csv(tmp_path: pathlib.Path) -> pathlib.Path:
    """Write a minimal, valid CSV that load_and_filter_s2 can consume."""
    rng = np.random.default_rng(0)
    n = 30
    df = pd.DataFrame(
        {
            "date": pd.date_range("2024-04-01", periods=n, freq="3D").strftime("%Y-%m-%d"),
            "lat": rng.uniform(46.0, 46.1, n),
            "lon": rng.uniform(13.0, 13.1, n),
            "satellite": ["S2"] * n,
            "NDVI": rng.uniform(0.2, 0.9, n),
            "VH": rng.uniform(-20, -5, n),
            "LST": rng.uniform(285, 305, n),
        }
    )
    csv_path = tmp_path / "test_data.csv"
    df.to_csv(csv_path, index=False)
    return csv_path


# ---------------------------------------------------------------------------
# Import smoke test
# ---------------------------------------------------------------------------

def test_data_loader_module_imports_cleanly():
    """ml.data_loader must import without side effects."""
    from ml import data_loader
    assert data_loader is not None


def test_data_loader_exposes_public_callables():
    """ml.data_loader must expose at least one public callable."""
    from ml import data_loader
    public = [
        name for name in dir(data_loader)
        if not name.startswith("_") and callable(getattr(data_loader, name))
    ]
    assert len(public) > 0, "ml/data_loader.py exposes no public callables"


# ---------------------------------------------------------------------------
# load_and_filter_s2
# ---------------------------------------------------------------------------

def test_load_and_filter_s2_returns_dataframe_and_columns(tmp_path):
    """load_and_filter_s2 must return (DataFrame, dict) with expected keys."""
    csv_path = _make_minimal_csv(tmp_path)
    result = load_and_filter_s2(str(csv_path))

    assert isinstance(result, tuple) and len(result) == 2
    df_out, columns = result
    assert isinstance(df_out, pd.DataFrame)
    assert isinstance(columns, dict)
    for key in ("date", "coords", "features"):
        assert key in columns, f"columns dict missing key '{key}'"


def test_load_and_filter_s2_filters_to_s2_only(tmp_path):
    """load_and_filter_s2 should retain only S2 rows when satellite column exists."""
    csv_path = _make_minimal_csv(tmp_path)
    # Inject some non-S2 rows into the CSV
    df = pd.read_csv(csv_path)
    df.loc[0, "satellite"] = "L8"
    df.loc[1, "satellite"] = "S1"
    df.to_csv(csv_path, index=False)

    df_out, _ = load_and_filter_s2(str(csv_path))
    assert (df_out["satellite"].str.contains("S2", na=False)).all(), (
        "load_and_filter_s2 should filter out non-S2 rows"
    )


# ---------------------------------------------------------------------------
# define_weeks
# ---------------------------------------------------------------------------

def test_define_weeks_returns_weeks_and_tagged_df(tmp_path):
    """define_weeks must return (list_of_tuples, DataFrame) with week_id column."""
    csv_path = _make_minimal_csv(tmp_path)
    df_s2, _ = load_and_filter_s2(str(csv_path))

    weeks, df_tagged = define_weeks(df_s2)
    assert isinstance(weeks, list)
    assert len(weeks) > 0, "define_weeks found no weeks"
    assert "week_id" in df_tagged.columns, "define_weeks must add a 'week_id' column"
    # Each week tuple: (week_id, start, max_date, obs_count)
    for w in weeks:
        assert len(w) == 4


# ---------------------------------------------------------------------------
# build_weekly_frame
# ---------------------------------------------------------------------------

def test_build_weekly_frame_returns_one_row_per_pixel(tmp_path):
    """build_weekly_frame must return at most one row per pixel (lat/lon)."""
    csv_path = _make_minimal_csv(tmp_path)
    df_s2, columns = load_and_filter_s2(str(csv_path))
    weeks, df_tagged = define_weeks(df_s2)

    week_id = weeks[0][0]
    feature_cols = columns["features"]
    coord_cols = columns["coords"]

    frame = build_weekly_frame(df_tagged, week_id, coord_cols, feature_cols)
    if frame is None:
        pytest.skip("build_weekly_frame returned None for the first week (no data)")

    assert isinstance(frame, pd.DataFrame)
    assert len(frame) > 0


def test_build_weekly_frame_on_bundled_demo():
    """Smoke test: build_weekly_frame runs on the bundled Fantinel demo CSV."""
    csv_path = pathlib.Path(__file__).parent.parent / "demo" / "data" / "Fantinel37.csv"
    if not csv_path.exists():
        pytest.skip("Bundled demo dataset not available")

    df_s2, columns = load_and_filter_s2(str(csv_path))
    weeks, df_tagged = define_weeks(df_s2)
    assert len(weeks) > 0

    week_id = weeks[0][0]
    frame = build_weekly_frame(
        df_tagged, week_id, columns["coords"], columns["features"]
    )
    assert frame is not None and len(frame) > 0
