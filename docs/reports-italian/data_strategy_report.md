# SmartHarvest Data Strategy Report

## 1. Analisi delle Variabili Attuali

Attualmente il dataset `SmartHarvest_DataCube_Temporal.csv` contiene le seguenti variabili. Di seguito un'analisi critica per ciascuna.

| Variabile | Fonte | Risoluzione | Significato | Criticità / Note |
| :--- | :--- | :--- | :--- | :--- |
| **NDVI_Peak** | Sentinel-2 | 10m | Massimo vigore raggiunto (T1+T2). | **Ottima**. Fondamentale per stimare il potenziale produttivo. Da mantenere. |
| **NDVI_Late** | Sentinel-2 | 10m | Vigore mediano in maturazione (T2). | **Buona**, ma la mediana può nascondere cali improvvisi. |
| **NDVI_Delta** | Sentinel-2 | 10m | Differenza T2 - T1. | **Cruciale**. Indica la senescenza o lo stress. Da mantenere assolutamente. |
| **NDVI_Stability** | Sentinel-2 | 10m | Deviazione Standard (T1+T2). | **Utile** per identificare zone instabili, ma non distingue tra instabilità "buona" (crescita rapida) e "cattiva" (stress). |
| **VH_Late** | Sentinel-1 | 10m | Struttura/Umidità in T2. | **Buona**. Il segnale SAR è rumoroso (speckle), ma la media temporale lo stabilizza. |
| **VH_Drop** | Sentinel-1 | 10m | Variazione Struttura T2 - T1. | **Ottima** per rilevare defogliazione o forte stress idrico (calo dielettrico). |
| **Slope** | SRTM | 30m -> 10m | Pendenza del terreno. | **Base**. Utile per il drenaggio. Risoluzione nativa (30m) un po' bassa per filari stretti. |
| **Aspect** | SRTM | 30m -> 10m | Esposizione (0-360°). | **Problematica**. Essendo circolare (0° = 360°), crea problemi ai modelli lineari. Va trasformata (es. Seno/Coseno). |
| **Insolation** | SRTM | 30m -> 10m | Proxy semplice (`Slope * cos(Aspect)`). | **Limitata**. Non considera le ombre portate dalle montagne vicine né l'elevazione solare reale. Da sostituire. |
| **LST** | Landsat 8/9 | 30m -> 10m | Temperatura Superficiale. | **Buona**, ma la frequenza di passaggio (16 giorni) è bassa. Rischio pochi dati utili se nuvoloso. |
| **Rain_tot** | ERA5-Land | 9km -> 10m | Pioggia totale accumulata. | **Critica**. Varianza zero all'interno del vigneto. Utile solo come costante per confronti tra annate diverse. |
| **GDD_tot** | ERA5-Land | 9km -> 10m | Gradi Giorno accumulati. | **Critica**. Come sopra. Varianza zero locale. |

---

## 2. Raccomandazioni Strategiche (Keep / Drop / Modify)

### ✅ Da Mantenere (Keep)
*   **NDVI_Peak, NDVI_Delta**: Sono i pillar dell'analisi vegetativa.
*   **VH_Drop**: Unico indicatore strutturale affidabile indipendente dalle nuvole.
*   **Slope**: Essenziale per la gestione idrica.

### ❌ Da Eliminare o Sostituire (Drop/Replace)
*   **Insolation (attuale)**: Sostituire con un modello di **Radiazione Solare Cumulativa** (vedi sez. 5).
*   **Aspect (grezzo)**: Sostituire con **Northness** (`cos(Aspect)`) e **Eastness** (`sin(Aspect)`) per renderlo digeribile ai modelli ML.
*   **Rain_tot / GDD_tot (grezzi)**: Inutili per l'analisi intra-vigneto. Sostituire con variabili downscalate o indici topografici (vedi sez. 5).

### 🛠 Da Modificare (Modify)
*   **NDVI_Stability**: Sostituire con un indice di **Volatilità Direzionale** (es. quante volte il trend cambia segno) o semplicemente analizzare la serie temporale completa.

---

## 3. Strategia Serie Temporali (Time Series)

L'approccio attuale "T1 vs T2" è una semplificazione efficace ma perde molte informazioni. Ecco come evolvere:

### A. Finestre Temporali (Windowing)
Invece di due blocchi statici (T1, T2), passare a:
*   **Sliding Windows (Finestre Mobili)**: Calcolare media/max su finestre di 15 giorni che scorrono (es. 1-15 Giugno, 15-30 Giugno...).
*   **Vantaggio**: Cattura il *momento esatto* del picco o del declino, non solo la media.

### B. Aggregazioni Avanzate
*   **Medie Ponderate**: Dare più peso alle acquisizioni recenti o a quelle con qualità pixel migliore (meno probabilità di nubi residue).
*   **Percentili (10° e 90°)**: Invece della media, usare il 90° percentile per stimare il potenziale massimo escludendo gli outlier negativi (ombre/nuvole non mascherate).

### C. Feature Derivate (Time-Series Features)
*   **Time to Peak**: Giorni trascorsi dall'inizio dell'anno al raggiungimento del picco NDVI. (Anticipo fenologico = rischio gelate o stress).
*   **Green-Up Rate**: Velocità di crescita in primavera (pendenza della curva ascendente).
*   **Senescence Rate**: Velocità di decadimento in autunno.

---

## 4. Nuove Variabili Proposte

Per superare i limiti attuali (soprattutto su Clima e Insolazione), propongo di introdurre:

### 1. Topographic Wetness Index (TWI)
*   **Logica**: L'acqua scorre in discesa e si accumula nelle zone pianeggianti o concave.
*   **Formula**: `ln(Area Contribuente / tan(Slope))`
*   **Utilità**: Sostituisce la pioggia (costante) con un proxy ad alta risoluzione (10m) di **dove va l'acqua**. Fondamentale per stress idrico e vigore.

### 2. Solar Radiation (GEE Model)
*   **Logica**: Calcolare l'energia solare reale (Wh/m²) integrando il percorso del sole e le ombre orografiche (hillshade) ogni ora.
*   **Utilità**: Molto più preciso dell'Aspect per capire quali zone maturano prima.

### 3. Temperature Downscaling (Lapse Rate)
*   **Logica**: La temperatura scende di ~0.65°C ogni 100m di dislivello.
*   **Formula**: `Temp_ERA5 - (Elevation_10m - Elevation_ERA5) * 0.0065`
*   **Utilità**: Introduce varianza locale nella temperatura basata sull'altimetria reale del vigneto.

### 4. Texture Analysis (GLCM)
*   **Logica**: Analizzare la "trama" dell'immagine Sentinel-2.
*   **Utilità**: Un vigneto sano e uniforme ha una texture diversa da uno con fallanze o filari irregolari. Metriche come *Entropia* o *Contrasto* possono evidenziare eterogeneità spaziale.

---

## 5. Sintesi del Piano di Miglioramento

1.  **Immediato**: Implementare **TWI** e **Solar Radiation** (GEE) per sostituire Rain/Insolation attuali.
2.  **Medio Termine**: Implementare il calcolo di **Northness/Eastness** e il **Downscaling Termico**.
3.  **Avanzato**: Passare dall'approccio T1/T2 all'estrazione di feature fenologiche (Time to Peak, Green-Up Rate) usando l'intera serie temporale.
