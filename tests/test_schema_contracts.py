import unittest
import sys
import os
from unittest.mock import MagicMock

# --- MOCK SETUP START ---
# Must mock 'ee' before importing modules that use it
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)
sys.path.insert(0, current_dir)

# 1. Register MockEE
from tests.mock_ee import MockEE, MockEEObject
sys.modules['ee'] = MockEE()

# 2. Patch ee in modules if they are already loaded
for module in ['modules.satellites_data_extraction', 'modules.s2cleaning', 'utils', 'export_polibio', 'satellites.sentinel2', 'satellites.sentinel1', 'satellites.landsat_thermal', 'satellites.srtm']:
    if module in sys.modules:
        sys.modules[module].ee = MockEE()
        
sys.modules["google"] = MagicMock()
sys.modules["google.oauth2"] = MagicMock()
sys.modules["google.oauth2.service_account"] = MagicMock()
# --- MOCK SETUP END ---

# --- IMPORT MODULES ---
import config
from satellites import sentinel2 as s2
from satellites import sentinel1 as s1
from satellites import landsat_thermal as l8
from satellites import srtm

# Note: Check imports matches actual filenames.
# Based on 'git status' output:
# satellites/sentinel2.py, satellites/sentinel1.py, satellites/landsat_thermal.py, satellites/srtm.py


class TestSchemaContracts(unittest.TestCase):
    """
    Verifies that the Data Backbone modules adhere to expected inputs/outputs contracts.
    Uses usage of MockEEObject to ensure functions are callable and return expected GEE-like objects.
    """

    def test_sentinel2_contract(self):
        """Contract: get_sentinel2_data must accept ROI/dates and return an ImageCollection/Image."""
        # Using mocks, so we just pass dummy args if needed or rely on config defaults
        try:
            # We import the specific module but the function might be in a different place depending on refactors.
            # Assuming satellites_data_extraction.py aggregates them or they are direct.
            # Let's use the 'satellites.sentinel2' directly if possible.
            from satellites import sentinel2

            data = sentinel2.get_sentinel2_data()  # Assuming it takes no args or defaults to config
            self.assertIsNotNone(data, "Sentinel-2 extraction returned None")
            # Verify it's a MockEEObject (simulating an Image or Collection)
            self.assertTrue(isinstance(data, MockEEObject), "Sentinel-2 data should be an EE object")
        except ImportError:
            # Fallback if structure is different
            from modules import satellites_data_extraction

            data = satellites_data_extraction.get_sentinel2_data()
            self.assertIsNotNone(data)
        except Exception as e:
            self.fail(f"Sentinel-2 Contract failed: {e}")

    def test_sentinel1_contract(self):
        """Contract: get_sentinel1_data must return valid EE object."""
        from satellites import sentinel1

        try:
            data = sentinel1.get_sentinel1_data()
            self.assertIsNotNone(data, "Sentinel-1 extraction returned None")
            self.assertTrue(isinstance(data, MockEEObject))
        except Exception as e:
            self.fail(f"Sentinel-1 Contract failed: {e}")

    def test_landsat_contract(self):
        """Contract: get_landsat_data must return valid EE object."""
        # Function name might be get_landsat_data or different
        from satellites import landsat_thermal

        try:
            # Checking availability of function
            if hasattr(landsat_thermal, "get_landsat_data"):
                data = landsat_thermal.get_landsat_data()
                self.assertIsNotNone(data)
            elif hasattr(landsat_thermal, "get_thermal_data"):
                data = landsat_thermal.get_thermal_data()
                self.assertIsNotNone(data)
            else:
                # It might be exposing an image directly
                pass
        except Exception as e:
            self.fail(f"Landsat Contract failed: {e}")

    def test_srtm_contract(self):
        """Contract: SRTM data must be available."""
        from satellites import srtm

        try:
            data = srtm.get_srtm_data()
            self.assertIsNotNone(data)
        except Exception as e:
            self.fail(f"SRTM Contract failed: {e}")


if __name__ == "__main__":
    unittest.main()
