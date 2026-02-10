"""
Automatic validation script for SmartHarvest pipeline output.
Checks CSV structure, data coverage, and common errors.
"""

import os
import sys
import pandas as pd
import json
from datetime import datetime


class PipelineValidator:
    def __init__(self, project_name):
        self.project_name = project_name
        self.output_dir = os.path.join('output', project_name)
        self.errors = []
        self.warnings = []
        self.passed = []

    def check_file_exists(self, filename, file_type):
        """Check if a required file exists."""
        path = os.path.join(self.output_dir, filename)
        if os.path.exists(path):
            self.passed.append(f"✓ {file_type} exists: {filename}")
            return True
        else:
            self.errors.append(f"✗ {file_type} MISSING: {filename}")
            return False

    def validate_csv_structure(self, csv_path):
        """Validate CSV has correct columns and structure."""
        if not os.path.exists(csv_path):
            self.errors.append("✗ CSV file not found")
            return None

        try:
            df = pd.read_csv(csv_path)
            self.passed.append(f"✓ CSV loaded successfully ({len(df)} rows)")

            # Check required columns
            required_cols = ['date', 'lat', 'lon', '.geo', 'satellite']
            missing = [c for c in required_cols if c not in df.columns]
            if missing:
                self.errors.append(f"✗ Missing required columns: {missing}")
            else:
                self.passed.append(f"✓ All required columns present")

            # Check expected data columns
            data_cols = ['NDVI', 'NDWI', 'MNDWI', 'NDRE', 'IRECI', 'S2REP',
                         'VH', 'VV', 'Ratio', 'LST', 'Slope']
            present_cols = [c for c in data_cols if c in df.columns]
            missing_cols = [c for c in data_cols if c not in df.columns]

            if missing_cols:
                self.warnings.append(f"⚠ Missing data columns: {missing_cols}")

            self.passed.append(f"✓ Data columns present: {', '.join(present_cols)}")

            return df

        except Exception as e:
            self.errors.append(f"✗ Error reading CSV: {e}")
            return None

    def validate_data_coverage(self, df):
        """Check data coverage for each variable."""
        if df is None:
            return

        total_rows = len(df)

        # Count discarded images (rows where satellite marked but all data is NaN)
        data_cols = ['NDVI', 'NDWI', 'MNDWI', 'NDRE', 'IRECI', 'S2REP', 'VH', 'VV', 'Ratio', 'LST']
        existing_data_cols = [c for c in data_cols if c in df.columns]

        if existing_data_cols and 'satellite' in df.columns:
            # Rows with satellite marked but all data NaN (cloud-masked/QA-filtered)
            has_satellite = df['satellite'].notna()
            all_data_nan = ~df[existing_data_cols].notna().any(axis=1)
            discarded = (has_satellite & all_data_nan).sum()

            if discarded > 0:
                discarded_pct = (discarded / total_rows) * 100
                self.passed.append(f"ℹ Discarded images (cloud/QA-filtered): {discarded:,} rows ({discarded_pct:.1f}%)")

        # S2 variables
        s2_vars = ['NDVI', 'NDWI', 'MNDWI', 'NDRE', 'IRECI', 'S2REP']
        for var in s2_vars:
            if var in df.columns:
                count = df[var].notna().sum()
                pct = (count / total_rows) * 100
                if pct == 0:
                    self.errors.append(f"✗ {var}: NO DATA (0%)")
                elif pct < 10:
                    self.warnings.append(f"⚠ {var}: LOW COVERAGE ({pct:.1f}%)")
                else:
                    self.passed.append(f"✓ {var}: {pct:.1f}% coverage")

        # S1 variables
        s1_vars = ['VH', 'VV', 'Ratio']
        for var in s1_vars:
            if var in df.columns:
                count = df[var].notna().sum()
                pct = (count / total_rows) * 100
                if pct == 0:
                    self.errors.append(f"✗ {var}: NO DATA (0%)")
                elif pct < 10:
                    self.warnings.append(f"⚠ {var}: LOW COVERAGE ({pct:.1f}%)")
                else:
                    self.passed.append(f"✓ {var}: {pct:.1f}% coverage")

        # LST (may be sparse due to cloud cover)
        if 'LST' in df.columns:
            count = df['LST'].notna().sum()
            pct = (count / total_rows) * 100
            if pct == 0:
                self.errors.append(f"✗ LST: NO DATA (0%) - Check Landsat availability")
            elif pct < 3:
                self.warnings.append(f"⚠ LST: VERY LOW ({pct:.1f}%) - Landsat has fewer passes")
            else:
                self.passed.append(f"✓ LST: {pct:.1f}% coverage")

        # Slope (should be 100%)
        if 'Slope' in df.columns:
            count = df['Slope'].notna().sum()
            pct = (count / total_rows) * 100
            if pct < 99:
                self.errors.append(f"✗ Slope: INCOMPLETE ({pct:.1f}%) - Should be 100%")
            else:
                self.passed.append(f"✓ Slope: {pct:.1f}% coverage")

    def validate_spatial_alignment(self, df):
        """Check if S2 and S1 data align properly on same dates."""
        if df is None:
            return

        # Find dates where both S2 and S1 acquired
        both_dates = df[(df['NDVI'].notna()) & (df['VH'].notna())]['date'].unique()

        if len(both_dates) == 0:
            self.warnings.append("⚠ No dates with both S2 and S1 data to check alignment")
            return

        # Check first such date
        test_date = both_dates[0]
        day_df = df[df['date'] == test_date]

        # Count misaligned rows
        s2_only = day_df[(day_df['NDVI'].notna()) & (day_df['VH'].isna())]
        s1_only = day_df[(day_df['NDVI'].isna()) & (day_df['VH'].notna())]
        both = day_df[(day_df['NDVI'].notna()) & (day_df['VH'].notna())]

        total_misaligned = len(s2_only) + len(s1_only)
        misalignment_pct = (total_misaligned / len(day_df)) * 100

        # Calculate S2 coverage (to detect cloud masking)
        s2_coverage = (len(both) + len(s2_only)) / len(day_df) * 100 if len(day_df) > 0 else 0

        if misalignment_pct > 5:
            # Check if this is due to S2 cloud masking (S1 only, no S2 only)
            if len(s2_only) == 0 and len(s1_only) > 0 and s2_coverage < 80:
                # This is cloud masking, not alignment issue
                self.warnings.append(
                    f"⚠ S2 cloud masking on {test_date}: "
                    f"{s2_coverage:.1f}% S2 coverage, {misalignment_pct:.1f}% S1-only points "
                    f"(likely clouds/shadows filtered by SCL mask)"
                )
            else:
                # Real alignment issue
                self.errors.append(
                    f"✗ SPATIAL MISALIGNMENT on {test_date}: "
                    f"{misalignment_pct:.1f}% misaligned "
                    f"(S2 only: {len(s2_only)}, S1 only: {len(s1_only)})"
                )
        elif misalignment_pct > 0:
            self.warnings.append(
                f"⚠ Minor data gaps on {test_date}: {misalignment_pct:.1f}% "
                f"(S2 coverage: {s2_coverage:.1f}%)"
            )
        else:
            self.passed.append(f"✓ Perfect S2/S1 alignment on {test_date} (100% coverage)")

    def validate_temporal_consistency(self, df):
        """Check temporal data consistency."""
        if df is None:
            return

        # Check unique dates
        unique_dates = df['date'].nunique()
        if unique_dates == 0:
            self.errors.append("✗ No date data in CSV")
        else:
            self.passed.append(f"✓ {unique_dates} unique dates")

        # Check date range
        if 'date' in df.columns and df['date'].notna().sum() > 0:
            date_range = f"{df['date'].min()} to {df['date'].max()}"
            self.passed.append(f"✓ Date range: {date_range}")

        # Check for duplicate (date, spatial_id) pairs if spatial_id exists
        if 'spatial_id' in df.columns:
            duplicates = df.duplicated(subset=['date', 'spatial_id']).sum()
            if duplicates > 0:
                self.errors.append(f"✗ {duplicates} duplicate (date, spatial_id) pairs")
            else:
                self.passed.append("✓ No duplicate spatial points per date")

        # Check for empty rows (all satellite data is NaN)
        data_cols = ['NDVI', 'NDWI', 'MNDWI', 'NDRE', 'IRECI', 'S2REP',
                     'VH', 'VV', 'Ratio', 'LST']
        existing_data_cols = [c for c in data_cols if c in df.columns]
        if existing_data_cols:
            empty_rows = (~df[existing_data_cols].notna().any(axis=1)).sum()
            if empty_rows > 0:
                self.warnings.append(
                    f"⚠ {empty_rows} rows with all NaN data "
                    f"(cloud-masked or QA-filtered images)"
                )
            else:
                self.passed.append("✓ No empty rows (all dates have valid data)")

    def check_tmp_files(self):
        """Check intermediate _tmp files for debugging."""
        tmp_files = ['_tmp_S2', '_tmp_S1', '_tmp_L8', '_tmp_SRTM']
        found = []
        for tmp in tmp_files:
            pattern = f'{tmp}_{self.project_name}.csv'
            path = os.path.join(self.output_dir, pattern)
            if os.path.exists(path):
                found.append(tmp.replace('_tmp_', ''))

        if len(found) == 4:
            self.passed.append(f"✓ All satellite downloads complete: {', '.join(found)}")
        else:
            missing = [s for s in ['S2', 'S1', 'L8', 'SRTM'] if s not in found]
            self.warnings.append(f"⚠ Missing download files: {', '.join(missing)}")

    def run_validation(self):
        """Run all validation checks."""
        print("\n" + "="*70)
        print(f"SMARTHARVEST PIPELINE VALIDATION - {self.project_name}")
        print("="*70 + "\n")

        # Check main files
        csv_filename = f'SmartHarvest_{self.project_name}.csv'
        csv_path = os.path.join(self.output_dir, csv_filename)
        map_filename = f'Map_{self.project_name}.html'
        report_filename = f'Report_{self.project_name}.md'

        self.check_file_exists(csv_filename, "CSV Dataset")
        self.check_file_exists(map_filename, "Map HTML")
        self.check_file_exists(report_filename, "Report")

        # Check intermediate files
        self.check_tmp_files()

        # Validate CSV
        df = None
        if os.path.exists(csv_path):
            df = self.validate_csv_structure(csv_path)
            if df is not None:
                self.validate_data_coverage(df)
                self.validate_spatial_alignment(df)
                self.validate_temporal_consistency(df)

        # Print results
        print("\n" + "─"*70)
        print("RESULTS:")
        print("─"*70 + "\n")

        if self.passed:
            print("✓ PASSED:")
            for msg in self.passed:
                print(f"  {msg}")

        if self.warnings:
            print("\n⚠ WARNINGS:")
            for msg in self.warnings:
                print(f"  {msg}")

        if self.errors:
            print("\n✗ ERRORS:")
            for msg in self.errors:
                print(f"  {msg}")

        # Summary
        print("\n" + "="*70)
        if len(self.errors) == 0:
            if len(self.warnings) == 0:
                print("🎉 ALL CHECKS PASSED!")
            else:
                print(f"⚠️  PASSED WITH {len(self.warnings)} WARNINGS")
        else:
            print(f"❌ FAILED: {len(self.errors)} CRITICAL ERRORS")
        print("="*70 + "\n")

        return len(self.errors) == 0


if __name__ == "__main__":
    if len(sys.argv) > 1:
        project_name = sys.argv[1]
    else:
        project_name = "New_Vineyard"

    validator = PipelineValidator(project_name)
    success = validator.run_validation()
    sys.exit(0 if success else 1)
