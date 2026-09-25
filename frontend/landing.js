/**
 * Shared marketing-site behavior (loaded on index.html and pricing.html
 * alike):
 *  - Book a Demo form: posts to the backend and swaps in a confirmation
 *    state instead of navigating away. Only present on index.html --
 *    guarded so pages without it (pricing.html, which links back to
 *    index.html's form instead of duplicating it) don't throw on this
 *    line and silently skip the reveal-animation wiring below it as a
 *    result.
 *  - Pageview beacon: fire-and-forget first-party analytics (see
 *    backend/app/api.py's POST /analytics/pageview) -- one per page
 *    load, plus a synthetic one on a successful demo request so the
 *    owner console's funnel can show conversions, not just visits.
 *  - Scroll reveal: a subtle fade + rise for elements marked .reveal
 *    as they enter the viewport, restrained rather than bouncy, and
 *    skipped entirely for prefers-reduced-motion (handled in CSS).
 * API_BASE_URL comes from config.js, loaded before this script.
 */

// A per-tab id in sessionStorage, NOT a cookie -- gone when the tab
// closes, never sent anywhere except this one beacon, and not read by
// or shared with anything else on the page. Only exists so the owner
// console can count distinct visits/conversions instead of raw
// pageview volume; see database.get_pageview_summary's own docstring.
function _pageviewSessionId() {
    try {
        let id = sessionStorage.getItem('_pvsid');
        if (!id) {
            id = (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`);
            sessionStorage.setItem('_pvsid', id);
        }
        return id;
    } catch (e) {
        // Private browsing / storage disabled: still send a beacon, just
        // without session continuity across this page's other beacons.
        return null;
    }
}

function recordPageview(path) {
    try {
        fetch(`${API_BASE_URL}/analytics/pageview`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path, referrer: document.referrer || null, session_id: _pageviewSessionId() }),
        }).catch(() => {}); // analytics must never surface an error to a visitor
    } catch (e) { /* same -- never let telemetry break the page */ }
}

recordPageview(window.location.pathname);

const _EMAIL_SHAPE_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

const demoFormEl = document.getElementById('demoForm');
if (demoFormEl) {
    demoFormEl.addEventListener('submit', async (e) => {
        e.preventDefault();

        const errorEl = document.getElementById('demoFormError');
        const submitBtn = document.getElementById('demoSubmitBtn');

        const name = document.getElementById('demoName').value.trim();
        const workEmail = document.getElementById('demoWorkEmail').value.trim();
        const company = document.getElementById('demoCompany').value.trim();
        const unitsRaw = document.getElementById('demoUnits').value.trim();
        const message = document.getElementById('demoMessage').value.trim();
        // Honeypot -- left empty by a real visitor (it's hidden off-screen);
        // sent through as-is so the server applies the same spam check
        // regardless of what filled it in.
        const website = document.getElementById('demoWebsite').value.trim();

        errorEl.classList.remove('show');

        // Client-side validation mirrors the server's (backend/app/api.py's
        // POST /demo-request) so a real visitor sees a fast, specific error
        // without a round trip -- the server re-validates everything
        // regardless, since client-side checks are trivially bypassable.
        let clientError = null;
        if (!name) {
            clientError = 'Please enter your name';
        } else if (!workEmail || !_EMAIL_SHAPE_RE.test(workEmail)) {
            clientError = 'Please enter a valid work email address';
        } else if (!company) {
            clientError = 'Please enter your company name';
        } else {
            const units = parseInt(unitsRaw, 10);
            if (!unitsRaw || !Number.isInteger(units) || String(units) !== unitsRaw || units < 1 || units > 1000000) {
                clientError = 'Please enter a valid number of units';
            }
        }
        if (clientError) {
            errorEl.textContent = clientError;
            errorEl.classList.add('show');
            return;
        }

        submitBtn.disabled = true;
        submitBtn.textContent = 'Submitting...';

        try {
            let response;
            try {
                response = await fetch(`${API_BASE_URL}/demo-request`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        name,
                        work_email: workEmail,
                        company,
                        units: parseInt(unitsRaw, 10),
                        message: message || null,
                        website,
                    }),
                });
            } catch (networkErr) {
                // A raw fetch() failure (backend unreachable, network down)
                // throws a browser-internal string like "Failed to fetch" --
                // caught here and replaced before it can reach a prospective
                // client's screen on the single most important form on the
                // page.
                throw new Error("Couldn't reach the server. Check your connection and try again.");
            }
            const data = await response.json().catch(() => ({}));

            if (!response.ok) {
                throw new Error(data.error || 'Something went wrong. Please try again.');
            }

            document.getElementById('demoFormWrap').classList.add('submitted');
            document.getElementById('demoFormConfirm').classList.add('show');
            // Synthetic "path" -- a conversion marker, not a real page. Any
            // path starting with "/" is accepted by POST /analytics/pageview
            // (see backend/app/api.py), so this needs no backend change.
            recordPageview('/__event/demo_requested');
        } catch (err) {
            errorEl.textContent = err.message;
            errorEl.classList.add('show');
            submitBtn.disabled = false;
            submitBtn.textContent = 'Book a Demo';
        }
    });
}

if ('IntersectionObserver' in window) {
    const observer = new IntersectionObserver((entries) => {
        entries.forEach((entry) => {
            if (entry.isIntersecting) {
                entry.target.classList.add('in-view');
                observer.unobserve(entry.target);
            }
        });
    }, { threshold: 0.15, rootMargin: '0px 0px -60px 0px' });

    document.querySelectorAll('.reveal').forEach((el) => observer.observe(el));
} else {
    // No IntersectionObserver support: show everything immediately
    // rather than leaving it permanently hidden.
    document.querySelectorAll('.reveal').forEach((el) => el.classList.add('in-view'));
}
