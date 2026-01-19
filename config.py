ROI_COORDS = [
    [
        
            [
              12.829590050244093,
              46.10537642826068
            ],
            [
              12.832761609248365,
              46.10586059869124
            ],
            [
              12.832819802992134,
              46.10606233511484
            ],
            [
              12.835002068361632,
              46.10666753995807
            ],
            [
              12.835205746463458,
              46.106949966611126
            ],
            [
              12.835758587023236,
              46.10721221863571
            ],
            [
              12.835496715178579,
              46.10769637294237
            ],
            [
              12.836806074400869,
              46.108019140117506
            ],
            [
              12.837620786806156,
              46.10692979332691
            ],
            [
              12.84035589273634,
              46.107817410854466
            ],
            [
              12.837620786806156,
              46.110298629483594
            ],
            [
              12.84012311776317,
              46.110802928555245
            ],
            [
              12.838610080440048,
              46.11227545543616
            ],
            [
              12.836689686914212,
              46.11683398784979
            ],
            [
              12.82828069102274,
              46.115301072127835
            ],
            [
              12.8283388847656,
              46.11461528023602
            ],
            [
              12.829182694042316,
              46.11324367085004
            ],
            [
              12.829793728345834,
              46.111327394694854
            ],
            [
              12.830055600189581,
              46.11037931764528
            ],
            [
              12.83049205326364,
              46.10995570347956
            ],
            [
              12.829881018960151,
              46.10979432579782
            ],
            [
              12.829502759629804,
              46.10822086864232
            ],
            [
              12.829357275271803,
              46.108039313003104
            ],
            [
              12.829502759629804,
              46.10537642826068
            ]
         
    ]
]

# Placeholder for the actual ee.Geometry object (initialized in main.py)
ROI = None

# Dynamic ROI Loading
import os
import json

if os.path.exists('roi.json'):
    try:
        with open('roi.json', 'r') as f:
            roi_data = json.load(f)
            # GeoJSON stores coordinates as [lon, lat], which is what we need
            # But it might be nested depending on how it was saved (Polygon vs MultiPolygon)
            # The tool saves the raw geometry object: {"type": "Polygon", "coordinates": [...]}
            if 'coordinates' in roi_data:
                ROI_COORDS = roi_data['coordinates']
                print(f"Loaded custom ROI from roi.json")
    except Exception as e:
        print(f"Error loading roi.json: {e}. Using default coordinates.")


# Phenological Windows (Temporal Dynamics)
# T1: Vegetative Development (June 1 - July 20)
DATE_T1_START = '2025-06-01'
# T2: Ripening / Maturation (July 21 - September 10)
DATE_T2_START = '2025-07-21'
DATE_T2_END = '2025-09-10'

# Global range for other datasets (e.g. ERA5, Thermal)
HISTORICAL_START_DATE = '2018-01-01' # For Time Series context
START_DATE = DATE_T1_START
END_DATE = DATE_T2_END
TARGET_SCALE = 10 # Resolution in meters (10 for S2, 30 for Landsat)
CLOUD_THRESHOLD_S2 = 50      # Sentinel-2 (Optical) - Keep strict for good indices
CLOUD_THRESHOLD_LANDSAT = 80 # Landsat (Thermal) - More permissive as data is scarcer

# Seasonal Filter (Months to include in historical stats)
# Extended: April (4) to September (9)
SEASONAL_START_MONTH = 4
SEASONAL_END_MONTH = 9

