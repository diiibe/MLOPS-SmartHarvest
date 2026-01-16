// ========================================
// PHENOLOGY LAB & DATA REPORT - CLEAN REWRITE
// ========================================

// Global data (from Jinja2)
const phenologyData = {{ ts_data | tojson | safe }};

// ========================================
// PHENOLOGY LAB FUNCTIONS
// ========================================

function initPhenoLab() {
    console.log('[Pheno] Initializing Phenology Lab...');

    // Validate data
    if (!phenologyData || !phenologyData.daily_full || phenologyData.daily_full.length === 0) {
        console.warn('[Pheno] No daily_full data available');
        showPhenoError('No data available. Run analysis first.');
        return;
    }

    console.log(`[Pheno] Data loaded: ${phenologyData.daily_full.length} records`);

    // Extract unique years
    const years = [...new Set(phenologyData.daily_full.map(d => d.Year))].filter(y => y).sort();

    if (years.length === 0) {
        console.warn('[Pheno] No years found in data');
        showPhenoError('No year data available');
        return;
    }

    console.log(`[Pheno] Years found: ${years.join(', ')}`);

    // Populate year dropdown
    const yearSelect = document.getElementById('phenoYear');
    if (!yearSelect) {
        console.error('[Pheno] Year select element not found');
        return;
    }

    // Clear existing options
    yearSelect.innerHTML = '';

    // Add year options
    years.forEach(year => {
        const option = document.createElement('option');
        option.value = year;
        option.textContent = year;
        yearSelect.appendChild(option);
    });

    // Select last year by default
    yearSelect.value = years[years.length - 1];

    // Render charts for default year
    renderPhenoChartsV2(year Select.value);
}

function renderPhenoChartsV2(selectedYear) {
    console.log(`[Pheno] Rendering charts for year ${selectedYear}`);

    try {
        // Filter data for selected year
        const yearData = phenologyData.daily_full.filter(d => d.Year == selectedYear);

        if (yearData.length === 0) {
            showPhenoError(`No data for year ${selectedYear}`);
            return;
        }

        console.log(`[Pheno] ${yearData.length} records for ${selectedYear}`);

        // Extract data
        const dates = yearData.map(d => d.date);
        const ndvi = yearData.map(d => d.NDVI_mean || 0);
        const vh = yearData.map(d => d.VH_mean || 0);
        const vv = yearData.map(d => d.VV_mean || 0);
        const doy = yearData.map(d => d.DOY || 0);

        // Calculate derived metrics
        const ratio = yearData.map(d => {
            if (d.VH_mean && d.VV_mean && d.VV_mean !== 0) {
                return d.VH_mean / d.VV_mean;
            }
            return null;
        });

        // NDVI Velocity (simple derivative)
        const velocity = ndvi.map((v, i, arr) => {
            if (i < 2 || i >= arr.length - 2) return null;
            return (arr[i + 1] - arr[i - 1]) / 2 * 100; // Scale up for visibility
        });

        // Chart 1: Voting Signals (Velocity + Ratio)
        renderVelocityChart(dates, velocity, ratio, ndvi);

        // Chart 2: Hysteresis (Phase Space)
        renderHysteresisChart(ndvi, ratio, doy, dates);

        console.log('[Pheno] Charts rendered successfully');

    } catch (error) {
        console.error('[Pheno] Error rendering charts:', error);
        showPhenoError(`Error: ${error.message}`);
    }
}

function renderVelocityChart(dates, velocity, ratio, ndvi) {
    const trace1 = {
        x: dates,
        y: velocity,
        name: 'NDVI Velocity (Greening)',
        type: 'scatter',
        mode: 'lines',
        line: { color: '#2ecc71', width: 2 }
    };

    const trace2 = {
        x: dates,
        y: ratio,
        name: 'Radar Ratio (VH/VV)',
        type: 'scatter',
        mode: 'lines',
        line: { color: '#9b59b6', width: 2 },
        yaxis: 'y2'
    };

    const trace3 = {
        x: dates,
        y: ndvi,
        name: 'NDVI (Reference)',
        type: 'scatter',
        mode: 'lines',
        line: { color: '#2ecc71', width: 1, dash: 'dot' },
        visible: 'legendonly'
    };

    const layout = {
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        xaxis: { title: 'Date', color: '#aaa', gridcolor: '#333' },
        yaxis: { title: 'Velocity Index', color: '#2ecc71', gridcolor: '#333' },
        yaxis2: {
            title: 'VH/VV Ratio',
            color: '#9b59b6',
            overlaying: 'y',
            side: 'right',
            gridcolor: '#333',
            showgrid: false
        },
        legend: { x: 0, y: 1.1, orientation: 'h', font: { color: '#fff' } },
        margin: { l: 50, r: 50, t: 20, b: 40 }
    };

    Plotly.newPlot('phenoVelocityChart', [trace1, trace2, trace3], layout, { responsive: true });
}

function renderHysteresisChart(ndvi, ratio, doy, dates) {
    const trace = {
        x: ndvi,
        y: ratio,
        mode: 'lines+markers',
        marker: {
            size: 6,
            color: doy,
            colorscale: 'Viridis',
            showscale: true,
            colorbar: { title: 'DOY', thickness: 10 }
        },
        line: { color: '#aaa', width: 1, dash: 'dot' },
        text: dates,
        name: 'Seasonal Trajectory'
    };

    const layout = {
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        xaxis: { title: 'NDVI (Vigor)', color: '#aaa', gridcolor: '#333' },
        yaxis: { title: 'Radar Ratio (Structure)', color: '#aaa', gridcolor: '#333' },
        margin: { l: 50, r: 20, t: 20, b: 40 }
    };

    Plotly.newPlot('phenoHysteresisChart', [trace], layout, { responsive: true });
}

function showPhenoError(message) {
    const chartDiv = document.getElementById('phenoVelocityChart');
    if (chartDiv) {
        chartDiv.innerHTML = `<div style="color: #e74c3c; padding: 40px; text-align: center; font-size: 14px;">${message}</div>`;
    }
}

// ========================================
// DATA REPORT FUNCTIONS
// ========================================

function initReportView() {
    console.log('[Report] Initializing Data Report...');

    const reportContent = document.getElementById('reportContent');
    const reportFallback = document.getElementById('reportFallback');

    if (!reportContent) {
        console.error('[Report] reportContent element not found');
        return;
    }

    if (reportContent.innerHTML.trim() === '') {
        console.warn('[Report] No report content found');
        if (reportFallback) reportFallback.style.display = 'block';
    } else {
        console.log('[Report] Report content loaded');
        if (reportFallback) reportFallback.style.display = 'none';
    }
}

// ========================================
// TAB SWITCHING (SIMPLIFIED)
// ========================================

function switchTabV2(tabName) {
    console.log(`[Tab] Switching to: ${tabName}`);

    // Hide all views
    const allViews = ['map-view', 'analysis-view', 'timeseries-view', 'phenology-view', 'report-view'];
    allViews.forEach(viewId => {
        const el = document.getElementById(viewId);
        if (el) el.style.display = 'none';
    });

    // Update tab styles
    document.querySelectorAll('.tab').forEach(tab => tab.classList.remove('active'));

    // Show selected view
    const targetId = `${tabName}-view`;
    const targetEl = document.getElementById(targetId);

    if (targetEl) {
        targetEl.style.display = 'block';

        // Find and activate corresponding tab button
        const matchingTab = Array.from(document.querySelectorAll('.tab')).find(t =>
            t.getAttribute('onclick') && t.getAttribute('onclick').includes(tabName)
        );
        if (matchingTab) matchingTab.classList.add('active');

        // Trigger specific initialization
        if (tabName === 'phenology') {
            const yearSelect = document.getElementById('phenoYear');
            if (yearSelect && yearSelect.value) {
                renderPhenoChartsV2(yearSelect.value);
            }
        }
    } else {
        console.error(`[Tab] View not found: ${targetId}`);
    }
}

// ========================================
// INITIALIZATION
// ========================================

document.addEventListener('DOMContentLoaded', function () {
    console.log('[Init] Dashboard loaded');

    // Initialize all components
    initPhenoLab();
    initReportView();

    // Render existing charts (if any)
    if (typeof renderCharts === 'function') {
        renderCharts();
    }
});
