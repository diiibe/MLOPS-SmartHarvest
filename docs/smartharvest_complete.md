# SMARTHARVEST WINE
## Piattaforma SaaS per la Zonazione Dinamica dei Vigneti

---

## INDICE

1. [Executive Summary](#1-executive-summary)
2. [Architettura del Sistema](#2-architettura-del-sistema)
3. [Pre-Requisiti Globali](#3-pre-requisiti-globali)
4. [Pipeline di Elaborazione Dati](#4-pipeline-di-elaborazione-dati)
5. [Specifica Tecnica per Dataset](#5-specifica-tecnica-per-dataset)
6. [Data Cube Assembly](#6-data-cube-assembly)
7. [Output Finale](#7-output-finale)
8. [Validazione e Gestione Errori](#8-validazione-e-gestione-errori)
9. [Checklist Operativa](#9-checklist-operativa)

---

## 1. EXECUTIVE SUMMARY

### 1.1 Il Problema

In un vigneto di 50 ettari, l'uva non matura uniformemente. La topografia e il suolo creano zone a maturazione precoce e zone ritardate nello stesso appezzamento. La parte alta della collina può essere pronta mentre quella a valle è ancora acerba. Se si vendemmia tutto insieme (metodo classico), si ottiene un vino "medio", perdendo la qualità delle uve migliori.

### 1.2 La Soluzione

**SmartHarvest Wine** è una piattaforma SaaS scalabile che utilizza l'intelligenza artificiale e dati satellitari per la **Zonazione Dinamica**. Il sistema divide il vigneto in 2-3 zone di vigore diverse (High Vigor, Low Vigor) basandosi su dati satellitari storici e attuali.

Utilizzando dati satellitari multispettrali (Sentinel-2) ed elaborandoli tramite algoritmi di clustering non supervisionato, il sistema genera mappe di vigore (zonazione) che permettono la raccolta differenziata.

### 1.3 Obiettivo Olistico

Costruire il **Master Data Cube**: un oggetto digitale unico in cui ogni pixel del vigneto contiene informazioni ottiche, radar, topografiche, climatiche e pedologiche, tutte allineate spazialmente e temporalmente.

---

## 2. ARCHITETTURA DEL SISTEMA

### 2.1 Pattern Master-Slave Grid

Il flusso segue il pattern **Master-Slave Grid**. L'immagine Sentinel-2 funge da "Master" per la griglia spaziale; tutti gli altri dataset ("Slaves") subiscono resampling o broadcasting per adattarsi a tale griglia.

### 2.2 Schema di Flusso

```
1. SENTINEL-2 (Master Layer)
   ├── Acquisizione e Mascheramento Nuvole
   ├── Resampling bande 20m → 10m
   ├── Calcolo Indici (NDVI, NDRE)
   ├── Aggregazione Temporale (Mediana)
   └── Definizione MASTER_CRS e MASTER_TRANSFORM

2. SRTM (Topografia)
   ├── Calcolo Slope/Aspect su nativo (30m)
   └── Upsampling → 10m (Bilineare) su MASTER_CRS

3. SENTINEL-1 (Radar)
   ├── Filtro Orbita/Polarizzazione
   ├── Despeckling
   ├── Aggregazione Temporale (Media)
   └── Align → 10m su MASTER_CRS

4. ECOSTRESS (Termico)
   ├── Filtro Orario (Diurno)
   ├── Aggregazione Temporale (Mediana)
   └── Upsampling aggressivo (70m → 10m) su MASTER_CRS

5. ERA5 / SOIL (Contesto)
   ├── Aggregazione Temporale (Somma/Media)
   └── Broadcasting (Nearest Neighbor) → 10m su MASTER_CRS

6. DATA CUBE ASSEMBLY
   ├── Concatenazione bande (ee.Image.cat)
   └── Sampling geometrico (sampleRegions)
```

---

## 3. PRE-REQUISITI GLOBALI

### 3.1 Setup dell'Ambiente

Prima di toccare i dataset, definiamo le costanti che "governano" l'unificazione.

#### Parametri Obbligatori

| Parametro | Tipo | Descrizione | Esempio |
|-----------|------|-------------|---------|
| **ROI** | `ee.Geometry.Polygon` | Region of Interest (GeoJSON) | Poligono del vigneto |
| **START_DATE** | String | Data inizio (YYYY-MM-DD) | '2023-06-01' |
| **END_DATE** | String | Data fine (YYYY-MM-DD) | '2023-09-15' |
| **TARGET_SCALE** | Integer | Risoluzione target in metri | 10 |
| **TARGET_PROJECTION** | String | CRS dell'immagine Sentinel-2 | Derivato automaticamente |
| **CLOUD_THRESHOLD** | Float | Soglia percentuale nuvole | 20 |

#### Logica di Controllo

⚠️ **BLOCCO CRITICO**: Se uno di questi parametri è `None`, nullo o malformato, la pipeline deve abortire immediatamente.

> **BLOCCO OPERATIVO (Simulazione)**
> 
> **Parametro mancante:** ROI (Region of Interest)
> 
> **Impatto:** Impossibile definire l'estensione spaziale del Data Cube e calcolare le statistiche zonali.
> 
> **Domanda:** Fornire un GeoJSON valido o coordinate lat/lon dei vertici del vigneto.

---

## 4. PIPELINE DI ELABORAZIONE DATI

### 4.1 SENTINEL-2: Il Master Layer

*Questo dataset comanda. Definisce la griglia su cui tutti gli altri devono adattarsi.*

#### Sequenza Operativa

**1. Query & Filter**
- Caricare `COPERNICUS/S2_SR_HARMONIZED`
- Filtrare per `bounds` (ROI), `date` (Time Window) e `CLOUDY_PIXEL_PERCENTAGE < 20`

**2. Cloud Masking (Bitwise)**
- Usare la banda `QA60`
- Creare una funzione che imposta a `masked` (trasparente) i pixel con bit "nuvole" o "cirri"
- *Tecnica:* Applicare questa funzione tramite `.map()` su tutta la collezione
- ⚠️ **IMPORTANTE**: Il Cloud Masking deve essere applicato *prima* del calcolo della mediana

**3. Resampling delle Bande Red Edge**
- Sentinel-2 ha bande a risoluzioni miste
- **Azione:** Selezionare B5, B6, B7 (20m) e riproiettarle sulla scala di B4/B8 (10m) usando interpolazione **Bicubica** (più morbida del Nearest Neighbor)

**4. Feature Engineering (Indici)**
- Calcolare `NDVI = (B8-B4)/(B8+B4)`
- Calcolare `NDRE = (B8-B5)/(B8+B5)`
- Aggiungere queste nuove bande a ogni immagine della collezione

**5. Time Aggregation (Riduzione)**
- Passare da N foto a 1 foto "sintetica"
- **Azione:** Applicare `.median()`
- *Perché:* La mediana rimuove le ombre residue e i picchi anomali meglio della media

**6. Salvataggio Proiezione**
- Salvare la proiezione di questa immagine finale (`master_crs = image.projection()`)
- Servirà per forzare gli altri dataset

---

### 4.2 SRTM: Il Contesto Fisico (Topografia)

*Dato statico che va adattato alla griglia 10m.*

#### Sequenza Operativa

**1. Query**
- Caricare `USGS/SRTMGL1_003`
- Clip sulla ROI

**2. Feature Calculation (Prima del Resampling)**
- **⚠️ IMPORTANTE:** Calcolare Slope e Aspect *sui dati nativi a 30m*
- *Errore da evitare:* Se fai l'upsampling a 10m prima di calcolare la pendenza, introduci artefatti
- Usare `ee.Terrain.products(dem)`

**3. Insolation Calculation (Opzionale/Avanzato)**
- Se il budget computazionale lo permette, eseguire qui l'algoritmo di insolazione cumulativa

**4. Alignment (Resampling)**
- Prendere l'immagine risultante (Elevation, Slope, Aspect)
- **Azione:** `reproject(crs=master_crs, scale=10)`
- Usare interpolazione **Bilineare** per "lisciare" i gradoni dei pixel 30m

---

### 4.3 SENTINEL-1: Il Backup Robusto (Radar)

*Dato complesso che richiede pulizia prima dell'integrazione.*

#### Sequenza Operativa

**1. Query & Filter**
- Caricare `COPERNICUS/S1_GRD`
- Filtrare per `instrumentMode: IW`, `polarization: VV, VH`
- Filtrare per `orbitProperties_pass: ASCENDING` (o Descending, ma mantenerne uno solo per coerenza geometrica)

**2. Preprocessing (Despeckling)**
- Il radar grezzo ha rumore "sale e pepe"
- **Azione:** Applicare un filtro spaziale (es. **Refined Lee Filter** o un semplice BoxCar 5x5) su ogni immagine tramite `.map()`

**3. Time Aggregation**
- Applicare `.mean()` temporale (qui la media funziona meglio della mediana per il radar distribuito logaritmicamente)

**4. Alignment**
- Anche se è già a 10m, forzare il `reproject` per garantire che i pixel siano perfettamente sovrapposti a quelli di Sentinel-2 (Pixel Alignment)

---

### 4.4 ECOSTRESS: Lo Stress Termico (Dati Irregolari)

*Dato ad alta entropia che va filtrato e ingrandito.*

#### Sequenza Operativa

**1. Query & Filter**
- Caricare `NASA/ECOSTRESS/L2_LSTE`
- **⚠️ Filtro Orario (Cruciale):** Le immagini notturne non servono. Filtrare metadati per acquisizioni tra le 10:00 e le 16:00 locali

**2. Quality Masking**
- Usare le bande di qualità (QC) interne per rimuovere pixel con errori o nubi (il termico non vede attraverso le nubi)

**3. Conversion**
- Moltiplicare per lo scale factor (0.02) per ottenere Kelvin
- Convertire opzionalmente in Celsius

**4. Time Aggregation**
- Calcolare la `.median()` delle temperature massime

**5. Upsampling (Aggressive)**
- Passare da 70m a 10m
- **Azione:** `reproject(crs=master_crs, scale=10)`
- L'immagine risulterà sfocata, ma mostrerà i gradienti di calore (es. "la cima della collina è più calda")

---

### 4.5 ERA5 & SoilGrids: Il Contesto Macro (Dati a bassa risoluzione)

*Dati che vanno "spalmati" (Broadcast) su tutto il vigneto.*

#### Sequenza Operativa (Identica per entrambi)

**1. Query**
- Caricare `ECMWF/ERA5_LAND/HOURLY` (Meteo) o `OpenLandMap` (Suolo)

**2. Aggregation (Solo per Meteo)**
- Sommare `total_precipitation` nel periodo
- Calcolare media `temperature_2m`
- Calcolare `GDD` (Accumulo termico sopra i 10°C)

**3. Broadcasting (La Magia)**
- Questi pixel sono enormi (9km o 250m)
- Quando fai `reproject(scale=10)`, GEE prende il valore del pixel grande e lo assegna a tutti i 10.000 pixel piccoli che ci stanno dentro
- *Risultato:* Una "tinta piatta" o un gradiente molto lieve che fornisce il **Bias Context** al modello ML

---

## 5. SPECIFICA TECNICA PER DATASET

### 5.1 Sentinel-2 (Master Optical)

| Campo | Specifica |
|-------|-----------|
| **Dataset** | `COPERNICUS/S2_SR_HARMONIZED` |
| **Input** | Bande: B4, B5, B6, B7, B8, QA60 |
| **Filtri** | `bounds(ROI)`, `date(START, END)`, `CLOUDY_PIXEL_PERCENTAGE < CLOUD_THRESHOLD` |
| **Preprocessing** | **Bitwise Masking:** Usare banda QA60. Bit 10 (nuvole opache) e Bit 11 (cirri) devono essere 0 |
| **Resampling** | Bande B5, B6, B7 (20m) riproiettate a 10m su proiezione B4. Metodo: **Bicubic** |
| **Feature Eng.** | `NDVI = (B8-B4)/(B8+B4)` <br> `NDRE = (B8-B5)/(B8+B5)` |
| **Aggregazione** | `.median()` su tutta la collezione filtrata |
| **Output** | Immagine 2 bande: `NDVI_med`, `NDRE_med` (Risoluzione 10m) |

### 5.2 SRTM (Topography)

| Campo | Specifica |
|-------|-----------|
| **Dataset** | `USGS/SRTMGL1_003` |
| **Input** | Banda: elevation |
| **Preprocessing** | Clipping sulla ROI estesa (+ buffer 100m per evitare effetti bordo) |
| **Feature Eng.** | `slope = ee.Terrain.slope(elevation)` <br> `aspect = ee.Terrain.aspect(elevation)` |
| **Resampling** | `reproject(crs=MASTER_CRS, scale=10)`. Metodo: **Bilinear** (per evitare gradoni) |
| **Output** | Immagine 2 bande: `Slope`, `Aspect` (Risoluzione 10m) |

### 5.3 Sentinel-1 (Radar SAR)

| Campo | Specifica |
|-------|-----------|
| **Dataset** | `COPERNICUS/S1_GRD` |
| **Input** | Bande: VV, VH. `instrumentMode: IW` |
| **Filtri** | `orbitProperties_pass: ASCENDING` (o Descending, purché coerente) |
| **Preprocessing** | **Despeckling:** Applicazione kernel di smoothing (es. BoxCar 5x5 o Refined Lee) su ogni immagine |
| **Aggregazione** | `.mean()` (Media temporale del coefficiente di backscatter) |
| **Resampling** | `reproject(crs=MASTER_CRS, scale=10)` |
| **Output** | Immagine 2 bande: `VV_mean`, `VH_mean` (Risoluzione 10m) |

### 5.4 ECOSTRESS (Thermal)

| Campo | Specifica |
|-------|-----------|
| **Dataset** | `NASA/ECOSTRESS/L2_LSTE` |
| **Input** | Banda: LST |
| **Filtri** | Filtro orario metadati: Acquisizione tra 10:00 e 16:00 (Local Time) per catturare stress diurno |
| **Feature Eng.** | Conversione Kelvin → Celsius (opzionale): `LST * 0.02 - 273.15` |
| **Aggregazione** | `.median()` (per mitigare outlier atmosferici) |
| **Resampling** | `reproject(crs=MASTER_CRS, scale=10)`. Metodo: **Bicubic** (per gradienti termici) |
| **Output** | Immagine 1 banda: `LST_med` (Risoluzione 10m, interpolata) |

### 5.5 ERA5-Land & SoilGrids (Context)

| Campo | Specifica |
|-------|-----------|
| **Dataset** | `ECMWF/ERA5_LAND/HOURLY` / `OpenLandMap/SOL/...` |
| **Input** | ERA5: `total_precipitation`, `temperature_2m`. Soil: `clay_content` |
| **Aggregazione** | ERA5: `sum()` per precipitazioni, `mean()` per temperatura. Soil: Statico (nessuna aggregazione) |
| **Feature Eng.** | ERA5: Calcolo GDD (Cumulative sum of (Temp - 10)) |
| **Resampling** | **Broadcasting:** `reproject(crs=MASTER_CRS, scale=10)`. Metodo: **Nearest Neighbor** (il valore del pixel grande viene copiato su tutti i pixel piccoli) |
| **Output** | Immagine 3 bande: `Rain_tot`, `GDD_tot`, `Clay` (Risoluzione 10m) |

---

## 6. DATA CUBE ASSEMBLY

### 6.1 Regole di Allineamento e Coerenza

Per garantire che la matrice finale non abbia buchi o disallineamenti spaziali:

**1. Estrazione Master Projection**
```python
master_proj = sentinel2_median.select('NDVI_med').projection()
```

**2. Reprojection Forzata**
- Ogni dataset successivo (B, C, D, E) deve terminare con: `.reproject(crs=master_proj)`

**3. Gestione Collezioni Vuote**
- Se `Sentinel-1` o `ECOSTRESS` ritornano 0 immagini (collection size = 0), la pipeline deve generare una **Banda Costante di Fallback** (es. valore -9999 o media storica) per mantenere la struttura dimensionale del Data Cube senza rompere l'esecuzione, flaggando l'errore nei metadati

### 6.2 Guida all'Assemblaggio Finale

#### Ordine di Stacking (Bande)

1. Sentinel-2 (NDVI, NDRE)
2. SRTM (Slope, Aspect)
3. Sentinel-1 (VV, VH)
4. ECOSTRESS (LST)
5. ERA5 (Rain, GDD)
6. Soil (Clay)

#### Procedura

**1. Stacking**
- Creare una lista delle immagini finali processate: `[img_S2, img_SRTM, img_S1, img_ECO, img_Meteo, img_Soil]`
- Unirle in un'unica immagine multibanda: `final_image = ee.Image.cat(list)`
- Rinominare le bande per chiarezza: `['NDVI', 'NDRE', 'Slope', 'Aspect', 'VV', 'VH', 'LST', 'Rain', 'GDD', 'Clay']`

**2. Clipping**
- Tagliare l'immagine finale sui bordi esatti del vigneto: `.clip(ROI)`

**3. Casting**
- `float()`: Cast di tutte le bande a Float32 per uniformità

**4. Sampling (Da Immagine a Tabella)**
- Usare `final_image.sampleRegions()`
- **Parametri:**
  - `collection`: ROI (Poligono)
  - `scale`: **10** (Cruciale! Qui avviene l'estrazione fisica dei valori)
  - `geometries`: **True** (Per mantenere Lat/Lon di ogni punto)
  - `tileScale`: 4 (per evitare OutOfMemory errors su GEE)

**5. Output**
- Il risultato è una `FeatureCollection` che può essere esportata come CSV in Drive o Cloud Storage

---

## 7. OUTPUT FINALE

### 7.1 Struttura del Master Dataset

Il file CSV che darai in pasto al tuo script Python locale (Pandas + Scikit-Learn). Ogni riga rappresenta un quadrato di terra di 10x10 metri.

| ID | Geo (Lat/Lon) | Vegetazione (S2) | Vegetazione (S2) | Topografia (SRTM) | Topografia (SRTM) | Radar (S1) | Radar (S1) | Termico (ECO) | Meteo (ERA5) | Meteo (ERA5) | Suolo (Soil) |
|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| *Pixel* | *Coords* | **NDVI_med** | **NDRE_med** | **Slope_deg** | **Aspect_deg** | **VV_dB** | **VH_dB** | **LST_C** | **Rain_mm** | **GDD** | **Clay_%** |
| 0001 | 45.10, 10.20 | 0.78 | 0.42 | 5.2 | 180.2 | -10.5 | -12.5 | 32.1 | 145 | 1400 | 28 |
| 0002 | 45.10, 10.21 | 0.76 | 0.41 | 5.4 | 182.1 | -10.8 | -12.8 | 32.2 | 145 | 1400 | 28 |
| 0003 | 45.10, 10.22 | **0.45** | **0.18** | **18.5** | 165.3 | -15.2 | **-16.2** | **35.4** | 145 | 1400 | **15** |
| ... | ... | ... | ... | ... | ... | ... | ... | ... | ... | ... | ... |
| 9999 | 45.12, 10.29 | 0.65 | 0.35 | 8.1 | 175.8 | -11.1 | -13.1 | 31.8 | 145 | 1400 | 30 |

### 7.2 Esempio di Lettura dei Dati (riga 0003)

**Diagnosi:** Questa riga mostra un **NDVI basso** (0.45) e un **NDRE basso** (0.18).

**Spiegazione dai dati integrati:**
- **Slope:** 18.5° (Molto ripido → l'acqua scivola via)
- **LST:** 35.4°C (Molto caldo → Stress idrico confermato)
- **Radar VH:** -16.2 dB (Basso → poca biomassa fogliare)
- **Suolo:** 15% argilla (Suolo sabbioso che non trattiene acqua)
- **Meteo:** 145mm (Uguale per tutti, quindi non è colpa della pioggia generale)

**Conclusione del Modello:** Classificherà questo pixel come **"Low Vigor / Zona C"** (da vendemmiare tardi o gestire separatamente) con altissima confidenza, perché tutti i sensori concordano.

**Questa è la potenza della pipeline olistica:** trasforma dati grezzi disgiunti in una **narrazione agronomica coerente**.

---

## 8. VALIDAZIONE E GESTIONE ERRORI

### 8.1 Strategia di Validazione Automatica

| Controllo | Dataset | Condizione di Errore | Azione Automatica |
|-----------|---------|---------------------|-------------------|
| **Copertura** | Sentinel-2 | Count < 1 su ROI | **🚨 STOP CRITICO**. Impossibile procedere senza ottico |
| **Nuvole** | Sentinel-2 | Pixel mascherati > 50% | ⚠️ Warning. Estendere finestra temporale di 15 giorni |
| **Range Fisico** | S2 (NDVI) | Valori fuori [-1, 1] | Clip valori a [-1, 1] |
| **Range Fisico** | ECOSTRESS | LST > 60°C o < 0°C (Estate) | Mascherare come outlier/errore sensore |
| **Dati Mancanti** | Sentinel-1 | Collection Size == 0 | Usare banda dummy con valore 0 e loggare Warning |

### 8.2 Matrice dei Possibili Errori

| Errore | Causa | Rilevazione | Mitigazione Automatica |
|--------|-------|-------------|------------------------|
| **Projection Mismatch** | Dati raw hanno CRS diversi (UTM vs WGS84) | Errore in fase di stacking | **Preventiva:** `reproject()` forzato su Master CRS |
| **Mixed Pixels** | Bordi del vigneto su strade/boschi | NDVI anomalo sui bordi | **Negative Buffer:** `ROI.buffer(-10)` per erodere i bordi |
| **NaN Values** | Nuvole persistenti in S2 | Valori `null` nel CSV finale | **Interpolazione Lineare** temporale o riempimento con mediana spaziale |
| **Temporal Drift** | ECOSTRESS passa solo di mattina presto | LST troppo bassa | Filtro rigoroso `hour > 10` |

### 8.3 Istruzioni di Interruzione e Domanda

Il modello (e il codice) deve bloccarsi se si verificano queste condizioni critiche.

> **🚨 BLOCCO OPERATIVO #1**
> 
> **Problema:** Sentinel-2 Collection vuota dopo il filtraggio.
> 
> **Conseguenza:** Impossibile generare la Master Grid e calcolare il vigore.
> 
> **Domanda Necessaria:** Nessuna immagine valida trovata tra [Start] e [End] con nuvole < [Threshold]. Vuoi estendere la finestra temporale o aumentare la soglia di tolleranza nuvole?

> **🚨 BLOCCO OPERATIVO #2**
> 
> **Problema:** ROI area troppo grande (> 10.000 ettari) per l'elaborazione interattiva.
> 
> **Conseguenza:** Timeout di Google Earth Engine (User Memory Limit Exceeded).
> 
> **Domanda Necessaria:** L'area selezionata è troppo vasta per l'analisi real-time. Confermi di voler procedere con un export Batch (Task) invece del download diretto?

---

## 9. CHECKLIST OPERATIVA

### 9.1 Checklist di Autogaranzia

- [ ] La proiezione Master è derivata dinamicamente dalla prima immagine Sentinel-2 valida?
- [ ] Il Cloud Masking è applicato *prima* del calcolo della mediana?
- [ ] Il calcolo dello Slope è fatto sul DEM nativo (30m) *prima* del resampling a 10m?
- [ ] I dati termici (ECOSTRESS) sono filtrati per orario diurno?
- [ ] Il CSV di output contiene le coordinate (Lat/Lon) per la visualizzazione?
- [ ] Sono gestiti i valori nulli (NaN) in caso di buchi nei dati?
- [ ] Tutte le bande sono state convertite a Float32 per uniformità?
- [ ] Il `tileScale` è impostato a 4 per evitare errori di memoria?
- [ ] Il negative buffer sui bordi del ROI è stato applicato se necessario?
- [ ] Le bande sono state rinominate con nomi descrittivi?

### 9.2 Garanzia di Riproducibilità

Questa specifica è **deterministica**: forniti gli stessi input (ROI, Date), produrrà sempre lo stesso identico Data Cube, garantendo la riproducibilità scientifica necessaria per una pipeline MLOps.

---

## APPENDICE: Implementazione Google Earth Engine

### Struttura Generale del Codice Python

```python
import ee

# Inizializzazione
ee.Initialize()

# 1. Definizione Parametri Globali
ROI = ee.Geometry.Polygon([...])  # GeoJSON
START_DATE = '2023-06-01'
END_DATE = '2023-09-15'
TARGET_SCALE = 10
CLOUD_THRESHOLD = 20

# 2. Sentinel-2 (Master)
s2 = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
# ... processing ...
master_proj = s2_median.projection()

# 3. SRTM
srtm = ee.Image('USGS/SRTMGL1_003')
# ... processing ...

# 4. Sentinel-1
s1 = ee.ImageCollection('COPERNICUS/S1_GRD')
# ... processing ...

# 5. ECOSTRESS
eco = ee.ImageCollection('NASA/ECOSTRESS/L2_LSTE')
# ... processing ...

# 6. ERA5 & Soil
era5 = ee.ImageCollection('ECMWF/ERA5_LAND/HOURLY')
soil = ee.Image('OpenLandMap/SOL/...')
# ... processing ...

# 7. Assembly
final_cube = ee.Image.cat([
    s2_processed,
    srtm_processed,
    s1_processed,
    eco_processed,
    era5_processed,
    soil_processed
]).float()

# 8. Sampling & Export
samples = final_cube.sampleRegions(
    collection=ROI,
    scale=TARGET_SCALE,
    geometries=True,
    tileScale=4
)

# Export to Drive
task = ee.batch.Export.table.toDrive(
    collection=samples,
    description='SmartHarvest_DataCube',
    fileFormat='CSV'
)
task.start()
```

---

**Fine Documentazione**

*SmartHarvest Wine v1.0 - Pipeline Completa per la Zonazione Dinamica dei Vigneti*