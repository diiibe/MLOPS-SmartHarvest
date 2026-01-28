
import unittest
import os
import json
import pandas as pd
import tempfile
import glob
import sys
from unittest.mock import MagicMock, patch

# Gate D Dependencies
try:
    from shapely.geometry import shape
    from pypdf import PdfReader
except ImportError:
    # Fail gracefully if deps not installed (though CI should install them)
    shape = None
    PdfReader = None

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

class TestGateDExportValidity(unittest.TestCase):
    """
    Gate D: Export Validity Checks (SC2).
    Purpose: Validate that exports are structurally correct and interoperable.
    Focus:
    1. GeoJSON: valid geometry (shapely), required fields.
    2. CSV: parseable, non-empty, required cols.
    3. PDF: readable, non-empty text.
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
    def test_export_validity_terminal_state(self, mock_missing, mock_srtm, mock_landsat, mock_st2, mock_st1):
        """
        Simulate pipeline and strictly validate generated artifacts via Manifest.
        """
        print("\n=== Gate D Verification: Export Validity & Interoperability ===")

        if shape is None or PdfReader is None:
            self.fail("Gate D dependencies (shapely, pypdf) not installed. Test cannot run.")

        # 1. Setup Mock
        from datetime import datetime
        start_date = datetime(2025, 6, 1)
        mock_missing.return_value = [start_date]
        
        # 2. RUN PIPELINE
        try:
            main.run_pipeline()
        except Exception as e:
            self.fail(f"Pipeline crashed. Gate D requires a terminal state run. Error: {e}")

        # 3. LOCATE MANIFEST
        manifest_pattern = os.path.join("output", "runs", "*", "run_manifest.json")
        found_manifests = glob.glob(manifest_pattern)
        self.assertTrue(len(found_manifests) > 0, "Gate D Fail: No run_manifest.json found.")
        manifest_path = found_manifests[0]
        
        with open(manifest_path, "r") as f:
            manifest = json.load(f)

        # 4. ITERATE ARTIFACTS
        artifacts = manifest.get("artifacts", {})
        self.assertTrue(len(artifacts) > 0, "Gate D: No artifacts declared in manifest to validate.")

        for art_key, art_meta in artifacts.items():
            art_type = art_meta.get("type")
            rel_path = art_meta.get("path")
            # Using simple os.path.join since CWD is self.output_root (temp dir)
            # path in manifest is relative to 'output' often (e.g. 'runs/../foo') or just 'runs/..'
            # Let's resolve safely based on manifest construction in main.py.
            # Manifest path: "runs/{run_id}/run_manifest.json"
            # Artifact path in manifest: "runs/{run_id}/foo.pdf"
            # Main.py uses os.path.relpath(..., start="output") -> "runs/{run_id}/foo.pdf"
            # So absolute path in test context = output_root + "output" + rel_path
            
            # Wait, main.py says: relpath(..., start="output").
            # If generated file is output/runs/id/foo, relpath is runs/id/foo.
            # Local structure: temp_dir/output/runs/id/foo.
            
            full_path = os.path.join("output", rel_path)
            
            print(f"   [Checking] {art_key} ({art_type}) at {full_path}")
            self.assertTrue(os.path.exists(full_path), f"Artifact {art_key} missing at {full_path}")

            # --- VALIDATION LOGIC ---
            if art_type == "csv":
                self._validate_csv(full_path, art_key)
            elif art_type == "geojson":
                self._validate_geojson(full_path, art_key)
            elif art_type == "pdf":
                self._validate_pdf(full_path, art_key)
            else:
                print(f"      Unknown artifact type '{art_type}', skipping deep validation.")

        print("Gate D: Export Validity Checks - PASS")

    def _validate_csv(self, path, key):
        """Standard pandas check."""
        try:
            df = pd.read_csv(path)
        except Exception as e:
            self.fail(f"CSV {key} parsing failed: {e}")
        
        self.assertGreater(len(df), 0, f"CSV {key} is empty (0 rows)")
        
        # Critical checks depend on artifact key usually, but generic non-null is good
        if "macro_anomaly" in key:
            self.assertTrue(df["parcel_id"].notna().all(), "CSV Macro: Null parcel_id found")
            self.assertTrue(df["anomaly_status"].notna().all(), "CSV Macro: Null anomaly_status found")
        print("      PASS (Pandas parseable, non-empty, schema basics)")

    def _validate_geojson(self, path, key):
        """Shapely geometry check."""
        try:
            with open(path, "r") as f:
                data = json.load(f)
        except Exception as e:
            self.fail(f"GeoJSON {key} parsing failed: {e}")
            
        self.assertEqual(data.get("type"), "FeatureCollection", "GeoJSON must be FeatureCollection")
        features = data.get("features", [])
        
        if not features:
             # Depending on run, empty might be valid, but for smoke test we expect mocks
             pass 
             
        for idx, feat in enumerate(features):
            geom = feat.get("geometry")
            self.assertIsNotNone(geom, f"Feature {idx} missing geometry")
            
            # Shapely Validity
            try:
                shp = shape(geom)
                self.assertTrue(shp.is_valid, f"Feature {idx} geometry is invalid (self-intersection etc.)")
            except Exception as e:
                self.fail(f"Shapely validaton crashed for Feature {idx}: {e}")
                
            # CRS/Coords check (simple range for Lat/Lon 4326)
            # Assuming bounds [long, lat]. 
            # SmartHarvest usually Italy/Europe? Just check valid global bounds.
            bounds = shp.bounds # (minx, miny, maxx, maxy)
            self.assertTrue(-180 <= bounds[0] <= 180, f"Feature {idx} Lon out of bounds")
            self.assertTrue(-90 <= bounds[1] <= 90, f"Feature {idx} Lat out of bounds")

        print(f"      PASS (Valid GeoJSON, {len(features)} valid geometries)")

    def _validate_pdf(self, path, key):
        """PdfReader check."""
        try:
            reader = PdfReader(path)
        except Exception as e:
             self.fail(f"PDF {key} unreadable by pypdf: {e}")
             
        self.assertGreater(len(reader.pages), 0, "PDF has 0 pages")
        
        try:
            first_page_text = reader.pages[0].extract_text()
        except:
            first_page_text = ""
            
        self.assertTrue(len(first_page_text.strip()) > 0, "PDF first page is blank (no text extracted)")
        
        # Verify Key Metadata (Gate A/B Traceability in PDF)
        self.assertIn("Run ID", first_page_text, "PDF missing 'Run ID' keyword")
        self.assertIn("Date", first_page_text, "PDF missing 'Date' keyword")
        
        print("      PASS (PDF Readable, Non-empty text, Metadata present)")

if __name__ == "__main__":
    unittest.main()
