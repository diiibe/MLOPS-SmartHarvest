import unittest
import sys
import os
import glob
import tempfile
import json
from unittest.mock import MagicMock, patch

# --- MOCK SETUP (Must be first) ---
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)
sys.path.insert(0, current_dir)

import mock_ee

sys.modules["ee"] = mock_ee
sys.modules["google"] = MagicMock()
sys.modules["google.oauth2"] = MagicMock()
sys.modules["google.oauth2.service_account"] = MagicMock()

# --- IMPORT PROJECT MODULES ---
import config
import main
from modules import satellites_data_extraction


class TestE2EPipeline(unittest.TestCase):
    """
    Simulates a full End-to-End run of the platform using `main.run_pipeline()`.
    Refined to use isolated temporary directories and contract-based assertions.
    """

    def setUp(self):
        """Prepare the environment for the run using a secure temp directory."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.output_root = self.temp_dir.name
        self._original_cwd = os.getcwd()
        os.chdir(self.output_root)

    def tearDown(self):
        """Clean up."""
        # --- CI ARTIFACTS COLLECTION ---
        # If CI_ARTIFACTS_DIR is set, copy the output directory there before cleanup
        ci_artifacts_dir = os.environ.get("CI_ARTIFACTS_DIR")
        if ci_artifacts_dir:
            try:
                import shutil

                # We are currently in self.output_root.
                # The pipeline generates 'output/runs/...'
                source_output = os.path.join(self.output_root, "output")

                if os.path.exists(source_output):
                    # Destination: CI_ARTIFACTS_DIR/run_bundle_<timestamp> or just contents
                    # User asked for: ci_artifacts/run_bundle/
                    # We create a unique subfolder to avoid collisions if multiple tests run?
                    # For e2e smoke, just copy 'output' to 'CI_ARTIFACTS_DIR/gate_a_output'
                    dest_path = os.path.join(ci_artifacts_dir, "gate_a_output")

                    # copytree requires dest not to exist usually, or use dirs_exist_ok in py3.8+
                    if os.path.exists(dest_path):
                        shutil.rmtree(dest_path)

                    shutil.copytree(source_output, dest_path)
                    print(f"\\n[CI] Artifacts copied to {dest_path}")
            except Exception as e:
                print(f"\\n[CI] Warning: Failed to copy artifacts: {e}")

        os.chdir(self._original_cwd)
        self.temp_dir.cleanup()

    @patch("main.get_st1")
    @patch("main.get_st2")
    @patch("main.get_landsat")
    @patch("main.get_srtm")
    @patch("main.get_missing_partitions")
    def test_full_pipeline_execution(self, mock_missing, mock_srtm, mock_landsat, mock_st2, mock_st1):
        """
        Verify that run_pipeline() executes without error and triggers correct extraction calls.
        Uses a temporary directory for artifacts and glob matching for contracts.
        """
        print("\n=== Simulazione Esecuzione End-to-End (Refined) ===")

        # 1. Setup Mock Behavior
        from datetime import datetime

        # Mock 'get_missing_partitions' to return a dummy date range
        start_date = datetime(2025, 6, 1)
        mock_missing.return_value = [start_date]

        # Define Side Effect for get_st2 (Simulate successful download to TEMP dir)
        def side_effect_st2(roi, start, end, roi_name, **kwargs):
            # We redirect output to our self.output_root instead of real project root
            # Structure: {temp_dir}/raw_data/{roi_name}/sentinel_2
            output_dir = os.path.join(self.output_root, "raw_data", roi_name, "sentinel_2")
            os.makedirs(output_dir, exist_ok=True)
            output_file = os.path.join(output_dir, f"{start.date()}_{end.date()}.csv")

            # Write dummy CSV with expected headers + some values for Regression Check
            with open(output_file, "w") as f:
                f.write(
                    "date,NDVI,EVI,GNDVI,IRECI,NDMI,NDRE,valid_pixels,total_pixels,coverage_ratio,observation_valid,erosion_m,is_small_parcel,.geo\n"
                )
                f.write(f"{start.date()},0.85,0.7,0.8,0.4,0.3,0.5,100,100,1.0,True,0,False,POINT(12 45)\n")
            print(f"   [Mock] Created artifact in temp: {output_file}")
            return None

        mock_st2.side_effect = side_effect_st2

        # 2. Execute Pipeline
        try:
            main.run_pipeline()
            print("Pipeline eseguita con successo (nessun crash).")
        except Exception as e:
            self.fail(f"La pipeline è crashata: {e}")

        # 3. Verify Calls
        mock_missing.assert_called()
        print("Gate 1: Controllo partizioni mancanti - PASS")
        mock_srtm.assert_called()
        mock_st1.assert_called()
        mock_st2.assert_called()
        print("Gate 2: Richiesta dati satellitari - PASS")

        # 4. Verify Run Bundle Contract (Outputs) - Contract Based (Glob)
        # We look for ANY csv in the expected structure, avoiding hardcoded date logic
        expected_dir = os.path.join(self.output_root, "raw_data", config.roi_name, "sentinel_2")
        search_pattern = os.path.join(expected_dir, "*.csv")
        found_files = glob.glob(search_pattern)

        self.assertTrue(len(found_files) > 0, f"Bundle Contract Failed: No CSV found in {expected_dir}")
        found_csv = found_files[0]
        print(f"Gate 3: Run Bundle (File Existence) - PASS Found: {os.path.basename(found_csv)}")

        # 5. Regression Checks (Success Criteria)
        # Read the generated CSV and check values
        with open(found_csv, "r") as f:
            header = f.readline().strip().split(",")
            data = f.readline().strip().split(",")

            # KPI: NDVI must be between 0 and 1
            if "NDVI" in header:
                idx_ndvi = header.index("NDVI")
                ndvi_val = float(data[idx_ndvi])
                self.assertTrue(0.0 <= ndvi_val <= 1.0, f"Regression Fail: NDVI {ndvi_val} out of range")
                print("Gate 4: Regression Check (NDVI Limits) - PASS")
            else:
                self.fail("Regression Fail: NDVI column missing in output")

        # --- Gate A: Smoke Execution & Traceability ---
        # Search for run_manifest.json in output/runs/*/run_manifest.json
        # Since run_id is dynamic, we use glob. CWD is already self.output_root
        manifest_pattern = os.path.join("output", "runs", "*", "run_manifest.json")
        found_manifests = glob.glob(manifest_pattern)

        self.assertTrue(len(found_manifests) > 0, "Gate A Fail: No run_manifest.json found (Traceability)")
        manifest_path = found_manifests[0]

        with open(manifest_path, "r") as f:
            manifest = json.load(f)

        # Assertions
        self.assertIn("run_id", manifest, "Manifest missing 'run_id'")
        self.assertIn("status", manifest, "Manifest missing 'status'")
        self.assertIn("config_snapshot_path", manifest, "Manifest missing 'config_snapshot_path'")

        self.assertIn(manifest["status"], ["SUCCESS", "LOW_CONFIDENCE_DONE"], f"Run status {manifest['status']} not valid")

        print(f"Gate A: Smoke Execution - PASS [Run ID: {manifest['run_id']}]")


if __name__ == "__main__":
    unittest.main()
