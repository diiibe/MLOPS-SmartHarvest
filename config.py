import os
import json

# 1. Region of Interest (GeoJSON) - Coordinates only
# Format: [Longitude, Latitude]
ROI_COORDS = [
    [
        [12.829590050244093, 46.10537642826068],
        [12.832761609248365, 46.10586059869124],
        [12.832819802992134, 46.10606233511484],
        [12.835002068361632, 46.10666753995807],
        [12.835205746463458, 46.106949966611126],
        [12.835758587023236, 46.10721221863571],
        [12.835496715178579, 46.10769637294237],
        [12.836806074400869, 46.108019140117506],
        [12.837620786806156, 46.10692979332691],
        [12.84035589273634, 46.107817410854466],
        [12.837620786806156, 46.110298629483594],
        [12.84012311776317, 46.110802928555245],
        [12.838610080440048, 46.11227545543616],
        [12.836689686914212, 46.11683398784979],
        [12.82828069102274, 46.115301072127835],
        [12.8283388847656, 46.11461528023602],
        [12.829182694042316, 46.11324367085004],
        [12.829793728345834, 46.111327394694854],
        [12.830055600189581, 46.11037931764528],
        [12.83049205326364, 46.10995570347956],
        [12.829881018960151, 46.10979432579782],
        [12.829502759629804, 46.10822086864232],
        [12.829357275271803, 46.108039313003104],
        [12.829502759629804, 46.10537642826068],
    ]
]

# Placeholder for the actual ee.Geometry object (initialized in main.py)
ROI = None

# Dynamic ROI Loading
if os.path.exists("roi.json"):
    try:
        with open("roi.json", "r") as f:
            roi_data = json.load(f)
            if "coordinates" in roi_data:
                ROI_COORDS = roi_data["coordinates"]
                print(f"Loaded custom ROI from roi.json")
    except Exception as e:
        print(f"Error loading roi.json: {e}. Using default coordinates.")


# Analysis Range (Updated by main.py from the UI date - 90 days)
START_DATE = "2025-06-01"
END_DATE = "2025-09-01"

# Resolution in meters (10m for S2 native, all data resampled to this)
# NOTE: For very large vineyards (>50 ha), consider increasing to 20m to reduce data volume
# 10m → ~10K points/km²
# 20m → ~2.5K points/km² (4x reduction)
TARGET_SCALE = 10

# Cloud thresholds
CLOUD_THRESHOLD_S2 = 50  # Sentinel-2 (Optical)
CLOUD_THRESHOLD_LANDSAT = 80  # Landsat (Thermal) - more permissive, data is scarcer

# Download chunking (for large datasets that exceed GEE limits)
# Temporal data is automatically split into chunks if direct download fails
# Chunk size auto-selected: S2 = 7 days, S1/L8 = 15 days (optimized per satellite)
