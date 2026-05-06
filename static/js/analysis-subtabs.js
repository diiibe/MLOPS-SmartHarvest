/*
 * Data Analysis sub-tab controller.
 *
 * The Data Analysis tab now holds four themed sub-tabs (Overview /
 * Temporal / Spatial / Quality) plus a dismissible variable glossary
 * panel. This script wires the segmented control:
 *
 *   1. Tab switch — animates the outgoing panel (fade + 8 px slide
 *      up, 180 ms ease-out-quint), swaps the `[hidden]` attribute,
 *      and stagger-reveals the incoming panel's sections (40 ms
 *      offset, capped at 4 steps).
 *   2. Animated rail — a thin underline pill that slides under the
 *      active tab via measured `transform: translateX + scaleX`.
 *   3. Glossary panel — opens via the "Variables ↗" pill, closes on
 *      backdrop click / Escape.
 *
 * `prefers-reduced-motion: reduce` collapses every animation to ~10 ms.
 *
 * Plotly figures inside hidden panels keep their HTML in the DOM so
 * a tab switch doesn't trigger a re-render. The first switch into a
 * panel kicks Plotly's `Plots.resize` so figures fit the column
 * exactly even when the panel was hidden during the initial layout.
 */
(function () {
    "use strict";

    var ROOT_SELECTOR = ".analysis[data-component=\"analysis\"]";
    var REDUCED_MOTION = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    var DURATION_OUT = REDUCED_MOTION ? 10 : 180;
    var DURATION_IN = REDUCED_MOTION ? 10 : 220;
    var STAGGER_STEP = REDUCED_MOTION ? 0 : 40;
    var STAGGER_CAP = 4;

    function resizePlotly(panel) {
        if (typeof window.Plotly === "undefined" || !window.Plotly.Plots) return;
        var plots = panel.querySelectorAll(".js-plotly-plot");
        plots.forEach(function (el) {
            try {
                window.Plotly.Plots.resize(el);
            } catch (e) {
                // Silent — Plotly has no relayout context yet.
            }
        });
    }

    function staggerReveal(panel) {
        var sections = panel.querySelectorAll(".analysis-section, .subtab-panel__head");
        sections.forEach(function (s, i) {
            var delay = Math.min(i, STAGGER_CAP) * STAGGER_STEP;
            s.style.animation = "none";
            // Force reflow so the animation restarts even on rapid tab toggling.
            void s.offsetWidth;
            s.style.animation = (
                "subtab-section-in " +
                (REDUCED_MOTION ? 10 : 320) + "ms " +
                "cubic-bezier(0.16, 1, 0.3, 1) " +
                delay + "ms both"
            );
        });
    }

    function moveRail(rail, btn) {
        if (!rail || !btn) return;
        var nav = btn.parentElement;
        var navRect = nav.getBoundingClientRect();
        var btnRect = btn.getBoundingClientRect();
        var x = btnRect.left - navRect.left;
        var w = btnRect.width;
        rail.style.transform = "translateX(" + x + "px)";
        rail.style.width = w + "px";
        rail.style.opacity = "1";
    }

    function switchTo(root, name, options) {
        options = options || {};
        var panels = root.querySelectorAll(".subtab-panel");
        var current = root.querySelector(".subtab-panel:not([hidden])");
        var target = root.querySelector(
            ".subtab-panel[data-subtab-panel=\"" + name + "\"]"
        );
        if (!target || target === current) {
            return;
        }

        var doSwap = function () {
            panels.forEach(function (p) {
                if (p !== target) p.setAttribute("hidden", "");
            });
            target.removeAttribute("hidden");
            target.style.opacity = "0";
            target.style.transform = "translateY(6px)";
            // Force reflow so the in-transition starts cleanly.
            void target.offsetWidth;
            target.style.transition =
                "opacity " + DURATION_IN + "ms cubic-bezier(0.16, 1, 0.3, 1), " +
                "transform " + DURATION_IN + "ms cubic-bezier(0.16, 1, 0.3, 1)";
            target.style.opacity = "1";
            target.style.transform = "translateY(0)";
            staggerReveal(target);
            // First reveal of a panel may need a Plotly resize after
            // the transition finishes so figures pick up the live width.
            window.setTimeout(function () {
                resizePlotly(target);
                target.style.transition = "";
            }, DURATION_IN + 20);
        };

        if (current && !options.skipOut) {
            current.style.transition =
                "opacity " + DURATION_OUT + "ms cubic-bezier(0.25, 1, 0.5, 1), " +
                "transform " + DURATION_OUT + "ms cubic-bezier(0.25, 1, 0.5, 1)";
            current.style.opacity = "0";
            current.style.transform = "translateY(-8px)";
            window.setTimeout(doSwap, DURATION_OUT);
        } else {
            doSwap();
        }
    }

    function syncTabs(root, name) {
        var tabs = root.querySelectorAll(".subtab[data-subtab]");
        var rail = root.querySelector(".subtabs__rail");
        tabs.forEach(function (t) {
            var active = t.dataset.subtab === name;
            t.dataset.active = active ? "true" : "false";
            t.setAttribute("aria-selected", active ? "true" : "false");
            if (active) {
                moveRail(rail, t);
            }
        });
    }

    function openGlossary(root) {
        var panel = root.querySelector("#analysis-glossary-panel");
        var backdrop = root.querySelector(".glossary-panel__backdrop");
        if (!panel) return;
        panel.removeAttribute("hidden");
        if (backdrop) backdrop.removeAttribute("hidden");
        // Force reflow before flipping the open state so the
        // transition runs from closed → open every time.
        void panel.offsetWidth;
        panel.dataset.open = "true";
        if (backdrop) backdrop.dataset.open = "true";
        window.setTimeout(function () {
            var closeBtn = panel.querySelector(".glossary-panel__close");
            if (closeBtn) closeBtn.focus();
        }, 60);
    }

    function closeGlossary(root) {
        var panel = root.querySelector("#analysis-glossary-panel");
        var backdrop = root.querySelector(".glossary-panel__backdrop");
        if (!panel) return;
        panel.dataset.open = "false";
        if (backdrop) backdrop.dataset.open = "false";
        window.setTimeout(function () {
            panel.setAttribute("hidden", "");
            if (backdrop) backdrop.setAttribute("hidden", "");
        }, REDUCED_MOTION ? 10 : 240);
    }

    function init() {
        var root = document.querySelector(ROOT_SELECTOR);
        if (!root) return;

        // Click handler covers tabs + glossary controls.
        root.addEventListener("click", function (e) {
            var glossaryAction = e.target.closest("[data-action]");
            if (glossaryAction) {
                if (glossaryAction.dataset.action === "open-glossary") {
                    openGlossary(root);
                    e.preventDefault();
                    return;
                }
                if (glossaryAction.dataset.action === "close-glossary") {
                    closeGlossary(root);
                    e.preventDefault();
                    return;
                }
            }

            var tab = e.target.closest(".subtab[data-subtab]");
            if (!tab) return;
            var name = tab.dataset.subtab;
            switchTo(root, name);
            syncTabs(root, name);
        });

        // Keyboard: Escape closes the glossary; ←/→ navigate sub-tabs.
        document.addEventListener("keydown", function (e) {
            if (e.key === "Escape") {
                closeGlossary(root);
                return;
            }
            if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
            var active = root.querySelector(
                ".subtab[data-subtab][data-active=\"true\"]"
            );
            var siblings = Array.prototype.slice.call(
                root.querySelectorAll(".subtab[data-subtab]")
            );
            var idx = siblings.indexOf(active);
            if (idx < 0) return;
            var next = e.key === "ArrowRight"
                ? siblings[(idx + 1) % siblings.length]
                : siblings[(idx - 1 + siblings.length) % siblings.length];
            next.click();
            next.focus();
        });

        // Initial state: Overview is open. Sync the rail + sync the
        // first stagger animation so the panel feels alive on load.
        syncTabs(root, "overview");
        var overview = root.querySelector(
            ".subtab-panel[data-subtab-panel=\"overview\"]"
        );
        if (overview) {
            staggerReveal(overview);
        }

        // Recompute the rail position on viewport resize so the pill
        // tracks the active tab when the user resizes the window.
        window.addEventListener("resize", function () {
            var active = root.querySelector(
                ".subtab[data-subtab][data-active=\"true\"]"
            );
            if (active) {
                moveRail(root.querySelector(".subtabs__rail"), active);
            }
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
