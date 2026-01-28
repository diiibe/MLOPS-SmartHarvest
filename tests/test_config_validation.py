import unittest
import sys
import os
from datetime import datetime

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config


class TestConfigValidation(unittest.TestCase):
    """
    Validates the integrity of the Data Backbone configuration (config.py).
    Ensures that time windows, ROIs, and thresholds adhere to data contracts.
    """

    def test_roi_structure(self):
        """Verify ROI_TEST follows the expected Polygon structure."""
        roi = config.ROI_TEST
        self.assertIsInstance(roi, list, "ROI_TEST must be a list")
        self.assertTrue(len(roi) > 0, "ROI_TEST must not be empty")

        # 1. Structure Check: List of Lines (Polygon) or List of Lists (Simple Polygon)
        # Contract: We expect a Polygon structure [[[lon, lat], ...]]
        # (Assuming simple polygon for now, or MultiPolygon structure)
        
        # Ensure it's a list
        self.assertIsInstance(roi, list, "ROI_TEST must be a list")
        
        # Access the first ring (outer shell)
        ring = roi[0] if isinstance(roi[0], list) and isinstance(roi[0][0], list) else roi
        
        # 2. Minimum Points Check
        # A valid closed ring needs at least 4 points (Triangle + Close point) or 3 if implicitly closed (but GeoJSON standard is 4)
        # We enforce strict GeoJSON compliance: First == Last, Min 4 points.
        self.assertTrue(len(ring) >= 4, f"ROI Polygon ring must have at least 4 points (got {len(ring)})")

        # 3. Closed Loop Check
        first_point = ring[0]
        last_point = ring[-1]
        self.assertEqual(first_point, last_point, "ROI Polygon must be a closed loop (First Point == Last Point)")

        # 4. Coordinate Validity
        for point in ring:
            self.assertIsInstance(point, list, "Coordinate must be a list [lon, lat]")
            self.assertEqual(len(point), 2, "Coordinate must have 2 values [lon, lat]")
            self.assertIsInstance(point[0], (int, float), "Longitude must be numeric")
            self.assertIsInstance(point[1], (int, float), "Latitude must be numeric")
            # Bounds check (simple)
            self.assertTrue(-180 <= point[0] <= 180, f"Longitude {point[0]} out of bounds")
            self.assertTrue(-90 <= point[1] <= 90, f"Latitude {point[1]} out of bounds")

    def test_phenological_windows(self):
        """Verify T1 and T2 time windows are valid and chronological."""
        fmt = "%Y-%m-%d"

        t1_start = datetime.strptime(config.T1_START, fmt)
        t1_end = datetime.strptime(config.T1_END, fmt)
        t2_start = datetime.strptime(config.T2_START, fmt)
        t2_end = datetime.strptime(config.T2_END, fmt)

        # Contract: Start < End
        self.assertTrue(t1_start < t1_end, f"T1 Start ({config.T1_START}) must be before T1 End ({config.T1_END})")
        self.assertTrue(t2_start < t2_end, f"T2 Start ({config.T2_START}) must be before T2 End ({config.T2_END})")

        # Contract: T1 should start before T2 (Vegetative before Maturation)
        self.assertTrue(t1_start <= t2_start, "T1 should start before or at the same time as T2")
        
        # Contract: T1 should end before or when T2 ends
        self.assertTrue(t1_end <= t2_end, "T1 (Vegetative) must end before or when T2 (Maturation) ends")

        # Contract: Max Window Duration (365 days)
        # Prevents accidental multi-year queries that could timeout GEE
        MAX_DAYS = 365
        t1_days = (t1_end - t1_start).days
        t2_days = (t2_end - t2_start).days
        
        self.assertTrue(t1_days <= MAX_DAYS, f"T1 window too long ({t1_days} days). Max {MAX_DAYS}.")
        self.assertTrue(t2_days <= MAX_DAYS, f"T2 window too long ({t2_days} days). Max {MAX_DAYS}.")

    def test_cloud_thresholds(self):
        """Verify cloud thresholds are within valid percentage ranges (0-100)."""
        self.assertTrue(0 <= config.CLOUD_THRESH <= 100, "CLOUD_THRESH must be between 0 and 100")
        if hasattr(config, "CLOUD_THRESH_LANDSAT"):
            self.assertTrue(0 <= config.CLOUD_THRESH_LANDSAT <= 100, "CLOUD_THRESH_LANDSAT must be between 0 and 100")

    def test_sampling_scale(self):
        """Verify sampling scale is positive."""
        self.assertTrue(config.SAMPLING_SCALE > 0, "SAMPLING_SCALE must be positive")


if __name__ == "__main__":
    unittest.main()
