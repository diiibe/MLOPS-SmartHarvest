// ===== CONFIG =====
const YEAR_RANGE = { min: 2018, max: 2026 };
const TIME_FRAMES = ['Giornaliero', 'Settimanale', 'Mensile', 'Trimestrale', 'Annuale'];

// ===== STATE =====
const state = {
    selectedYear: 2024,
    timeFrame: 'Mensile',
    dateRange: { start: null, end: null },
    filterConfig: {}
};

// ===== FLATPICKR INSTANCE =====
let flatpickrInstance;

// ===== INITIALIZE =====
document.addEventListener('DOMContentLoaded', () => {
    initMap();
    initYearTimeline();
    initTimeFrameSelector();
    initDatePicker();
    loadSavedRois();
});

// ===== YEAR TIMELINE =====
function initYearTimeline() {
    const container = document.getElementById('yearTimeline');
    container.innerHTML = '';

    for (let year = YEAR_RANGE.min; year <= YEAR_RANGE.max; year++) {
        const chip = document.createElement('div');
        chip.className = 'year-chip';
        chip.textContent = year;
        chip.onclick = () => selectYear(year);

        if (year === state.selectedYear) {
            chip.classList.add('selected');
        }

        container.appendChild(chip);
    }
}

function selectYear(year) {
    state.selectedYear = year;

    // Update UI
    document.querySelectorAll('.year-chip').forEach(chip => {
        chip.classList.toggle('selected', parseInt(chip.textContent) === year);
    });

    // Update date picker viewport
    if (flatpickrInstance) {
        flatpickrInstance.jumpToDate(new Date(year, 0, 1));
    }

    updateSummary();
}

// ===== TIME FRAME =====
function initTimeFrameSelector() {
    const container = document.getElementById('timeFrameSelector');
    container.innerHTML = '';

    TIME_FRAMES.forEach(frame => {
        const btn = document.createElement('div');
        btn.className = 'timeframe-btn';
        btn.textContent = frame;
        btn.onclick = () => selectTimeFrame(frame);

        if (frame === state.timeFrame) {
            btn.classList.add('selected');
        }

        container.appendChild(btn);
    });
}

function selectTimeFrame(frame) {
    state.timeFrame = frame;

    document.querySelectorAll('.timeframe-btn').forEach(btn => {
        btn.classList.toggle('selected', btn.textContent === frame);
    });

    updateSummary();
}

// ===== DATE PICKER =====
function initDatePicker() {
    flatpickrInstance = flatpickr("#dateRangePicker", {
        mode: "range",
        dateFormat: "d/m/Y",
        minDate: `${YEAR_RANGE.min}-01-01`,
        maxDate: `${YEAR_RANGE.max}-12-31`,
        locale: "it",
        theme: "dark",
        defaultDate: [new Date(2024, 5, 1), new Date(2024, 8, 15)],
        onChange: function (selectedDates) {
            if (selectedDates.length === 2) {
                state.dateRange.start = selectedDates[0];
                state.dateRange.end = selectedDates[1];
                updateSummary();
            }
        }
    });
}

// ===== SUMMARY =====
function updateSummary() {
    const summary = document.getElementById('filterSummary');
    const content = document.getElementById('summaryContent');

    if (!state.dateRange.start || !state.dateRange.end) {
        summary.classList.add('hidden');
        return;
    }

    const startDate = state.dateRange.start.toLocaleDateString('it-IT');
    const endDate = state.dateRange.end.toLocaleDateString('it-IT');

    content.innerHTML = `
        <strong>Configurazione Attiva</strong>
        📅 Anno: ${state.selectedYear}<br>
        📊 Granularità: ${state.timeFrame}<br>
        📆 Periodo: ${startDate} → ${endDate}
    `;

    summary.classList.remove('hidden');

    // Update filter config
    state.filterConfig = {
        selectedYear: state.selectedYear,
        timeFrame: state.timeFrame,
        startDate: state.dateRange.start.toISOString(),
        endDate: state.dateRange.end.toISOString()
    };
}

// ===== MAP INITIALIZATION =====
let map, drawnItems;

function initMap() {
    map = L.map('map').setView([45.4642, 9.1900], 10);

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap'
    }).addTo(map);

    drawnItems = new L.FeatureGroup();
    map.addLayer(drawnItems);

    const drawControl = new L.Control.Draw({
        edit: { featureGroup: drawnItems },
        draw: {
            polygon: { allowIntersection: false },
            polyline: false,
            circle: false,
            rectangle: false,
            marker: false,
            circlemarker: false
        }
    });
    map.addControl(drawControl);

    map.on(L.Draw.Event.CREATED, function (e) {
        drawnItems.clearLayers();
        drawnItems.addLayer(e.layer);
    });
}

// ===== ROI FUNCTIONS =====
function loadSavedRois() {
    fetch('/rois')
        .then(res => res.json())
        .then(data => {
            const select = document.getElementById('savedRois');
            data.forEach(roi => {
                const option = document.createElement('option');
                option.value = roi;
                option.textContent = roi;
                select.appendChild(option);
            });
        })
        .catch(err => console.log('No backend available'));
}

function loadRoi() {
    const roiName = document.getElementById('savedRois').value;
    if (!roiName) return;

    fetch(`/roi/${roiName}`)
        .then(res => res.json())
        .then(data => {
            drawnItems.clearLayers();
            const layer = L.geoJSON(data.geometry);
            layer.eachLayer(l => drawnItems.addLayer(l));
            map.fitBounds(drawnItems.getBounds());
        });
}

function saveCurrentRoi() {
    const projectName = document.getElementById('projectName').value;
    if (!projectName) {
        alert('Inserisci un nome progetto');
        return;
    }

    const data = drawnItems.toGeoJSON();
    if (data.features.length === 0) {
        alert('Disegna prima un\'area sulla mappa');
        return;
    }

    fetch('/save_roi', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            name: projectName,
            geometry: data.features[0].geometry
        })
    })
        .then(res => res.json())
        .then(() => {
            alert('Area salvata!');
            loadSavedRois();
        })
        .catch(() => alert('Errore nel salvataggio'));
}

// ===== START ANALYSIS =====
function startAnalysis() {
    const projectName = document.getElementById('projectName').value;

    if (!projectName) {
        alert('Inserisci un nome progetto');
        return;
    }

    if (!state.dateRange.start || !state.dateRange.end) {
        alert('Seleziona un periodo');
        return;
    }

    const data = drawnItems.toGeoJSON();
    if (data.features.length === 0) {
        alert('Disegna un\'area sulla mappa');
        return;
    }

    const geometry = data.features[0].geometry;

    // Show progress
    document.getElementById('progress-container').classList.remove('hidden');

    // Simulate progress (replace with actual backend call)
    let progress = 0;
    const interval = setInterval(() => {
        progress += 10;
        document.getElementById('progressBar').style.width = progress + '%';
        document.getElementById('progressText').textContent =
            progress < 100 ? 'Analisi in corso...' : 'Completato!';

        if (progress >= 100) {
            clearInterval(interval);
            setTimeout(() => {
                alert(`Analisi completata!\n${JSON.stringify(state.filterConfig, null, 2)}`);
                document.getElementById('progress-container').classList.add('hidden');
                document.getElementById('progressBar').style.width = '0%';
            }, 500);
        }
    }, 300);
}
