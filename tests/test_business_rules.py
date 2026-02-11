"""
Unit Tests for Business Rules and System Contracts.

Tests the core business logic in modules/rules.py to ensure observation
quality evaluation follows the defined contracts and constraints.
"""

import pytest
from modules.rules import evaluate_observation_quality


class TestObservationQuality:
    """Tests for observation quality evaluation logic."""

    def test_perfect_observation_high_confidence(self):
        """Perfect large parcel observation should return SUCCESS."""
        result = evaluate_observation_quality(valid_pixels=100, total_pixels=100, coverage_ratio=1.0, is_small_parcel=False)
        assert result == "SUCCESS", "Perfect observation should be SUCCESS"

    def test_low_coverage_triggers_low_confidence(self):
        """Low coverage should trigger LOW_CONFIDENCE status."""
        result = evaluate_observation_quality(valid_pixels=100, total_pixels=100, coverage_ratio=0.59, is_small_parcel=False)
        assert result == "LOW_CONFIDENCE", "Coverage below 0.60 should be LOW_CONFIDENCE"

    def test_insufficient_pixels_despite_high_coverage(self):
        """High coverage but insufficient absolute pixels should be LOW_CONFIDENCE."""
        result = evaluate_observation_quality(valid_pixels=20, total_pixels=20, coverage_ratio=1.0, is_small_parcel=False)
        assert result == "LOW_CONFIDENCE", "Fewer than 25 pixels should be LOW_CONFIDENCE"

    def test_small_parcel_relaxed_thresholds_pass(self):
        """Small parcel with relaxed thresholds should pass."""
        result = evaluate_observation_quality(valid_pixels=15, total_pixels=20, coverage_ratio=0.75, is_small_parcel=True)
        assert result == "SUCCESS", "Small parcel with 15 pixels should pass"

    def test_small_parcel_below_threshold_fails(self):
        """Small parcel below minimum pixels should fail."""
        result = evaluate_observation_quality(valid_pixels=14, total_pixels=20, coverage_ratio=0.70, is_small_parcel=True)
        assert result == "LOW_CONFIDENCE", "Small parcel with <15 pixels should fail"

    def test_boundary_condition_exact_threshold(self):
        """Values exactly at threshold should pass."""
        result = evaluate_observation_quality(valid_pixels=100, total_pixels=100, coverage_ratio=0.60, is_small_parcel=False)
        assert result == "SUCCESS", "Exact threshold (0.60) should pass"

    @pytest.mark.parametrize(
        "valid_pixels,total_pixels,coverage_ratio,is_small,expected",
        [
            # Standard parcel tests
            (100, 100, 1.0, False, "SUCCESS"),  # Perfect
            (25, 100, 0.60, False, "SUCCESS"),  # Minimum valid
            (24, 100, 0.60, False, "LOW_CONFIDENCE"),  # Below pixel threshold
            (100, 100, 0.59, False, "LOW_CONFIDENCE"),  # Below coverage threshold
            # Small parcel tests
            (15, 20, 0.50, True, "SUCCESS"),  # Minimum valid small parcel
            (14, 20, 0.50, True, "LOW_CONFIDENCE"),  # Below small parcel threshold
            (20, 40, 0.49, True, "LOW_CONFIDENCE"),  # Below small parcel coverage
            # Edge cases
            (0, 100, 0.0, False, "LOW_CONFIDENCE"),  # No valid pixels
            (1, 1, 1.0, False, "LOW_CONFIDENCE"),  # Single pixel
        ],
    )
    def test_observation_quality_parametrized(self, valid_pixels, total_pixels, coverage_ratio, is_small, expected):
        """Parametrized tests for various observation quality scenarios."""
        result = evaluate_observation_quality(
            valid_pixels=valid_pixels,
            total_pixels=total_pixels,
            coverage_ratio=coverage_ratio,
            is_small_parcel=is_small,
        )
        assert result == expected, (
            f"Failed for valid={valid_pixels}, total={total_pixels}, " f"coverage={coverage_ratio}, small={is_small}"
        )


class TestBusinessRuleEdgeCases:
    """Tests for edge cases and error conditions in business rules."""

    def test_zero_total_pixels(self):
        """Zero total pixels should be handled gracefully."""
        # This might raise an exception or return LOW_CONFIDENCE
        # depending on implementation
        try:
            result = evaluate_observation_quality(valid_pixels=0, total_pixels=0, coverage_ratio=0.0, is_small_parcel=False)
            assert result == "LOW_CONFIDENCE", "Zero pixels should be LOW_CONFIDENCE"
        except (ValueError, ZeroDivisionError):
            # If the function raises an exception, that's also acceptable
            pass

    def test_negative_pixels_invalid(self):
        """Negative pixel counts should be invalid."""
        # Implementation should either raise ValueError or return LOW_CONFIDENCE
        try:
            result = evaluate_observation_quality(
                valid_pixels=-10, total_pixels=100, coverage_ratio=0.5, is_small_parcel=False
            )
            assert result == "LOW_CONFIDENCE", "Negative pixels should be invalid"
        except ValueError:
            # Raising ValueError is acceptable
            pass

    def test_coverage_ratio_out_of_bounds(self):
        """Coverage ratio outside [0, 1] should be handled."""
        try:
            result = evaluate_observation_quality(
                valid_pixels=100, total_pixels=100, coverage_ratio=1.5, is_small_parcel=False
            )
            # Should either clamp to 1.0 or raise error
            assert result in ["SUCCESS", "LOW_CONFIDENCE"]
        except ValueError:
            # Raising ValueError is acceptable
            pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
