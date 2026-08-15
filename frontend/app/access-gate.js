/**
 * Access gate for /app.
 *
 * Two ways in:
 *  1. LOCAL_DEV_MODE=true in backend/.env (local testing only). Reported
 *     by the backend's /config endpoint -- it can only be set by whoever
 *     controls the server process, never by a request, so a client can't
 *     flip it on itself.
 *  2. A waitlist email with status 'approved', re-checked against the
 *     backend on every load (not just cached client-side), so a later
 *     revocation takes effect the next time this page loads.
 *
 * This is NOT real authentication -- there's no password and no proof
 * the visitor typing an email actually owns it, just a self-reported
 * match against the waitlist's approval status. See DECISIONS.md
 * "Access gate uses self-reported email, not real auth" for the full
 * reasoning and what real auth would need to add on top of this.
 *
 * Also responsible for loading the rest of the app's scripts, and only
 * after access is confirmed -- so no dashboard/API calls ever fire
 * before the gate passes.
 */
(function () {
    const API_BASE_URL = 'http://localhost:5000';
    const STORAGE_KEY = 'leaseAbstractionApprovedEmail';

    // Order matters: api.js and app.js must load before the view modules
    // that depend on their globals (Api, AppState, registerView, etc).
    const APP_SCRIPTS = [
        'api.js', 'app.js', 'upload-view.js', 'dashboard-view.js',
        'detail-view.js', 'timeline-view.js', 'comparison-view.js',
        'qa-view.js', 'report-view.js',
    ];

    const gateEl = document.getElementById('accessGate');
    const shellEl = document.getElementById('appShell');
    const formEl = document.getElementById('accessGateForm');
    const emailEl = document.getElementById('accessGateEmail');
    const submitBtn = document.getElementById('accessGateSubmitBtn');
    const messageEl = document.getElementById('accessGateMessage');

    function showMessage(text, isError) {
        messageEl.textContent = text || '';
        messageEl.classList.toggle('is-error', !!isError);
    }

    function showGate(prefillEmail, message, isError) {
        gateEl.style.display = '';
        shellEl.style.display = 'none';
        if (prefillEmail) emailEl.value = prefillEmail;
        if (message) showMessage(message, isError);
    }

    function grant() {
        gateEl.style.display = 'none';
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

    async function fetchConfig() {
        const response = await fetch(`${API_BASE_URL}/config`);
        if (!response.ok) throw new Error('config request failed');
        return response.json();
    }

    async function checkAccess(email) {
        const response = await fetch(`${API_BASE_URL}/waitlist/check`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email }),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.error || 'Something went wrong. Please try again.');
        return data; // { approved, found }
    }

    formEl.addEventListener('submit', async (e) => {
        e.preventDefault();
        const email = emailEl.value.trim();
        submitBtn.disabled = true;
        submitBtn.textContent = 'Checking...';
        showMessage('', false);

        try {
            const result = await checkAccess(email);
            if (result.approved) {
                try { localStorage.setItem(STORAGE_KEY, email); } catch (e2) { /* localStorage unavailable -- just won't persist across reloads */ }
                grant();
                return;
            }
            if (result.found) {
                showMessage("You're on the waitlist, but not approved yet. We'll be in touch once you are.", false);
            } else {
                showMessage("That email isn't on the waitlist yet.", true);
            }
        } catch (err) {
            showMessage(err.message || "Couldn't reach the server. Is the backend running?", true);
        } finally {
            submitBtn.disabled = false;
            submitBtn.textContent = 'Continue';
        }
    });

    (async function init() {
        let config;
        try {
            config = await fetchConfig();
        } catch (err) {
            // Fail closed: if we can't even reach the backend to ask
            // whether the local-dev bypass is on, don't guess -- show the
            // real gate with a clear explanation rather than silently
            // granting or silently blocking access either way.
            showGate(null, "Couldn't reach the server to verify access. Is the backend running?", true);
            return;
        }

        if (config.local_dev_mode) {
            grant();
            return;
        }

        let cachedEmail = null;
        try { cachedEmail = localStorage.getItem(STORAGE_KEY); } catch (e) { /* localStorage unavailable */ }

        if (!cachedEmail) {
            showGate(null, null, false);
            return;
        }

        try {
            const result = await checkAccess(cachedEmail);
            if (result.approved) {
                grant();
                return;
            }
            // Cached email is no longer approved (or the underlying
            // signup was removed) -- clear it so we don't keep re-trying
            // a stale value, and prefill the gate with it for convenience.
            try { localStorage.removeItem(STORAGE_KEY); } catch (e) { /* ignore */ }
            showGate(cachedEmail, result.found
                ? 'Your access is no longer approved. Enter your email to re-check.'
                : 'Enter your approved email to continue.', false);
        } catch (err) {
            showGate(cachedEmail, err.message || "Couldn't verify access. Is the backend running?", true);
        }
    })();
})();
