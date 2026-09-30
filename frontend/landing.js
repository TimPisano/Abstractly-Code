/**
 * Shared marketing-site behavior (loaded on index.html and pricing.html
 * alike):
 *  - Book a Demo form: posts to the backend and swaps in a confirmation
 *    state instead of navigating away. Only present on index.html --
 *    guarded so pricing.html doesn't throw on this line.
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
 *    canvas behind every section (see #siteCanvas in both HTML files
 *    and .site-bg/.site-canvas in landing.css).
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
            document.getElementById('demoFormConfirm').classList.add('show');
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
 * ===================== Hero: fluted-glass WebGL shader =====================
 * index.html only (#hero / #heroGlCanvas aren't present on pricing.html).
 * Evenly spaced vertical "ribs," each shaded like a rounded glass
 * cylinder (soft highlight + darker grooves between them), lit by a
 * point light that eases toward the cursor and never snaps. Ribs near
 * the light glow in the accent color; brightness falls off smoothly
 * with distance. A slow perpetual idle drift keeps it visibly alive
 * when the cursor is still, and a faint per-rib shimmer plays across
 * lit ribs. All of this lives in the fragment shader below -- the JS
 * here only compiles/links it, feeds it u_mouse/u_time each frame, and
 * decides whether to run a loop at all.
 *
 * CSS fallback: `.hero`'s own background (landing.css) already paints a
 * static approximation of this same design (off-center radial glow +
 * matching rib spacing). #heroGlCanvas starts at opacity:0 and only
 * fades in once WebGL actually initializes and compiles successfully
 * (`.is-ready`) -- so a browser with no WebGL support, or where shader
 * compilation fails for any reason, silently keeps the CSS version
 * permanently instead of showing a blank hero.
 *
 * Touch devices and prefers-reduced-motion: per the brief, these get a
 * single still WebGL frame with the light centered (not the plainer CSS
 * fallback) -- that's a true-to-design static render, not a downgrade,
 * and it costs one draw call, not an animation loop.
 */
(function () {
    const hero = document.getElementById('hero');
    const canvas = document.getElementById('heroGlCanvas');
    if (!hero || !canvas) return;

    const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
    if (!gl) return; // no WebGL -- .hero's own CSS background stays the permanent look

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

            // Tall, soft elliptical falloff -- "a spotlight shining
            // through the ribs," not a circular pool of light.
            vec2 d = (uv - lightPos) / vec2(u_resolution.x * 0.16, u_resolution.y * 0.8);
            float glow = exp(-dot(d, d) * 2.4);

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
            console.warn('Abstractly hero shader failed to compile:', gl.getShaderInfoLog(shader));
            gl.deleteShader(shader);
            return null;
        }
        return shader;
    }

    const vertShader = compileShader(gl.VERTEX_SHADER, VERT_SRC);
    const fragShader = compileShader(gl.FRAGMENT_SHADER, FRAG_SRC);
    if (!vertShader || !fragShader) return; // falls back to .hero's CSS background

    const program = gl.createProgram();
    gl.attachShader(program, vertShader);
    gl.attachShader(program, fragShader);
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
        console.warn('Abstractly hero shader failed to link:', gl.getProgramInfoLog(program));
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

    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const hasFinePointer = window.matchMedia('(hover: hover) and (pointer: fine)').matches;
    const isStatic = prefersReducedMotion || !hasFinePointer;

    let width = 0;
    let height = 0;

    function resize() {
        const rect = hero.getBoundingClientRect();
        const dpr = Math.min(window.devicePixelRatio || 1, 2); // capped per the brief
        width = rect.width;
        height = rect.height;
        canvas.width = Math.round(width * dpr);
        canvas.height = Math.round(height * dpr);
        canvas.style.width = `${width}px`;
        canvas.style.height = `${height}px`;
        gl.viewport(0, 0, canvas.width, canvas.height);
    }

    resize();

    // Resting position is behind the deal-card side of the hero, not
    // dead center -- keeps the light away from the headline column by
    // default (the interactive case still follows the cursor anywhere,
    // including over the text; that's handled separately by .hero-copy's
    // scrim in landing.css). The reduced-motion/touch still frame below
    // stays literally centered, per the brief.
    let targetX = canvas.width * 0.68;
    let targetY = canvas.height * 0.4;
    let easedX = targetX;
    let easedY = targetY;

    let resizeTimer = null;
    window.addEventListener('resize', () => {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(resize, 150);
    });

    function render(mx, my, time, reduced) {
        gl.uniform2f(uResolution, canvas.width, canvas.height);
        gl.uniform2f(uMouse, mx, my);
        gl.uniform1f(uTime, time);
        gl.uniform1f(uReduced, reduced ? 1.0 : 0.0);
        gl.drawArrays(gl.TRIANGLES, 0, 3);
    }

    if (isStatic) {
        render(canvas.width * 0.5, canvas.height * 0.4, 0, true);
        canvas.classList.add('is-ready');
        return;
    }

    hero.addEventListener('mousemove', (e) => {
        const rect = hero.getBoundingClientRect();
        const dpr = canvas.width / width;
        targetX = (e.clientX - rect.left) * dpr;
        targetY = (e.clientY - rect.top) * dpr;
    });

    hero.addEventListener('mouseleave', () => {
        targetX = canvas.width * 0.68;
        targetY = canvas.height * 0.4;
    });

    let heroVisible = true;
    let rafId = null;
    let lastTime = performance.now();
    // Exponential, frame-rate-independent easing: reaches ~95% of the
    // way to the target in about 3*EASE_TAU seconds -- "drifts toward
    // the cursor over roughly half a second, never snaps."
    const EASE_TAU = 0.16;

    function loop(now) {
        if (!heroVisible || document.hidden) {
            rafId = null;
            return;
        }
        const dt = Math.min(0.05, (now - lastTime) / 1000);
        lastTime = now;
        const k = 1 - Math.exp(-dt / EASE_TAU);
        easedX += (targetX - easedX) * k;
        easedY += (targetY - easedY) * k;
        render(easedX, easedY, now / 1000, false);
        rafId = requestAnimationFrame(loop);
    }

    function startLoop() {
        lastTime = performance.now();
        if (rafId === null) rafId = requestAnimationFrame(loop);
    }

    // Render only while the hero is actually on screen.
    if ('IntersectionObserver' in window) {
        const io = new IntersectionObserver((entries) => {
            entries.forEach((entry) => {
                heroVisible = entry.isIntersecting;
                if (heroVisible) startLoop();
            });
        }, { threshold: 0 });
        io.observe(hero);
    }

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
