import ee
import config
import math
from utils import cloudmask, to_celsius

# SENTINEL-2


def s2resample(image):
    """
    Resampling of the 20m bands (B5, B11) to 10m using bicubic interpolatation.
    """
    b4 = image.select("B4")
    b8 = image.select("B8")
    b5 = image.select("B5").resample("bicubic")
    b11 = image.select("B11").resample("bicubic")
    return b4, b8, b5, b11


def tdays(image, startdate):
    """
    Adds a band 't' that represents the days elapsed since a start date necessary to compute the slope of the linear regression.
    """
    days = image.date().difference(ee.Date(startdate), "day")
    return image.addBands(ee.Image.constant(days).rename("t"))


def s2stats(s2data):
    """
    Computes vigor and growth metrics based on Sentinel-2.
    """
    # cloud masking using external function
    s2masked = s2data.map(cloudmask)

    def indices(image):

        b4, b8, b5, b11 = s2resample(image)

        # NDVI (Vigor), NDMI (Moisture), NDRE (Chlorophyll)
        ndvi = b8.subtract(b4).divide(b8.add(b4)).rename("NDVI")
        ndmi = b8.subtract(b11).divide(b8.add(b11)).rename("NDMI")
        ndre = b8.subtract(b5).divide(b8.add(b5)).rename("NDRE")

        return image.addBands([ndvi, ndmi, ndre])

    indexedcol = s2masked.map(indices)

    # Maximum vigor registered in the period
    peak = indexedcol.qualityMosaic("NDVI")

    # Green-Up rate
    s2t1 = indexedcol.filterDate(config.DATE_T1_START, config.DATE_T1_END).map(lambda img: tdays(img, config.DATE_T1_START))
    green_up = s2t1.select(["t", "NDVI"]).reduce(ee.Reducer.linearFit()).select("scale").rename("Green_Up")

    # Senescence
    s2t2 = indexedcol.filterDate(config.DATE_T2_START, config.DATE_T2_END).map(lambda img: tdays(img, config.DATE_T2_START))
    senescence = s2t2.select(["t", "NDVI"]).reduce(ee.Reducer.linearFit()).select("scale").rename("Senescence")

    # Texture analysis
    ndviint = peak.select("NDVI").multiply(100).toInt()
    glcm = ndviint.glcmTexture(size=3)

    return ee.Image.cat(
        [
            peak.select(["NDVI", "NDMI", "NDRE"]).rename(["NDVI_Peak", "NDMI_Peak", "NDRE_Peak"]),
            green_up,
            senescence,
            glcm.select("NDVI_ent").rename("Texture_Entropy"),
            glcm.select("NDVI_contrast").rename("Texture_Contrast"),
        ]
    )


# SENTINEL-1


def s1stats(s1data):
    """
    Cleans the radar signal using despeckling and computes VH variations.
    """

    # focal mean filter to reduce speckle noise in SAR data
    def despeckle(image):
        return image.focal_mean(radius=2.5, units="pixels", iterations=1).copyProperties(image, ["system:time_start"])

    s1clean = s1data.map(despeckle)

    vht1 = s1clean.filterDate(config.DATE_T1_START, config.DATE_T1_END).select("VH").mean()
    vht2 = s1clean.filterDate(config.DATE_T2_START, config.DATE_T2_END).select("VH").mean()

    return ee.Image.cat([vht2.rename("VH_Late"), vht2.subtract(vht1).rename("VH_Drop")])


# LANDSAT


def landsatstats(landsatdata):
    """
    Converts ST_B10 band to celsius and calculates thermal stability.
    """

    lstcol = to_celsius("landsat", landsatdata)
    lstmed = lstcol.median().rename("LST_med")
    lststd = lstcol.reduce(ee.Reducer.stdDev()).rename("LST_Stability")

    return ee.Image.cat([lstmed, lststd])


# ECOSTRESS


def ecostressstats(ecostressdata):
    """
    Converts ECOSTRESS data to celsius.
    """

    lst_eco = to_celsius("landsat", ecostressdata)
    lst_eco_median = lst_eco.median().rename("LST_eco_med")

    return lst_eco_median


# SRTM


def srtmstats(srtmdata):
    """
    Calculates metrics from the DEM.
    """
    elevation = srtmdata.select("elevation")

    # Slope
    slope = ee.Terrain.slope(elevation).rename("Slope")

    # TWI
    hydro = ee.Image("WWF/HydroSHEDS/15ACC")
    flowacc = hydro.select("b1")
    sloperad = slope.multiply(math.pi).divide(180.0)
    twi = flowacc.divide(sloperad.tan().max(0.001)).log().rename("TWI")

    # Solar Radiation
    solar = ee.Terrain.hillshade(elevation, 180, 70).divide(255).rename("Solar_Rad")

    return ee.Image.cat([slope, twi, solar])


"""
SPATIAL ALIGNMENT IS NEEDED
Each function above returns layers at the satellite’s native resolution
(10 m for S1/S2, 30 m for Landsat/SRTM, 70 m for ECOSTRESS) so allignement is needed.
"""
