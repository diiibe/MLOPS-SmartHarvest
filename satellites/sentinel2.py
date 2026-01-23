import ee
import os
import json
import config
import requests

from utils import create_conn_ee, indicesanddate, generate_metadata
from modules.satellites_data_extraction import get_sentinel2_data
from modules.s2cleaning import get_adaptive_core, extract_parcel_stats, validate_parcel_observation


def get_st2(ROI=config.ROI_TEST, start_date=config.T1_START, end_date=config.T2_END, use_erosion=True):

    create_conn_ee()
    st2_raw = get_sentinel2_data(ROI, start_date, end_date)
    st2 = st2_raw.map(indicesanddate)

    # def sample_pixel(img):
    #     img = img.set('date_str', img.date().format('YYYY-MM-dd'))
    #     # Seleciona banda e amostra
    #     return img.select(['NDVI', 'EVI', 'GNDVI', 'IRECI', 'NDMI', 'MNDWI', 'NDRE']).sample(
    #         region=ee.Geometry.Polygon(ROI),
    #         scale=config.SAMPLING_SCALE,
    #         geometries=True, # Mantém a geometria
    #     ).map(lambda feat: feat.set('date', img.get('date_str'))) # Passa a data da imagem para cada ponto

    # # Transforma a coleção de imagens em uma coleção de pontos (FeatureCollection)
    # features = st2.map(sample_pixel).flatten()

    # try:
    #     # 2. Solicitar a URL de download (formato CSV ou GeoJSON)
    #     url = features.getDownloadURL(
    #             filetype='CSV',
    #             selectors=['date', 'NDVI', 'EVI', 'GNDVI', 'IRECI', 'NDMI', 'MNDWI', 'NDRE', '.geo'],  # '.geo' traz a geometria em formato WKT
    #             filename='sentinel_data'
    #         )

    #     response = requests.get(url)


    count = st2.size().getInfo()
    print(f"   Found {count} clean images")
    
    if count == 0:
        print("   No images found. Exiting.")
        return None
    
    # Step 2: Apply adaptive erosion (if enabled)
    if use_erosion:
        print("\n2. Applying adaptive parcel erosion...")
        core_result = get_adaptive_core(ROI, sampling_scale=config.SAMPLING_SCALE)
        roi_to_use = core_result['core_geometry']
        erosion_applied = core_result['erosion_applied'].getInfo()
        is_small = core_result['is_small_parcel'].getInfo()
        
        original_area = ee.Geometry.Polygon(ROI).area().getInfo() if isinstance(ROI, list) else ROI.area().getInfo()
        core_area = roi_to_use.area().getInfo()
        
        print(f"   Original area: {original_area:.0f} m²")
        print(f"   Core area: {core_area:.0f} m² ({((original_area - core_area) / original_area * 100):.1f}% reduction)")
        print(f"   Erosion applied: {erosion_applied}m")
        print(f"   Small parcel: {bool(is_small)}")
    else:
        roi_to_use = ee.Geometry.Polygon(ROI) if isinstance(ROI, list) else ROI
        erosion_applied = 0
        is_small = 0
        print("\n2. Erosion disabled, using full ROI")
    
    # Step 3: Extract data with QA metadata
    print("\n3. Extracting pixel data with QA metadata...")
    
    def sample_with_qa(img):
        """Sample pixels and add QA metadata per image."""
        img = img.set('date_str', img.date().format('YYYY-MM-dd'))
        
        # Extract statistics for QA
        stats = extract_parcel_stats(img, roi_to_use, sampling_scale=config.SAMPLING_SCALE)
        
        # Validate observation
        is_valid = validate_parcel_observation(stats, is_small_parcel=is_small)
        
        # Get QA values
        valid_count = stats.get('valid_pixel_count')
        total_count = stats.get('total_pixel_count')
        coverage = stats.get('coverage_ratio')

        # Sample pixels
        # Note: MNDWI is not available (bug in utils.py - mndwi function calculates NDRE instead)
        indices = ['NDVI', 'EVI', 'GNDVI', 'IRECI', 'NDMI', 'NDRE']
        sampled = img.select(indices).sample(
            region=roi_to_use,
            scale=config.SAMPLING_SCALE,
            geometries=True
        )
        
        # Add metadata to each feature
        def add_metadata(feat):
            return feat.set({
                'date': img.get('date_str'),
                'valid_pixels': valid_count,
                'total_pixels': total_count,
                'coverage_ratio': coverage,
                'observation_valid': is_valid,
                'erosion_m': erosion_applied,
                'is_small_parcel': is_small
            })
        
        return sampled.map(add_metadata)
    
    # Process all images
    features = st2.map(sample_with_qa).flatten()
    
    # Get download URL
    print("\n4. Generating download URL...")
    selectors = [
        'date', 
        'NDVI', 'EVI', 'GNDVI', 'IRECI', 'NDMI', 'NDRE',
        'valid_pixels', 'total_pixels', 'coverage_ratio', 
        'observation_valid', 'erosion_m', 'is_small_parcel',
        '.geo'
    ]
    
    try:
        url = features.getDownloadURL(
            filetype='CSV',
            selectors=selectors,
            filename='sentinel2_polibio'
        )
        
        print("   Downloading data...")
        response = requests.get(url)

        with open(f'raw_data/sentinel_2_{start_date}_{end_date}.csv', 'wb') as f:
            f.write(response.content)

    except Exception as e:
        print(f"Erro ao gerar URL: {e}")


    metadata = generate_metadata("Sentinel-2", "COPERNICUS/S2_SR_HARMONIZED", st2.size().getInfo(), start_date, end_date, selectors, config.runid)
    metadata_filename = f'{config.runid}/metadata_sentinel_2.json'
    metadata_path = os.path.join(config.metadata_path, metadata_filename)
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=4)

    return