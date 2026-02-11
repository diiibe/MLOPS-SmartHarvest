#!/usr/bin/env python3
"""
SmartHarvest ML Weekly Analysis - Standalone Entrypoint

Usage:
    python run_ml_weekly.py <project_name>
    python run_ml_weekly.py <project_name> --force
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ml.pipeline import run_ml_pipeline


import argparse

def main():
    parser = argparse.ArgumentParser(description="SmartHarvest ML Weekly Analysis")
    parser.add_argument("project_pos", nargs="?", help="Project name")
    parser.add_argument("--project", dest="project_flag", help="Project name (alternative flag)")
    parser.add_argument("--force", action="store_true", help="Reprocess all weeks")

    args = parser.parse_args()
    project_name = args.project_flag or args.project_pos
    
    if not project_name:
        parser.print_help()
        sys.exit(1)
    
    force_reprocess = args.force

    # Paths
    output_dir = os.path.join('output', project_name)
    csv_path = os.path.join(output_dir, f'SmartHarvest_{project_name}.csv')

    if not os.path.exists(csv_path):
        print(f"ERROR: CSV not found at {csv_path}")
        print(f"\nAvailable projects:")
        if os.path.exists('output'):
            for p in os.listdir('output'):
                if os.path.isdir(os.path.join('output', p)):
                    csv = os.path.join('output', p, f'SmartHarvest_{p}.csv')
                    if os.path.exists(csv):
                        print(f"  - {p}")
        sys.exit(1)

    print(f"\nProject: {project_name}")
    print(f"CSV: {csv_path}")
    print(f"Force reprocess: {force_reprocess}\n")

    # Run pipeline
    result = run_ml_pipeline(csv_path, output_dir, force_reprocess=force_reprocess)

    if result['success']:
        print(f"\n✓ SUCCESS: Processed {result['weeks_processed']} weeks")
        print(f"✓ Latest week: {result['latest_week']}")
        print(f"✓ Cluster map: {result['latest_cluster_map']}")
        print(f"✓ ML outputs: {result['ml_dir']}")
        sys.exit(0)
    else:
        print(f"\n✗ FAILED: {result.get('error', 'Unknown error')}")
        sys.exit(1)


if __name__ == '__main__':
    main()
