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

/**
 * ===================== Hero: cursor-reactive light bands =====================
 * index.html only (#hero / #heroCanvas aren't present on pricing.html).
 * A handful of soft vertical bands in the brand accent color, drawn on
 * a canvas layered behind the hero copy, that brighten and widen near
 * the mouse and ease toward it rather than snapping -- "light through
 * blinds." landing.css already renders a static CSS-gradient version of
 * the same pattern (.hero-bands) unconditionally as a progressive-
 * enhancement fallback; this block only takes over from it when the
 * visitor can actually benefit from the motion:
 *  - never under prefers-reduced-motion
 *  - never on a touch/coarse-pointer device (nothing to react to, and
 *    it's the brief's own instruction to keep those static)
 * When it does run: paused via IntersectionObserver whenever the hero
 * scrolls off-screen, and via the page Visibility API whenever the tab
 * is hidden, so it only ever costs a frame budget while actually
 * visible to someone who can see the motion.
 */
(function () {
    const hero = document.getElementById('hero');
    const canvas = document.getElementById('heroCanvas');
    if (!hero || !canvas) return;

    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const hasFinePointer = window.matchMedia('(hover: hover) and (pointer: fine)').matches;
    if (prefersReducedMotion || !hasFinePointer) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Must match --lux-accent-rgb in landing.css (both derive from
    // design-system.css's --lux-accent, #b68a4e) -- there's no way to
    // read a CSS custom property into a canvas rgba() string without an
    // extra getComputedStyle round trip, so this is kept as a plain
    // constant and the two are kept in sync by hand.
    const ACCENT_RGB = '182, 138, 78';

    let width = 0;
    let height = 0;
    let targetX = 0;
    let easedX = 0;
    let heroVisible = true;
    let rafId = null;

    function resize() {
        const rect = hero.getBoundingClientRect();
        // Capped at 1: these are large, soft, blurry-by-design gradient
        // bands, not text or a hard edge -- retina sharpness buys
        // nothing visible here, and a canvas this size at a real
        // device's DPR (2-3x) is real per-frame fill-rate cost for zero
        // perceptible benefit.
        const dpr = 1;
        width = rect.width;
        height = rect.height;
        canvas.width = width * dpr;
        canvas.height = height * dpr;
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }

    resize();
    // Resting position roughly behind the report card (right side of the
    // hero) rather than dead center, so the very first frame -- before
    // any mousemove -- already looks intentional.
    targetX = width * 0.72;
    easedX = targetX;

    let resizeTimer = null;
    window.addEventListener('resize', () => {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(resize, 150);
    });

    hero.addEventListener('mousemove', (e) => {
        const rect = hero.getBoundingClientRect();
        targetX = e.clientX - rect.left;
    });

    hero.addEventListener('mouseleave', () => {
        targetX = width * 0.72;
    });

    // Capped independent of viewport width -- a 3440px ultrawide has no
    // business drawing more gradient fills per frame than a 1440px
    // laptop, and the pattern still reads fine slightly denser/sparser.
    const BAND_COUNT = 12;

    function draw() {
        ctx.clearRect(0, 0, width, height);

        const spacing = width / BAND_COUNT;

        for (let i = 0; i < BAND_COUNT; i++) {
            const bandX = spacing * (i + 0.5);
            const dist = Math.abs(bandX - easedX);
            // Gaussian falloff: bands within ~150px of the cursor
            // brighten noticeably, further ones stay near the resting
            // baseline -- keeps peak brightness capped (subtle, not
            // flashy) regardless of how close the cursor gets.
            const falloff = Math.exp(-(dist * dist) / (2 * 150 * 150));
            const alphaPeak = 0.045 + falloff * 0.16;
            const bandWidth = 2.5 + falloff * 5;

            const gradient = ctx.createLinearGradient(bandX, 0, bandX, height);
            gradient.addColorStop(0, `rgba(${ACCENT_RGB}, 0)`);
            gradient.addColorStop(0.18, `rgba(${ACCENT_RGB}, ${alphaPeak})`);
            gradient.addColorStop(0.55, `rgba(${ACCENT_RGB}, ${alphaPeak * 0.45})`);
            gradient.addColorStop(1, `rgba(${ACCENT_RGB}, 0)`);

            ctx.fillStyle = gradient;
            ctx.fillRect(bandX - bandWidth / 2, 0, bandWidth, height);
        }
    }

    // Throttled to ~24fps -- this is a slow ease toward a slow-moving
    // target (the cursor), not fast-motion content, so a lower frame
    // rate is imperceptible here while meaningfully cutting main-thread
    // work on every device, not just this one being profiled on.
    const FRAME_INTERVAL_MS = 1000 / 24;
    let lastFrameTime = 0;

    function loop(now) {
        if (!heroVisible || document.hidden) {
            rafId = null; // dropped here, not just skipped -- startLoop() below checks for exactly this
            return;
        }
        if (now - lastFrameTime >= FRAME_INTERVAL_MS) {
            lastFrameTime = now;
            easedX += (targetX - easedX) * 0.08; // ease toward the pointer, never snap
            draw();
        }
        rafId = requestAnimationFrame(loop);
    }

    function startLoop() {
        if (rafId === null) {
            rafId = requestAnimationFrame(loop);
        }
    }

    if ('IntersectionObserver' in window) {
        const heroObserver = new IntersectionObserver((entries) => {
            entries.forEach((entry) => {
                heroVisible = entry.isIntersecting;
                if (heroVisible) startLoop();
            });
        }, { threshold: 0 });
        heroObserver.observe(hero);
    }

    document.addEventListener('visibilitychange', () => {
        if (!document.hidden) startLoop();
    });

    // Only now -- everything above succeeded -- do we actually swap the
    // static CSS fallback out for the canvas (see .js-canvas-active in
    // landing.css). Any early return above leaves that class off, so a
    // visitor always gets a correct-looking hero either way.
    hero.classList.add('js-canvas-active');
    startLoop();
})();

/**
 * ===================== Hero: Deal Mismatch Report count-up =====================
 * #dealCardNumber carries the true final value in data-target (plain
 * dollars, no formatting) so the DOM always has the real number even if
 * this script never runs. Counts up once, the first time the card
 * scrolls into view; shows the final value immediately (no animation)
 * under prefers-reduced-motion.
 */
(function () {
    const numberEl = document.getElementById('dealCardNumber');
    if (!numberEl) return;

    const target = parseInt(numberEl.getAttribute('data-target'), 10);
    if (!Number.isFinite(target)) return;

    const formatDollars = (n) => `$${Math.round(n).toLocaleString('en-US')}`;

    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
        numberEl.textContent = formatDollars(target);
        return;
    }

    function animateCount() {
        const duration = 1400;
        const start = performance.now();

        function tick(now) {
            const progress = Math.min((now - start) / duration, 1);
            const eased = 1 - Math.pow(1 - progress, 3); // ease-out cubic
            numberEl.textContent = formatDollars(target * eased);
            if (progress < 1) requestAnimationFrame(tick);
        }
        requestAnimationFrame(tick);
    }

    if ('IntersectionObserver' in window) {
        const observer = new IntersectionObserver((entries) => {
            entries.forEach((entry) => {
                if (entry.isIntersecting) {
                    animateCount();
                    observer.unobserve(entry.target);
                }
            });
        }, { threshold: 0.4 });
        observer.observe(numberEl);
    } else {
        animateCount();
    }
})();

/**
 * ===================== Pricing preview (index.html only) =====================
 * Reuses PRICING_CONFIG (pricing-config.js, loaded before this file on
 * index.html the same way it already is on pricing.html) so the teaser
 * on the landing page can never drift out of sync with the real numbers
 * on /pricing -- one source of truth, no duplicated figures to maintain.
 */
(function () {
    const grid = document.getElementById('pricingPreviewGrid');
    if (!grid || typeof PRICING_CONFIG === 'undefined') return;

    grid.innerHTML = PRICING_CONFIG.tiers.map((tier) => {
        const featuredClass = tier.featured ? ' pricing-preview-card-featured' : '';
        const priceHtml = tier.custom
            ? '<div class="pricing-preview-price">Contact us</div>'
            : `<div class="pricing-preview-price">$${tier.monthlyPricePerProperty}<span>/property/mo</span></div>`;
        return `
            <div class="pricing-preview-card${featuredClass}">
                <div class="pricing-preview-name">${tier.name}</div>
                ${priceHtml}
            </div>
        `;
    }).join('');
})();
