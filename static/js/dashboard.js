// Variable chip tooltips — click to pin the definition open so the
// user can read it without keeping the cursor still. A second click
// (or a click anywhere outside the chip) unpins. Hover and keyboard
// focus continue to show the bubble transiently via CSS.
//
// `flipAlign` is the edge-aware piece: the tooltip is anchored to
// the chip's centre by default, but if the bubble's natural
// bounding box would overflow the viewport we flip `data-align` to
// `start` (pin to chip's left edge) or `end` (pin to right edge)
// so the bubble always stays inside the screen.
(function () {
    var TOOLTIP_MAX_WIDTH = 240;
    var EDGE_PADDING = 8;

    function flipAlign(chip) {
        var rect = chip.getBoundingClientRect();
        var halfTooltip = TOOLTIP_MAX_WIDTH / 2;
        var chipCentre = rect.left + rect.width / 2;
        var leftEdge = chipCentre - halfTooltip;
        var rightEdge = chipCentre + halfTooltip;
        var viewportWidth = document.documentElement.clientWidth;

        if (leftEdge < EDGE_PADDING) {
            chip.dataset.align = "start";
        } else if (rightEdge > viewportWidth - EDGE_PADDING) {
            chip.dataset.align = "end";
        } else {
            delete chip.dataset.align;
        }
    }

    function init() {
        var chips = document.querySelectorAll(".sensor-row__chips .chip[data-tooltip]");
        if (!chips.length) return;

        chips.forEach(function (chip) {
            // Compute alignment on-demand instead of at init time so it
            // reacts to sidebar resize / browser zoom without hooking
            // a window resize listener for every chip.
            var maybeFlip = function () { flipAlign(chip); };
            chip.addEventListener("mouseenter", maybeFlip);
            chip.addEventListener("focus", maybeFlip);

            chip.addEventListener("click", function (e) {
                e.stopPropagation();
                var pinned = chip.dataset.pinned === "true";
                document
                    .querySelectorAll('.chip[data-pinned="true"]')
                    .forEach(function (c) { c.dataset.pinned = "false"; });
                chip.dataset.pinned = pinned ? "false" : "true";
                if (!pinned) flipAlign(chip);
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
