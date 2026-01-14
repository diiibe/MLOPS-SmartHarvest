import ee
import config
from utils import ndvi, ndmi, ndre, timebands

# Calculates Sentinel-2 statistics
def s2stats(collection):

    # Adds indices and date band to collection
    def indicesanddate(image):
        img = ndvi(image)
        img = ndmi(img)
        img = ndre(img)
        date_band = ee.Image.constant(image.get('system:time_start')).rename('date').toDouble()
        return img.addBands(date_band)
    
    col = collection.map(indicesanddate)
    
    # Median Indices over the whole period
    medians = col.select(['NDVI', 'NDMI', 'NDRE']).median()
    
    # Peak Indices using qualityMosaic for the highest value of the specified band
    # The resulting image will have the 'date' band from the image that had the peak NDVI
    ndvi_peak_img = col.qualityMosaic('NDVI')
    ndmi_peak_img = col.qualityMosaic('NDMI')
    ndre_peak_img = col.qualityMosaic('NDRE')
    
    peaks = ee.Image.cat([
        ndvi_peak_img.select('NDVI').rename('NDVI_Peak'),
        ndmi_peak_img.select('NDMI').rename('NDMI_Peak'),
        ndre_peak_img.select('NDRE').rename('NDRE_Peak')
    ])
    
    # Time to Peak as days from T1_START to Peak NDVI date
    peak_date_millis = ndvi_peak_img.select('date')
    t1_start_millis = ee.Date(config.T1_START).millis()
    time_to_peak = peak_date_millis.subtract(t1_start_millis).divide(1000 * 60 * 60 * 24).rename('Time_to_Peak')
    
    # Green_Up as T1 slope
    t1_col = col.filterDate(config.T1_START, config.T1_END).map(timebands)
    green_up = t1_col.select(['t', 'constant', 'NDVI']).reduce(ee.Reducer.linearRegression(2, 1))
    # linearRegression returns [coefficients, residuals] so coefficients is 2x1 array image.
    green_up_slope = green_up.select('coefficients').arrayGet([0, 0]).rename('Green_Up')
    
    # Senescence as T2 slope
    t2_col = col.filterDate(config.T2_START, config.T2_END).map(timebands)
    senescence = t2_col.select(['t', 'constant', 'NDVI']).reduce(ee.Reducer.linearRegression(2, 1))
    senescence_slope = senescence.select('coefficients').arrayGet([0, 0]).rename('Senescence')
    
    # NDVI_Delta as (Median T2 - Median T1)
    ndvi_t1_med = t1_col.select('NDVI').median()
    ndvi_t2_med = t2_col.select('NDVI').median()
    ndvi_delta = ndvi_t2_med.subtract(ndvi_t1_med).rename('NDVI_Delta')
    
    # Texture as (Entropy/Contrast on NDVI_Peak)
    # glcmTexture needs integer values. Scaling NDVI to 0-100 or 0-255.
    ndvi_int = ndvi_peak_img.select('NDVI').multiply(100).toInt()
    glcm = ndvi_int.glcmTexture(size=1) # 3x3 window (size 1 is 3x3)
    texture = glcm.select(['NDVI_ent', 'NDVI_contrast']).rename(['Entropy', 'Contrast'])
    
    return ee.Image.cat([
        medians, peaks, time_to_peak, 
        green_up_slope, senescence_slope, ndvi_delta,
        texture
    ])

# Calculates Sentinel-1 statistics
def s1stats(collection):

    vh_t1 = collection.filterDate(config.T1_START, config.T1_END).select('VH').mean()
    vh_t2 = collection.filterDate(config.T2_START, config.T2_END).select('VH').mean()
    
    # VH_Late (Mean T2)
    vh_late = vh_t2.rename('VH_Late')
    
    # VH_Drop (Mean T2 - Mean T1)
    vh_drop = vh_t2.subtract(vh_t1).rename('VH_Drop')
    
    return ee.Image.cat([vh_late, vh_drop])

# Calculates Landsat Thermal statistics
def landsatstats(collection):

    from utils import lstbands
    lst_col = collection.map(lstbands).select('LST')
    
    lst_median = lst_col.median().rename('LST')
    lst_stability = lst_col.reduce(ee.Reducer.stdDev()).rename('LST_Stability')
    
    return ee.Image.cat([lst_median, lst_stability])

# Calculates Topographic statistics
def terrainstats(elevation):

    slope = ee.Terrain.slope(elevation).rename('Slope')
    
    # TWI Calculation: ln(Accumulation / tan(Slope))
    # Accumulation from HydroSHEDS: WWF/HydroSHEDS/15ACC
    acc = ee.Image('WWF/HydroSHEDS/15ACC').clip(config.ROI)
    # Convert slope to radians for tan()
    slope_rad = slope.multiply(3.14159 / 180).max(0.001) # Avoid tan(0)
    twi = acc.divide(slope_rad.tan()).log().rename('TWI')
    
    # Solar Radiation (Hillshade with specific params)
    solar_rad = ee.Terrain.hillshade(elevation, 180, 70).rename('Solar_Rad')
    
    return ee.Image.cat([
        elevation.rename('Elevation'),
        slope, twi, solar_rad
    ])
