import unittest

class TestSchemaValidators(unittest.TestCase):
    """
    Deterministic Unit Tests for Schema Validation.
    Target: Validation of metadata/bundle structures (Artifacts and Exports).
    """

    def validate_run_bundle_manifest(self, manifest: dict) -> bool:
        """
        Pure validator function to check if a manifest dictionary is valid.
        (In a real app, this might be imported from modules.validators)
        """
        required_keys = ['run_id', 'created_at', 'status', 'source', 'image_count']
        
        # 1. Check Missing Keys
        for key in required_keys:
            if key not in manifest:
                raise ValueError(f"Missing required key: {key}")
        
        # 2. Check Type Constraints
        if not isinstance(manifest.get('run_id'), str):
            raise TypeError("run_id must be a string")
        
        if not isinstance(manifest.get('image_count'), int):
            raise TypeError("image_count must be an integer")
            
        return True

    def test_manifest_valid_schema(self):
        """Case: Valid schema should pass."""
        valid_manifest = {
            'run_id': 'test_run_001',
            'created_at': '2025-01-01T00:00:00',
            'status': 'COMPLETED',
            'source': 'Sentinel-2',
            'image_count': 10
        }
        self.assertTrue(self.validate_run_bundle_manifest(valid_manifest))

    def test_manifest_missing_field(self):
        """Case: Missing required field should raise ValueError."""
        invalid_manifest = {
            'run_id': 'test_run_001',
            # 'created_at': MISSING
            'status': 'COMPLETED',
            'source': 'Sentinel-2',
            'image_count': 10
        }
        with self.assertRaisesRegex(ValueError, "Missing required key: created_at"):
            self.validate_run_bundle_manifest(invalid_manifest)

    def test_manifest_wrong_type(self):
        """Case: Wrong type should raise TypeError."""
        invalid_manifest = {
            'run_id': 12345, # Should be str
            'created_at': '2025-01-01',
            'status': 'COMPLETED',
            'source': 'Sentinel-2',
            'image_count': 10
        }
        with self.assertRaisesRegex(TypeError, "run_id must be a string"):
            self.validate_run_bundle_manifest(invalid_manifest)

if __name__ == '__main__':
    unittest.main()
