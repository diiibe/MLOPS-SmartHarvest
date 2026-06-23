// Initialize map
var map = L.map('map', { zoomControl: true }).setView([45.0, 10.0], 6);

// Basemap registry — when a Mapbox token is configured we expose the
// same four styles landslide-app does (Outdoors / Light / Satellite /
// Dark). Otherwise we fall back to the original Esri + OSM tiles so
// the demo path keeps working without an account.
var MAPBOX_TOKEN = (window.SH_CONFIG && window.SH_CONFIG.mapboxToken) || '';

function mapboxRaster(styleId) {
    return L.tileLayer(
        'https://api.mapbox.com/styles/v1/mapbox/' + styleId +
        '/tiles/512/{z}/{x}/{y}@2x?access_token=' + MAPBOX_TOKEN,
        {
            tileSize: 512,
            zoomOffset: -1,
            attribution: '&copy; <a href="https://www.mapbox.com/about/maps/">Mapbox</a> &copy; <a href="https://www.openstreetmap.org/about/">OSM</a>',
            maxZoom: 22
        }
    );
}

var basemaps = MAPBOX_TOKEN
    ? [
        { id: 'dark',      label: 'Dark',      layer: mapboxRaster('dark-v11') },
        { id: 'satellite', label: 'Satellite', layer: mapboxRaster('satellite-streets-v12') },
        { id: 'outdoors',  label: 'Outdoors',  layer: mapboxRaster('outdoors-v12') },
        { id: 'light',     label: 'Light',     layer: mapboxRaster('light-v11') }
    ]
    : [
        { id: 'satellite', label: 'Satellite', layer: L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', { attribution: 'Tiles &copy; Esri', maxZoom: 19 }) },
        { id: 'osm',       label: 'Street',    layer: L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution: '&copy; OpenStreetMap', maxZoom: 19 }) },
        { id: 'terrain',   label: 'Terrain',   layer: L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}', { attribution: 'Tiles &copy; Esri', maxZoom: 17 }) }
    ];

// Default basemap: Mapbox dark when a token is configured (matches the
// dashboard iframes), otherwise the first available fallback.
var activeBasemap = basemaps.find(function (b) { return b.id === 'dark'; })
    || basemaps.find(function (b) { return b.id === 'satellite'; })
    || basemaps[0];
activeBasemap.layer.addTo(map);

function setBasemap(id) {
    var next = basemaps.find(function (b) { return b.id === id; });
    if (!next || next === activeBasemap) return;
    map.removeLayer(activeBasemap.layer);
    next.layer.addTo(map);
    activeBasemap = next;
    document.querySelectorAll('.sh-basemap__btn').forEach(function (btn) {
        btn.dataset.active = btn.dataset.basemap === id ? 'true' : 'false';
    });
}

// Landslide-style basemap switcher — small pill panel anchored to the
// bottom-right of the map. Each pill is one of the registered
// basemaps; the active one carries `data-active="true"` for the CSS
// underline accent.
function renderBasemapSwitcher() {
    var BasemapControl = L.Control.extend({
        options: { position: 'topright' },
        onAdd: function () {
            var container = L.DomUtil.create('div', 'sh-basemap');
            container.setAttribute('aria-label', 'Basemap');
            L.DomEvent.disableClickPropagation(container);
            L.DomEvent.disableScrollPropagation(container);
            var head = L.DomUtil.create('div', 'sh-basemap__head', container);
            head.textContent = 'Basemap';
            var row = L.DomUtil.create('div', 'sh-basemap__row', container);
            basemaps.forEach(function (b) {
                var btn = L.DomUtil.create('button', 'sh-basemap__btn', row);
                btn.type = 'button';
                btn.textContent = b.label;
                btn.dataset.basemap = b.id;
                btn.dataset.active = b === activeBasemap ? 'true' : 'false';
                btn.addEventListener('click', function () {
                    setBasemap(b.id);
                });
            });
            return container;
        }
    });
    new BasemapControl().addTo(map);
}
renderBasemapSwitcher();

var ui = {
    statusMessage: document.getElementById('statusMessage'),
    projectName: document.getElementById('projectName'),
    analysisDate: document.getElementById('analysisDate'),
    runButton: document.getElementById('runButton'),
    runHint: document.getElementById('runHint'),
    roiArea: document.getElementById('roiArea'),
    roiStatus: document.getElementById('roiStatus')
};

var state = {
    roiSource: 'N/A',
    isRunning: false
};

function showMessage(type, text) {
    ui.statusMessage.className = 'status-message is-' + type;
    ui.statusMessage.textContent = text;
}

function clearMessage() {
    ui.statusMessage.className = 'status-message';
    ui.statusMessage.textContent = '';
}


function formatArea(areaSqm) {
    if (areaSqm === null || Number.isNaN(areaSqm)) return 'N/A';
    if (areaSqm >= 1000000) {
        return (areaSqm / 1000000).toFixed(2) + ' km2';
    }
    if (areaSqm >= 10000) {
        return (areaSqm / 10000).toFixed(2) + ' ha';
    }
    return areaSqm.toFixed(0) + ' m2';
}

function extractLayerInfo(layer) {
    var areaSqm = 0;
    var hasArea = false;
    var vertices = 0;

    function processPolygon(latlngs) {
        if (!latlngs || latlngs.length === 0) return;
        vertices += latlngs.length;
        if (L.GeometryUtil && L.GeometryUtil.geodesicArea) {
            areaSqm += L.GeometryUtil.geodesicArea(latlngs);
            hasArea = true;
        }
    }

    function processLayer(current) {
        if (!current) return;
        if (current.getLatLngs) {
            var latlngs = current.getLatLngs();
            if (Array.isArray(latlngs) && latlngs.length > 0) {
                if (Array.isArray(latlngs[0])) {
                    processPolygon(latlngs[0]);
                } else {
                    processPolygon(latlngs);
                }
            }
        } else if (current.getLayers) {
            current.eachLayer(function (child) {
                processLayer(child);
            });
        }
    }

    processLayer(layer);

    return {
        areaSqm: hasArea ? areaSqm : null,
        vertices: vertices
    };
}

function updateRoiSummary() {
    var layer = null;
    drawnItems.eachLayer(function (l) {
        layer = l;
    });

    if (!layer) {
        ui.roiArea.textContent = 'N/A';
        ui.roiStatus.textContent = 'No ROI';
        return;
    }

    var info = extractLayerInfo(layer);
    ui.roiArea.textContent = formatArea(info.areaSqm);
    ui.roiStatus.textContent = 'Ready';
}

function validateDates(showErrors) {
    var analysisDate = ui.analysisDate.value;

    if (!analysisDate) {
        if (showErrors) showMessage('error', 'Please select an analysis date.');
        return false;
    }
    return true;
}

function hasRoi() {
    return drawnItems.getLayers().length > 0;
}

function updateRunState() {
    var nameValid = ui.projectName.value.trim().length > 0;
    var datesValid = validateDates(false);
    var roiValid = hasRoi();
    var canRun = nameValid && datesValid && roiValid && !state.isRunning;

    ui.runButton.disabled = !canRun;

    if (!nameValid) {
        ui.runHint.textContent = 'Enter project name.';
    } else if (!datesValid) {
        ui.runHint.textContent = 'Select analysis date.';
    } else if (!roiValid) {
        ui.runHint.textContent = 'Draw or load ROI.';
    } else {
        ui.runHint.textContent = 'Ready to run.';
    }
}

function setDefaultDates() {
    var now = new Date();
    ui.analysisDate.value = now.toISOString().split('T')[0];
}

// Search Control
L.Control.geocoder({
    defaultMarkGeocode: false,
    position: 'topleft'
})
    .on('markgeocode', function (e) {
        var bbox = e.geocode.bbox;
        var poly = L.polygon([
            bbox.getSouthEast(),
            bbox.getNorthEast(),
            bbox.getNorthWest(),
            bbox.getSouthWest()
        ]);
        map.fitBounds(poly.getBounds());
    })
    .addTo(map);

// Draw Control
var drawnItems = new L.FeatureGroup();
map.addLayer(drawnItems);

var drawControl = new L.Control.Draw({
    draw: {
        polygon: { allowIntersection: false, showArea: true },
        marker: false,
        circle: false,
        circlemarker: false,
        polyline: false,
        rectangle: true
    },
    edit: { featureGroup: drawnItems, remove: true }
});
map.addControl(drawControl);

map.on(L.Draw.Event.CREATED, function (e) {
    drawnItems.clearLayers();
    drawnItems.addLayer(e.layer);
    state.roiSource = 'Drawn';
    updateRoiSummary();
    updateRunState();
    clearMessage();
});

map.on(L.Draw.Event.DELETED, function () {
    updateRoiSummary();
    updateRunState();
});

// Load Saved ROIs
fetch('/rois')
    .then(response => response.json())
    .then(data => {
        var select = document.getElementById('savedRois');
        data.forEach(name => {
            var option = document.createElement('option');
            option.value = name;
            option.text = name;
            select.appendChild(option);
        });
    });

// Load Existing Projects
fetch('/projects')
    .then(response => response.json())
    .then(data => {
        var select = document.getElementById('existingProjects');
        data.forEach(proj => {
            var option = document.createElement('option');
            option.value = proj.name;
            var meta = proj.metadata || {};
            var infoText = '';
            if (meta.area_ha) infoText += meta.area_ha.toFixed(1) + ' ha';
            if (meta.dates) infoText += infoText ? ', ' + meta.dates + ' dates' : meta.dates + ' dates';
            option.text = proj.name + (infoText ? ' (' + infoText + ')' : '');
            select.appendChild(option);
        });
    });

function loadRoi() {
    var name = document.getElementById('savedRois').value;
    if (!name) return;

    fetch('/rois/' + encodeURIComponent(name))
        .then(response => response.json())
        .then(geometry => {
            drawnItems.clearLayers();
            var layer = L.geoJSON(geometry);
            drawnItems.addLayer(layer);
            map.fitBounds(layer.getBounds());
            state.roiSource = 'Saved: ' + name;
            updateRoiSummary();
            updateRunState();
            clearMessage();
        });
}

function saveCurrentRoi() {
    var data = drawnItems.toGeoJSON();
    if (data.features.length === 0) {
        showMessage('error', 'Draw a polygon before saving.');
        return;
    }

    var name = prompt('Enter a name for this location:');
    if (!name) return;

    var geometry = data.features[0].geometry;

    fetch('/rois', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name, geometry: geometry })
    })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showMessage('success', 'Location saved successfully.');
                location.reload();
            } else {
                showMessage('error', 'Error saving location.');
            }
        });
}

function updateTimeRangeHint() {
    var timeRange = document.getElementById('timeRange').value;
    var hint = document.getElementById('timeRangeHint');
    var days = parseInt(timeRange);

    var label;
    if (days === 7) label = '1 week';
    else if (days === 14) label = '2 weeks';
    else if (days === 30) label = '1 month';
    else if (days === 60) label = '2 months';
    else if (days === 90) label = '3 months';
    else label = days + ' days';

    hint.textContent = 'Data will be collected for ' + label + ' prior to analysis date.';
}

function loadExistingProject() {
    var projectName = document.getElementById('existingProjects').value;

    if (!projectName) {
        // "New Project" selected - reset to default
        ui.projectName.value = 'New Vineyard';
        showMessage('info', 'Ready to start a new project.');
        return;
    }

    // Existing project selected - ask to reuse or start fresh
    if (confirm('Load existing data for "' + projectName + '"?\n\nClick OK to reuse existing data (map will be regenerated).\nClick Cancel to start a fresh analysis with the same name.')) {
        // Reuse existing data
        clearMessage();
        showMessage('info', 'Loading project: ' + projectName + '...');
        state.isRunning = true;
        document.getElementById('progress-container').style.display = 'block';
        ui.runButton.disabled = true;

        fetch('/reuse_project', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ project_name: projectName })
        })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    window.location.href = '/dashboard/' + data.project_name;
                } else {
                    showMessage('error', 'Error loading project: ' + data.error);
                    state.isRunning = false;
                    document.getElementById('progress-container').style.display = 'none';
                    updateRunState();
                }
            })
            .catch(error => {
                console.error('Error:', error);
                showMessage('error', 'An unexpected error occurred.');
                state.isRunning = false;
                document.getElementById('progress-container').style.display = 'none';
                updateRunState();
            });
    } else {
        // Use name but start fresh analysis
        ui.projectName.value = projectName;
        showMessage('info', 'Ready to analyze "' + projectName + '" with new parameters.');
    }
}

function startAnalysis() {
    clearMessage();

    var projectName = ui.projectName.value.trim();
    if (!projectName) {
        showMessage('error', 'Please enter a project name.');
        return;
    }

    var analysisDate = ui.analysisDate.value;
    var timeRange = document.getElementById('timeRange').value;

    if (!validateDates(true)) {
        return;
    }

    var data = drawnItems.toGeoJSON();
    if (data.features.length === 0) {
        showMessage('error', 'Please draw a ROI first.');
        return;
    }

    var geometry = data.features[0].geometry;

    // UI Update
    state.isRunning = true;
    document.getElementById('progress-container').style.display = 'block';
    ui.runButton.disabled = true;
    showMessage('info', 'Running analysis pipeline...');

    updateRunState();

    // Start Polling
    var pollInterval = setInterval(function () {
        fetch('/progress/' + encodeURIComponent(projectName))
            .then(response => response.json())
            .then(data => {
                document.getElementById('progressBar').style.width = data.percent + '%';
                document.getElementById('progressText').innerText = data.status;
            });
    }, 1000);

    // Only forward advanced params that the user actually set. The
    // backend falls back to the same server-side defaults the CLI
    // would use whenever a field is left blank.
    function optionalNumber(id) {
        var el = document.getElementById(id);
        if (!el || el.value === '') return null;
        var n = parseFloat(el.value);
        return isFinite(n) ? n : null;
    }

    var payload = {
        project_name: projectName,
        geometry: geometry,
        analysis_date: analysisDate,
        time_range_days: parseInt(timeRange)
    };
    var advanced = {
        cloud_threshold_s2: optionalNumber('cloudS2'),
        cloud_threshold_landsat: optionalNumber('cloudLandsat'),
        target_scale: optionalNumber('targetScale')
    };
    // Drop unset keys so the server's `data.get(..., default)` falls
    // back to its constants rather than receiving a None override.
    var pipelineConfig = {};
    Object.keys(advanced).forEach(function (k) {
        if (advanced[k] != null) pipelineConfig[k] = advanced[k];
    });
    if (Object.keys(pipelineConfig).length) {
        payload.pipeline_config = pipelineConfig;
    }

    fetch('/run_analysis', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    })
        .then(response => response.json())
        .then(data => {
            clearInterval(pollInterval);
            if (data.success) {
                window.location.href = '/dashboard/' + projectName;
            } else {
                showMessage('error', 'Error: ' + data.error);
                document.getElementById('progress-container').style.display = 'none';
                state.isRunning = false;
                updateRunState();
            }
        })
        .catch(error => {
            clearInterval(pollInterval);
            console.error('Error:', error);
            showMessage('error', 'An unexpected error occurred.');
            document.getElementById('progress-container').style.display = 'none';
            state.isRunning = false;
            updateRunState();
        });
}

setDefaultDates();
updateRoiSummary();
updateRunState();

[ui.projectName, ui.analysisDate].forEach(function (el) {
    el.addEventListener('input', function () {
        updateRunState();
        clearMessage();
    });
    el.addEventListener('change', function () {
        updateRunState();
        clearMessage();
    });
});
