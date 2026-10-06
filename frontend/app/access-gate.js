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
        'upload-view.js', 'dashboard-view.js', 'actionitems-view.js', 'alerts-view.js', 'discrepancies-view.js', 'deal-mismatch-view.js', 'team-notes-view.js',
        'detail-view.js', 'timeline-view.js', 'rentroll-view.js', 'comparison-view.js',
        'qa-view.js', 'report-view.js', 'trends-view.js', 'team-view.js', 'tasks-view.js', 'messaging.js',
        'task-detail-modal.js',
    ];

    const bootLoadingEl = document.getElementById('appBootLoading');
    const bootLoadingHintEl = document.getElementById('appBootLoadingHint');
    const shellEl = document.getElementById('appShell');

    // Render's free tier spins the backend down after 15 min idle, and
    // the first request after that takes 30-60s to wake it back up
    // (DEPLOYMENT.md's "Free-tier behavior you should know about").
    // Without this, that wait is indistinguishable from a hung page --
    // this only fires if the /auth/session check below is still
    // pending past the point a warm backend would have already
    // responded, so a normal warm load never shows it.
    const BOOT_COLD_START_HINT_DELAY_MS = 5000;
    const bootColdStartHintTimer = setTimeout(() => {
        bootLoadingHintEl.textContent = 'Still waking up the server after inactivity — this can take up to a minute.';
    }, BOOT_COLD_START_HINT_DELAY_MS);

    function hideBootLoading() {
        bootLoadingEl.style.display = 'none';
    }

    // Sign out: ends the cookie session server-side and forgets the
    // token in BOTH storages ("Keep me signed in" keeps it in
    // localStorage, which would otherwise survive this). Other open tabs
    // using that same localStorage token get bounced to the login page
    // on their next request.
    const signOutBtn = document.getElementById('signOutBtn');
    if (signOutBtn) {
        signOutBtn.addEventListener('click', async () => {
            signOutBtn.disabled = true;
            try {
                await fetch(`${API_BASE_URL}/auth/logout`, { method: 'POST', credentials: 'include' });
            } catch (e) { /* offline: still forget the token locally */ }
            forgetTokenHere();
            if (tabChannel) tabChannel.postMessage({ type: 'signed-out' });
            window.location.replace('login.html?signedout=1');
        });
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

    // Shown if any of APP_SCRIPTS fails to load (a flaky connection mid
    // page-load, a bad deploy, a static-host hiccup) -- without this, a
    // missing script silently leaves the shell partially wired (already
    // visible, since grant() reveals it before this function even runs)
    // with no visible sign anything's wrong, same failure shape as the
    // "dashboard renders permanently blank" case the comment below
    // documents, just triggered by the network instead of call ordering.
    function showScriptLoadError(failedSrc) {
        bootLoadingEl.innerHTML = `
            <div class="upload-result-warning" style="margin: 2rem auto; max-width: 32rem;">
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z"/></svg>
                <span>Part of the app failed to load. Check your connection and reload the page. If this keeps happening, contact support.</span>
            </div>
        `;
        bootLoadingEl.style.display = '';
        shellEl.style.display = 'none';
        console.error(`access-gate.js: failed to load ${failedSrc} -- app cannot start.`);
    }

    function loadAppScripts() {
        let failed = false;

        // Dynamically-created classic <script src> elements run async by
        // default; async = false preserves the listed load/execution
        // order without blocking anything -- there's nothing left to
        // parse at this point, we're well past DOMContentLoaded already.
        const scripts = APP_SCRIPTS.map((src) => {
            const script = document.createElement('script');
            script.src = src;
            script.async = false;
            script.addEventListener('error', () => {
                failed = true;
                showScriptLoadError(src);
            });
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
            // An earlier script's own 'error' listener already showed
            // the failure banner -- don't also run init() against a
            // shell that's missing pieces it depends on.
            if (failed) return;
            if (typeof window.init === 'function') {
                window.init();
            } else {
                // Would mean app.js itself failed to load/execute --
                // nothing left to do but make the failure visible rather
                // than leaving a silently blank page.
                showScriptLoadError('app.js (loaded, but did not define window.init)');
            }
        });

        scripts.forEach((script) => document.body.appendChild(script));
    }

    // ---- Sharing a login between tabs --------------------------------
    // Without "Keep me signed in" the token lives in THIS tab's
    // sessionStorage, which a new tab doesn't get -- so opening the app
    // in a second tab (or a link in a new tab) bounced to the login page.
    // (The session-cookie fallback can't cover it: the API is on another
    // site, and Safari and Chrome block that cookie.) So a tab with no
    // token asks the others, over a same-origin BroadcastChannel, and
    // any signed-in tab answers with its token. It never leaves this
    // origin -- the same scripts that could read it from sessionStorage
    // are the only ones that can hear it. Sign-out is broadcast the same
    // way, so it ends the login in every tab, not just this one.
    const TAB_CHANNEL = 'abstractly-auth';
    const tabChannel = ('BroadcastChannel' in window) ? new BroadcastChannel(TAB_CHANNEL) : null;

    function storedToken() {
        try {
            return sessionStorage.getItem('authToken') || localStorage.getItem('authToken');
        } catch (e) {
            return null;
        }
    }

    function forgetTokenHere() {
        try {
            sessionStorage.removeItem('authToken');
            localStorage.removeItem('authToken');
        } catch (e) { /* storage blocked */ }
    }

    if (tabChannel) {
        tabChannel.addEventListener('message', (event) => {
            const msg = event.data || {};
            if (msg.type === 'token-request') {
                let mine = null;
                try { mine = sessionStorage.getItem('authToken'); } catch (e) { /* blocked */ }
                if (mine && window.CURRENT_USER) tabChannel.postMessage({ type: 'token', id: msg.id, token: mine });
            } else if (msg.type === 'signed-out') {
                forgetTokenHere();
                window.location.replace('login.html?signedout=1');
            }
        });
    }

    function askOtherTabsForToken(waitMs) {
        if (!tabChannel) return Promise.resolve(null);
        return new Promise((resolve) => {
            const id = Math.random().toString(36).slice(2);
            const onMessage = (event) => {
                const msg = event.data || {};
                if (msg.type === 'token' && msg.id === id && msg.token) {
                    tabChannel.removeEventListener('message', onMessage);
                    clearTimeout(timer);
                    resolve(msg.token);
                }
            };
            const timer = setTimeout(() => {
                tabChannel.removeEventListener('message', onMessage);
                resolve(null);
            }, waitMs);
            tabChannel.addEventListener('message', onMessage);
            tabChannel.postMessage({ type: 'token-request', id });
        });
    }

    // Two people, one browser: with "Keep me signed in" the token lives in
    // localStorage, which every tab shares. If someone signs in as a
    // DIFFERENT user in another tab, this tab's next request silently runs
    // as them while the screen still shows the first person's name and
    // data. So when the shared token changes, re-check who it belongs to:
    // a different person (or no one) -> reload into the honest state. Tabs
    // holding their own sessionStorage token are unaffected -- api.js
    // prefers it.
    // (A change during the second or so before this tab finishes booting
    // is not caught -- CURRENT_USER isn't set yet. Accepted: the boot
    // itself just read the token, so the window is tiny.)
    window.addEventListener('storage', async (event) => {
        if (event.key !== 'authToken' || event.storageArea !== localStorage) return;
        let ownToken = null;
        try { ownToken = sessionStorage.getItem('authToken'); } catch (e) { /* blocked */ }
        if (ownToken || !window.CURRENT_USER) return;
        if (!event.newValue) {
            // Give a sign-in that's mid-write a moment, then trust what's
            // actually stored.
            await new Promise((resolve) => setTimeout(resolve, 300));
            let now = null;
            try { now = localStorage.getItem('authToken'); } catch (e) { /* blocked */ }
            if (!now) {
                window.location.replace('login.html?signedout=1');
                return;
            }
            event = { newValue: now };
        }
        try {
            const { data } = await fetchJson(`${API_BASE_URL}/auth/session`, {
                credentials: 'include', headers: { 'Authorization': `Bearer ${event.newValue}` },
            });
            if (data.authenticated && data.id === window.CURRENT_USER.id) return;
        } catch (e) { /* unreachable: reload and let the gate decide */ }
        window.location.reload();
    });

    // Back button after signing out (or after this login expired / was
    // revoked elsewhere): browsers restore the whole page from the
    // back/forward cache WITHOUT re-running this file, which would put
    // the last person's dashboard back on screen on a shared computer.
    // So a restored page hides itself and re-checks the session first.
    window.addEventListener('pageshow', async (event) => {
        if (!event.persisted) return;
        shellEl.style.display = 'none';
        const token = storedToken();
        if (!token) {
            window.location.replace('login.html');
            return;
        }
        try {
            const { data } = await fetchJson(`${API_BASE_URL}/auth/session`, {
                credentials: 'include', headers: { 'Authorization': `Bearer ${token}` },
            });
            if (data.authenticated) {
                shellEl.style.display = '';
                return;
            }
        } catch (e) { /* unreachable: fail closed */ }
        forgetTokenHere();
        window.location.replace('login.html?expired=1');
    });

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
        let session = { authenticated: null };
        let token = null;
        try {
            token = storedToken();
            if (!token) {
                token = await askOtherTabsForToken(400);
                if (token) {
                    try { sessionStorage.setItem('authToken', token); } catch (e) { /* blocked */ }
                }
            }
            const headers = token ? { 'Authorization': `Bearer ${token}` } : {};
            const { data } = await fetchJson(`${API_BASE_URL}/auth/session`, { credentials: 'include', headers });
            session = data;
        } catch (err) {
            // Can't reach the backend at all -- fail closed to the login
            // page, same as any other "not authenticated" outcome.
        }
        clearTimeout(bootColdStartHintTimer);
        if (session.authenticated) {
            grant(session);
            return;
        }
        // A stored token the server no longer accepts (it expired, or a
        // password reset signed this device out) -- drop it and say why,
        // rather than a bare login form with no explanation.
        if (token && session.authenticated === false) {
            forgetTokenHere();
            window.location.replace('login.html?expired=1');
            return;
        }
        window.location.replace('login.html');
    })();
})();
