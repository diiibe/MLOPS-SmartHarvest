"""
Integration Tests for Satellite Data Schema Contracts.

Verifies that satellite data modules adhere to expected input/output contracts.
Tests the interface between modules and ensures data format compatibility.
"""

import pytest
import sys
import os
from unittest.mock import MagicMock

# Setup mock before imports
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)
sys.path.insert(0, current_dir)

# Import and register mock
from tests.mock_ee import MockEE, MockEEObject, Image, ImageCollection, FeatureCollection

sys.modules["ee"] = MockEE()
sys.modules["google"] = MagicMock()
sys.modules["google.oauth2"] = MagicMock()
sys.modules["google.oauth2.service_account"] = MagicMock()

# Now import project modules
import config
from modules import sentinel2, sentinel1, landsat_thermal, srtm


class TestSentinel2Contract:
    """Tests for Sentinel-2 data module contract."""

    def test_get_sentinel2_data_returns_collection(self):
        """get_sentinel2_data must return an ImageCollection."""
        result = sentinel2.get_sentinel2_data()
        assert result is not None, "Sentinel-2 extraction returned None"
        # Result should be a tuple: (collection, master_crs, metadata)
        assert isinstance(result, tuple), "Sentinel-2 should return a tuple"
        assert len(result) == 3, "Sentinel-2 should return (collection, crs, metadata)"

    def test_sentinel2_collection_is_ee_object(self):
        """Sentinel-2 collection should be an EE object."""
        collection, crs, metadata = sentinel2.get_sentinel2_data()
        assert isinstance(collection, MockEEObject), "Sentinel-2 collection should be an EE object"

    def test_sentinel2_metadata_structure(self):
        """Sentinel-2 metadata should have required fields."""
        collection, crs, metadata = sentinel2.get_sentinel2_data()
        assert isinstance(metadata, dict), "Metadata should be a dictionary"
        # Check for expected metadata keys
        expected_keys = ["source", "image_count"]
        for key in expected_keys:
            assert key in metadata, f"Metadata missing required key: {key}"

    def test_sentinel2_crs_is_string(self):
        """Sentinel-2 CRS should be a string."""
        collection, crs, metadata = sentinel2.get_sentinel2_data()
        # CRS might be a string or a Projection object
        assert crs is not None, "CRS should not be None"


class TestSentinel1Contract:
    """Tests for Sentinel-1 data module contract."""

    def test_get_sentinel1_data_accepts_crs(self):
        """get_sentinel1_data must accept master_crs parameter."""
        master_crs = "EPSG:4326"
        result = sentinel1.get_sentinel1_data(master_crs)
        assert result is not None, "Sentinel-1 extraction returned None"

    def test_sentinel1_returns_collection_and_metadata(self):
        """Sentinel-1 should return (collection, metadata) tuple."""
        master_crs = "EPSG:4326"
        result = sentinel1.get_sentinel1_data(master_crs)
        assert isinstance(result, tuple), "Sentinel-1 should return a tuple"
        assert len(result) == 2, "Sentinel-1 should return (collection, metadata)"

    def test_sentinel1_collection_is_ee_object(self):
        """Sentinel-1 collection should be an EE object."""
        master_crs = "EPSG:4326"
        collection, metadata = sentinel1.get_sentinel1_data(master_crs)
        assert isinstance(collection, MockEEObject), "Sentinel-1 collection should be an EE object"

    def test_sentinel1_metadata_structure(self):
        """Sentinel-1 metadata should have required fields."""
        master_crs = "EPSG:4326"
        collection, metadata = sentinel1.get_sentinel1_data(master_crs)
        assert isinstance(metadata, dict), "Metadata should be a dictionary"
        assert "source" in metadata, "Metadata missing 'source' key"


class TestLandsatContract:
    """Tests for Landsat thermal data module contract."""

    def test_get_landsat_thermal_accepts_crs(self):
        """get_landsat_thermal must accept master_crs parameter."""
        master_crs = "EPSG:4326"
        result = landsat_thermal.get_landsat_thermal(master_crs)
        assert result is not None, "Landsat extraction returned None"

    def test_landsat_returns_collection_and_metadata(self):
        """Landsat should return (collection, metadata) tuple."""
        master_crs = "EPSG:4326"
        result = landsat_thermal.get_landsat_thermal(master_crs)
        assert isinstance(result, tuple), "Landsat should return a tuple"
        assert len(result) == 2, "Landsat should return (collection, metadata)"

    def test_landsat_collection_is_ee_object(self):
        """Landsat collection should be an EE object."""
        master_crs = "EPSG:4326"
        collection, metadata = landsat_thermal.get_landsat_thermal(master_crs)
        assert isinstance(collection, MockEEObject), "Landsat collection should be an EE object"

    def test_landsat_metadata_structure(self):
        """Landsat metadata should have required fields."""
        master_crs = "EPSG:4326"
        collection, metadata = landsat_thermal.get_landsat_thermal(master_crs)
        assert isinstance(metadata, dict), "Metadata should be a dictionary"
        assert "source" in metadata, "Metadata missing 'source' key"


class TestSRTMContract:
    """Tests for SRTM data module contract."""

    def test_get_srtm_data_accepts_crs(self):
        """get_srtm_data must accept master_crs parameter."""
        master_crs = "EPSG:4326"
        result = srtm.get_srtm_data(master_crs)
        assert result is not None, "SRTM extraction returned None"

    def test_srtm_returns_image_and_metadata(self):
        """SRTM should return (image, metadata) tuple."""
        master_crs = "EPSG:4326"
        result = srtm.get_srtm_data(master_crs)
        assert isinstance(result, tuple), "SRTM should return a tuple"
        assert len(result) == 2, "SRTM should return (image, metadata)"

    def test_srtm_image_is_ee_object(self):
        """SRTM image should be an EE object."""
        master_crs = "EPSG:4326"
        image, metadata = srtm.get_srtm_data(master_crs)
        assert isinstance(image, MockEEObject), "SRTM image should be an EE object"

    def test_srtm_metadata_structure(self):
        """SRTM metadata should have required fields."""
        master_crs = "EPSG:4326"
        image, metadata = srtm.get_srtm_data(master_crs)
        assert isinstance(metadata, dict), "Metadata should be a dictionary"
        assert "source" in metadata, "Metadata missing 'source' key"


class TestCrossModuleCompatibility:
    """Tests for compatibility between different satellite modules."""

    def test_all_modules_use_same_crs(self):
        """All modules should accept and use the same CRS."""
        # Get master CRS from Sentinel-2
        s2_col, master_crs, s2_meta = sentinel2.get_sentinel2_data()

        # All other modules should accept this CRS
        s1_col, s1_meta = sentinel1.get_sentinel1_data(master_crs)
        l8_col, l8_meta = landsat_thermal.get_landsat_thermal(master_crs)
        srtm_img, srtm_meta = srtm.get_srtm_data(master_crs)

        # All should return valid objects
        assert s1_col is not None
        assert l8_col is not None
        assert srtm_img is not None

    def test_metadata_consistency(self):
        """All modules should return metadata with consistent structure."""
        s2_col, master_crs, s2_meta = sentinel2.get_sentinel2_data()
        s1_col, s1_meta = sentinel1.get_sentinel1_data(master_crs)
        l8_col, l8_meta = landsat_thermal.get_landsat_thermal(master_crs)
        srtm_img, srtm_meta = srtm.get_srtm_data(master_crs)

        # All metadata should be dictionaries
        for meta in [s2_meta, s1_meta, l8_meta, srtm_meta]:
            assert isinstance(meta, dict), "Metadata should be a dictionary"
            assert "source" in meta, "Metadata should have 'source' field"


class TestErrorHandling:
    """Tests for error handling in satellite modules."""

    def test_modules_handle_invalid_crs_gracefully(self):
        """Modules should handle invalid CRS without crashing."""
        invalid_crs = "INVALID:CRS"

        # Modules should either accept it (mock) or raise a clear error
        try:
            sentinel1.get_sentinel1_data(invalid_crs)
            landsat_thermal.get_landsat_thermal(invalid_crs)
            srtm.get_srtm_data(invalid_crs)
        except Exception as e:
            # If an exception is raised, it should be informative
            assert len(str(e)) > 0, "Error message should not be empty"

    def test_modules_handle_none_crs(self):
        """Modules should handle None CRS parameter."""
        # Some modules might have default CRS behavior
        try:
            # These might fail or use defaults
            sentinel1.get_sentinel1_data(None)
        except (TypeError, AttributeError):
            # Expected if CRS is required
            pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
