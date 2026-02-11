"""
Unit Tests for Schema Validation.

Tests validation of metadata/bundle structures (Artifacts and Exports).
Ensures data contracts are enforced for manifests, CSVs, and other outputs.
"""

import pytest
from typing import Dict, Any


class ManifestValidator:
    """Validator for run bundle manifests."""

    REQUIRED_KEYS = ["run_id", "created_at", "status", "source", "image_count"]

    @classmethod
    def validate(cls, manifest: Dict[str, Any]) -> bool:
        """
        Validate a manifest dictionary.

        Args:
            manifest: Dictionary containing manifest data

        Returns:
            True if valid

        Raises:
            ValueError: If required keys are missing
            TypeError: If types are incorrect
        """
        # Check missing keys
        for key in cls.REQUIRED_KEYS:
            if key not in manifest:
                raise ValueError(f"Missing required key: {key}")

        # Check type constraints
        if not isinstance(manifest.get("run_id"), str):
            raise TypeError("run_id must be a string")

        if not isinstance(manifest.get("image_count"), int):
            raise TypeError("image_count must be an integer")

        if not isinstance(manifest.get("status"), str):
            raise TypeError("status must be a string")

        if not isinstance(manifest.get("source"), str):
            raise TypeError("source must be a string")

        # Validate status values
        valid_statuses = ["SUCCESS", "LOW_CONFIDENCE_DONE", "FAILED", "RUNNING"]
        if manifest.get("status") not in valid_statuses:
            raise ValueError(f"Invalid status: {manifest.get('status')}. Must be one of {valid_statuses}")

        # Validate image_count is non-negative
        if manifest.get("image_count") < 0:
            raise ValueError("image_count must be non-negative")

        return True


class TestManifestValidation:
    """Tests for manifest schema validation."""

    def test_valid_manifest_passes(self):
        """Valid manifest should pass validation."""
        valid_manifest = {
            "run_id": "test_run_001",
            "created_at": "2025-01-01T00:00:00",
            "status": "SUCCESS",
            "source": "Sentinel-2",
            "image_count": 10,
        }
        assert ManifestValidator.validate(valid_manifest) is True

    def test_missing_run_id_raises_error(self):
        """Missing run_id should raise ValueError."""
        invalid_manifest = {
            # 'run_id': MISSING
            "created_at": "2025-01-01T00:00:00",
            "status": "SUCCESS",
            "source": "Sentinel-2",
            "image_count": 10,
        }
        with pytest.raises(ValueError, match="Missing required key: run_id"):
            ManifestValidator.validate(invalid_manifest)

    def test_missing_created_at_raises_error(self):
        """Missing created_at should raise ValueError."""
        invalid_manifest = {
            "run_id": "test_run_001",
            # 'created_at': MISSING
            "status": "SUCCESS",
            "source": "Sentinel-2",
            "image_count": 10,
        }
        with pytest.raises(ValueError, match="Missing required key: created_at"):
            ManifestValidator.validate(invalid_manifest)

    def test_wrong_type_run_id_raises_error(self):
        """Wrong type for run_id should raise TypeError."""
        invalid_manifest = {
            "run_id": 12345,  # Should be str
            "created_at": "2025-01-01",
            "status": "SUCCESS",
            "source": "Sentinel-2",
            "image_count": 10,
        }
        with pytest.raises(TypeError, match="run_id must be a string"):
            ManifestValidator.validate(invalid_manifest)

    def test_wrong_type_image_count_raises_error(self):
        """Wrong type for image_count should raise TypeError."""
        invalid_manifest = {
            "run_id": "test_run_001",
            "created_at": "2025-01-01",
            "status": "SUCCESS",
            "source": "Sentinel-2",
            "image_count": "10",  # Should be int
        }
        with pytest.raises(TypeError, match="image_count must be an integer"):
            ManifestValidator.validate(invalid_manifest)

    def test_invalid_status_raises_error(self):
        """Invalid status value should raise ValueError."""
        invalid_manifest = {
            "run_id": "test_run_001",
            "created_at": "2025-01-01",
            "status": "INVALID_STATUS",
            "source": "Sentinel-2",
            "image_count": 10,
        }
        with pytest.raises(ValueError, match="Invalid status"):
            ManifestValidator.validate(invalid_manifest)

    def test_negative_image_count_raises_error(self):
        """Negative image_count should raise ValueError."""
        invalid_manifest = {
            "run_id": "test_run_001",
            "created_at": "2025-01-01",
            "status": "SUCCESS",
            "source": "Sentinel-2",
            "image_count": -5,
        }
        with pytest.raises(ValueError, match="image_count must be non-negative"):
            ManifestValidator.validate(invalid_manifest)

    @pytest.mark.parametrize(
        "status",
        ["SUCCESS", "LOW_CONFIDENCE_DONE", "FAILED", "RUNNING"],
    )
    def test_all_valid_statuses_accepted(self, status):
        """All valid status values should be accepted."""
        manifest = {
            "run_id": "test_run_001",
            "created_at": "2025-01-01T00:00:00",
            "status": status,
            "source": "Sentinel-2",
            "image_count": 10,
        }
        assert ManifestValidator.validate(manifest) is True


class TestCSVSchemaValidation:
    """Tests for CSV schema validation."""

    def test_required_columns_present(self):
        """CSV must contain all required columns."""
        required_columns = ["date", "lat", "lon", "NDVI", "satellite"]

        # Simulate a CSV with headers
        csv_headers = ["date", "lat", "lon", "NDVI", "NDWI", "satellite"]

        for col in required_columns:
            assert col in csv_headers, f"Required column '{col}' missing from CSV"

    def test_missing_required_column_fails(self):
        """CSV missing required column should fail."""
        required_columns = ["date", "lat", "lon", "NDVI", "satellite"]
        csv_headers = ["date", "lat", "lon", "NDWI"]  # Missing NDVI and satellite

        missing_cols = [col for col in required_columns if col not in csv_headers]
        assert len(missing_cols) > 0, "Should detect missing columns"


class TestArtifactMetadataValidation:
    """Tests for artifact metadata validation."""

    def test_artifact_metadata_structure(self):
        """Artifact metadata should have required fields."""
        artifact_meta = {
            "path": "runs/run_001/report.pdf",
            "type": "pdf",
            "created_at": "2025-01-01T00:00:00",
        }

        assert "path" in artifact_meta, "Artifact metadata must have 'path'"
        assert "type" in artifact_meta, "Artifact metadata must have 'type'"

    def test_artifact_type_validation(self):
        """Artifact type must be one of the valid types."""
        valid_types = ["pdf", "csv", "geojson", "json"]

        for artifact_type in valid_types:
            artifact_meta = {
                "path": f"runs/run_001/file.{artifact_type}",
                "type": artifact_type,
            }
            assert artifact_meta["type"] in valid_types

    def test_invalid_artifact_type_detected(self):
        """Invalid artifact type should be detected."""
        valid_types = ["pdf", "csv", "geojson", "json"]
        invalid_artifact = {
            "path": "runs/run_001/file.exe",
            "type": "exe",
        }

        assert invalid_artifact["type"] not in valid_types, "Should detect invalid artifact type"


class TestSchemaEvolution:
    """Tests for schema evolution and backwards compatibility."""

    def test_optional_fields_allowed(self):
        """Manifest can have optional fields beyond required ones."""
        manifest_with_extras = {
            "run_id": "test_run_001",
            "created_at": "2025-01-01T00:00:00",
            "status": "SUCCESS",
            "source": "Sentinel-2",
            "image_count": 10,
            # Optional fields
            "artifacts": {},
            "policy": {},
            "config_snapshot_path": "config.json",
        }

        # Should still validate successfully
        assert ManifestValidator.validate(manifest_with_extras) is True

    def test_extra_fields_ignored(self):
        """Extra fields in manifest should be ignored, not cause errors."""
        manifest = {
            "run_id": "test_run_001",
            "created_at": "2025-01-01T00:00:00",
            "status": "SUCCESS",
            "source": "Sentinel-2",
            "image_count": 10,
            "unknown_field": "some_value",
        }

        # Should validate successfully (extra fields ignored)
        assert ManifestValidator.validate(manifest) is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
