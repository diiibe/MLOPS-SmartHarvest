import unittest
from modules.rules import evaluate_observation_quality


class TestBusinessRules(unittest.TestCase):
    """
    Deterministic Unit Tests for System Contracts and Constraints.
    Target: modules/rules.py (Pure Logic)
    """

    def test_observation_validity_high_confidence(self):
        """Case: Perfect, large parcel observation."""
        # Total: 100, Valid: 100, Coverage: 1.0 -> SUCCESS
        result = evaluate_observation_quality(valid_pixels=100, total_pixels=100, coverage_ratio=1.0, is_small_parcel=False)
        self.assertEqual(result, "SUCCESS")

    def test_observation_validity_low_coverage(self):
        """Case: Low coverage triggers LOW_CONFIDENCE."""
        # Coverage 0.59 < 0.60 threshold
        result = evaluate_observation_quality(valid_pixels=100, total_pixels=100, coverage_ratio=0.59, is_small_parcel=False)
        self.assertEqual(result, "LOW_CONFIDENCE")

    def test_observation_validity_low_pixels(self):
        """Case: High coverage but insufficient absolute pixels."""
        # Valid: 20 < 25 (Standard Min), Coverage: 1.0
        result = evaluate_observation_quality(valid_pixels=20, total_pixels=20, coverage_ratio=1.0, is_small_parcel=False)
        self.assertEqual(result, "LOW_CONFIDENCE")

    def test_small_parcel_relaxed_thresholds(self):
        """Case: Small parcel uses relaxed thresholds."""
        # Small Parcel: (< 60 pixels logic in caller, passed as flag here)
        # Thresholds: Coverage 0.50, Min Pixels 15

        # Scenario: 20 pixels total, 15 valid. Coverage 0.75.
        # Should PASS (15 >= 15)
        result = evaluate_observation_quality(valid_pixels=15, total_pixels=20, coverage_ratio=0.75, is_small_parcel=True)
        self.assertEqual(result, "SUCCESS")

        # Scenario: 14 pixels valid.
        # Should FAIL (14 < 15)
        result = evaluate_observation_quality(valid_pixels=14, total_pixels=20, coverage_ratio=0.70, is_small_parcel=True)
        self.assertEqual(result, "LOW_CONFIDENCE")

    def test_boundary_conditions_exact_thresholds(self):
        """Case: Values exactly at the threshold should PASS."""
        # Exact 60% coverage
        result = evaluate_observation_quality(valid_pixels=100, total_pixels=100, coverage_ratio=0.60, is_small_parcel=False)
        self.assertEqual(result, "SUCCESS")


if __name__ == "__main__":
    unittest.main()
