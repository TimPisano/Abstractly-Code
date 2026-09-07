/**
 * Shared marketing-site behavior (loaded on index.html and pricing.html
 * alike):
 *  - Request-access form: posts to the backend and swaps in a
 *    confirmation state instead of navigating away. Only present on
 *    index.html (the hero) -- guarded so pages without it (pricing.html,
 *    which links back to the hero's form instead of duplicating it)
 *    don't throw on this line and silently skip the reveal-animation
 *    wiring below it as a result.
 *  - Pageview beacon: fire-and-forget first-party analytics (see
 *    backend/app/api.py's POST /analytics/pageview) -- one per page
 *    load, plus a synthetic one on a successful waitlist submission so
 *    the owner console's funnel can show conversions, not just visits.
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

const waitlistFormEl = document.getElementById('waitlistForm');
if (waitlistFormEl) {
    waitlistFormEl.addEventListener('submit', async (e) => {
        e.preventDefault();

        const emailInput = document.getElementById('waitlistEmail');
        const errorEl = document.getElementById('waitlistError');
        const submitBtn = document.getElementById('waitlistSubmitBtn');
        const email = emailInput.value.trim();

        errorEl.classList.remove('show');
        submitBtn.disabled = true;
        submitBtn.textContent = 'Submitting...';

        try {
            let response;
            try {
                response = await fetch(`${API_BASE_URL}/waitlist`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email }),
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

            document.getElementById('heroFormWrap').classList.add('submitted');
            document.getElementById('waitlistConfirm').classList.add('show');
            // Synthetic "path" -- a conversion marker, not a real page.
            // Must match backend/app/database.py's PAGEVIEW_CONVERSION_PATH.
            recordPageview('/__event/waitlist_submitted');
        } catch (err) {
            errorEl.textContent = err.message;
            errorEl.classList.add('show');
            submitBtn.disabled = false;
            submitBtn.textContent = 'Request Access';
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
