// Variable chip tooltips — click to pin the definition open so the
// user can read it without keeping the cursor still. A second click
// (or a click anywhere outside the chip) unpins. Hover and keyboard
// focus continue to show the bubble transiently via CSS.
(function () {
    function init() {
        var chips = document.querySelectorAll(".sensor-row__chips .chip[data-tooltip]");
        if (!chips.length) return;

        chips.forEach(function (chip) {
            chip.addEventListener("click", function (e) {
                e.stopPropagation();
                var pinned = chip.dataset.pinned === "true";
                document
                    .querySelectorAll('.chip[data-pinned="true"]')
                    .forEach(function (c) { c.dataset.pinned = "false"; });
                chip.dataset.pinned = pinned ? "false" : "true";
            });
            chip.addEventListener("keydown", function (e) {
                if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    chip.click();
                }
            });
        });

        document.addEventListener("click", function () {
            document
                .querySelectorAll('.chip[data-pinned="true"]')
                .forEach(function (c) { c.dataset.pinned = "false"; });
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();

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
