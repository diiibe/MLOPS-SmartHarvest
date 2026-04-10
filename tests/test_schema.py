"""Unit tests for schema.py — constants and structure checks."""
from __future__ import annotations

import pytest
import schema


def test_schema_module_imports_cleanly():
    """schema module must import without side effects."""
    assert schema is not None


def test_temporal_columns_is_list_of_strings():
    """TEMPORAL_COLUMNS must be a non-empty list of strings."""
    cols = schema.TEMPORAL_COLUMNS
    assert isinstance(cols, list), "TEMPORAL_COLUMNS should be a list"
    assert len(cols) > 0, "TEMPORAL_COLUMNS must not be empty"
    assert all(isinstance(c, str) for c in cols), "All entries in TEMPORAL_COLUMNS must be strings"


def test_temporal_columns_contains_core_fields():
    """TEMPORAL_COLUMNS must contain the core positional and index fields."""
    required = {"date", "lat", "lon", "satellite"}
    missing = required - set(schema.TEMPORAL_COLUMNS)
    assert not missing, f"TEMPORAL_COLUMNS is missing required fields: {missing}"


def test_stats_columns_is_subset_of_temporal_columns():
    """Every column in STATS_COLUMNS must also appear in TEMPORAL_COLUMNS."""
    temporal_set = set(schema.TEMPORAL_COLUMNS)
    for col in schema.STATS_COLUMNS:
        assert col in temporal_set, (
            f"STATS_COLUMNS contains '{col}' which is not in TEMPORAL_COLUMNS"
        )


def test_column_labels_keys_match_stats_columns():
    """COLUMN_LABELS should have an entry for every column in STATS_COLUMNS."""
    for col in schema.STATS_COLUMNS:
        assert col in schema.COLUMN_LABELS, (
            f"COLUMN_LABELS is missing an entry for STATS_COLUMNS member '{col}'"
        )


def test_column_satellite_keys_match_stats_columns():
    """COLUMN_SATELLITE should map every STATS_COLUMNS entry to a satellite string."""
    for col in schema.STATS_COLUMNS:
        assert col in schema.COLUMN_SATELLITE, (
            f"COLUMN_SATELLITE is missing an entry for '{col}'"
        )
        assert isinstance(schema.COLUMN_SATELLITE[col], str)


def test_column_colors_values_are_lists_of_three():
    """Each color ramp must be a list of exactly 3 color strings."""
    for col, ramp in schema.COLUMN_COLORS.items():
        assert isinstance(ramp, list) and len(ramp) == 3, (
            f"COLUMN_COLORS['{col}'] must be a list of 3 color strings, got {ramp!r}"
        )
