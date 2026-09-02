/**
 * Access check for /app: real per-user login only (see
 * backend/app/auth.py). Checks GET /auth/session on load; an
 * authenticated session loads the rest of the app, anything else (not
 * logged in, or the backend unreachable) redirects to the real login
 * page. Also responsible for loading the rest of the app's scripts,
 * and only after access is confirmed -- so no dashboard/API calls ever
 * fire before it passes. There is no gate UI of its own to show or
 * hide here -- #appBootLoading (index.html) covers the brief window
 * while the session check is in flight.
 *
 * This file used to also implement an older, pre-real-auth access
 * model (a self-reported-email waitlist flow with its own sign-in/
 * request-access/pending-approval panels, no password, no proof of
 * identity) that a real per-user `users` table replaced entirely --
 * see DECISIONS.md's "Reliability hardening pass"/team-collaboration
 * entries. That flow was retired but its ~250 lines of dead code and
 * matching unreachable HTML in index.html were deliberately left in
 * place at the time (to avoid churn on a file also under active
 * feature work) rather than removed. Removed now, during a dedicated
 * consistency/cleanup pass, once that reason no longer applied.
 */
(function () {
    // API_BASE_URL comes from ../config.js, loaded before this script.

    // Order matters: api.js and app.js must load before the view modules
    // that depend on their globals (Api, AppState, registerView, etc).
    const APP_SCRIPTS = [
        // verify-popover.js and discrepancy-modal.js are shared utility
        // globals (VerifyPopover, DiscrepancyModal, verifyTriggerHtml,
        // etc.) used by several of the view modules below -- loaded
        // right after app.js, before any view that calls into them.
        'api.js', 'app.js', 'verify-popover.js', 'comments.js', 'discrepancy-modal.js', 'export-modal.js',
        'upload-view.js', 'dashboard-view.js', 'alerts-view.js', 'discrepancies-view.js', 'team-notes-view.js',
        'detail-view.js', 'timeline-view.js', 'rentroll-view.js', 'comparison-view.js',
        'qa-view.js', 'report-view.js', 'trends-view.js', 'team-view.js', 'tasks-view.js', 'messaging.js',
        'task-detail-modal.js',
    ];

    const bootLoadingEl = document.getElementById('appBootLoading');
    const shellEl = document.getElementById('appShell');

    function hideBootLoading() {
        bootLoadingEl.style.display = 'none';
    }

    function grant(session) {
        // Stashed globally (not fetched again per-module) so tasks-view.js,
        // messaging.js, and the Today dashboard rebuild can all know "who
        // am I" without a duplicate /auth/session round trip -- set before
        // loadAppScripts() so every dynamically-loaded module sees it
        // already populated by the time its own load()/init runs.
        window.CURRENT_USER = session;
        hideBootLoading();
        shellEl.style.display = '';
        loadAppScripts();
    }

    function loadAppScripts() {
        // Dynamically-created classic <script src> elements run async by
        // default; async = false preserves the listed load/execution
        // order without blocking anything -- there's nothing left to
        // parse at this point, we're well past DOMContentLoaded already.
        const scripts = APP_SCRIPTS.map((src) => {
            const script = document.createElement('script');
            script.src = src;
            script.async = false;
            return script;
        });

        // app.js's init() must not run until every one of these has
        // loaded AND executed -- it calls showView('dashboard'), which
        // depends on dashboard-view.js (later in this list) having
        // already registered itself via registerView(). Calling it any
        // earlier silently no-ops that lookup instead of erroring, which
        // is exactly what caused the LOCAL_DEV_MODE dashboard to render
        // permanently blank (see the comment above window.init = init
        // in app.js for the full explanation). The 'load' event on the
        // LAST script only fires after it has executed, and async=false
        // guarantees every earlier script already executed by then too
        // -- so this is the correct, not approximate, signal to use.
        scripts[scripts.length - 1].addEventListener('load', () => {
            if (typeof window.init === 'function') {
                window.init();
            } else {
                // Would mean app.js itself failed to load/execute --
                // nothing left to do but make the failure visible rather
                // than leaving a silently blank page.
                console.error('access-gate.js: app.js did not define window.init -- app cannot start.');
            }
        });

        scripts.forEach((script) => document.body.appendChild(script));
    }

    // access-gate.js runs before api.js even loads (it's the thing that
    // decides whether api.js gets loaded at all), so it can't share
    // apiRequest()'s network-failure handling and needs its own copy of
    // the same fix: a raw fetch() failure (backend unreachable, DNS/
    // network down) throws a browser-internal string like "Failed to
    // fetch" that would otherwise end up on screen verbatim. Translated
    // here, once, into one consistent human-readable message, rather
    // than trusting every call site's own `err.message || "fallback"`
    // -- which doesn't work anyway, since a truthy raw message always
    // wins over the fallback.
    async function fetchJson(url, options) {
        let response;
        try {
            response = await fetch(url, options);
        } catch (networkErr) {
            throw new Error("Couldn't reach the server. Check your connection and try again.");
        }
        const data = await response.json().catch(() => ({}));
        return { response, data };
    }

    (async function init() {
        let session = { authenticated: false };
        try {
            const { data } = await fetchJson(`${API_BASE_URL}/auth/session`, { credentials: 'include' });
            session = data;
        } catch (err) {
            // Can't reach the backend at all -- fail closed to the login
            // page, same as any other "not authenticated" outcome.
        }
        if (session.authenticated) {
            grant(session);
            return;
        }
        window.location.href = 'login.html';
    })();
})();
