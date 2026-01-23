import ee
import os
import json
import config
import requests
from utils import create_conn_ee, despeckle, indicesst1, generate_metadata
from modules.satellites_data_extraction import get_sentinel1_data

def get_st1(ROI=config.ROI_TEST, start_date=config.T1_START, end_date=config.T2_END, ROI_NAME="ROI_TEST"):

    create_conn_ee()
    st1_raw = get_sentinel1_data(ROI, start_date, end_date)
    st1 = st1_raw.map(despeckle)
    st1 = st1_raw.map(indicesst1)

    def sample_pixel(img):
        img = img.set('date_str', img.date().format('YYYY-MM-dd'))
        # Seleciona banda e amostra
        return img.select(['VV', 'VH', 'RATIOVHVV']).sample(
            region=ee.Geometry.Polygon(ROI),
            scale=config.SAMPLING_SCALE,
            geometries=True, # Mantém a geometria
        ).map(lambda feat: feat.set('date', img.get('date_str'))) # Passa a data da imagem para cada ponto

    # Transforma a coleção de imagens em uma coleção de pontos (FeatureCollection)
    features = st1.map(sample_pixel).flatten()

    try:
        # 2. Solicitar a URL de download (formato CSV ou GeoJSON)
        url = features.getDownloadURL(
                filetype='CSV',
                selectors=['date', 'VV', 'VH', 'RATIOVHVV', '.geo'],  # '.geo' traz a geometria em formato WKT
                filename='sentinel_data'
            )

        response = requests.get(url)
        with open(f'raw_data/{ROI_NAME}/sentinel_1/{start_date}_{end_date}.csv', 'wb') as f:
            f.write(response.content)

    except Exception as e:
        print(f"Erro ao gerar URL: {e}")

    metadata = generate_metadata("Sentinel-1", "COPERNICUS/S1_GRD", st1_raw.size().getInfo(), start_date, end_date, ['date', 'VV', 'VH', 'RATIOVHVV', '.geo'], config.runid)
    metadata_filename = f'{ROI_NAME}/sentinel_1/{config.runid}.json'
    metadata_path = os.path.join(config.metadata_path, metadata_filename)
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=4)


    return

