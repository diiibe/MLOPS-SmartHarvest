import ee
import config
import pandas as pd
from utils import create_conn_ee, ndvi, gdd
from modules.satellites import sentinel1, sentinel2, landsat_thermal, era5_soil, srtm

def staticexport():
    # 1. Initialize Connection and ROI
    print("Test A: Connecting to Earth Engine...")
    create_conn_ee()
    
    # Initialize ROI in config
    config.ROI = ee.Geometry.Polygon(config.ROI_TEST)
    print("ROI initialized.")

    # 2. Data Availability Checks (Test B)
    s2_col = sentinel2.get_sentinel2_data()
    era5_col = era5_soil.get_era5_data()
    
    print(f"Test B: Data Availability")
    print(f"Immagini S2 caricate: {s2_col.size().getInfo()}")
    print(f"Immagini ERA5 caricate: {era5_col.size().getInfo()}")

    # 3. Sentinel-2 Aggregation (NDVI Peak & Late)
    s2_with_ndvi = s2_col.map(ndvi)
    ndvi_peak = s2_with_ndvi.select('NDVI').max().rename('NDVI_Peak')
    ndvi_late = s2_with_ndvi.sort('system:time_start', False).first().select('NDVI').rename('NDVI_Late')

    # 4. Sentinel-1 Aggregation (VH Drop)
    # T1: Vegetative, T2: Ripening
    s1_col = sentinel1.get_sentinel1_data()
    vh_t1 = s1_col.filterDate(config.T1_START, config.T2_START).select('VH').mean()
    vh_t2 = s1_col.filterDate(config.T2_START, config.T2_END).select('VH').mean()
    vh_drop = vh_t1.subtract(vh_t2).rename('VH_Drop')

    # 5. ERA5 Aggregation (GDD & Rain)
    era5_processed = era5_col.map(gdd)
    gdd_tot = era5_processed.select('GDD').sum().rename('GDD_tot')
    rain_tot = era5_processed.select('total_precipitation').sum().rename('Rain_tot')

    # 6. Landsat Aggregation (Mean LST)
    # LST calculation: ST_B10 * 0.00341802 + 149.0 - 273.15
    lst_col = landsat_thermal.get_landsat_thermal()
    def lst(img):
        lst = img.select('ST_B10').multiply(0.00341802).add(149.0).subtract(273.15).rename('LST')
        return img.addBands(lst)
    
    lst_mean = lst_col.map(lst).select('LST').mean().rename('LST')

    # 7. SRTM (Elevation, Slope, Aspect)
    elevation = srtm.get_srtm_data()
    slope = ee.Terrain.slope(elevation).rename('Slope')
    aspect = ee.Terrain.aspect(elevation).rename('Aspect')
    elevation = elevation.rename('Elevation')

    # 8. Stacking all bands (Test C)
    final_stack = ee.Image.cat([
        ndvi_peak, ndvi_late, vh_drop, 
        gdd_tot, rain_tot, lst_mean, 
        elevation, slope, aspect
    ]).clip(config.ROI)
    
    print("Test C: Stack Bands")
    print("Bande generate:", final_stack.bandNames().getInfo())

    # 9. Extracting Data using reduceRegion (more efficient)
    print(f"Extracting pixels at {config.SAMPLING_SCALE}m scale...")
    
    # Add coordinates as bands to extract them as well
    coord_img = ee.Image.pixelLonLat()
    final_stack_with_coords = final_stack.addBands(coord_img)
    
    data_dict = final_stack_with_coords.reduceRegion(
        reducer=ee.Reducer.toList(),
        geometry=config.ROI,
        scale=config.SAMPLING_SCALE,
        maxPixels=1e9
    ).getInfo()

    # 10. Converting to Pandas and Exporting (Step 4)
    df = pd.DataFrame(data_dict)
    
    # Format .geo column
    if 'longitude' in df.columns and 'latitude' in df.columns:
        df['.geo'] = df.apply(lambda row: f"Point [{row['longitude']}, {row['latitude']}]", axis=1)
    
    # Save to CSV
    output_file = 'SmartHarvest_New_Vineyard.csv'
    df.to_csv(output_file, index=False)
    print(f"Step 4: Dataset saved to {output_file}")
    print(f"Total rows: {len(df)}")

if __name__ == "__main__":
    staticexport()
