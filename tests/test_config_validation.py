"""
Unit Tests for Configuration Validation.

Validates the integrity of the Data Backbone configuration (config.py).
Ensures that time windows, ROIs, and thresholds adhere to data contracts.
"""

import pytest
import sys
import os
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config


class TestROIStructure:
    """Tests for ROI (Region of Interest) structure validation."""

    def test_roi_is_list(self):
        """ROI_COORDS must be a list."""
        assert isinstance(config.ROI_COORDS, list), "ROI_COORDS must be a list"

    def test_roi_not_empty(self):
        """ROI_COORDS must not be empty."""
        assert len(config.ROI_COORDS) > 0, "ROI_COORDS must not be empty"

    def test_roi_minimum_points(self):
        """ROI polygon ring must have at least 4 points (GeoJSON standard)."""
        # Access the first ring (outer shell)
        ring = (
            config.ROI_COORDS[0]
            if isinstance(config.ROI_COORDS[0], list) and isinstance(config.ROI_COORDS[0][0], list)
            else config.ROI_COORDS
        )
        assert len(ring) >= 4, f"ROI Polygon ring must have at least 4 points (got {len(ring)})"

    def test_roi_closed_loop(self):
        """ROI polygon must be a closed loop (first point == last point)."""
        ring = (
            config.ROI_COORDS[0]
            if isinstance(config.ROI_COORDS[0], list) and isinstance(config.ROI_COORDS[0][0], list)
            else config.ROI_COORDS
        )
        first_point = ring[0]
        last_point = ring[-1]
        assert first_point == last_point, "ROI Polygon must be a closed loop (First Point == Last Point)"

    def test_roi_coordinate_structure(self):
        """Each coordinate must be [lon, lat] with numeric values."""
        ring = (
            config.ROI_COORDS[0]
            if isinstance(config.ROI_COORDS[0], list) and isinstance(config.ROI_COORDS[0][0], list)
            else config.ROI_COORDS
        )

        for i, point in enumerate(ring):
            assert isinstance(point, list), f"Coordinate {i} must be a list [lon, lat]"
            assert len(point) == 2, f"Coordinate {i} must have 2 values [lon, lat]"
            assert isinstance(point[0], (int, float)), f"Longitude at {i} must be numeric"
            assert isinstance(point[1], (int, float)), f"Latitude at {i} must be numeric"

    def test_roi_coordinate_bounds(self):
        """Coordinates must be within valid geographic bounds."""
        ring = (
            config.ROI_COORDS[0]
            if isinstance(config.ROI_COORDS[0], list) and isinstance(config.ROI_COORDS[0][0], list)
            else config.ROI_COORDS
        )

        for i, point in enumerate(ring):
            lon, lat = point[0], point[1]
            assert -180 <= lon <= 180, f"Longitude {lon} at point {i} out of bounds [-180, 180]"
            assert -90 <= lat <= 90, f"Latitude {lat} at point {i} out of bounds [-90, 90]"


class TestPhenologicalWindows:
    """Tests for phenological time window validation."""

    def test_t1_dates_valid_format(self):
        """T1 dates must be valid YYYY-MM-DD format."""
        fmt = "%Y-%m-%d"
        try:
            datetime.strptime(config.T1_START, fmt)
            datetime.strptime(config.T1_END, fmt)
        except ValueError as e:
            pytest.fail(f"T1 dates have invalid format: {e}")

    def test_t2_dates_valid_format(self):
        """T2 dates must be valid YYYY-MM-DD format."""
        fmt = "%Y-%m-%d"
        try:
            datetime.strptime(config.T2_START, fmt)
            datetime.strptime(config.T2_END, fmt)
        except ValueError as e:
            pytest.fail(f"T2 dates have invalid format: {e}")

    def test_t1_start_before_end(self):
        """T1 start date must be before T1 end date."""
        fmt = "%Y-%m-%d"
        t1_start = datetime.strptime(config.T1_START, fmt)
        t1_end = datetime.strptime(config.T1_END, fmt)
        assert t1_start < t1_end, f"T1 Start ({config.T1_START}) must be before T1 End ({config.T1_END})"

    def test_t2_start_before_end(self):
        """T2 start date must be before T2 end date."""
        fmt = "%Y-%m-%d"
        t2_start = datetime.strptime(config.T2_START, fmt)
        t2_end = datetime.strptime(config.T2_END, fmt)
        assert t2_start < t2_end, f"T2 Start ({config.T2_START}) must be before T2 End ({config.T2_END})"

    def test_t1_before_t2(self):
        """T1 should start before or at the same time as T2."""
        fmt = "%Y-%m-%d"
        t1_start = datetime.strptime(config.T1_START, fmt)
        t2_start = datetime.strptime(config.T2_START, fmt)
        assert t1_start <= t2_start, "T1 should start before or at the same time as T2"

    def test_t1_ends_before_t2_ends(self):
        """T1 (Vegetative) must end before or when T2 (Maturation) ends."""
        fmt = "%Y-%m-%d"
        t1_end = datetime.strptime(config.T1_END, fmt)
        t2_end = datetime.strptime(config.T2_END, fmt)
        assert t1_end <= t2_end, "T1 (Vegetative) must end before or when T2 (Maturation) ends"

    def test_window_duration_reasonable(self):
        """Time windows should not exceed 365 days (prevents multi-year queries)."""
        fmt = "%Y-%m-%d"
        MAX_DAYS = 365

        t1_start = datetime.strptime(config.T1_START, fmt)
        t1_end = datetime.strptime(config.T1_END, fmt)
        t2_start = datetime.strptime(config.T2_START, fmt)
        t2_end = datetime.strptime(config.T2_END, fmt)

        t1_days = (t1_end - t1_start).days
        t2_days = (t2_end - t2_start).days

        assert t1_days <= MAX_DAYS, f"T1 window too long ({t1_days} days). Max {MAX_DAYS}."
        assert t2_days <= MAX_DAYS, f"T2 window too long ({t2_days} days). Max {MAX_DAYS}."

    def test_minimum_window_duration(self):
        """Time windows should be at least 1 day."""
        fmt = "%Y-%m-%d"

        t1_start = datetime.strptime(config.T1_START, fmt)
        t1_end = datetime.strptime(config.T1_END, fmt)
        t2_start = datetime.strptime(config.T2_START, fmt)
        t2_end = datetime.strptime(config.T2_END, fmt)

        t1_days = (t1_end - t1_start).days
        t2_days = (t2_end - t2_start).days

        assert t1_days >= 1, f"T1 window too short ({t1_days} days). Minimum 1 day."
        assert t2_days >= 1, f"T2 window too short ({t2_days} days). Minimum 1 day."


class TestThresholds:
    """Tests for threshold value validation."""

    def test_cloud_threshold_in_range(self):
        """Cloud threshold must be between 0 and 100."""
        assert 0 <= config.CLOUD_THRESH <= 100, "CLOUD_THRESH must be between 0 and 100"

    def test_cloud_threshold_landsat_in_range(self):
        """Landsat cloud threshold must be between 0 and 100 if defined."""
        if hasattr(config, "CLOUD_THRESH_LANDSAT"):
            assert 0 <= config.CLOUD_THRESH_LANDSAT <= 100, "CLOUD_THRESH_LANDSAT must be between 0 and 100"

    def test_sampling_scale_positive(self):
        """Sampling scale must be positive."""
        assert config.SAMPLING_SCALE > 0, "SAMPLING_SCALE must be positive"

    def test_sampling_scale_reasonable(self):
        """Sampling scale should be reasonable (between 1 and 1000 meters)."""
        assert 1 <= config.SAMPLING_SCALE <= 1000, "SAMPLING_SCALE should be between 1 and 1000 meters"


class TestConfigCompleteness:
    """Tests for configuration completeness."""

    def test_required_attributes_exist(self):
        """All required configuration attributes must exist."""
        required_attrs = [
            "ROI_COORDS",
            "T1_START",
            "T1_END",
            "T2_START",
            "T2_END",
            "CLOUD_THRESH",
            "SAMPLING_SCALE",
        ]

        for attr in required_attrs:
            assert hasattr(config, attr), f"Required configuration attribute '{attr}' is missing"

    def test_roi_name_defined(self):
        """ROI name should be defined for output organization."""
        if hasattr(config, "roi_name"):
            assert isinstance(config.roi_name, str), "roi_name must be a string"
            assert len(config.roi_name) > 0, "roi_name must not be empty"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
