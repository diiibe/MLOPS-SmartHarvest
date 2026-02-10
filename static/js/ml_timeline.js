/**
 * ML Timeline Controller - Handles week navigation and cluster details
 */

class MLTimeline {
    constructor(projectName) {
        this.projectName = projectName;
        this.weeks = [];
        this.currentWeekIndex = 0;
        this.playing = false;
        this.playInterval = null;
        this.initialized = false;
    }

    async init() {
        if (this.initialized) {
            return;
        }

        console.log('[ML Timeline] Initializing...');

        try {
            // Fetch available weeks
            const response = await fetch(`/api/ml_weeks/${this.projectName}`);
            const data = await response.json();
            this.weeks = data.weeks || [];

            if (this.weeks.length === 0) {
                this.showError('No ML analysis data available. Run: python run_ml_weekly.py ' + this.projectName);
                return;
            }

            // Setup slider
            const slider = document.getElementById('ml-week-slider');
            slider.max = this.weeks.length - 1;
            slider.value = this.weeks.length - 1;  // Start at latest
            this.currentWeekIndex = this.weeks.length - 1;

            this.updateMap();
            this.setupEventListeners();
            this.initialized = true;

            console.log(`[ML Timeline] Loaded ${this.weeks.length} weeks`);
        } catch (error) {
            console.error('[ML Timeline] Error:', error);
            this.showError('Failed to load ML analysis data.');
        }
    }

    updateMap() {
        const week = this.weeks[this.currentWeekIndex];
        const iframe = document.getElementById('ml-map-iframe');
        iframe.src = `/ml_map/${this.projectName}?week=${week.week_id}`;

        const label = document.getElementById('ml-week-label');
        label.textContent = `${week.week_id} (${week.clusters_count} clusters)`;

        console.log(`[ML Timeline] Showing week ${week.week_id}`);

        // Clear sidebar
        this.clearSidebar();
    }

    setupEventListeners() {
        // Slider
        document.getElementById('ml-week-slider').addEventListener('input', (e) => {
            this.currentWeekIndex = parseInt(e.target.value);
            this.updateMap();
        });

        // Play/Pause button
        document.getElementById('ml-play-btn').addEventListener('click', () => {
            this.togglePlay();
        });

        // Previous button
        document.getElementById('ml-prev-btn').addEventListener('click', () => {
            if (this.currentWeekIndex > 0) {
                this.currentWeekIndex--;
                document.getElementById('ml-week-slider').value = this.currentWeekIndex;
                this.updateMap();
            }
        });

        // Next button
        document.getElementById('ml-next-btn').addEventListener('click', () => {
            if (this.currentWeekIndex < this.weeks.length - 1) {
                this.currentWeekIndex++;
                document.getElementById('ml-week-slider').value = this.currentWeekIndex;
                this.updateMap();
            }
        });

        // Listen for cluster clicks (from map iframe)
        window.addEventListener('message', (event) => {
            if (event.data && event.data.type === 'cluster_click') {
                this.showClusterDetails(event.data.cluster_label);
            }
        });
    }

    togglePlay() {
        this.playing = !this.playing;
        const btn = document.getElementById('ml-play-btn');
        btn.textContent = this.playing ? '⏸' : '▶';

        if (this.playing) {
            this.playInterval = setInterval(() => {
                this.currentWeekIndex = (this.currentWeekIndex + 1) % this.weeks.length;
                document.getElementById('ml-week-slider').value = this.currentWeekIndex;
                this.updateMap();
            }, 2000);  // 2 seconds per week
        } else {
            clearInterval(this.playInterval);
        }
    }

    async showClusterDetails(clusterLabel) {
        const week = this.weeks[this.currentWeekIndex];
        const sidebar = document.getElementById('ml-cluster-info');

        sidebar.innerHTML = '<p style="color: #888;">Loading cluster details...</p>';

        try {
            const response = await fetch(`/api/ml_cluster/${this.projectName}/${week.week_id}/${clusterLabel}`);
            const data = await response.json();

            if (data.error) {
                sidebar.innerHTML = `<p style="color: #e74c3c;">Error: ${data.error}</p>`;
                return;
            }

            // Build sidebar HTML
            let html = `
                <div style="margin-bottom: 15px;">
                    <h4 style="margin: 0 0 10px 0; color: #3498db;">Cluster ${data.cluster_label}</h4>
                    <div style="font-size: 12px; color: #ccc; line-height: 1.8;">
                        <b>Track ID:</b> ${data.track_id}<br>
                        <b>Status:</b> <span style="background-color: ${this.getStatusColor(data.status)}; padding: 2px 6px; border-radius: 3px; color: black; font-weight: bold;">${data.status.toUpperCase()}</span><br>
                        <b>Pixel Count:</b> ${data.pixel_count}<br>
                        <b>Outlier Score:</b> ${data.outlier_score_mean.toFixed(3)}
                    </div>
                </div>
            `;

            // Feature values
            if (data.features && Object.keys(data.features).length > 0) {
                html += '<div style="margin-bottom: 15px; border-top: 1px solid #555; padding-top: 10px;">';
                html += '<h5 style="margin: 0 0 8px 0; color: #f39c12;">Feature Values</h5>';
                html += '<div style="font-size: 11px; color: #aaa; line-height: 1.6;">';

                for (const [feature, value] of Object.entries(data.features)) {
                    if (!isNaN(value)) {
                        html += `<b>${feature}:</b> ${value.toFixed(4)}<br>`;
                    }
                }

                html += '</div></div>';
            }

            // Tracking history
            if (data.history && data.history.length > 0) {
                html += '<div style="border-top: 1px solid #555; padding-top: 10px;">';
                html += '<h5 style="margin: 0 0 8px 0; color: #2ecc71;">Tracking History</h5>';
                html += '<div style="font-size: 11px; color: #aaa;">';

                data.history.forEach(h => {
                    const isCurrent = h.week_id === week.week_id;
                    const style = isCurrent ? 'font-weight: bold; color: #3498db;' : '';
                    html += `
                        <div style="margin-bottom: 5px; ${style}">
                            ${isCurrent ? '➤ ' : ''}${h.week_id}: ${h.pixel_count} px, Score ${h.outlier_score.toFixed(3)}
                        </div>
                    `;
                });

                html += '</div></div>';
            }

            sidebar.innerHTML = html;

        } catch (error) {
            console.error('[ML Timeline] Error fetching cluster details:', error);
            sidebar.innerHTML = '<p style="color: #e74c3c;">Failed to load cluster details.</p>';
        }
    }

    getStatusColor(status) {
        const colors = {
            'new': '#FFD700',       // Gold
            'continued': '#1E90FF',  // DodgerBlue
            'unknown': '#808080'     // Gray
        };
        return colors[status] || '#808080';
    }

    clearSidebar() {
        document.getElementById('ml-cluster-info').innerHTML = '<p style="color: #888; font-size: 13px;">Click on a cluster marker to see details...</p>';
    }

    showError(message) {
        const label = document.getElementById('ml-week-label');
        label.textContent = 'Error';
        label.style.color = '#e74c3c';

        document.getElementById('ml-cluster-info').innerHTML = `<p style="color: #e74c3c; font-size: 13px;">${message}</p>`;
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    // Get project name from template (set in dashboard.html)
    const projectName = window.PROJECT_NAME;

    if (!projectName) {
        console.error('[ML Timeline] PROJECT_NAME not found in window. Check dashboard.html template.');
        return;
    }

    window.mlTimeline = new MLTimeline(projectName);

    // Don't auto-init - wait for tab switch
    console.log(`[ML Timeline] Ready for project: ${projectName}. Will initialize on tab switch.`);
});
