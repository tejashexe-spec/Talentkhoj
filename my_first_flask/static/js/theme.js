/* ═════════════════════════════════════════════════════════════════
   Talent Khoj — Theme controller
   • Toggles data-theme / data-bs-theme on <html>
   • Persists choice in localStorage
   • Safe inline-color mapper: rewrites a fixed allow-list of light
     hex tokens to dark equivalents ONLY while dark mode is active.
     Fully reversible — original inline styles are restored on light.
   Pure additive; never alters DOM structure. Loaded after DOM ready.
   ═════════════════════════════════════════════════════════════════ */
(function () {
    'use strict';

    var STORAGE_KEY = 'talentkhoj-theme';

    /* Map of light token -> dark token. Only these specific values are
       touched, so we never corrupt unrelated inline colors. */
    var TOKEN_MAP = {
        // backgrounds / surfaces
        '#ffffff': '#151c2c',
        '#fff': '#151c2c',
        '#f8fafc': '#1a2336',
        '#f1f5f9': '#222d44',
        '#f0f4ff': '#1c2740',
        '#f4f7ff': '#1c2740',
        '#eff6ff': '#1e2a4a',
        '#eef2ff': '#1e2a4a',
        '#e2e8f0': '#283449',
        // text greys
        '#0f172a': '#e6edf7',
        '#1e293b': '#d4ddea',
        '#334155': '#b8c4d6',
        '#475569': '#b8c4d6',
        '#64748b': '#94a3b8',
        '#94a3b8': '#6b7a91',
        // navy (footer/sidebar) — keep dark, just nudge
        '#05154b': '#080d18'
    };

    var MAPPED_ATTR = 'data-tk-orig';

    function getTheme() {
        try {
            return localStorage.getItem(STORAGE_KEY) || 'light';
        } catch (e) {
            return 'light';
        }
    }

    function setTheme(theme) {
        try {
            localStorage.setItem(STORAGE_KEY, theme);
        } catch (e) { /* ignore */ }
        applyTheme(theme);
    }

    function applyTheme(theme) {
        var root = document.documentElement;
        root.setAttribute('data-theme', theme);
        // Keep Bootstrap admin pages in sync (5.3 native dark mode)
        root.setAttribute('data-bs-theme', theme);
        mapInlineColors(theme === 'dark');
    }

    /* Walk every element with an inline style and remap known light
       tokens. Stores the original style string so we can restore it. */
    function mapInlineColors(toDark) {
        var nodes = document.querySelectorAll('[style]');
        for (var i = 0; i < nodes.length; i++) {
            var el = nodes[i];
            if (toDark) {
                if (!el.hasAttribute(MAPPED_ATTR)) {
                    el.setAttribute(MAPPED_ATTR, el.getAttribute('style') || '');
                }
                var original = el.getAttribute(MAPPED_ATTR);
                el.setAttribute('style', remap(original, true));
            } else {
                if (el.hasAttribute(MAPPED_ATTR)) {
                    el.setAttribute('style', el.getAttribute(MAPPED_ATTR));
                    el.removeAttribute(MAPPED_ATTR);
                }
            }
        }
    }

    function remap(styleStr, toDark) {
        if (!styleStr) return styleStr;
        return styleStr.replace(/#[0-9a-fA-F]{3,8}\b/g, function (match) {
            var key = match.toLowerCase();
            if (toDark && TOKEN_MAP.hasOwnProperty(key)) {
                return TOKEN_MAP[key];
            }
            return match;
        });
    }

    function toggle() {
        setTheme(getTheme() === 'dark' ? 'light' : 'dark');
    }

    // Wire up toggle buttons (any element with .theme-toggle)
    function bindToggles() {
        var btns = document.querySelectorAll('.theme-toggle');
        for (var i = 0; i < btns.length; i++) {
            btns[i].addEventListener('click', toggle);
        }
    }

    // Re-run inline mapping for any dynamically injected content
    // (e.g. AJAX-loaded dashboard panels, chat widgets).
    function observe() {
        if (typeof MutationObserver === 'undefined') return;
        var mo = new MutationObserver(function (mutations) {
            if (getTheme() !== 'dark') return;
            var needsMap = false;
            for (var i = 0; i < mutations.length; i++) {
                if (mutations[i].addedNodes.length) { needsMap = true; break; }
            }
            if (needsMap) mapInlineColors(true);
        });
        mo.observe(document.body, { childList: true, subtree: true });
    }

    document.addEventListener('DOMContentLoaded', function () {
        bindToggles();
        // Re-apply once on load so inline colors reflect stored theme
        applyTheme(getTheme());
        observe();
    });

    // Expose for debugging / programmatic use
    window.TKTheme = { get: getTheme, set: setTheme, toggle: toggle };
})();
