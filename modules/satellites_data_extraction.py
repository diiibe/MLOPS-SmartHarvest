import ee
import config
from utils import retrieve_sensor_data, filter_hour


def get_ecostress_data(ROI=config.ROI_TEST, start_date=config.START, end_date=config.END):

    roi = ee.Geometry.Polygon(ROI)
    try:
        eco = retrieve_sensor_data('NASA/ECOSTRESS/LT_LSTE', roi, start_date, end_date)
        # 'NASA/ECOSTRESS/L2T_LSTE/V2'
        # Filter by hour (approximate local time, assuming UTC+1 or similar for Italy/Europe based on coords in example)
        # The example coords are 45.10, 10.20 (Italy). UTC+1/UTC+2.
        # Let's filter by UTC hours 9 to 15 (approx 10-16 local).
        # A more robust way is to use solar time or just filter by 'solar_zenith' if available, but hour is requested.

        eco = eco.map(filter_hour).filter(ee.Filter.rangeContains('hour', 9, 15))

        # Check if collection is empty
        count = eco.size().getInfo()

    except Exception as e:
        print(f"Warning: ECOSTRESS data not found or error loading collection ({e}). Using dummy data.")

    return eco

def get_era5_data(ROI=config.ROI_TEST, start_date=config.START, end_date=config.END):

    try:
        roi = ee.Geometry.Polygon(ROI)
        era5 = retrieve_sensor_data('ECMWF/ERA5_LAND/HOURLY', roi, start_date, end_date,
        seasonal_months=(config.SEASONAL_START_MONTH, config.SEASONAL_END_MONTH)
        )

    except Exception as e:
        print(f"Warning: era5 data not found or error loading collection ({e}). Using dummy data.")

    return era5

def get_landsat_thermal_data(ROI=config.ROI_TEST, start_date=config.START, end_date=config.END):

    roi = ee.Geometry.Polygon(ROI)
    try:
        # Try Landsat 9 first (newer)
        l9 = retrieve_sensor_data('LANDSAT/LC09/C02/T1_L2', roi, start_date, end_date,
            cloud_max=config.CLOUD_THRESH_LANDSAT
        )

        l8 = retrieve_sensor_data('LANDSAT/LC08/C02/T1_L2', roi, start_date, end_date,
            cloud_max=config.CLOUD_THRESH_LANDSAT
        )

        # Merge both collections
        landsat = l9.merge(l8)

    except Exception as e:
        print(f"Warning: Error processing Landsat thermal data ({e}). Using dummy data.")


    return landsat

def get_sentinel1_data(ROI=config.ROI_TEST, start_date=config.T1_START, end_date=config.T2_END):

    roi = ee.Geometry.Polygon(ROI)
    try:
        # 1. Query & Filter (Full Range)
        s1_full = retrieve_sensor_data('COPERNICUS/S1_GRD', roi, start_date, end_date, # Using specific dates
            s1_pol=['VV', 'VH'],
            s1_mode='IW',
            s1_orbit='ASCENDING'
        )

    except Exception as e:
        print(f"Warning: sentinel1 data not found or error loading collection ({e}). Using dummy data.")

    return s1_full

def get_sentinel2_data(ROI=config.ROI_TEST, start_date=config.T1_START, end_date=config.T2_END):

    roi = ee.Geometry.Polygon(ROI)
    try:
        s2 = retrieve_sensor_data('COPERNICUS/S2_SR_HARMONIZED', roi, start_date, end_date, # Using specific dates
            cloud_max=config.CLOUD_THRESH
        )

        # 2. Auxiliary Collections
        cs_plus = ee.ImageCollection('GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED') \
            .filterBounds(roi) \
            .filterDate(start_date, end_date)
        
        s2_cloudless = ee.ImageCollection('COPERNICUS/S2_CLOUD_PROBABILITY') \
            .filterBounds(roi) \
            .filterDate(start_date, end_date)
        
        # Pre-rename bands to avoid confusion/collisions
        def rename_cs(img):
            return img.select(['cs', 'cs_cdf'], ['cs_cs', 'cs_cs_cdf'])
        cs_plus = cs_plus.map(rename_cs)
        
        def rename_cld(img):
            return img.select(['probability'], ['cld_probability'])
        s2_cloudless = s2_cloudless.map(rename_cld)
        
        # Combine (Inner Join on system:index)
        s2_full = s2.combine(cs_plus).combine(s2_cloudless)

        def apply_masks(img):
            """
            Applies the ensemble mask rules to a single image.
            """
            
            # --- 1A. Thresholds (Regole Base) ---
            # Cloud Score+ Rules: cs >= 0.60 AND cs_cdf >= 0.70
            # bands: cs_cs, cs_cs_cdf
            is_cs_clear = img.select('cs_cs').gte(0.60).And(img.select('cs_cs_cdf').gte(0.70))
            
            # S2Cloudless Rules: probability <= 30
            # band: cld_probability
            is_prob_clear = img.select('cld_probability').lte(30)
            
            # --- 1B. SCL Toxic Classes ---
            # 0: No Data, 1: Saturated, 2: Dark, 3: Cloud Shadow, 7: Unclassified,
            # 8: Medium Cloud, 9: High Cloud, 10: Thin Cirrus, 11: Snow
            scl = img.select('SCL')
            # We keep only: 4 (Vegetation), 5 (Bare Soil), 6 (Water)
            # Note: We include 6 for now, but exclude it for dark pixel check later.
            is_scl_clear = scl.eq(4).Or(scl.eq(5)).Or(scl.eq(6))
            
            # Combine "Cloud-Like" detections (Inverted logic: invalid if ANY says bad)
            # But here we defined "clear" conditions.
            # Pixel is clear if ALL say clear.
            cloud_mask = is_cs_clear.And(is_prob_clear).And(is_scl_clear)
            
            # --- 1D. Shadow Projection (Ombre) ---
            # Temporarily DISABLED for debugging GE/Server error
            # 1. Identification of Cloud Core (Strict cloud for projection)
            # is_cloud_core = img.select('cld_probability').gt(50).Or(scl.eq(8)).Or(scl.eq(9))
            
            # 2. Geometric Projection params
            # azimuth = ee.Number(img.get('MEAN_SOLAR_AZIMUTH_ANGLE'))
            # zenith = ee.Number(img.get('MEAN_SOLAR_ZENITH_ANGLE'))
            
            # Shadow direction = Azimuth + 180 (moved to radians)
            # shadow_azimuth = azimuth.add(180).multiply(3.14159265 / 180)
            
            # Project function
            # def project_shadows(cloud_mask, height):
            #     # Distance = height * tan(zenith)
            #     dist = ee.Number(height).multiply(zenith.multiply(3.14159265 / 180).tan())
            #     x_shift = dist.multiply(shadow_azimuth.sin()).divide(10) # divide by scale (10m)
            #     y_shift = dist.multiply(shadow_azimuth.cos()).divide(10)
            #     return cloud_mask.changeProj(cloud_mask.projection(), cloud_mask.projection().translate(x_shift, y_shift))

            # Try multiple heights (simplified for MVP: 500m, 1000m, 2000m)
            # Using a reduce/iterate approach or hardcoded union for simplicity
            # shadow_proj = ee.Image(0)
            # for h in [500, 1000, 2000]:
            #      shadow_proj = shadow_proj.Or(project_shadows(is_cloud_core, h))
            
            # 3. Dark Pixel Confirmation (Intersection)
            # Must be projected shadow AND dark (NIR < 0.15) AND Not Water (SCL!=6)
            # nir = img.select('B8').divide(10000) # L2A is scaled by 10000
            # is_dark = nir.lt(0.15).And(scl.neq(6))
            
            # confirmed_shadow = shadow_proj.And(is_dark)
            
            # Dilate masks (Buffer) - Simulated with focal_min/max
            # "Dilate Cloud 20m" -> 2 pixels radius (focal_max on cloud mask)
            # "Dilate Shadow 10m" -> 1 pixel radius
            
            # Note: cloud_mask is 1 for CLEAR. So we invert to dilate CLOUDS.
            is_cloud = cloud_mask.Not()
            is_cloud_dilated = is_cloud.focal_max(20, 'circle', 'meters')
            
            # is_shadow_dilated = confirmed_shadow.focal_max(10, 'circle', 'meters')
            
            # Final Invalid Mask
            is_invalid = is_cloud_dilated #.Or(is_shadow_dilated)
            
            # --- 1E. Final Masking ---
            return img.updateMask(is_invalid.Not())

        return s2_full.map(apply_masks)
   
    except Exception as e:
        print(f"Warning: sentinel2 data not found or error loading collection ({e}). Using dummy data.")

    return s2_full

def get_srtm_data(ROI=config.ROI_TEST):

    roi = ee.Geometry.Polygon(ROI)
    try:
        srtm = ee.Image('USGS/SRTMGL1_003')

        # Clip on ROI extended buffer (100m) to avoid edge effects
        roi_buffer = roi.buffer(100)
        srtm_clipped = srtm.clip(roi_buffer)

    except Exception as e:
        print(f"Warning: srtm data not found or error loading image ({e}). Using dummy data.")

    return srtm_clipped

def get_master_crs(ROI=config.ROI_TEST, start_date=config.T1_START, end_date=config.T2_END):

    roi = ee.Geometry.Polygon(ROI)

    try:
        s2_full = retrieve_sensor_data('COPERNICUS/S2_SR_HARMONIZED', roi, start_date, end_date, # Using specific dates
            cloud_max=config.CLOUD_THRESH
        )
        first_img = s2_full.first()
        master_crs = first_img.select('B4').projection()

    except Exception as e:
        print(f"Warning: sentinel2 data not found or error loading collection ({e}). Using dummy data.")

    return master_crs
