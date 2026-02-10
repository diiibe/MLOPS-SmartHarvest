function switchTab(tabName) {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.getElementById('map-view').style.display = 'none';
    document.getElementById('analysis-view').style.display = 'none';
    document.getElementById('ml-anomalies-view').style.display = 'none';
    document.getElementById('report-view').style.display = 'none';

    if (tabName === 'map') {
        document.querySelectorAll('.tab')[0].classList.add('active');
        document.getElementById('map-view').style.display = 'block';
    } else if (tabName === 'analysis') {
        document.querySelectorAll('.tab')[1].classList.add('active');
        document.getElementById('analysis-view').style.display = 'block';
        window.dispatchEvent(new Event('resize'));
    } else if (tabName === 'ml-anomalies') {
        document.querySelectorAll('.tab')[2].classList.add('active');
        document.getElementById('ml-anomalies-view').style.display = 'flex';

        // Initialize ML timeline if not already done
        if (window.mlTimeline && !window.mlTimeline.initialized) {
            window.mlTimeline.init();
        }
    } else {
        document.querySelectorAll('.tab')[3].classList.add('active');
        document.getElementById('report-view').style.display = 'block';
    }
}
