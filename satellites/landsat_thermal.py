import ee
import config
import requests
from utils import create_conn_ee
from modules.satellites_data_extraction import get_landsat_thermal_data

def get_landsat(ROI=config.ROI_TEST, start_date=config.START, end_date=config.END):

    create_conn_ee()
    landsat_raw = get_landsat_thermal_data(ROI, start_date, end_date)

    def process_thermal(image):
        # ST_B10 is the thermal band in Landsat Collection 2 Level 2
        # It's already in Kelvin, scaled by 0.00341802 + 149.0
        lst_kelvin = image.select('ST_B10').multiply(0.00341802).add(149.0)
        lst_celsius = lst_kelvin.subtract(273.15)
        
        # Apply QA mask if needed
        qa = image.select('QA_PIXEL')
        # Bit 3: Cloud
        # Bit 4: Cloud Shadow
        cloud_mask = qa.bitwiseAnd(1 << 3).eq(0).And(qa.bitwiseAnd(1 << 4).eq(0))
        
        return lst_celsius.updateMask(cloud_mask).rename('LST').copyProperties(image, ['system:time_start'])
    
    # Process all images
    landsat_processed = landsat_raw.map(process_thermal)

    def sample_pixel(img):
        img = img.set('date_str', img.date().format('YYYY-MM-dd'))
        # Seleciona banda e amostra
        return img.select(['LST']).sample(
            region=ROI, 
            scale=config.SAMPLING_SCALE,
            geometries=True, # Mantém a geometria
        ).map(lambda feat: feat.set('date', img.get('date_str'))) # Passa a data da imagem para cada ponto

    # Transforma a coleção de imagens em uma coleção de pontos (FeatureCollection)
    features = landsat_processed.map(sample_pixel).flatten()

    try:        
        # 2. Solicitar a URL de download (formato CSV ou GeoJSON)
        url = features.getDownloadURL(
                filetype='CSV', 
                selectors=['date', 'LST', '.geo'],  # '.geo' traz a geometria em formato WKT
                filename='sentinel_data'
            )
        
        print(f"URL gerada com sucesso: {url}")
        print("\nVocê pode clicar no link acima ou o Python baixará o arquivo agora:")

        # 3. (Opcional) Baixar o arquivo via Python e salvar no disco
        response = requests.get(url)
        with open('landsat.csv', 'wb') as f:
            f.write(response.content)

    except Exception as e:
        print(f"Erro ao gerar URL: {e}")

    return

