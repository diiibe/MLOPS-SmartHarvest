"""Shared fixtures for the SmartHarvest test suite."""
from __future__ import annotations

import pathlib

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def synthetic_pixel_dataframe() -> pd.DataFrame:
    """Deterministic three-blob synthetic dataset in (NDVI, VH, LST) space.

    Three well-separated Gaussian blobs, 100 points each. Seed is fixed at 42.
    Used by clustering tests to verify HDBSCAN discovers the three expected
    clusters without relying on real data.
    """
    rng = np.random.default_rng(42)
    n = 100
    blob_low_vigor = rng.normal([0.25, 0.35, 290.0], [0.03, 0.03, 1.5], size=(n, 3))
    blob_mid_vigor = rng.normal([0.55, 0.60, 295.0], [0.03, 0.03, 1.5], size=(n, 3))
    blob_high_vigor = rng.normal([0.80, 0.25, 300.0], [0.03, 0.03, 1.5], size=(n, 3))
    data = np.vstack([blob_low_vigor, blob_mid_vigor, blob_high_vigor])
    df = pd.DataFrame(data, columns=["NDVI", "VH", "LST"])
    df["week"] = "2025-W40"
    df["lat"] = rng.uniform(46.00, 46.05, size=len(df))
    df["lon"] = rng.uniform(13.00, 13.05, size=len(df))
    return df


@pytest.fixture
def fantinel_sample_single_week() -> pd.DataFrame:
    """Load a single week from the bundled demo dataset.

    Skips the test (does not fail it) if the demo dataset is not available.
    """
    csv_path = pathlib.Path(__file__).parent.parent / "demo" / "data" / "Fantinel37.csv"
    if not csv_path.exists():
        pytest.skip("Bundled demo dataset not available (demo/data/Fantinel37.csv)")

    df = pd.read_csv(csv_path)
    # The demo CSV has a 'week' column (e.g. "2025-W40")
    week_cols = [c for c in df.columns if c.lower() == "week"]
    if not week_cols:
        # Fallback: any column whose name contains 'week'
        week_cols = [c for c in df.columns if "week" in c.lower()]
    if not week_cols:
        pytest.skip("Demo CSV does not contain a week column")
    week_col = week_cols[0]
    first_week = df[week_col].dropna().iloc[0]
    return df[df[week_col] == first_week].head(500).reset_index(drop=True)
