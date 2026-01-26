ROI_TEST = [
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
from datetime import datetime

if os.path.exists('roi.json'):
    try:
        with open('roi.json', 'r') as f:
            roi_data = json.load(f)
            # GeoJSON stores coordinates as [lon, lat], which is what we need
            # But it might be nested depending on how it was saved (Polygon vs MultiPolygon)
            # The tool saves the raw geometry object: {"type": "Polygon", "coordinates": [...]}
            if 'coordinates' in roi_data:
                ROI_TEST = roi_data['coordinates']
                print(f"Loaded custom ROI from roi.json")
    except Exception as e:
        print(f"Error loading roi.json: {e}. Using default coordinates.")


# Phenological windows for static dataset 
# T1: Vegetative Development
T1_START = '2025-06-01'
T1_END = '2025-07-20' 
# T2: Maturation
T2_START = '2025-07-21'
T2_END = '2025-09-10'

# Range for meteorological modules
START = T1_START
END = T2_END
# For future multi year analysis
HISTORICAL_START = '2018-01-01' # Start of historical data to current day
HISTORICAL_END = datetime.now().strftime('%Y-%m-%d')
SEASONAL_START_MONTH = 4 # Filter out winter data from averages
SEASONAL_END_MONTH = 9

# Cloud thresholds
CLOUD_THRESH = 50 # Strict cloud threshold for NDVI
CLOUD_THRESH_LANDSAT = 80 

# Static Dataset sampling scale
SAMPLING_SCALE = 10 
metadata_path = f"{os.getcwd()}/metadata/"

runid = "test"