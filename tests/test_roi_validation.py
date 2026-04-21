"""Unit tests for modules/roi_validation.py."""
from __future__ import annotations

import pytest

from modules.roi_validation import ROIValidationError, validate_roi_coords


_VALID_SQUARE = [
    [
        [12.82, 46.10],
        [12.83, 46.10],
        [12.83, 46.11],
        [12.82, 46.11],
        [12.82, 46.10],
    ]
]


def test_validate_accepts_well_formed_polygon():
    out = validate_roi_coords(_VALID_SQUARE)
    assert out[0][0] == [12.82, 46.10]


def test_validate_rejects_too_few_vertices():
    bad = [[[0, 0], [1, 1], [0, 0]]]  # only 3 vertices (closed)
    with pytest.raises(ROIValidationError, match="at least 4"):
        validate_roi_coords(bad)


def test_validate_rejects_unclosed_ring():
    bad = [
        [
            [12.82, 46.10],
            [12.83, 46.10],
            [12.83, 46.11],
            [12.82, 46.11],
            # missing closing vertex
        ]
    ]
    with pytest.raises(ROIValidationError, match="not closed"):
        validate_roi_coords(bad)


def test_validate_rejects_out_of_range_latitude():
    bad = [[[0, 100], [1, 100], [1, 101], [0, 101], [0, 100]]]
    with pytest.raises(ROIValidationError, match="latitude"):
        validate_roi_coords(bad)


def test_validate_rejects_out_of_range_longitude():
    bad = [[[200, 10], [201, 10], [201, 11], [200, 11], [200, 10]]]
    with pytest.raises(ROIValidationError, match="longitude"):
        validate_roi_coords(bad)


def test_validate_rejects_antimeridian_span():
    bad = [
        [
            [-170, 10],
            [170, 10],
            [170, 11],
            [-170, 11],
            [-170, 10],
        ]
    ]
    with pytest.raises(ROIValidationError, match="antimeridian"):
        validate_roi_coords(bad)


def test_validate_rejects_oversized_polygon():
    # ~1° × 1° at the equator ≈ 12_300 km² = 1_230_000 ha — easily over 1 ha cap
    big = [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]
    with pytest.raises(ROIValidationError, match="area"):
        validate_roi_coords(big, max_area_ha=1)
