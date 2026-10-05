/**
 * Shared marketing-site behavior (loaded on index.html and pricing.html
 * alike):
 *  - Book a Demo form: posts to the backend and swaps in a confirmation
 *    state instead of navigating away. Only present on index.html --
 *    guarded so pricing.html doesn't throw on this line.
 *  - "Book a call" links: pointed at the API's CALENDLY_URL once
 *    /public-config answers (fallback: the on-page demo form).
 *  - Pageview beacon: fire-and-forget first-party analytics (see
 *    backend/app/api.py's POST /analytics/pageview).
 *  - Scroll reveal: a subtle fade + rise for elements marked .reveal
 *    as they enter the viewport, skipped under prefers-reduced-motion
 *    (handled in CSS).
 *  - Sticky header: toggles body.scrolled past a small scroll
 *    threshold so the header can go from transparent (over the hero)
 *    to a blurred dark bar (see landing.css's body.scrolled .site-header).
 *  - Mobile nav: opens/closes the slide-down panel on narrow viewports.
 *  - Sitewide cursor-reactive light bands: a fixed, viewport-sized
 *    canvas behind every section (see #siteGlCanvas in both HTML files
 *    and .site-bg/.site-gl-canvas in landing.css).
 *  - Hero Deal Mismatch Report count-up.
 *  - Pricing preview teaser (index.html only), rendered from
 *    PRICING_CONFIG so it can never drift from the real pricing page.
 * API_BASE_URL comes from config.js, loaded before this script.
 */

// A per-tab id in sessionStorage, NOT a cookie -- gone when the tab
// closes, never sent anywhere except this one beacon.
function _pageviewSessionId() {
    try {
        let id = sessionStorage.getItem('_pvsid');
        if (!id) {
            id = (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`);
            sessionStorage.setItem('_pvsid', id);
        }
        return id;
    } catch (e) {
        return null;
    }
}

function recordPageview(path) {
    try {
        fetch(`${API_BASE_URL}/analytics/pageview`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path, referrer: document.referrer || null, session_id: _pageviewSessionId() }),
        }).catch(() => {});
    } catch (e) { /* telemetry must never break the page */ }
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
        const website = document.getElementById('demoWebsite').value.trim();

        errorEl.classList.remove('show');

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
                throw new Error("Couldn't reach the server. Check your connection and try again.");
            }
            const data = await response.json().catch(() => ({}));

            if (!response.ok) {
                throw new Error(data.error || 'Something went wrong. Please try again.');
            }

            document.getElementById('demoFormWrap').classList.add('submitted');
            const confirmEl = document.getElementById('demoFormConfirm');
            // The server says whether a booking link was actually emailed;
            // the HTML's own text stays as the fallback.
            const confirmText = confirmEl.querySelector('span');
            if (data.message && confirmText) confirmText.textContent = data.message;
            confirmEl.classList.add('show');
            recordPageview('/__event/demo_requested');
        } catch (err) {
            errorEl.textContent = err.message;
            errorEl.classList.add('show');
            submitBtn.disabled = false;
            submitBtn.textContent = 'Book a Demo';
        }
    });
}

/**
 * ===================== "Book a call" links -> Calendly =====================
 * Every a[data-book-call] (footer + FAQ on index.html and pricing.html)
 * starts pointed at the on-page demo form. GET /public-config returns
 * the API's CALENDLY_URL; once it arrives, those links open it in a new
 * tab instead. If the API is asleep or slow, unreachable, or CALENDLY_URL
 * is unset (calendly_url: null), the links simply keep going to the form
 * -- never a dead click.
 */
(function () {
    const links = document.querySelectorAll('a[data-book-call]');
    if (!links.length) return;

    fetch(`${API_BASE_URL}/public-config`)
        .then((resp) => (resp.ok ? resp.json() : null))
        .then((config) => {
            const url = config && config.calendly_url;
            if (typeof url !== 'string' || !url.startsWith('https://')) {
                console.warn('Book a call: no CALENDLY_URL from /public-config; links stay on the demo form.');
                return;
            }
            links.forEach((a) => {
                a.href = url;
                a.target = '_blank';
                a.rel = 'noopener';
            });
        })
        .catch(() => { /* network error: keep the form fallback */ });
})();

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
    document.querySelectorAll('.reveal').forEach((el) => el.classList.add('in-view'));
}

/**
 * ===================== Sticky header scroll state =====================
 * Toggles body.scrolled once the page has scrolled past a small
 * threshold, so the header can go from fully transparent (sitting over
 * the hero) to the blurred dark bar defined in landing.css. Passive
 * listener, no layout reads beyond scrollY, cheap on every scroll frame.
 */
(function () {
    const THRESHOLD = 24;
    function updateScrolled() {
        document.body.classList.toggle('scrolled', window.scrollY > THRESHOLD);
    }
    updateScrolled();
    window.addEventListener('scroll', updateScrolled, { passive: true });
})();

/**
 * ===================== Mobile nav toggle =====================
 */
(function () {
    const toggle = document.getElementById('navToggle');
    const panel = document.getElementById('navMobilePanel');
    if (!toggle || !panel) return;

    toggle.addEventListener('click', () => {
        const isOpen = panel.classList.toggle('open');
        toggle.setAttribute('aria-expanded', String(isOpen));
    });

    // Close the panel after following a link, rather than leaving it
    // open behind the section the visitor just navigated to.
    panel.querySelectorAll('a').forEach((a) => {
        a.addEventListener('click', () => {
            panel.classList.remove('open');
            toggle.setAttribute('aria-expanded', 'false');
        });
    });
})();

/**
 * ===================== Sitewide fluted-glass WebGL shader =====================
 * Runs on every page that has #siteGlCanvas (index.html and
 * pricing.html alike) -- a single `position: fixed` canvas sized to the
 * viewport, painted behind the whole page (see .site-gl-canvas in
 * landing.css), never scoped to the hero or any other single section.
 * Evenly spaced vertical "ribs," each shaded like a rounded glass
 * cylinder (soft highlight + darker grooves between them), lit by a
 * point light that eases toward the cursor and never snaps. Ribs near
 * the light glow in the accent color; brightness falls off smoothly
 * with distance. A slow perpetual idle drift keeps it visibly alive
 * when the cursor is still, and a faint per-rib shimmer plays across
 * lit ribs.
 *
 * The light's overall intensity (u_scrollFade) eases from full at the
 * top of the page down to a faint floor over the first 1.5 screen
 * heights of scroll, then holds at that floor -- never a hard cutoff,
 * and the glow plus cursor-follow keep running all the way to the
 * bottom of the page, because this is the one and only background
 * layer for the entire site, not something confined to the hero.
 *
 * CSS fallback: .site-bg (landing.css) already paints a static
 * approximation of this same design (soft top glow + matching rib
 * spacing) across the whole viewport. #siteGlCanvas starts at
 * opacity:0 and only fades in once WebGL actually initializes and
 * compiles successfully (`.is-ready`) -- so a browser with no WebGL
 * support, or where shader compilation fails for any reason, silently
 * keeps the CSS version permanently instead of showing nothing.
 *
 * prefers-reduced-motion gets a single still WebGL frame with the light
 * centered, at full intensity, and no further updates -- a true-to-
 * design static render, not a downgrade, and it costs one draw call,
 * not an animation loop. Touch / coarse-pointer devices still get the
 * animated loop (idle drift, shimmer, and scroll-driven fade) just
 * without cursor-follow, since there's no cursor to follow.
 */
(function () {
    const canvas = document.getElementById('siteGlCanvas');
    if (!canvas) return;

    const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
    if (!gl) return; // no WebGL -- .site-bg's own CSS background stays the permanent look

    const VERT_SRC = `
        attribute vec2 a_position;
        void main() {
            gl_Position = vec4(a_position, 0.0, 1.0);
        }
    `;

    // Must match --lux-accent-rgb in landing.css (both derive from
    // design-system.css's --lux-accent, #b68a4e), as 0-1 floats.
    const FRAG_SRC = `
        precision highp float;
        uniform vec2 u_resolution;
        uniform vec2 u_mouse;
        uniform float u_time;
        uniform float u_reduced;
        uniform float u_scrollFade;

        const float RIB_COUNT = 34.0;
        const vec3 ACCENT = vec3(0.7137, 0.5412, 0.3059);
        const vec3 BASE_DARK = vec3(0.035, 0.035, 0.04);

        void main() {
            vec2 uv = gl_FragCoord.xy;
            uv.y = u_resolution.y - uv.y; // match CSS/mouse y-down convention

            float ribWidth = u_resolution.x / RIB_COUNT;
            float ribIndex = floor(uv.x / ribWidth);
            float localX = fract(uv.x / ribWidth);

            // Rounded-glass-cylinder cross-section: smooth bright center,
            // darker grooves at each rib boundary, plus a thin specular
            // highlight offset off-center like light catching a curve.
            float cyl = sin(localX * 3.14159265);
            float shade = pow(max(0.0, cyl), 1.6);
            float highlight = pow(max(0.0, cos((localX - 0.62) * 3.14159265)), 24.0);

            // Slow perpetual idle drift, layered on top of the already-
            // eased (in JS) cursor position -- zeroed under
            // prefers-reduced-motion for a genuinely still frame.
            vec2 drift = vec2(sin(u_time * 0.13), cos(u_time * 0.09)) * 22.0 * (1.0 - u_reduced);
            vec2 lightPos = u_mouse + drift;

            // True circular spotlight centered on the cursor: distance is
            // measured in viewport-HEIGHT units (both axes divided by
            // u_resolution.y) so a wide or narrow viewport can't stretch
            // it into an oval -- a radius means the same thing regardless
            // of aspect ratio. smoothstep gives a soft falloff with zero
            // slope at the boundary (brightest dead center, genuinely
            // nothing felt at the edge -- no visible ring), scaled by
            // u_scrollFade (eased in JS from scroll position, never a
            // step) so the light also dims smoothly as you scroll.
            vec2 normUv = uv / u_resolution.y;
            vec2 normLight = lightPos / u_resolution.y;
            float dist = distance(normUv, normLight);
            const float RADIUS = 0.375; // ~37.5% of viewport height
            float glow = (1.0 - smoothstep(0.0, RADIUS, dist)) * u_scrollFade;

            // Subtle per-rib shimmer, only visible where glow is present.
            float shimmer = 0.5 + 0.5 * sin(u_time * 2.2 + ribIndex * 1.7);
            float shimmerAmt = shimmer * 0.06 * glow * (1.0 - u_reduced * 0.6);

            vec3 litColor = mix(BASE_DARK, ACCENT, min(1.0, glow * 1.6));
            vec3 color = litColor * (shade * 0.55 + 0.45) + highlight * glow * 0.5;
            color *= (1.0 + shimmerAmt);

            gl_FragColor = vec4(color, 1.0);
        }
    `;

    function compileShader(type, src) {
        const shader = gl.createShader(type);
        gl.shaderSource(shader, src);
        gl.compileShader(shader);
        if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
            console.warn('Abstractly site shader failed to compile:', gl.getShaderInfoLog(shader));
            gl.deleteShader(shader);
            return null;
        }
        return shader;
    }

    const vertShader = compileShader(gl.VERTEX_SHADER, VERT_SRC);
    const fragShader = compileShader(gl.FRAGMENT_SHADER, FRAG_SRC);
    if (!vertShader || !fragShader) return; // falls back to .site-bg's CSS background

    const program = gl.createProgram();
    gl.attachShader(program, vertShader);
    gl.attachShader(program, fragShader);
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
        console.warn('Abstractly site shader failed to link:', gl.getProgramInfoLog(program));
        return;
    }
    gl.useProgram(program);

    // One oversized triangle covering the whole clip space -- standard
    // fullscreen-shader trick, one buffer, no index buffer needed.
    const posLoc = gl.getAttribLocation(program, 'a_position');
    const posBuffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, posBuffer);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    gl.enableVertexAttribArray(posLoc);
    gl.vertexAttribPointer(posLoc, 2, gl.FLOAT, false, 0, 0);

    const uResolution = gl.getUniformLocation(program, 'u_resolution');
    const uMouse = gl.getUniformLocation(program, 'u_mouse');
    const uTime = gl.getUniformLocation(program, 'u_time');
    const uReduced = gl.getUniformLocation(program, 'u_reduced');
    const uScrollFade = gl.getUniformLocation(program, 'u_scrollFade');

    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const hasFinePointer = window.matchMedia('(hover: hover) and (pointer: fine)').matches;

    let width = 0;
    let height = 0;
    let mouseMoved = false;

    // Idle default rests just behind the headline (the hero's left
    // column) rather than dead center, so the circle has somewhere
    // deliberate to sit before the cursor ever touches the page.
    // Recomputed on resize as long as the cursor hasn't actually moved
    // yet, so it never drifts to a stale pixel position after a
    // viewport resize.
    const IDLE_X_FRACTION = 0.3;
    const IDLE_Y_FRACTION = 0.4;
    let targetX = 0;
    let targetY = 0;
    let easedX = 0;
    let easedY = 0;

    function resize() {
        const dpr = Math.min(window.devicePixelRatio || 1, 2); // capped per the brief
        width = window.innerWidth;
        height = window.innerHeight;
        canvas.width = Math.round(width * dpr);
        canvas.height = Math.round(height * dpr);
        canvas.style.width = `${width}px`;
        canvas.style.height = `${height}px`;
        gl.viewport(0, 0, canvas.width, canvas.height);
        if (!mouseMoved) {
            targetX = canvas.width * IDLE_X_FRACTION;
            targetY = canvas.height * IDLE_Y_FRACTION;
            easedX = targetX;
            easedY = targetY;
        }
    }

    resize();

    let resizeTimer = null;
    window.addEventListener('resize', () => {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(resize, 150);
    });

    // Eases from 1.0 (full intensity) at the top of the page down to
    // MIN_SCROLL_INTENSITY (a faint floor, never fully off) by 1.5
    // screen heights of scroll, via a smoothstep -- a continuous curve,
    // not a step, so there is no point on the page where the light's
    // brightness changes abruptly. Holds at the floor for any scroll
    // beyond that, all the way to the bottom of the page.
    const MIN_SCROLL_INTENSITY = 0.16;
    function computeScrollFade() {
        const t = Math.min(1, window.scrollY / (window.innerHeight * 1.5));
        const eased = t * t * (3 - 2 * t);
        return 1 - eased * (1 - MIN_SCROLL_INTENSITY);
    }

    function render(mx, my, time, reduced, scrollFade) {
        gl.uniform2f(uResolution, canvas.width, canvas.height);
        gl.uniform2f(uMouse, mx, my);
        gl.uniform1f(uTime, time);
        gl.uniform1f(uReduced, reduced ? 1.0 : 0.0);
        gl.uniform1f(uScrollFade, scrollFade);
        gl.drawArrays(gl.TRIANGLES, 0, 3);
    }

    if (prefersReducedMotion) {
        render(canvas.width * IDLE_X_FRACTION, canvas.height * IDLE_Y_FRACTION, 0, true, 1.0);
        canvas.classList.add('is-ready');
        return;
    }

    // Cursor-follow only makes sense with an actual pointer -- touch
    // devices still get the idle drift + shimmer + scroll-driven fade
    // below, just without a light that chases a finger.
    if (hasFinePointer) {
        window.addEventListener('mousemove', (e) => {
            mouseMoved = true;
            const dpr = canvas.width / width;
            targetX = e.clientX * dpr;
            targetY = e.clientY * dpr;
        });

        document.documentElement.addEventListener('mouseleave', () => {
            mouseMoved = false;
            targetX = canvas.width * IDLE_X_FRACTION;
            targetY = canvas.height * IDLE_Y_FRACTION;
        });
    }

    let rafId = null;
    let lastTime = performance.now();
    // Exponential, frame-rate-independent easing: reaches ~95% of the
    // way to the target in about 3*EASE_TAU seconds -- "drifts toward
    // the cursor over roughly half a second, never snaps."
    const EASE_TAU = 0.16;

    function loop(now) {
        if (document.hidden) {
            rafId = null;
            return;
        }
        const dt = Math.min(0.05, (now - lastTime) / 1000);
        lastTime = now;
        const k = 1 - Math.exp(-dt / EASE_TAU);
        easedX += (targetX - easedX) * k;
        easedY += (targetY - easedY) * k;
        render(easedX, easedY, now / 1000, false, computeScrollFade());
        rafId = requestAnimationFrame(loop);
    }

    function startLoop() {
        lastTime = performance.now();
        if (rafId === null) rafId = requestAnimationFrame(loop);
    }

    // The canvas is `position: fixed` and covers the whole page, so
    // unlike the old hero-scoped version there's no "is it on screen"
    // check to gate the loop on -- only tab visibility matters.
    document.addEventListener('visibilitychange', () => {
        if (!document.hidden) startLoop();
    });

    canvas.classList.add('is-ready');
    startLoop();
})();

/**
 * ===================== Hero: Deal Mismatch Report count-up =====================
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
            const eased = 1 - Math.pow(1 - progress, 3);
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
 * Reuses PRICING_CONFIG so the teaser can never drift out of sync with
 * the real numbers on /pricing.
 */
(function () {
    const grid = document.getElementById('pricingPreviewGrid');
    if (!grid || typeof PRICING_CONFIG === 'undefined') return;

    grid.innerHTML = PRICING_CONFIG.tiers.map((tier) => {
        const featuredClass = tier.featured ? ' pricing-preview-card-featured' : '';
        const priceHtml = tier.custom
            ? '<div class="pricing-preview-price">Contact us</div>'
            : `<div class="pricing-preview-price">$${tier.monthlyPrice.toLocaleString('en-US')}<span>/mo</span></div>`;
        return `
            <div class="pricing-preview-card${featuredClass}">
                <div class="pricing-preview-name">${tier.name}</div>
                ${priceHtml}
            </div>
        `;
    }).join('');
})();

/**
 * ===================== Lenis smooth scroll =====================
 * vendor/lenis.min.js (MIT, vendored locally -- see vendor/LENIS_LICENSE
 * -- not loaded from a CDN) exposes a global `Lenis` constructor when
 * loaded as a plain <script>. Never initialized under
 * prefers-reduced-motion -- native scrolling is the correct behavior
 * there, not an animated one running at a different speed. Anchor links
 * (nav, hero, footer, "See a sample report", etc.) are intercepted here
 * so they go through lenis.scrollTo instead of the browser's native
 * jump -- landing.css deliberately drops `scroll-behavior: smooth` for
 * the same reason (the two would otherwise fight).
 */
(function () {
    if (typeof Lenis === 'undefined') return; // script failed to load -- native scroll still works fine
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

    const lenis = new Lenis({
        duration: 1.1,
        easing: (t) => (t === 1 ? 1 : 1 - Math.pow(2, -10 * t)),
        smoothWheel: true,
    });

    function raf(time) {
        lenis.raf(time);
        requestAnimationFrame(raf);
    }
    requestAnimationFrame(raf);

    document.addEventListener('click', (e) => {
        const link = e.target.closest('a[href*="#"]');
        if (!link) return;
        const href = link.getAttribute('href');
        const hashIndex = href.indexOf('#');
        if (hashIndex === -1) return;
        const path = href.slice(0, hashIndex);
        const hash = href.slice(hashIndex + 1);
        // Only intercept a same-page anchor (bare "#id" or a link to
        // this exact page + "#id") -- "index.html#book-demo" from
        // pricing.html must still navigate for real.
        if (path && path !== window.location.pathname.split('/').pop()) return;
        if (!hash) return;
        const target = document.getElementById(hash);
        if (!target) return;
        e.preventDefault();
        // -96: clears the ~80px sticky header plus a little breathing
        // room, so the target section's heading isn't left hidden
        // behind the header after the scroll settles.
        lenis.scrollTo(target, { offset: -96 });
    });
})();

/**
 * ===================== Card spotlight: cursor-aware glow =====================
 * One delegated mousemove listener (not one per card) updates --mx/--my
 * on whichever card the cursor is over; landing.css's ::before radial-
 * gradient on .pricing-card/.trust-item/.differentiator-card/.faq-item/
 * .pricing-preview-card reads those custom properties. Delegation means
 * this works for the two pricing grids even though they're rendered
 * dynamically (by pricing.js and the block above) after this script
 * would otherwise have already run a querySelectorAll.
 */
(function () {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

    const SPOTLIGHT_SELECTOR = '.pricing-card, .trust-item, .differentiator-card, .faq-item, .pricing-preview-card';

    document.addEventListener('mousemove', (e) => {
        const card = e.target.closest(SPOTLIGHT_SELECTOR);
        if (!card) return;
        const rect = card.getBoundingClientRect();
        card.style.setProperty('--mx', `${e.clientX - rect.left}px`);
        card.style.setProperty('--my', `${e.clientY - rect.top}px`);
    });
})();

/**
 * ===================== Background parallax =====================
 * A subtle scroll-linked drift on the fixed faint rib texture (.site-bg)
 * -- a single passive-listener transform update, GPU-composited, no
 * layout/paint cost. Skipped entirely under prefers-reduced-motion.
 */
(function () {
    const bg = document.querySelector('.site-bg');
    if (!bg) return;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

    let ticking = false;
    function update() {
        bg.style.transform = `translate3d(0, ${window.scrollY * 0.04}px, 0)`;
        ticking = false;
    }
    window.addEventListener('scroll', () => {
        if (!ticking) {
            requestAnimationFrame(update);
            ticking = true;
        }
    }, { passive: true });
})();
