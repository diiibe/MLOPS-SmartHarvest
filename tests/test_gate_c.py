
import unittest
import os
import json
import pandas as pd
import tempfile
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

class TestGateCConservativePolicy(unittest.TestCase):
    """
    Gate C: Conservative Policy Invariant (SC3).
    Invariant: status == 'CONFIRMED' IMPLIES (coherence >= T1 AND persistence >= T2).
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
    def test_invariant_check(self, mock_missing, mock_srtm, mock_landsat, mock_st2, mock_st1):
        """
        Verify that NO Confirmed anomaly violates the policy thresholds.
        """
        print("\n=== Gate C Verification: Conservative Policy Invariant ===")

        # 1. Setup Mock
        from datetime import datetime
        start_date = datetime(2025, 6, 1)
        mock_missing.return_value = [start_date]
        
        # 2. RUN PIPELINE
        try:
            main.run_pipeline()
        except Exception as e:
            self.fail(f"Pipeline crashed. Gate C requires a terminal state run. Error: {e}")

        # 3. LOCATE MANIFEST
        import glob
        manifest_pattern = os.path.join("output", "runs", "*", "run_manifest.json")
        found_manifests = glob.glob(manifest_pattern)
        self.assertTrue(len(found_manifests) > 0, "Gate C Fail: No manifest found.")
        manifest_path = found_manifests[0]
        
        with open(manifest_path, "r") as f:
            manifest = json.load(f)

        # 4. READ POLICY SNAPSHOT
        self.assertIn("policy", manifest, "Manifest missing 'policy' section (Gate C requirement)")
        policy = manifest["policy"]["confirmation"]
        t_coherence = policy["coherence_min"]
        t_persistence = policy["persistence_min"]
        print(f"   [Policy Snapshot] Coherence Min: {t_coherence}, Persistence Min: {t_persistence}")

        # 5. LOAD MACRO REPORT
        artifacts = manifest.get("artifacts", {})
        self.assertIn("macro_anomaly_report", artifacts, "Macro report artifact missing")
        macro_rel_path = artifacts["macro_anomaly_report"]["path"]
        macro_abs_path = os.path.join("output", macro_rel_path)
        
        df = pd.read_csv(macro_abs_path)
        print(f"   [Data] Loaded {len(df)} rows from macro report.")

        # 6. INVARIANT CHECK
        # Filter Confirmed
        confirmed_df = df[df["anomaly_status"] == "CONFIRMED"]
        print(f"   [Check] Found {len(confirmed_df)} CONFIRMED anomalies.")
        
        # Assertions
        if not confirmed_df.empty:
            coherence_violations = confirmed_df[confirmed_df["coherence_score"] < t_coherence]
            persistence_violations = confirmed_df[confirmed_df["persistence_score"] < t_persistence]
            
            if not coherence_violations.empty:
                print("   [VIOLATION] Found Confirmed rows with insufficient Coherence:")
                print(coherence_violations)
                self.fail(f"Invariant Violation: {len(coherence_violations)} Confirmed rows have Coherence < {t_coherence}")
                
            if not persistence_violations.empty:
                print("   [VIOLATION] Found Confirmed rows with insufficient Persistence:")
                print(persistence_violations)
                self.fail(f"Invariant Violation: {len(persistence_violations)} Confirmed rows have Persistence < {t_persistence}")

        # 7. NEGATIVE CHECK (Optional but recommended)
        # Verify that rows meeting criteria ARE confirmed (unless other rules apply, but for now exact match)
        # Actually our policy says IF coherent & persistent => Confirmed.
        should_be_confirmed = df[
            (df["coherence_score"] >= t_coherence) & 
            (df["persistence_score"] >= t_persistence)
        ]
        # Check if they are indeed labeled CONFIRMED
        # Note: If there are other rules, this might not hold. But based on our Policy module, it should.
        missed_confirmations = should_be_confirmed[should_be_confirmed["anomaly_status"] != "CONFIRMED"]
        if not missed_confirmations.empty:
             print("   [WARNING] Some anomalies met criteria but were NOT confirmed (Logic inconsistency?):")
             print(missed_confirmations)
             # Not failing on this strictly unless requirement says "MUST Confirm if..."
             # Gate C is "Conservative Policy" -> "Don't confirm unless..." (Safety Safety)
             # So false negatives are less critical than false positives for this specific gate.
             pass

        print("Gate C: Conservative Policy Invariant - PASS")

if __name__ == "__main__":
    unittest.main()
