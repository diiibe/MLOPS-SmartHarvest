/*
 * Dashboard Settings — palette / background depth / shadow strength.
 *
 * Reads the user's preferences from `localStorage` on load, applies
 * them to `<html>` as `data-palette`, `data-bg-depth`, `data-shadows`
 * attributes (consumed by `tokens.css` overrides), and wires the
 * Settings card buttons so future clicks persist + apply
 * immediately.
 */
(function () {
    "use strict";

    var STORAGE_KEY = "smartharvest_design_prefs_v1";
    var DEFAULTS = {
        palette: "vino",
        "bg-depth": "standard",
        shadows: "standard"
    };
    var ATTR_MAP = {
        palette: "data-palette",
        "bg-depth": "data-bg-depth",
        shadows: "data-shadows"
    };

    function load() {
        try {
            var raw = window.localStorage.getItem(STORAGE_KEY);
            if (!raw) return Object.assign({}, DEFAULTS);
            var parsed = JSON.parse(raw);
            return Object.assign({}, DEFAULTS, parsed);
        } catch (e) {
            return Object.assign({}, DEFAULTS);
        }
    }

    function save(prefs) {
        try {
            window.localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
        } catch (e) {
            // Quota / disabled storage — silent fail; the in-memory
            // state still drives the current session.
        }
    }

    function apply(prefs) {
        var html = document.documentElement;
        Object.keys(ATTR_MAP).forEach(function (key) {
            var attr = ATTR_MAP[key];
            html.setAttribute(attr, prefs[key] || DEFAULTS[key]);
        });
    }

    function syncActiveStates(prefs) {
        document.querySelectorAll(".settings-card .settings-group").forEach(function (group) {
            var key = group.getAttribute("data-setting");
            if (!key) return;
            var active = prefs[key] || DEFAULTS[key];
            group.querySelectorAll("[data-value]").forEach(function (btn) {
                btn.dataset.active = btn.dataset.value === active ? "true" : "false";
            });
        });
    }

    function wire() {
        var card = document.querySelector(".settings-card[data-component=\"settings\"]");
        if (!card) return;
        var prefs = load();
        apply(prefs);
        syncActiveStates(prefs);

        card.addEventListener("click", function (e) {
            var btn = e.target.closest("[data-value], [data-action]");
            if (!btn || !card.contains(btn)) return;

            if (btn.dataset.action === "reset") {
                prefs = Object.assign({}, DEFAULTS);
                save(prefs);
                apply(prefs);
                syncActiveStates(prefs);
                return;
            }

            var group = btn.closest(".settings-group");
            if (!group) return;
            var key = group.getAttribute("data-setting");
            if (!key) return;
            var value = btn.dataset.value;
            if (!value || prefs[key] === value) return;

            prefs[key] = value;
            save(prefs);
            apply(prefs);
            syncActiveStates(prefs);
        });
    }

    // Apply preferences before paint to avoid a flash of the default
    // theme. The `wire()` step (which depends on the sidebar markup)
    // happens after DOMContentLoaded.
    apply(load());
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", wire);
    } else {
        wire();
    }
})();
