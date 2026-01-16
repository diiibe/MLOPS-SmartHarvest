import ee
import config
import requests
from utils import create_conn_ee, process_era5
from modules.satellites_data_extraction import get_era5_data, get_master_crs

def get_eras5(ROI=config.ROI_TEST, start_date=config.T1_START, end_date=config.T2_END):

    create_conn_ee()
    eras5_raw = get_era5_data(ROI, start_date, end_date)
    eras5 = eras5_raw.map(process_era5)

    # 2. Iteração Diária (Server-side)
    s_date = ee.Date(start_date)
    e_date = ee.Date(end_date)
    n_days = e_date.difference(s_date, 'day').round()

    def create_daily_image(n):
        day_start = s_date.advance(n, 'day')
        day_end = day_start.advance(1, 'day')

        # Filtra as 24h do dia
        daily_hours = eras5.filterDate(day_start, day_end)

        # A. Calcula as agregações (Redução Temporal -> Gera 1 Imagem)
        # Temperatura (Min, Mean, Max)
        temp_stats = daily_hours.select('temp_c').reduce(
            ee.Reducer.min().combine(ee.Reducer.mean(), sharedInputs=True).combine(ee.Reducer.max(), sharedInputs=True)
        ).rename(['MIN_TEMP_C', 'MEAN_TEMP_C', 'MAX_TEMP_C'])

        # Precipitação e Evaporação (Soma)
        water_sums = daily_hours.select(['precip', 'pet', 'aet']).reduce(
            ee.Reducer.sum()
        ).rename(['RAIN_TOTAL', 'PET_TOTAL', 'AET_TOTAL'])

        # Combina tudo em uma imagem
        daily_img = temp_stats.addBands(water_sums)

        # B. Calcula WDI (Band Operation) na imagem diária
        # WDI = PET - Rain
        wdi = daily_img.select('PET_TOTAL').subtract(daily_img.select('RAIN_TOTAL')).rename('WDI')
        daily_img = daily_img.addBands(wdi)

        # Define a data e o timestamp na imagem
        return daily_img.set({
            'system:time_start': day_start.millis(),
            'date_str': day_start.format('YYYY-MM-dd')
        })

    # Gera a lista de imagens diárias e converte para ImageCollection
    daily_images_list = ee.List.sequence(0, n_days.subtract(1)).map(create_daily_image)
    daily_col = ee.ImageCollection(daily_images_list)

    def sample_pixel(img):
        # Seleciona as bandas desejadas
        bands_to_sample = ['MIN_TEMP_C', 'MEAN_TEMP_C', 'MAX_TEMP_C', 'RAIN_TOTAL', 'PET_TOTAL', 'AET_TOTAL', 'WDI']

        return img.select(bands_to_sample).sample(
            region=ROI,
            scale=config.SAMPLING_SCALE,    # Resolução nativa do ERA5 (~11km)
            geometries=True # Mantém a geometria
        ).map(lambda feat: feat.set('date', img.get('date_str')))

    # Transforma a coleção de imagens em uma coleção de pontos (FeatureCollection)
    features = daily_col.map(sample_pixel).flatten()

    try:
        # 2. Solicitar a URL de download (formato CSV ou GeoJSON)
        url = features.getDownloadURL(
                filetype='CSV',
                selectors=['date', 'MIN_TEMP_C', 'MEAN_TEMP_C', 'MAX_TEMP_C', 'RAIN_TOTAL', 'PET_TOTAL', 'AET_TOTAL', 'WDI', '.geo'],  # '.geo' traz a geometria em formato WKT
                filename='eras5'
            )

        print(f"URL gerada com sucesso: {url}")
        print("\nVocê pode clicar no link acima ou o Python baixará o arquivo agora:")

        # 3. (Opcional) Baixar o arquivo via Python e salvar no disco
        response = requests.get(url)
        with open('dados_sentinel.csv', 'wb') as f:
            f.write(response.content)

    except Exception as e:
        print(f"Erro ao gerar URL: {e}")

    return

# master_crs = get_master_crs()
# daily_col.select(['MIN_TEMP_C', 'MEAN_TEMP_C', 'MAX_TEMP_C', 'RAIN_TOTAL', 'PET_TOTAL', 'AET_TOTAL', 'WDI']).reproject(
#     crs=master_crs,
#     scale=config.SAMPLING_SCALE,
# )