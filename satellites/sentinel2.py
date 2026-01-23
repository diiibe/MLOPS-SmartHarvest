import ee
import config
import requests
from modules.satellites_data_extraction import get_sentinel2_data
from utils import create_conn_ee, cloudmask, indicesanddate

def get_st2(ROI=config.ROI_TEST, start_date=config.T1_START, end_date=config.T2_END):

    create_conn_ee()
    st2_raw = get_sentinel2_data(ROI, start_date, end_date)
    st2 = st2_raw.map(indicesanddate)

    def sample_pixel(img):
        img = img.set('date_str', img.date().format('YYYY-MM-dd'))
        # Seleciona banda e amostra
        return img.select(['NDVI', 'EVI', 'GNDVI', 'IRECI', 'NDMI', 'MNDWI', 'NDRE']).sample(
            region=ee.Geometry.Polygon(ROI),
            scale=config.SAMPLING_SCALE,
            geometries=True, # Mantém a geometria
        ).map(lambda feat: feat.set('date', img.get('date_str'))) # Passa a data da imagem para cada ponto

    # Transforma a coleção de imagens em uma coleção de pontos (FeatureCollection)
    features = st2.map(sample_pixel).flatten()

    try:
        # 2. Solicitar a URL de download (formato CSV ou GeoJSON)
        url = features.getDownloadURL(
                filetype='CSV',
                selectors=['date', 'NDVI', 'EVI', 'GNDVI', 'IRECI', 'NDMI', 'MNDWI', 'NDRE', '.geo'],  # '.geo' traz a geometria em formato WKT
                filename='sentinel_data'
            )

        response = requests.get(url)
        with open(f'raw_data/sentinel_2_{start_date}_{end_date}.csv', 'wb') as f:
            f.write(response.content)

    except Exception as e:
        print(f"Erro ao gerar URL: {e}")

    return