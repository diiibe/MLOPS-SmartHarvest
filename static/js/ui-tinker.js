/*
 * SmartHarvest UI tinker — a floating dev panel for live colour
 * experiments. Renders a pill bottom-right that opens into a small
 * drawer with native colour pickers for the dominant tokens; values
 * are written straight onto the `<html>` element as inline custom
 * properties so they win over the `tokens.css` defaults.
 *
 * Persists to localStorage so a reload preserves the working palette
 * for the current dev session. The "Reset" button removes the
 * inline overrides and clears storage in one go.
 */
(function () {
    "use strict";

    const STORAGE_KEY = "sh-tinker:v1";
    // Tokens exposed in the panel. Keep the list short so the dev
    // tool stays focused on the dominant surfaces — pickers for every
    // accent would just turn this into a token editor.
    const TOKENS = [
        { name: "Canvas",     prop: "--c-bg-linen", fallback: "#1A1814" },
        { name: "Surface",    prop: "--c-surface",  fallback: "#25221C" },
        { name: "Border",     prop: "--c-border",   fallback: "#3A352A" },
        { name: "Text",       prop: "--c-text",     fallback: "#ECE4D2" },
        { name: "Accent",     prop: "--c-ochre",    fallback: "#E2B95C" },
        { name: "Wine",       prop: "--c-russet",   fallback: "#E07A66" },
    ];

    function readStored() {
        try {
            return JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");
        } catch (_) {
            return {};
        }
    }

    function writeStored(state) {
        try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
        } catch (_) {
            /* private mode etc. — silently noop */
        }
    }

    // Resolve a token's *effective* current value: explicit override
    // first, then the computed value from `tokens.css`, then the
    // hard-coded fallback.
    function effectiveColor(prop, override, fallback) {
        if (override) return override;
        const computed = getComputedStyle(document.documentElement)
            .getPropertyValue(prop)
            .trim();
        return normaliseHex(computed) || fallback;
    }

    // `<input type="color">` only accepts `#rrggbb`. Convert anything
    // CSS hands us into that form when possible; bail to `null` if
    // the value is a named colour or otherwise unparseable so we
    // fall back to the hard-coded default.
    function normaliseHex(value) {
        if (!value) return null;
        const trimmed = value.trim();
        if (/^#([0-9a-f]{6})$/i.test(trimmed)) return trimmed.toLowerCase();
        if (/^#([0-9a-f]{3})$/i.test(trimmed)) {
            const [r, g, b] = trimmed.slice(1);
            return ("#" + r + r + g + g + b + b).toLowerCase();
        }
        return null;
    }

    function applyState(state) {
        const html = document.documentElement;
        if (state.theme) html.setAttribute("data-theme", state.theme);
        else html.removeAttribute("data-theme");
        TOKENS.forEach(({ prop }) => {
            if (state.colors && state.colors[prop]) {
                html.style.setProperty(prop, state.colors[prop]);
            } else {
                html.style.removeProperty(prop);
            }
        });
    }

    function buildPanel(state, onChange, onReset) {
        const root = document.createElement("div");
        root.className = "sh-tinker";
        root.dataset.open = "false";

        const toggle = document.createElement("button");
        toggle.type = "button";
        toggle.className = "sh-tinker__toggle";
        toggle.textContent = "tinker";
        toggle.setAttribute("aria-label", "Open UI tinker panel");

        const panel = document.createElement("div");
        panel.className = "sh-tinker__panel";

        const title = document.createElement("h4");
        title.className = "sh-tinker__title";
        title.textContent = "UI tinker";
        panel.appendChild(title);

        // Theme row sits above the colour pickers because it usually
        // cascades through every other token at once.
        const themeRow = document.createElement("div");
        themeRow.className = "sh-tinker__row";
        const themeLabel = document.createElement("label");
        themeLabel.textContent = "Theme";
        themeLabel.htmlFor = "sh-tinker-theme";
        const themeSelect = document.createElement("select");
        themeSelect.id = "sh-tinker-theme";
        themeSelect.style.cssText =
            "grid-column: span 2; height: 24px; background: var(--c-surface);" +
            " border: 1px solid var(--c-border); border-radius: var(--radius-sm);" +
            " color: var(--c-text); font-size: 11.5px; padding: 0 6px;";
        ["dark", "light"].forEach((t) => {
            const opt = document.createElement("option");
            opt.value = t;
            opt.textContent = t;
            if ((state.theme || "dark") === t) opt.selected = true;
            themeSelect.appendChild(opt);
        });
        themeSelect.addEventListener("change", () => {
            state.theme = themeSelect.value === "dark" ? null : themeSelect.value;
            applyState(state);
            onChange();
            // Re-pull colour values so the pickers reflect the freshly
            // applied theme rather than stale dark-mode swatches.
            refreshPickers();
        });
        themeRow.appendChild(themeLabel);
        themeRow.appendChild(themeSelect);
        panel.appendChild(themeRow);

        const pickers = [];
        TOKENS.forEach(({ name, prop, fallback }) => {
            const row = document.createElement("div");
            row.className = "sh-tinker__row";

            const label = document.createElement("label");
            label.textContent = name;
            label.htmlFor = "sh-tinker-" + prop.replace(/--/, "");
            row.appendChild(label);

            const input = document.createElement("input");
            input.type = "color";
            input.id = label.htmlFor;
            input.value = effectiveColor(
                prop,
                state.colors && state.colors[prop],
                fallback
            );
            input.addEventListener("input", () => {
                state.colors = state.colors || {};
                state.colors[prop] = input.value;
                applyState(state);
                code.textContent = input.value;
                onChange();
            });
            row.appendChild(input);

            const code = document.createElement("code");
            code.textContent = input.value;
            row.appendChild(code);

            panel.appendChild(row);
            pickers.push({ input, prop, fallback, code });
        });

        function refreshPickers() {
            // Defer one frame so the document picks up the freshly
            // applied `data-theme` before we read computed values.
            requestAnimationFrame(() => {
                pickers.forEach(({ input, prop, fallback, code }) => {
                    const v = effectiveColor(
                        prop,
                        state.colors && state.colors[prop],
                        fallback
                    );
                    input.value = v;
                    code.textContent = v;
                });
            });
        }

        const actions = document.createElement("div");
        actions.className = "sh-tinker__actions";

        const resetBtn = document.createElement("button");
        resetBtn.type = "button";
        resetBtn.textContent = "Reset";
        resetBtn.addEventListener("click", () => {
            onReset();
            refreshPickers();
        });

        const closeBtn = document.createElement("button");
        closeBtn.type = "button";
        closeBtn.textContent = "Close";
        closeBtn.addEventListener("click", () => {
            root.dataset.open = "false";
        });

        actions.appendChild(resetBtn);
        actions.appendChild(closeBtn);
        panel.appendChild(actions);

        toggle.addEventListener("click", () => {
            root.dataset.open = root.dataset.open === "true" ? "false" : "true";
        });

        root.appendChild(toggle);
        root.appendChild(panel);

        return { root, refreshPickers };
    }

    function init() {
        const state = readStored();
        // Always apply persisted state on first paint so the panel can
        // be opened later without flashing the default palette.
        applyState(state);

        const { root } = buildPanel(
            state,
            () => writeStored(state),
            () => {
                state.colors = {};
                state.theme = null;
                applyState(state);
                writeStored(state);
            }
        );
        document.body.appendChild(root);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
