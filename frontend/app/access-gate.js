/**
 * Access gate for /app.
 *
 * Three ways in:
 *  1. LOCAL_DEV_MODE=true in backend/.env (local testing only). Reported
 *     by the backend's /config endpoint -- it can only be set by whoever
 *     controls the server process, never by a request, so a client can't
 *     flip it on itself.
 *  2. A waitlist email with status 'approved', re-checked against the
 *     backend on every load (not just cached client-side), so a later
 *     revocation takes effect the next time this page loads.
 *  3. A brand-new request, submitted right here (not just from the
 *     marketing landing page), which lands the visitor on a dedicated
 *     "pending approval" screen -- not just an inline message next to
 *     the sign-in form -- until an admin approves it.
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
    // API_BASE_URL comes from ../config.js, loaded before this script.
    const STORAGE_KEY = 'leaseAbstractionApprovedEmail';

    // Order matters: api.js and app.js must load before the view modules
    // that depend on their globals (Api, AppState, registerView, etc).
    const APP_SCRIPTS = [
        // verify-popover.js and discrepancy-modal.js are shared utility
        // globals (VerifyPopover, DiscrepancyModal, verifyTriggerHtml,
        // etc.) used by several of the view modules below -- loaded
        // right after app.js, before any view that calls into them.
        'api.js', 'app.js', 'verify-popover.js', 'comments.js', 'discrepancy-modal.js', 'export-modal.js',
        'upload-view.js', 'dashboard-view.js', 'alerts-view.js',
        'detail-view.js', 'timeline-view.js', 'rentroll-view.js', 'comparison-view.js',
        'qa-view.js', 'report-view.js', 'trends-view.js',
    ];

    const bootLoadingEl = document.getElementById('appBootLoading');
    const gateEl = document.getElementById('accessGate');
    const shellEl = document.getElementById('appShell');

    // Called from every place that decides what to show first (the
    // gate, in any of its 3 panels, or the app itself) -- idempotent,
    // safe to call more than once (e.g. every time the pending screen's
    // "Check again" re-decides what to show).
    function hideBootLoading() {
        bootLoadingEl.style.display = 'none';
    }

    const panels = {
        signIn: document.getElementById('accessGateSignInPanel'),
        request: document.getElementById('accessGateRequestPanel'),
        pending: document.getElementById('accessGatePendingPanel'),
    };

    const formEl = document.getElementById('accessGateForm');
    const emailEl = document.getElementById('accessGateEmail');
    const submitBtn = document.getElementById('accessGateSubmitBtn');
    const messageEl = document.getElementById('accessGateMessage');
    const showRequestBtn = document.getElementById('accessGateShowRequestBtn');

    const requestFormEl = document.getElementById('accessGateRequestForm');
    const requestEmailEl = document.getElementById('accessGateRequestEmail');
    const requestSubmitBtn = document.getElementById('accessGateRequestSubmitBtn');
    const requestMessageEl = document.getElementById('accessGateRequestMessage');
    const backToSignInBtn = document.getElementById('accessGateBackToSignInBtn');

    const pendingEmailEl = document.getElementById('accessGatePendingEmail');
    const recheckBtn = document.getElementById('accessGateRecheckBtn');
    const pendingBackBtn = document.getElementById('accessGatePendingBackBtn');

    let pendingEmail = null;

    function showPanel(name) {
        Object.entries(panels).forEach(([key, el]) => {
            el.style.display = key === name ? '' : 'none';
        });
    }

    function showSignIn(prefillEmail, message, isError) {
        hideBootLoading();
        gateEl.style.display = '';
        shellEl.style.display = 'none';
        showPanel('signIn');
        if (prefillEmail) emailEl.value = prefillEmail;
        messageEl.textContent = message || '';
        messageEl.classList.toggle('is-error', !!isError);
    }

    function showRequestAccess(prefillEmail) {
        hideBootLoading();
        gateEl.style.display = '';
        shellEl.style.display = 'none';
        showPanel('request');
        requestEmailEl.value = prefillEmail || emailEl.value || '';
        requestMessageEl.textContent = '';
        requestMessageEl.classList.remove('is-error');
    }

    function showPending(email) {
        hideBootLoading();
        gateEl.style.display = '';
        shellEl.style.display = 'none';
        pendingEmail = email;
        pendingEmailEl.textContent = email;
        showPanel('pending');
    }

    function grant() {
        hideBootLoading();
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

    async function fetchConfig() {
        const { response, data } = await fetchJson(`${API_BASE_URL}/config`);
        if (!response.ok) throw new Error('config request failed');
        return data;
    }

    async function checkAccess(email) {
        const { response, data } = await fetchJson(`${API_BASE_URL}/waitlist/check`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email }),
        });
        if (!response.ok) throw new Error(data.error || 'Something went wrong. Please try again.');
        return data; // { approved, found }
    }

    async function submitAccessRequest(email) {
        const { response, data } = await fetchJson(`${API_BASE_URL}/waitlist`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email }),
        });
        if (!response.ok) throw new Error(data.error || 'Something went wrong. Please try again.');
        return data;
    }

    function cacheEmail(email) {
        try { localStorage.setItem(STORAGE_KEY, email); } catch (e) { /* localStorage unavailable -- just won't persist across reloads */ }
    }

    function clearCachedEmail() {
        try { localStorage.removeItem(STORAGE_KEY); } catch (e) { /* ignore */ }
    }

    // ---- Panel 1: sign in with an already-approved email ----

    formEl.addEventListener('submit', async (e) => {
        e.preventDefault();
        const email = emailEl.value.trim();
        submitBtn.disabled = true;
        submitBtn.textContent = 'Checking...';
        messageEl.textContent = '';
        messageEl.classList.remove('is-error');

        try {
            const result = await checkAccess(email);
            if (result.approved) {
                cacheEmail(email);
                grant();
                return;
            }
            if (result.found) {
                cacheEmail(email);
                showPending(email);
            } else {
                showSignIn(email, "That email isn't on the list yet. You can request access below.", true);
            }
        } catch (err) {
            showSignIn(email, err.message || "Couldn't reach the server. Is the backend running?", true);
        } finally {
            submitBtn.disabled = false;
            submitBtn.textContent = 'Continue';
        }
    });

    showRequestBtn.addEventListener('click', () => showRequestAccess());

    // ---- Panel 2: request access (new signup, right here -- not only
    // reachable by navigating away to the marketing landing page) ----

    requestFormEl.addEventListener('submit', async (e) => {
        e.preventDefault();
        const email = requestEmailEl.value.trim();
        requestSubmitBtn.disabled = true;
        requestSubmitBtn.textContent = 'Submitting...';
        requestMessageEl.textContent = '';
        requestMessageEl.classList.remove('is-error');

        try {
            await submitAccessRequest(email);
            cacheEmail(email);
            showPending(email);
        } catch (err) {
            requestMessageEl.textContent = err.message || "Couldn't reach the server. Is the backend running?";
            requestMessageEl.classList.add('is-error');
        } finally {
            requestSubmitBtn.disabled = false;
            requestSubmitBtn.textContent = 'Request Access';
        }
    });

    backToSignInBtn.addEventListener('click', () => showSignIn(requestEmailEl.value));

    // ---- Panel 3: pending approval ----

    recheckBtn.addEventListener('click', async () => {
        if (!pendingEmail) return;
        recheckBtn.disabled = true;
        recheckBtn.textContent = 'Checking...';

        try {
            const result = await checkAccess(pendingEmail);
            if (result.approved) {
                cacheEmail(pendingEmail);
                grant();
                return;
            }
            if (!result.found) {
                // The underlying signup was removed since we last checked.
                clearCachedEmail();
                showSignIn(pendingEmail, 'That request is no longer on file. Enter your email to try again.', true);
            }
            // Still pending -- stay on this screen, nothing else to show;
            // the button resetting below is enough feedback that the
            // check ran and nothing has changed yet.
        } catch (err) {
            // Network hiccup checking again isn't worth leaving the
            // pending screen over -- just let the visitor retry.
        } finally {
            recheckBtn.disabled = false;
            recheckBtn.textContent = 'Check again';
        }
    });

    pendingBackBtn.addEventListener('click', () => {
        clearCachedEmail();
        showSignIn(pendingEmail);
    });

    // ---- Initial load ----

    (async function init() {
        let config;
        try {
            config = await fetchConfig();
        } catch (err) {
            // Fail closed: if we can't even reach the backend to ask
            // whether the local-dev bypass is on, don't guess -- show the
            // real gate with a clear explanation rather than silently
            // granting or silently blocking access either way.
            showSignIn(null, "Couldn't reach the server to verify access. Is the backend running?", true);
            return;
        }

        if (config.local_dev_mode) {
            grant();
            return;
        }

        let cachedEmail = null;
        try { cachedEmail = localStorage.getItem(STORAGE_KEY); } catch (e) { /* localStorage unavailable */ }

        if (!cachedEmail) {
            showSignIn();
            return;
        }

        try {
            const result = await checkAccess(cachedEmail);
            if (result.approved) {
                grant();
                return;
            }
            if (result.found) {
                // Still pending from a previous visit -- go straight to
                // the pending screen rather than making them re-submit
                // the sign-in form just to be told the same thing again.
                showPending(cachedEmail);
                return;
            }
            // Cached email is no longer on the list at all (removed) --
            // clear it so we don't keep re-trying a stale value.
            clearCachedEmail();
            showSignIn(cachedEmail, 'Enter your approved email to continue.', false);
        } catch (err) {
            showSignIn(cachedEmail, err.message || "Couldn't verify access. Is the backend running?", true);
        }
    })();
})();
