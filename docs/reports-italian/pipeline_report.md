# SmartHarvest Wine - Relazione Tecnica di Progetto

**Progetto:** SmartHarvest Wine - Pipeline di Zonazione Viticola  
**Data:** Novembre 2025  
**Versione:** 1.0

---

## Indice

1. [Executive Summary](#1-executive-summary)
2. [Genesi del Progetto e Motivazioni](#2-genesi-del-progetto-e-motivazioni)
3. [Architettura della Pipeline](#3-architettura-della-pipeline)
4. [Flusso dei Dati e Processamento](#4-flusso-dei-dati-e-processamento)
5. [Feature Engineering: Dinamiche Temporali](#5-feature-engineering-dinamiche-temporali)
6. [Metriche e Statistiche: Guida all'Interpretazione](#6-metriche-e-statistiche-guida-allinterpretazione)
7. [Validazione e Controllo Qualità](#7-validazione-e-controllo-qualità)
8. [Scelte Progettuali e Rationale](#8-scelte-progettuali-e-rationale)
9. [Conclusioni e Sviluppi Futuri](#9-conclusioni-e-sviluppi-futuri)

---

## 1. Executive Summary

SmartHarvest Wine è una pipeline di elaborazione dati satellitari multi-sorgente progettata per generare un **Data Cube** ad alta risoluzione (10m) per la zonazione di precisione dei vigneti. Il sistema integra dati ottici (Sentinel-2), radar (Sentinel-1), termici (Landsat 8/9), topografici (SRTM) e climatici (ERA5) per catturare le **dinamiche spazio-temporali** della vegetazione e del terreno durante la stagione vegetativa.

**Obiettivo primario:** Fornire ai viticoltori uno strumento basato su dati scientifici per identificare zone omogenee all'interno del vigneto, ottimizzando la gestione differenziata e migliorando la qualità del prodotto finale.

**Risultato:** Un dataset georeferenziato di 10.994 pixel contenente 12 feature chiave, validato statisticamente e visivamente, pronto per algoritmi di clustering e machine learning.

---

## 2. Genesi del Progetto e Motivazioni

### 2.1 Il Problema

La viticoltura di precisione richiede la capacità di **comprendere la variabilità spaziale** all'interno di un vigneto. Due viti nella stessa parcella possono avere esigenze idriche, nutrizionali e fenologiche molto diverse a causa di:
- **Microtopografia** (pendenze, esposizione al sole)
- **Proprietà del suolo** (drenaggio, ritenzione idrica)
- **Vigore vegetativo** (densità fogliare, capacità fotosintetica)

Tradizionalmente, questa variabilità viene mappata attraverso **rilievi in campo**, costosi e limitati nel tempo. I dati satellitari offrono una **visione sinottica e continua**, ma richiedono:
1. **Integrazione multi-sensore** (ogni satellite cattura aspetti diversi)
2. **Analisi temporale** (la fenologia non è statica)
3. **Risoluzione spaziale adeguata** (10m per distinguere i filari)

### 2.2 La Soluzione

SmartHarvest Wine nasce dall'esigenza di **automatizzare** l'estrazione di informazioni agronomiche rilevanti da fonti eterogenee, trasformando terabyte di dati grezzi in un dataset compatto e interpretabile.

**Intuizione chiave:** Non basta misurare il vigore vegetativo in un istante (es. NDVI a luglio). È necessario catturare **come evolve** nel tempo:
- **NDVI Peak → Late:** Il vigneto sta crescendo o sta già senescendo?
- **VH Drop:** La struttura della chioma sta perdendo acqua (stress idrico)?
- **Insolation:** Questa zona riceve più sole e quindi maturerà prima?

Queste **dinamiche temporali** sono il cuore innovativo del progetto.

---

## 3. Architettura della Pipeline

### 3.1 Struttura Modulare

La pipeline è organizzata in **moduli indipendenti**, ciascuno responsabile di una sorgente dati:

```
main.py
   │
   ├─→ sentinel2.py      (Optical: NDVI dynamics)
   ├─→ sentinel1.py      (Radar: VH dynamics)
   ├─→ srtm.py           (Topography: Slope, Aspect, Insolation)
   ├─→ landsat_thermal.py (Thermal: LST)
   ├─→ era5_soil.py      (Climate: Rain, GDD)
   │
   └─→ assembly.py       (Data Cube assembly & export)
        └─→ reporting.py  (Metadata report)
```

**Vantaggi di questa architettura:**
- **Manutenibilità:** Ogni modulo può essere testato e modificato indipendentemente
- **Estensibilità:** Nuove sorgenti possono essere aggiunte senza modificare il core
- **Tracciabilità:** Ogni modulo restituisce metadati (count, date range) per il report finale

### 3.2 Componenti Chiave

#### config.py
Centralizza i parametri globali:
- **ROI_COORDS:** Coordinate del poligono del vigneto
- **Finestre Fenologiche:** T1 (sviluppo vegetativo), T2 (maturazione)
- **TARGET_SCALE:** Risoluzione finale (10m)
- **CLOUD_THRESHOLD:** Soglia di copertura nuvolosa (20%)

**Rationale:** Un file di configurazione unico rende la pipeline **riutilizzabile** per altri vigneti semplicemente cambiando le coordinate e le date.

#### modules/
Ogni modulo implementa una funzione standard:
```python
def get_<source>_data(master_crs) -> (ee.Image, metadata_dict)
```

**Contratto:** Restituire un'immagine Earth Engine proiettata sul CRS master (Sentinel-2) e un dizionario di metadati per il report.

#### tools/
Script di analisi e visualizzazione:
- **analyze_temporal_data.py:** Statistiche descrittive, correlazioni, plausibilità
- **visualize_data_map.py:** Mappa interattiva multi-layer
- **debug_bands.py:** Debugging delle bande di output di ogni modulo

---

## 4. Flusso dei Dati e Processamento

### 4.1 Fase 1: Inizializzazione

```python
ee.Initialize()  # Autenticazione Google Earth Engine
config.ROI = ee.Geometry.Polygon(config.ROI_COORDS)
```

**Earth Engine** è una piattaforma cloud per l'elaborazione geospaziale. Permette di processare petabyte di dati satellitari senza doverli scaricare localmente.

### 4.2 Fase 2: Processamento Sentinel-2 (Master)

**Sentinel-2** è il satellite ottico dell'ESA con risoluzione 10m nelle bande visibili e NIR.

```python
s2_collection = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
    .filterBounds(ROI)
    .filterDate(START_DATE, END_DATE)
    .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20))
```

**Passaggi:**
1. **Cloud Masking:** Rimozione pixel nuvolosi usando la banda QA60
2. **NDVI Calculation:** `(NIR - RED) / (NIR + RED)`
3. **Splitting temporale:** Collezione divisa in T1 e T2
4. **Feature Engineering:**
   - `NDVI_Peak = max(NDVI_T1)` → Vigore massimo in fase vegetativa
   - `NDVI_Late = mean(NDVI_T2)` → Vigore medio in maturazione
   - `NDVI_Delta = NDVI_Late - mean(NDVI_T1)` → Cambiamento tra le fasi
   - `NDVI_Stability = stdDev(NDVI_T2)` → Uniformità temporale

**Perché questi feature?**
- **NDVI_Peak:** Identifica le zone con massima capacità fotosintetica (potenziale produttivo)
- **NDVI_Delta:** Distingue zone che senescono presto (stress) da quelle stabili
- **NDVI_Stability:** Bassa stabilità indica disomogeneità fenologica (zone problematiche)

**Proiezione Master:** Il CRS di Sentinel-2 (EPSG:32633, UTM Zone 33N) diventa il **riferimento** per tutti gli altri layer, garantendo coerenza geometrica.

### 4.3 Fase 3: Processamento Sentinel-1 (Radar)

**Sentinel-1** è un radar ad apertura sintetica (SAR) che penetra le nuvole e misura la **backscatter** (riflessione del segnale).

**Banda VH (Vertical-Horizontal):** Sensibile alla struttura della vegetazione e al contenuto idrico.

```python
s1_collection = ee.ImageCollection('COPERNICUS/S1_GRD')
    .filter(ee.Filter.eq('instrumentMode', 'IW'))
    .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VH'))
```

**Passaggi:**
1. **Despeckling:** Filtro focale (BoxCar 5x5) per ridurre il rumore granulare tipico del SAR
2. **Metadata Preservation:** `copyProperties(image, ['system:time_start'])` → Preserva timestamp per filtraggio temporale
3. **Feature Engineering:**
   - `VH_Late = mean(VH_T2)` → Backscatter in maturazione
   - `VH_Drop = VH_Late - mean(VH_T1)` → Variazione tra fasi

**Perché VH_Drop?**
- Un **drop positivo** (VH diminuisce) indica **perdita di struttura** o **disseccamento** della chioma
- Tipicamente correla con stress idrico o senescenza anticipata
- VH è più sensibile a questi cambiamenti rispetto a NDVI in alcune condizioni

**Problema risolto:** Inizialmente VH_Drop risultava vuoto perché il despeckling rimuoveva la proprietà `system:time_start`. Aggiungendo `copyProperties()`, il filtraggio temporale funziona correttamente.

### 4.4 Fase 4: Processamento SRTM (Topografia)

**SRTM** (Shuttle Radar Topography Mission) fornisce un Digital Elevation Model (DEM) a 30m di risoluzione.

```python
srtm = ee.Image('USGS/SRTMGL1_003')
terrain = ee.Algorithms.Terrain(srtm)
slope = terrain.select('slope')
aspect = terrain.select('aspect')
```

**Feature Engineering:**
```python
insolation = slope.multiply(aspect.multiply(Math.PI/180).cos())
```

**Cosa rappresenta Insolation?**
- È un **proxy dell'esposizione solare** basato su pendenza e orientamento
- `cos(Aspect)`: Massimo quando il versante è a Sud (180°), minimo a Nord (0°/360°)
- `Slope × cos(Aspect)`: Zone ripide rivolte a Sud ricevono più radiazione

**Perché è importante?**
- L'esposizione influenza **temperatura del suolo**, **umidità relativa**, **accumulo GDD**
- Zone esposte a Sud maturano prima (anticipo vendemmia)
- Zone in ombra possono avere problemi di maturazione

**Upsampling:** Da 30m a 10m con interpolazione bilineare per allinearsi al master CRS.

### 4.5 Fase 5: Processamento Landsat Thermal

**Landsat 8/9** trasporta sensori termici (TIRS) che misurano la temperatura superficiale.

**Perché non ECOSTRESS?**
- Inizialmente previsto, ma la collezione `NASA/ECOSTRESS/L2_LSTE` è **deprecata/inaccessibile** su Earth Engine
- **Soluzione:** Merge di Landsat 8 e Landsat 9 (maggiore copertura temporale)

```python
l8 = ee.ImageCollection('LANDSAT/LC08/C02/T1_L2')
l9 = ee.ImageCollection('LANDSAT/LC09/C02/T1_L2')
landsat = l8.merge(l9)
```

**Conversione Kelvin → Celsius:**
```python
lst_celsius = (ST_B10 * 0.00341802 + 149.0) - 273.15
```

**Upsampling:** Da 100m (risoluzione nativa termica) a 10m con **interpolazione bicubica**.

**LST_med:** Mediana della temperatura superficiale nel periodo studiato.

**Interpretazione:**
- Temperature elevate indicano **stress termico** o **scarsa copertura vegetale**
- Correlazione positiva con NDVI_Delta (zone calde senescono prima)
- Utilizzabile per stimare **evapotraspirazione**

### 4.6 Fase 6: Processamento ERA5 (Clima)

**ERA5-Land** è il dataset di rianalisi climatica dell'ECMWF con risoluzione 9km.

```python
era5 = ee.ImageCollection('ECMWF/ERA5_LAND/DAILY_AGGR')
```

**Feature:**
1. **Rain_tot:** Somma precipitazioni totali nel periodo
2. **GDD_tot:** Somma Growing Degree Days

**GDD (Growing Degree Days):**
```python
GDD = (T_max + T_min)/2 - T_base
```
Con `T_base = 10°C` per la vite.

**Cosa rappresentano i GDD?**
- Misura dell'**accumulo termico** necessario per lo sviluppo fenologico
- 1500-2000 GDD → Maturazione completa per uve da tavola
- Zona-specifico: zone con più GDD maturano prima

**Broadcasting:** I dati 9km vengono "estesi" a 10m (ogni pixel 10m ha lo stesso valore del pixel 9km sovrastante).

**Perché includere dati climatici?**
- Contestualizzano le dinamiche vegetative osservate
- Rain + GDD spiegano parte della variabilità di NDVI e LST

### 4.7 Fase 7: Assembly e Export

```python
data_cube = ee.Image.cat([
    s2_img,      # NDVI_Peak, Late, Delta, Stability
    srtm_img,    # Slope, Aspect, Insolation
    s1_img,      # VH_Late, VH_Drop
    thermal_img, # LST_med
    era5_img     # Rain_tot, GDD_tot
])
```

**Sampling:**
```python
samples = data_cube.sample(
    region=ROI,
    scale=10,
    projection=master_crs,
    geometries=True  # Mantiene coordinate per la mappa
)
```

**Export:**
1. **Google Drive:** Task asincrono (`ee.batch.Export.table.toDrive`)
2. **Download locale:** `samples.getDownloadURL(filetype='csv')` → `output/SmartHarvest_DataCube_Temporal.csv`

**Perché entrambi?**
- Drive: Backup e condivisione
- Locale: Analisi immediata

---

## 5. Feature Engineering: Dinamiche Temporali

### 5.1 Filosofia

L'approccio tradizionale al telerilevamento viticolo si basa su **snapshot statici** (es. NDVI medio stagionale). SmartHarvest Wine adotta una **prospettiva dinamica**:

**Domanda chiave:** "Come cambia il vigneto nel tempo?"

**Finestre Fenologiche:**
- **T1 (1 Giugno - 20 Luglio):** Sviluppo vegetativo, crescita fogliare, fioritura
- **T2 (21 Luglio - 10 Settembre):** Inolizione, maturazione, accumulo zuccheri

### 5.2 Feature Dettagliate

#### NDVI_Peak
**Definizione:** Massimo NDVI durante T1  
**Formula:** `max(NDVI_t1_images)`

**Significato agronomico:**
- Rappresenta il **potenziale fotosintetico massimo** della zona
- Zone con NDVI_Peak > 0.85: Densità fogliare ottimale, probabile sovraproduzione
- Zone con NDVI_Peak < 0.65: Vigore limitato, possibile stress nutrizionale

**Interpretazione visiva (mappa):**
- **Verde intenso:** Alto vigore
- **Giallo/Arancione:** Vigore moderato
- **Rosso:** Vigore basso (gap, terreno nudo, stress)

**Esempio concreto:**
In un vigneto di Pinot Nero, zone con NDVI_Peak costantemente > 0.9 possono indicare eccesso di vigoria → rischio di diluizione aromatica → candidato per diradamento o gestione differenziata.

#### NDVI_Delta
**Definizione:** Variazione NDVI tra T1 e T2  
**Formula:** `mean(NDVI_T2) - mean(NDVI_T1)`

**Significato agronomico:**
- **Δ > 0 (positivo):** Crescita continua, possibile ritardo fenologico
- **Δ ≈ 0:** Stabilità, fenologia regolare
- **Δ < 0 (negativo):** Senescenza anticipata, possibile stress

**Errori comuni di interpretazione:**
- ❌ "NDVI_Delta negativo è sempre male" → Falso. Una senescenza fisiologica post-invaiatura è normale.
- ✅ **Attenzione a:** NDVI_Delta molto negativo (< -0.15) combinato con VH_Drop elevato → probabile stress idrico severo.

**Correlazioni attese:**
- Positiva con LST (zone calde senescono prima → Δ negativo, LST alto)
- Negativa con Rain_tot (più pioggia → mantenimento vigore)

#### NDVI_Stability
**Definizione:** Deviazione standard di NDVI in T2  
**Formula:** `stdDev(NDVI_T2)`

**Significato pratico:**
- **Bassa stabilità (σ > 0.1):** La zona ha comportamento **erratico** nel tempo
- **Alta stabilità (σ < 0.05):** Comportamento **omogeneo** e prevedibile

**Perché è importante?**
- Zone instabili possono indicare:
  - **Problemi di irrigazione** (stress intermittente)
  - **Eterogeneità del suolo** (zone con ristagno idrico alternato a zone drenanti)
  - **Malattie fogliari** (defogliazione irregolare)

**Uso nella zonazione:**
- Zone ad alta stabilità → Gestione standard
- Zone instabili → Monitoraggio intensivo, irrigazione localizzata

#### VH_Late
**Definizione:** Backscatter VH medio in T2  
**Unità:** dB (decibel)  
**Range tipico:** -20 a -15 dB

**Significato fisico:**
- VH misura la **riflessione incrociata** del segnale radar
- Sensibile alla **struttura tridimensionale** della chioma e al **contenuto idrico**
- Valori più alti (meno negativi) → Più biomassa/acqua

**Interpretazione:**
- VH_Late = -15 dB: Chioma densa e idratata
- VH_Late = -19 dB: Chioma rarefatta o disidratata

#### VH_Drop
**Definizione:** Variazione VH tra T1 e T2  
**Formula:** `mean(VH_T2) - mean(VH_T1)`

**Significato agronomico:**
- **VH_Drop > 0:** VH è aumentato (improbabile in viticultura)
- **VH_Drop ≈ 0:** Struttura stabile
- **VH_Drop < 0 (negativo):** VH è diminuito → **perdita di struttura o acqua**

**Attenzione alla semantica:**
Il nome "Drop" indica una diminuzione, ma matematicamente è un valore **negativo**. Nella nostra implementazione:
```python
vh_drop = vh_late.subtract(vh_t1_mean)
```
Se `vh_late < vh_t1_mean`, allora `vh_drop < 0` → "Drop" effettivo.

**Nella mappa:**
- **Verde:** VH stabile o in aumento (nessun drop)
- **Giallo:** Leggero drop
- **Rosso:** Drop significativo (stress)

**Esempio:**
Zona A: VH_Drop = -0.5 dB → Perdita moderata  
Zona B: VH_Drop = -2.0 dB → Perdita severa → Candidato per irrigazione d'emergenza

#### Insolation
**Definizione:** Proxy di esposizione solare  
**Formula:** `Slope × cos(Aspect)`

**Range:**
- Massimo: ~+3.7 (pendenza ripida verso Sud)
- Zero: Terreno pianeggiante o rivolto Est/Ovest
- Minimo: ~-5.5 (pendenza ripida verso Nord)

**Interpretazione:**
- **Insolation > 2:** Zona molto esposta → Maturazione anticipata, possibile stress termico
- **Insolation ≈ 0:** Esposizione neutra
- **Insolation < -2:** Zona in ombra → Maturazione ritardata, rischio di umidità eccessiva

**Uso pratico:**
- Pianificazione vendemmia zonale (zone esposte prima)
- Scelta clonale (cloni precoci in zone fresche, tardivi in zone calde)

#### LST (Land Surface Temperature)
**Unità:** °C  
**Range tipico (estate italiana):** 30-40°C

**Cosa rappresenta:**
- Temperatura della **superficie** (non dell'aria!)
- Misurata a mezzogiorno → Massimo stress termico
- Include contributo di suolo nudo + vegetazione

**Correlazioni:**
- Negativa con NDVI (più vegetazione → minore temperatura)
- Positiva con stress idrico (suolo secco si scalda di più)

**Interpretazione:**
- LST = 32°C: Condizioni ottimali
- LST > 38°C: Possibile stress termico
- LST < 30°C: Zona fresca (possibile eccesso di ombreggiamento)

#### Rain_tot
**Unità:** mm  
**Interpretazione:**
- Contestualizza le dinamiche osservate
- Stagione secca (Rain_tot < 100 mm) → NDVI_Delta negativo è atteso
- Piogge abbondanti → Mantenimento vigore, rischio malattie fungine

#### GDD_tot
**Unità:** Gradi-giorno (°C × giorni)  
**Range tipico:** 1200-1600 GDD per la stagione considerata

**Interpretazione:**
- GDD elevato → Maturazione rapida
- Zone con stesso GDD_tot ma NDVI_Delta diverso → Variabilità dovuta ad altri fattori (suolo, irrigazione)

---

## 6. Metriche e Statistiche: Guida all'Interpretazione

### 6.1 Statistiche Descrittive (DATA_VALIDATION_REPORT.md)

**Esempio dalla tabella:**
```
NDVI_Peak: mean=0.855, std=0.058, min=0.320, max=0.936
```

**Cosa ci dice:**
- **Media 0.855:** Il vigneto ha generalmente buon vigore
- **Std 0.058:** Variabilità moderata (~7% della media) → Vigneto abbastanza omogeneo
- **Min 0.320:** Presenza di anomalie (gap, strade, terreno nudo?)
- **Max 0.936:** Non saturazione → dati affidabili

**Red flag da cercare:**
- Std molto alta (>15% della media) → Forte disomogeneità
- Min molto basso in feature che dovrebbero essere positivi → Presenza di outlier

### 6.2 Matrice di Correlazione

**Esempio:**
```
          NDVI_Peak  NDVI_Delta  VH_Drop   LST
NDVI_Peak     1.00       -0.34    -0.37  -0.23
NDVI_Delta   -0.34        1.00     0.30   0.34
VH_Drop      -0.37        0.30     1.00   0.30
LST          -0.23        0.34     0.30   1.00
```

**Interpretazione:**

**NDVI_Peak ↔ NDVI_Delta (-0.34):**
- Correlazione **negativa moderata**
- Zone con alto vigore iniziale (NDVI_Peak alto) tendono a senescare leggermente (NDVI_Delta negativo)
- **Agronomicamente sensato:** Viti vigorose esauriscono prima le riserve

**NDVI_Delta ↔ LST (+0.34):**
- Correlazione **positiva moderata**
- Zone più calde mantengono o aumentano NDVI (paradossale?)
- **Possibile spiegazione:** Effetto confondente dell'irrigazione (zone calde irrigate mantengono vigore)

**VH_Drop ↔ NDVI_Delta (+0.30):**
- Correlazione **positiva debole**
- Zone con drop strutturale tendono a senescare (coerente con stress idrico)

**Cosa evitare:**
- ❌ "Correlazione alta → causalità" → Falso. Può essere confondimento.
- ✅ Usare correlazioni per **ipotesi da verificare**, non come verità assolute.

### 6.3 Plausibilità (Sanity Checks)

**NDVI_Delta Mean: +0.033**
- ✅ Plausibile: Leggera crescita tra T1 e T2 (fenologia regolare)
- Se fosse -0.30 → ⚠️ Anomalia (senescenza severa precoce)

**LST Mean: 34.25°C**
- ✅ Plausibile per estate italiana
- Se fosse 50°C → ⚠️ Errore nei dati o evento estremo

**Questi check intercettano:**
- Errori di conversione unità (es. Kelvin non convertiti)
- Date sbagliate (dati invernali invece che estivi)
- ROI errato (vigneto in altra regione climatica)

---

## 7. Validazione e Controllo Qualità

### 7.1 Validazione Statistica

**Script:** `tools/analyze_temporal_data.py`

**Controlli implementati:**
1. **Completezza:** Nessun valore mancante
2. **Range:** Ogni feature ha valori plausibili
3. **Distribuzione:** Ispezione visiva degli istogrammi
4. **Outlier:** Metodo IQR (valori oltre 1.5×IQR)

**Output:** `output/DATA_VALIDATION_REPORT.md`

### 7.2 Validazione Visiva

**Script:** `tools/visualize_data_map.py`

**Funzionalità:**
- Mappa interattiva con background satellitare
- **Layer switching:** Ogni metrica visualizzabile separatamente
- **Popup:** Click su punto → Valori esatti

**Come usarla:**
1. Apri `output/SmartHarvest_Verification_Map.html`
2. Seleziona layer "NDVI Peak"
3. Verifica che punti verdi coincidano con filari visibili
4. Seleziona "LST" → Zone rosse dovrebbero essere su terreno nudo/esposto
5. Seleziona "VH Drop" → Zone rosse (drop alto) dovrebbero corrispondere a zone visivamente secche

**Questo controllo incrociato garantisce:**
- Geometria corretta (punti sul vigneto, non fuori)
- Coerenza tra metriche (NDVI basso + LST alto = coerente)
- Assenza di artefatti spaziali (pattern a scacchiera, discontinuità innaturali)

### 7.3 Debug e Troubleshooting

**Script:** `tools/debug_bands.py`

**Quando usarlo:**
- Band mancanti nel CSV
- Valori tutti uguali (broadcasting errato)
- Errori in fase di export

**Output:**
```
Sentinel-1:
Bands: ['VH_Late', 'VH_Drop']  # ✅ OK

Sentinel-1:
Bands: []  # ❌ Problema!
```

**Esempio di debug reale:**
Durante lo sviluppo, `VH_Late` e `VH_Drop` risultavano vuoti. Il debug ha rivelato:
```
Sentinel-1 T1 images: 0  # ❌ Collezione vuota!
```
**Causa:** `focal_mean` rimuoveva `system:time_start` → `filterDate` falliva.  
**Fix:** Aggiunto `copyProperties(image, ['system:time_start'])`.

---

## 8. Scelte Progettuali e Rationale

### 8.1 Perché Earth Engine?

**Alternative considerate:**
- **Download locale + GDAL:** Richiede centinaia di GB, lento
- **Sentinel Hub:** A pagamento, meno flessibile
- **QGIS manuale:** Non scalabile, non riproducibile

**Vantaggi di Earth Engine:**
- ✅ Processamento cloud (veloce)
- ✅ Cataloghi pre-processati (Sentinel-2 SR già atmospherically corrected)
- ✅ API Python (automazione)
- ✅ Gratuito per uso ricerca/educazione

### 8.2 Perché Finestre Fenologiche e non Media Stagionale?

**Approccio tradizionale:**
```python
ndvi_mean = s2.filterDate('2025-04-01', '2025-10-01').mean()
```

**Problema:**
- Mischia fenologie diverse (crescita + maturazione)
- Non cattura **dinamica**
- Insensibile a stress transitori

**Approccio adottato:**
```python
ndvi_t1 = s2.filterDate(T1_START, T1_END)
ndvi_t2 = s2.filterDate(T2_START, T2_END)
ndvi_delta = ndvi_t2.mean() - ndvi_t1.mean()
```

**Vantaggi:**
- Cattura **evoluzione temporale**
- Sensibile a stress in fasi critiche
- Più informativo per zonazione dinamica

### 8.3 Perché Landsat invece di ECOSTRESS?

**Storia:**
Il piano originale prevedeva ECOSTRESS (risoluzione termica 70m, passaggio ogni 3 giorni).

**Problema scoperto:**
```
Error: Collection 'NASA/ECOSTRESS/L2_LSTE' not found
```

**Investigazione:** Collezione deprecata/rimossa da Earth Engine.

**Soluzione:**
```python
l8 = ee.ImageCollection('LANDSAT/LC08/C02/T1_L2')
l9 = ee.ImageCollection('LANDSAT/LC09/C02/T1_L2')
landsat = l8.merge(l9)  # 12 immagini totali
```

**Compromesso:**
- ❌ Risoluzione peggiore (100m → 10m upsampled)
- ✅ Disponibilità garantita
- ✅ Maggiore copertura temporale (due satelliti)

**Lezione:** Sempre avere **fallback** per sorgenti dati critiche.

### 8.4 Perché Rimozione Soil Data?

**Piano originale:** Includere `Clay`, `Sand`, `SOC` da OpenLandMap.

**Problema:**
```
Error: User memory limit exceeded
```
**Causa:** Collezioni SoilGrids molto pesanti (multi-banda, multi-depth).

**Decisione:** Rimuovere `soil` dal pipeline.

**Giustificazione:**
- Topografia (Slope, Aspect) è **proxy** per proprietà idrologiche del suolo
- NDVI e VH catturano **risposta della pianta** (più rilevante della texture)
- Semplifica architettura

**Possibile estensione futura:** Aggiungere soil da fonti locali (rilievi pedologici, resistività elettrica).

### 8.5 Perché Download Locale + Export Drive?

**Duplicazione apparente:**
```python
task.start()  # Export a Google Drive
samples.getDownloadURL()  # Download locale
```

**Rationale:**
- **Drive:** Backup, condivisione, accesso da altri script GEE
- **Locale:** Analisi immediata, validazione, no dipendenza da Drive sync

**Costo:** Duplicazione (~2.5 MB) trascurabile rispetto ai benefici.

---

## 9. Conclusioni e Sviluppi Futuri

### 9.1 Risultati Raggiunti

✅ **Pipeline funzionante e validata:**
- 10.994 pixel × 12 feature
- Dati multi-temporali, multi-sensore
- Validazione statistica e visiva completa

✅ **Architettura modulare e riutilizzabile:**
- Nuovi vigneti richiedono solo cambio coordinate
- Estensibile a nuove sorgenti dati

✅ **Documentazione completa:**
- README per quick start
- Report tecnico per comprensione approfondita
- Codice commentato

### 9.2 Limitazioni Attuali

⚠️ **Risoluzione termica:** 100m (Landsat) vs. 70m (ECOSTRESS desiderato)  
**Impatto:** Minore dettaglio in variabilità termica fine

⚠️ **Dati suolo assenti:** Basato solo su proxy topografici  
**Impatto:** Possibile sotto-caratterizzazione di zone con texture contrastante ma topografia simile

⚠️ **Finestre fenologiche fisse:** Non adattive alla stagione reale  
**Impatto:** In annate anomale (siccità, gelo), le date potrebbero non catturare le fasi ottimali

### 9.3 Sviluppi Futuri

#### 1. Clustering e Zonazione Automatica
**Obiettivo:** Algoritmo K-Means/Hierarchical per identificare 3-5 zone omogenee.

**Input:** `NDVI_Peak`, `NDVI_Delta`, `VH_Drop`, `Insolation`

**Output:** Mappa di zonazione + caratterizzazione agronomica di ogni zona.

**Esempio:**
- **Zona 1:** Alto vigore stabile → Gestione standard
- **Zona 2:** Vigore moderato + drop strutturale → Irrigazione supplementare
- **Zona 3:** Basso vigore + alta esposizione → Candidato per declassamento/ripristino

#### 2. Time Series Analysis
**Estensione:** Non solo T1 vs. T2, ma serie continua (immagini ogni 5 giorni).

**Feature derivate:**
- Trend lineare di NDVI
- Data di picco NDVI
- Velocità di senescenza

**Beneficio:** Cattura fenologia fine (fioritura, invaiatura).

#### 3. Integrazione Dati In-Field
**Fonti:**
- Dati vendemmiali (resa per zona)
- Analisi enologiche (°Brix, acidità)
- Mappe di vigore da droni (NDVI a 2cm)

**Beneficio:** Validazione ground-truth + calibrazione modelli predittivi.

#### 4. Piattaforma Web Interattiva
**Stack tecnologico:** React + Leaflet + FastAPI

**Funzionalità:**
- Upload ROI via interfaccia
- Selezione date fenologiche interattive
- Visualizzazione risultati in tempo reale
- Download report PDF

**Target:** Viticoltori senza competenze Python/GEE.

#### 5. Modelli Predittivi
**Machine Learning:**
- Regressione: Predire resa da feature temporali
- Classificazione: Predire classi qualitative (Premium, Standard, Declassamento)

**Training:** Multi-annate + multi-vigneti → generalizzabilità.

---

## Appendice A: Glossario Tecnico

**Earth Engine (GEE):** Piattaforma Google per elaborazione geospaziale cloud-based.

**ImageCollection:** Insieme di immagini satellitari filtrate per data/area.

**Reducer:** Funzione di aggregazione (mean, median, max, stdDev).

**Reproject:** Trasformazione di un'immagine in un nuovo sistema di coordinate.

**Sampling:** Estrazione di valori pixel da un'immagine in punti/poligoni specifici.

**Upsampling:** Interpolazione da bassa a alta risoluzione.

**Cloud Masking:** Rimozione pixel contaminati da nuvole.

**Backscatter:** Riflessione del segnale radar verso il sensore.

**Phenological Window:** Intervallo temporale corrispondente a una fase fenologica.

**CRS (Coordinate Reference System):** Sistema di riferimento spaziale (es. UTM, WGS84).

---

## Appendice B: Formule Chiave

**NDVI:**
```
NDVI = (NIR - RED) / (NIR + RED)
```

**NDVI Delta:**
```
Δ_NDVI = mean(NDVI_T2) - mean(NDVI_T1)
```

**VH Drop:**
```
VH_Drop = mean(VH_T2) - mean(VH_T1)
```

**Insolation:**
```
Insolation = Slope × cos(Aspect × π/180)
```

**LST Conversion:**
```
LST_C = (DN × 0.00341802 + 149.0) - 273.15
```

**GDD:**
```
GDD = Σ [(T_max + T_min)/2 - T_base]
```
Con `T_base = 10°C` per vite.

---

## Appendice C: Riferimenti Bibliografici

1. Hall, A., Lamb, D. W., Holzapfel, B., & Louis, J. (2002). *Optical remote sensing applications in viticulture*. Australian Journal of Grape and Wine Research.

2. Matese, A., & Di Gennaro, S. F. (2018). *Practical Applications of a Multisensor UAV Platform*. Agriculture.

3. Gorelick, N., et al. (2017). *Google Earth Engine: Planetary-scale geospatial analysis*. Remote Sensing of Environment.

4. ESA Sentinel Online. *Sentinel-2 User Handbook*. (2015).

5. Torres, R., et al. (2012). *GMES Sentinel-1 mission*. Remote Sensing of Environment.

---

**Fine del Documento**

*Per domande o chiarimenti, contattare il team di sviluppo SmartHarvest Wine.*
