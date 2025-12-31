
# **Data Ingestion & Processing Architecture**

This document is the proposed architecture for the satellite and topographic data ingestion, cleaning, normalization, and processing within the SmartHarvest platform. The system is designed to use both spatial and temporal pipelines.

## **1. Data Sources**

The architecture will be built on top of **Google Earth Engine (GEE)**, which would act as a cloud service that provides both the data and the computing power needed to obtain access to many Earth observation datasets at any scale.

### **Proposed Datasets from satellites:**

* **Optical (Sentinel-2):** resolution 10m, could be used for vegetation vigor, moisture, and chlorophyll-related indices such as NDVI, NDMI, and NDRE.
* **Radar (Sentinel-1):** resolution 10m, could support canopy structure analysis.
* **Thermal (Landsat 8/9):** resolution 30m but could be upsampled to 10m, could be used for Land Surface Temperature as an indicator of thermal stress.
* **Topographic (SRTM 30):** resolution 30m, could provide elevation data to derive slope and solar exposure.

## **2. Data cleaning and Normalization**

Before being used for statistical analysis all datasets will be preprocessed.
### **Filtering and Masking**

* **Sanitization:** the data will be cleaned to remove corrupted records.
* **Cloud Masking:** the biggest problem working with satellite data will be dealing with images contaminated by clouds, one solution could be to use specific bitmasks such as QA60 for Sentinel-2 and QA_PIXEL for Landsat.
### **Normalization**

* **Spatial Resampling:** for sources providing the data at lower resolutions such as SRTM and Landsat we need to reprojected and resample the data to a 10m grid using some kind of interpolation so that they are aligned to Sentinel-2 as the master spatial reference.
* **Unit Conversion:** raw numbers could be converted into physical quantities if needed like Degrees Celsius (°C) for thermal measurements

## **3. Processing Pipelines**

The system could support two different processes to prepare the datasets, one focused on a static approach and one folowing a time-series approach.

### **Static Pipeline**

This pipeline could generate a spatial dataset representing a snapshot overview of the vineyard over a defined time window. We would calcuate different statistics from the data collected looking for differences between different periods of the maturation cycle.

### **Time Series Pipeline**

We could calcuate statistics for the same wineyard every week or for whatever time frame is most suitable based on the avaiability of the satellite data and than analyze the evolution as the maturation cycle progresses. This approach could be used for anomaly detection within the maturing wineyard and also to compare with previous years.

## **4. Proposed framework**

The platform could be implemented using some of the following technologies:

* Python 3.x
* Google Earth Engine Python API
* FastAPI or Flask for API management
* Docker for deployment

