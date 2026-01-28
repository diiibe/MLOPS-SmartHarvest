import unittest
import sys
import os
import shutil
import tempfile
from unittest.mock import MagicMock, patch

# --- MOCK SETUP START ---
# Must mock 'ee' before importing modules that use it
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

# 1. Register MockEE
from tests.mock_ee import MockEE, MockEEObject

sys.modules["ee"] = MockEE()

# 2. Patch ee in modules if they are already loaded
for module in ["modules.satellites_data_extraction", "modules.s2cleaning", "utils", "export_polibio"]:
    if module in sys.modules:
        sys.modules[module].ee = MockEE()
# --- MOCK SETUP END ---

import ee
import config

# Import modules for Test A
from modules.satellites_data_extraction import get_sentinel2_data
from modules.s2cleaning import get_adaptive_core
from utils import indicesanddate

# Import serving layer for Test B
from export_polibio import export_with_step2


class TestIntegrationLayers(unittest.TestCase):
    """
    Integration Tests: Verifies that separately-developed modules interoperate correctly.
    Scope: Data Acquisition -> Preprocessing -> Serving (Export).
    """

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.output_file = os.path.join(self.test_dir, "test_export.csv")

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_data_pipeline_flow(self):
        """
        Test A: Verify Data Pipeline Flow
        Execute chain: get_sentinel2_data() -> indicesanddate() -> get_adaptive_core()
        """
        # 1. Extraction
        roi = config.ROI_TEST
        start = config.T1_START
        end = config.T1_END

        collection = get_sentinel2_data(roi, start, end)
        self.assertIsInstance(collection, MockEEObject, "Extraction must return an EE object (Collection)")

        # 2. Indexes & Dates (Map)
        # Note: In MockEE, map() returns self or a new MockEEObject
        processed_collection = collection.map(indicesanddate)
        self.assertIsInstance(processed_collection, MockEEObject, "Preprocessing must return an EE object")

        # 3. Geometry (Adaptive Core)
        # Verify that get_adaptive_core returns a dictionary with 'core_geometry'
        core_result = get_adaptive_core(roi)
        self.assertIsInstance(core_result, dict, "get_adaptive_core must return a dictionary")
        self.assertIn("core_geometry", core_result, "Result must contain 'core_geometry' key")
        self.assertIn("erosion_applied", core_result, "Result must contain 'erosion_applied' key")
        self.assertIsInstance(core_result["core_geometry"], MockEEObject, "core_geometry must be an EE object")

    @patch("requests.get")
    def test_serving_layer_contract(self, mock_get):
        """
        Test B: Verify Serving Layer Contract
        Call export_with_step2() -> Mock requests.get -> Assert Output CSV compatibility
        """

        # Setup Mock Response (Simulate GEE serving a CSV)
        # Content must satisfy the UI contract: date, coverage_ratio, valid_pixels, observation_valid
        csv_content = (
            "date,coverage_ratio,valid_pixels,observation_valid,NDVI,total_pixels,erosion_m,is_small_parcel\n"
            "2025-06-01,0.85,100,1,0.7,120,5,0\n"
            "2025-06-05,0.40,50,0,0.6,125,5,0\n"
        ).encode("utf-8")

        mock_response = MagicMock()
        mock_response.content = csv_content
        mock_get.return_value = mock_response

        # Execute Serving Layer
        df = export_with_step2(start_date="2025-06-01", end_date="2025-06-10", output_file=self.output_file, use_erosion=True)

        # 1. Assert requests.get called (Verification of GEE download trigger)
        mock_get.assert_called()

        # 2. Assert Output CSV created
        self.assertTrue(os.path.exists(self.output_file), "Output CSV must be created")

        # 3. Assert Mandatory UI Columns
        required_columns = ["date", "coverage_ratio", "valid_pixels", "observation_valid"]
        for col in required_columns:
            self.assertIn(col, df.columns, f"Output CSV must contain required UI column: {col}")

        # 4. Assert Types (Basic check)
        # 'valid_pixels' should be numeric (int/float)
        import pandas as pd

        self.assertTrue(pd.api.types.is_numeric_dtype(df["valid_pixels"]), "'valid_pixels' must be numeric")
        self.assertTrue(pd.api.types.is_numeric_dtype(df["coverage_ratio"]), "'coverage_ratio' must be numeric")


if __name__ == "__main__":
    unittest.main()
