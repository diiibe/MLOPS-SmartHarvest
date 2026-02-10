# SmartHarvest Wine - Vineyard Zonation Data Pipeline

A Google Earth Engine-based data pipeline for generating multi-source satellite data cubes to support precision viticulture and vineyard zonation.

## 📚 Documentation

- **[ARCHITECTURE.md](ARCHITECTURE.md)** - Complete architecture guide, module reference, and usage examples
- **[ML_QUICKSTART.md](ML_QUICKSTART.md)** - ML anomaly detection pipeline guide
- **[GEE_PROJECT_SETUP.md](GEE_PROJECT_SETUP.md)** - Google Earth Engine project setup

## 📁 Project Structure

```
smartwine/
├── config.py                  # Global configuration (ROI, dates, phenological windows)
├── main.py                    # Main pipeline execution script
├── requirements.txt           # Python dependencies
│
├── modules/                   # Data processing modules
│   ├── sentinel2.py          # Optical vegetation indices (NDVI dynamics)
│   ├── sentinel1.py          # Radar backscatter (VH dynamics)
│   ├── srtm.py               # Topography (Slope, Aspect, Insolation)
│   ├── landsat_thermal.py    # Land Surface Temperature
│   ├── era5_soil.py          # Climate data (Rain, GDD)
│   ├── assembly.py           # Data cube assembly and export
│   └── reporting.py          # Metadata report generation
│
├── tools/                     # Analysis and visualization scripts
│   ├── analyze_temporal_data.py    # Statistical validation
│   ├── visualize_data_map.py       # Interactive map generation
│   └── debug_bands.py              # Module output debugging
│
├── output/                    # Generated outputs
│   ├── SmartHarvest_DataCube_Temporal.csv      # Main data cube (10m resolution)
│   ├── SmartHarvest_Report.md                  # Metadata report
│   ├── DATA_VALIDATION_REPORT.md               # Validation statistics
│   ├── SmartHarvest_Verification_Map.html      # Interactive map
│   └── temporal_distributions.png              # Feature distributions
│
└── docs/                      # Documentation
    └── smartharvest_complete.md               # Full technical specification
```

## 🚀 Quick Start

### 1. Prerequisites
```bash
# Install dependencies
pip install -r requirements.txt

# Authenticate Google Earth Engine
earthengine authenticate
```

### 2. Configure ROI and Dates
**Option A: Interactive Selection (Recommended)** 🆕
1. Run the selection tool:
   ```bash
   python tools/select_roi.py
   ```
2. Open `http://127.0.0.1:5000` in your browser.
3. Draw your vineyard polygon on the map.
4. Click **Save ROI**. This creates `roi.json`.
5. The pipeline will automatically use this new ROI.

**Option B: Manual Configuration**
Edit `config.py` manually:
```python
ROI_COORDS = [[lon1, lat1], [lon2, lat2], ...]  # Your vineyard polygon
```

**Set Dates (`config.py`)**:
```python
DATE_T1_START = '2025-06-01'  # Vegetative development start
DATE_T1_END = '2025-07-20'    # Vegetative development end
DATE_T2_START = '2025-07-21'  # Ripening start
DATE_T2_END = '2025-09-10'    # Ripening end
```

### 3. Run the Pipeline
```bash
python main.py
```

This will:
- Process satellite data from Sentinel-2, Sentinel-1, Landsat, SRTM, and ERA5
- Generate temporal dynamics features (NDVI Delta, VH Drop, etc.)
- Export the data cube to `output/SmartHarvest_DataCube_Temporal.csv`
- Create a metadata report in `output/SmartHarvest_Report.md`

### 4. Validate and Visualize
```bash
# Generate validation report
python tools/analyze_temporal_data.py

# Create interactive map
python tools/visualize_data_map.py

# Open the map in your browser
open output/SmartHarvest_Verification_Map.html
```

## 📊 Output Data

### SmartHarvest_DataCube_Temporal.csv
A 10m resolution grid with the following features:

**Vegetation Dynamics (Sentinel-2)**
- `NDVI_Peak`: Maximum NDVI during T1 (vegetative vigor)
- `NDVI_Late`: Mean NDVI during T2 (late-season vigor)
- `NDVI_Delta`: Change from T1 to T2 (growth/senescence)
- `NDVI_Stability`: Standard deviation in T2 (uniformity)

**Radar Dynamics (Sentinel-1)**
- `VH_Late`: Mean VH backscatter in T2 (structure)
- `VH_Drop`: Change from T1 to T2 (water stress)

**Topography (SRTM)**
- `Slope`: Terrain slope (degrees)
- `Aspect`: Terrain orientation (degrees)
- `Insolation`: Solar exposure proxy (Slope × cos(Aspect))

**Thermal & Climate**
- `LST`: Land Surface Temperature (°C, Landsat 8/9)
- `Rain_tot`: Total precipitation (mm, ERA5)
- `GDD_tot`: Growing Degree Days (ERA5)

## 🛠️ Customization

### Adding New Data Sources
1. Create a new module in `modules/`
2. Implement `get_<source>_data(master_crs)` function
3. Return `(ee.Image, metadata_dict)`
4. Import and call in `main.py`

### Changing Phenological Windows
Edit `config.py`:
```python
DATE_T1_START = '2025-05-15'  # Earlier start
DATE_T2_END = '2025-09-30'    # Later harvest
```

## 📈 Validation

The pipeline includes built-in validation:
- **Statistical**: `DATA_VALIDATION_REPORT.md` shows descriptive stats, correlations, and plausibility checks
- **Visual**: `SmartHarvest_Verification_Map.html` allows spatial inspection on satellite background
- **Layer Selection**: Toggle between different metrics to verify spatial patterns

## 🔧 Troubleshooting

### Authentication Issues
```bash
earthengine authenticate
```

### Missing Bands in Output
```bash
python tools/debug_bands.py  # Check module outputs
```

### Empty T1/T2 Collections
- Verify date ranges in `config.py` match your growing season
- Check cloud coverage threshold (default: 20%)

## 📝 Citation

If you use this pipeline in your research, please cite:
```
SmartHarvest Wine - Vineyard Zonation Data Pipeline
https://github.com/yourusername/smartwine
```

## 📄 License

MIT License - see LICENSE file for details

## 🤝 Contributing

Contributions are welcome! Please open an issue or submit a pull request.

## 📧 Contact

For questions or support, please contact: your.email@example.com
