import unittest
import os
import json
import glob
import shutil
import tempfile
import pandas as pd
from unittest.mock import MagicMock, patch
import sys

# Ensure project root is in path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)
sys.path.insert(0, current_dir)

import mock_ee

sys.modules["ee"] = mock_ee
sys.modules["google"] = MagicMock()
sys.modules["google.oauth2"] = MagicMock()
sys.modules["google.oauth2.service_account"] = MagicMock()

import main
import config


class TestGateBOutputCompleteness(unittest.TestCase):
    """
    Gate B: Output Completeness (Run Bundle Contract).
    Condition: FOR EVERY TERMINAL RUN (Success/Low Confidence).
    Verifies:
        1. Mandatory Artifacts Existence (PDF, GeoJSON, CSVs).
        2. Contract Validity (Schema, FeatureCollection, PDF Header).
        3. Manifest Reference Integrity.
    """

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.output_root = self.temp_dir.name
        self._original_cwd = os.getcwd()
        os.chdir(self.output_root)

    def tearDown(self):
        os.chdir(self._original_cwd)
        self.temp_dir.cleanup()

    @patch("main.get_st1")
    @patch("main.get_st2")
    @patch("main.get_landsat")
    @patch("main.get_srtm")
    @patch("main.get_missing_partitions")
    def test_run_bundle_contract_terminal_state(self, mock_missing, mock_srtm, mock_landsat, mock_st2, mock_st1):
        """
        Simulate a terminal run and verify the strict output contract.
        """
        print("\n=== Gate B Verification: Output Completeness Contract ===")

        # 1. Setup Mock (Simulate minimal successful data flow)
        from datetime import datetime

        start_date = datetime(2025, 6, 1)
        mock_missing.return_value = [start_date]

        # 2. RUN PIPELINE
        try:
            main.run_pipeline()
        except Exception as e:
            self.fail(f"Pipeline crashed. Gate B requires a terminal state run. Error: {e}")

        # 3. LOCATE MANIFEST (Root of the bundle)
        manifest_pattern = os.path.join("output", "runs", "*", "run_manifest.json")
        found_manifests = glob.glob(manifest_pattern)
        self.assertTrue(len(found_manifests) > 0, "Gate B Fail: No manifest found. Run did not produce traceability.")
        manifest_path = found_manifests[0]
        run_bundle_dir = os.path.dirname(manifest_path)

        with open(manifest_path, "r") as f:
            manifest = json.load(f)

        # 4. PRECONDITION: Terminal Status
        print(f"   Run Status: {manifest.get('status')}")
        self.assertIn(
            manifest.get("status"),
            ["SUCCESS", "LOW_CONFIDENCE_DONE"],
            "Gate B Skip/Fail: Gate B applies to terminal runs. Status was not terminal.",
        )

        # 5. VERIFY MANIFEST ARTIFACTS SECTION
        print("1. Checking Manifest 'artifacts' contract...")
        self.assertIn("artifacts", manifest, "Manifest missing 'artifacts' section")
        artifacts = manifest["artifacts"]

        expected_keys = ["pdf_report", "macro_anomaly_report", "anomaly_heatmap", "coverage_reliability_report"]
        for key in expected_keys:
            self.assertIn(key, artifacts, f"Artifact key '{key}' missing in manifest")
            self.assertIn("path", artifacts[key], f"Path missing for artifact '{key}'")
            self.assertIn("type", artifacts[key], f"Type missing for artifact '{key}'")

        # 6. VERIFY ARTIFACT EXISTENCE & VALIDITY
        print("2. Checking File Existence & Content Validity...")

        # A. PDF REPORT
        pdf_rel_path = artifacts["pdf_report"]["path"]
        pdf_abs_path = os.path.join("output", pdf_rel_path)
        self.assertTrue(os.path.exists(pdf_abs_path), f"PDF file missing at {pdf_abs_path}")

        with open(pdf_abs_path, "rb") as f:
            header = f.read(5)
            self.assertEqual(header, b"%PDF-", "Invalid PDF header. File is not a valid PDF.")
        print("   [PDF] OK (%PDF header verified)")

        # B. GEOJSON HEATMAP
        geojson_rel_path = artifacts["anomaly_heatmap"]["path"]
        geojson_abs_path = os.path.join("output", geojson_rel_path)
        self.assertTrue(os.path.exists(geojson_abs_path), f"GeoJSON file missing at {geojson_abs_path}")

        with open(geojson_abs_path, "r") as f:
            geo_data = json.load(f)
            self.assertEqual(geo_data.get("type"), "FeatureCollection", "GeoJSON must be FeatureCollection")
            self.assertTrue(isinstance(geo_data.get("features"), list), "GeoJSON 'features' must be a list")
            # Contract: For this run (even dummy), we expect at least 1 feature logic
            self.assertGreaterEqual(len(geo_data["features"]), 1, "GeoJSON must contain at least 1 feature (contract)")
        print(f"   [GeoJSON] OK (Valid FeatureCollection, {len(geo_data['features'])} feats)")

        # C. MACRO ANOMALY REPORT (CSV)
        macro_rel_path = artifacts["macro_anomaly_report"]["path"]
        macro_abs_path = os.path.join("output", macro_rel_path)
        self.assertTrue(os.path.exists(macro_abs_path), f"Macro CSV missing at {macro_abs_path}")

        df_macro = pd.read_csv(macro_abs_path)
        required_cols_macro = ["parcel_id", "anomaly_score", "cluster_id", "date"]
        for col in required_cols_macro:
            self.assertIn(col, df_macro.columns, f"Macro CSV missing column: {col}")
        print("   [Macro CSV] OK (Schema verified)")

        # D. COVERAGE RELIABILITY REPORT (CSV)
        cov_rel_path = artifacts["coverage_reliability_report"]["path"]
        cov_abs_path = os.path.join("output", cov_rel_path)
        self.assertTrue(os.path.exists(cov_abs_path), f"Coverage CSV missing at {cov_abs_path}")

        df_cov = pd.read_csv(cov_abs_path)
        required_cols_cov = ["coverage_ratio", "valid_pixels", "reliability_factor", "status"]
        for col in required_cols_cov:
            self.assertIn(col, df_cov.columns, f"Coverage CSV missing column: {col}")
        print("   [Coverage CSV] OK (Schema verified)")

        print("Gate B: Output Completeness - PASS")


if __name__ == "__main__":
    unittest.main()
