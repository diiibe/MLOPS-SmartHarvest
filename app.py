from flask import Flask, jsonify, render_template, request


app = Flask(__name__)

SATELLITE_MODULES = [
    {
        "id": "sentinel2",
        "name": "Sentinel-2 (Optical)",
        "resolution": "10m",
        "focus": "Vegetation vigor, moisture, chlorophyll indices",
    },
    {
        "id": "sentinel1",
        "name": "Sentinel-1 (Radar)",
        "resolution": "10m",
        "focus": "Canopy structure and moisture dynamics",
    },
    {
        "id": "landsat_thermal",
        "name": "Landsat 8/9 (Thermal)",
        "resolution": "30m",
        "focus": "Land surface temperature and thermal stress",
    },
    {
        "id": "ecostress",
        "name": "ECOSTRESS (Thermal)",
        "resolution": "70m",
        "focus": "Evapotranspiration and water stress",
    },
    {
        "id": "srtm",
        "name": "SRTM (Topographic)",
        "resolution": "30m",
        "focus": "Elevation, slope, and solar exposure",
    },
    {
        "id": "era5_soil",
        "name": "ERA5 (Soil)",
        "resolution": "~9km",
        "focus": "Soil moisture and climatic context",
    },
]


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/health")
def health():
    return jsonify({"status": "ok"})


@app.get("/api/modules")
def list_modules():
    return jsonify({"modules": SATELLITE_MODULES})


@app.post("/api/plan")
def build_plan():
    payload = request.get_json(silent=True) or {}
    selection = payload.get("modules", [])
    time_window = payload.get("time_window", "")
    if not selection:
        return jsonify({"error": "Select at least one module."}), 400

    plan = {
        "summary": "Data ingestion plan generated.",
        "modules": selection,
        "time_window": time_window or "Not specified",
        "next_steps": [
            "Validate credentials for Earth Engine",
            "Trigger preprocessing for selected layers",
            "Export outputs to the analytics workspace",
        ],
    }
    return jsonify(plan)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
