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
        label.textContent = `${week.week_id}`;

        console.log(`[ML Timeline] Showing week ${week.week_id}`);
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

        // Use DOM APIs so the error string is rendered as text, never as
        // HTML. innerHTML here was an XSS vector since `message` can bubble
        // up from fetch rejections that include server-controlled content.
        const target = document.getElementById('ml-cluster-info');
        target.textContent = '';
        const p = document.createElement('p');
        p.style.color = '#e74c3c';
        p.style.fontSize = '13px';
        p.textContent = message;
        target.appendChild(p);
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
