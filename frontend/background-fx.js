/**
 * Full-page fluted-glass shader background (WebGL), driven by scroll
 * position and cursor location:
 *  - A constant, faint rib pattern is always visible so the page never
 *    looks flat -- the ribs are lit by a soft spotlight that follows
 *    the mouse.
 *  - Spotlight intensity and glow radius ease down over the first
 *    ~1.5 screens of scroll (the hero), then ease back up again near
 *    the bottom of the page so the final call-to-action lands on a lit
 *    moment instead of a dark one.
 *  - The rib pattern itself drifts slightly slower than actual scroll
 *    (parallax), driven by the same scroll value.
 *  - Lenis (vendor/lenis.min.js, loaded before this file) supplies the
 *    smooth-scroll feel and powers smooth in-page anchor navigation;
 *    this script reads the real scroll position each frame regardless
 *    of whether Lenis loaded, so it degrades gracefully if it didn't.
 *
 * prefers-reduced-motion and touch/no-hover devices get NONE of the
 * above -- no canvas, no rAF loop, no mousemove listener, no Lenis.
 * They fall back to the static CSS layer defined in landing.css
 * (html.bgfx-static), and native `scroll-behavior: smooth` handles
 * anchor navigation instead.
 *
 * Separately, and unconditionally for every visitor: toggles
 * .nav-scrolled on the fixed header once the page has scrolled past a
 * small threshold, so it's transparent over the hero and picks up a
 * translucent blurred fill after that (see landing.css).
 */
(function () {
    'use strict';

    var root = document.documentElement;

    // ---- Fixed-nav scroll toggle: transparent over the hero, a
    // translucent blurred fill once scrolled. This is a basic header
    // affordance, not part of the motion effect, so it runs
    // unconditionally -- reduced-motion and touch visitors get it too,
    // even though they skip everything below.
    var navEl = document.querySelector('.landing-nav');
    if (navEl) {
        var navTicking = false;
        var updateNav = function () {
            navTicking = false;
            navEl.classList.toggle('nav-scrolled', (window.scrollY || window.pageYOffset || 0) > 24);
        };
        updateNav();
        window.addEventListener('scroll', function () {
            if (navTicking) return;
            navTicking = true;
            requestAnimationFrame(updateNav);
        }, { passive: true });
    }

    var prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    var isTouch = window.matchMedia('(hover: none), (pointer: coarse)').matches;

    if (prefersReducedMotion || isTouch) {
        root.classList.add('bgfx-static');
        return;
    }

    var canvas = document.getElementById('bgfx-canvas');
    if (!canvas) return;

    var gl = canvas.getContext('webgl', { alpha: false, antialias: false, powerPreference: 'low-power' }) ||
        canvas.getContext('experimental-webgl');

    if (!gl) {
        root.classList.add('bgfx-static');
        return;
    }

    var VERT_SRC = [
        'attribute vec2 a_position;',
        'void main() {',
        '    gl_Position = vec4(a_position, 0.0, 1.0);',
        '}',
    ].join('\n');

    var FRAG_SRC = [
        'precision mediump float;',
        'uniform vec2 u_resolution;',
        'uniform vec2 u_mouse;',
        'uniform float u_time;',
        'uniform float u_intensity;',
        'uniform float u_scroll;',
        'void main() {',
        '    vec2 fragCoord = gl_FragCoord.xy;',
        '    vec2 coord = vec2(fragCoord.x, u_resolution.y - fragCoord.y);',
        '',
        '    float ribWidth = 30.0;',
        '    float parallax = u_scroll * 0.12;',
        '    float phase = (coord.x + parallax) / ribWidth * 3.14159265;',
        '    float wave = sin(phase);',
        '    float waveDeriv = cos(phase);',
        '',
        '    vec3 normal = normalize(vec3(waveDeriv * 0.85, 0.0, 0.55));',
        '',
        '    vec2 toLight = u_mouse - coord;',
        '    float dist = length(toLight);',
        '    vec3 lightDir = normalize(vec3(toLight / max(dist, 1.0), 260.0));',
        '    float diff = max(dot(normal, lightDir), 0.0);',
        '    diff = pow(diff, 1.6);',
        '',
        '    float radius = mix(u_resolution.y * 0.32, u_resolution.y * 0.95, u_intensity);',
        '    float falloff = smoothstep(radius, radius * 0.05, dist);',
        '',
        '    vec3 base = vec3(0.039, 0.039, 0.043);',
        '    vec3 ribShade = vec3(0.085, 0.083, 0.086);',
        '    vec3 accent = vec3(0.714, 0.541, 0.306);',
        '',
        '    vec3 color = base + ribShade * (0.5 + 0.5 * wave) * 0.55;',
        '',
        '    float shimmer = 0.012 * sin(u_time * 0.25 + phase * 2.0);',
        '    color += accent * shimmer * 0.4;',
        '',
        '    float lightAmount = diff * falloff * mix(0.35, 1.0, u_intensity);',
        '    color += accent * lightAmount * 0.85;',
        '    color += vec3(1.0) * lightAmount * 0.12;',
        '',
        '    vec2 uv = coord / u_resolution;',
        '    float vignette = smoothstep(1.05, 0.35, length(uv - 0.5) * 1.25);',
        '    color *= mix(0.8, 1.0, vignette);',
        '',
        '    gl_FragColor = vec4(color, 1.0);',
        '}',
    ].join('\n');

    function compileShader(type, src) {
        var shader = gl.createShader(type);
        gl.shaderSource(shader, src);
        gl.compileShader(shader);
        if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
            gl.deleteShader(shader);
            return null;
        }
        return shader;
    }

    var vertShader = compileShader(gl.VERTEX_SHADER, VERT_SRC);
    var fragShader = compileShader(gl.FRAGMENT_SHADER, FRAG_SRC);
    if (!vertShader || !fragShader) {
        root.classList.add('bgfx-static');
        return;
    }

    var program = gl.createProgram();
    gl.attachShader(program, vertShader);
    gl.attachShader(program, fragShader);
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
        root.classList.add('bgfx-static');
        return;
    }
    gl.useProgram(program);

    // Fullscreen triangle -- covers the viewport with one triangle
    // instead of two, no index buffer needed.
    var positionBuffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, positionBuffer);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    var positionLoc = gl.getAttribLocation(program, 'a_position');
    gl.enableVertexAttribArray(positionLoc);
    gl.vertexAttribPointer(positionLoc, 2, gl.FLOAT, false, 0, 0);

    var u_resolution = gl.getUniformLocation(program, 'u_resolution');
    var u_mouse = gl.getUniformLocation(program, 'u_mouse');
    var u_time = gl.getUniformLocation(program, 'u_time');
    var u_intensity = gl.getUniformLocation(program, 'u_intensity');
    var u_scroll = gl.getUniformLocation(program, 'u_scroll');

    root.classList.add('bgfx-active');

    var dpr = Math.min(window.devicePixelRatio || 1, 2);
    var width = 0;
    var height = 0;

    function resize() {
        width = window.innerWidth;
        height = window.innerHeight;
        canvas.width = Math.floor(width * dpr);
        canvas.height = Math.floor(height * dpr);
        gl.viewport(0, 0, canvas.width, canvas.height);
    }
    window.addEventListener('resize', resize);
    resize();

    var targetMouse = [width / 2, height * 0.32];
    var mouse = targetMouse.slice();
    window.addEventListener('mousemove', function (e) {
        targetMouse[0] = e.clientX;
        targetMouse[1] = e.clientY;
    }, { passive: true });

    // ---- Lenis: smooth scroll + smooth in-page anchor navigation.
    // Optional -- if the vendored script failed to load for any
    // reason, the render loop below still reads window.scrollY
    // directly, so scroll-linked intensity keeps working either way.
    if (window.Lenis) {
        var lenis = new window.Lenis({
            duration: 1.1,
            easing: function (t) { return 1 - Math.pow(1 - t, 3); },
            smoothWheel: true,
        });

        (function raf(time) {
            lenis.raf(time);
            requestAnimationFrame(raf);
        })(performance.now());

        document.addEventListener('click', function (e) {
            var link = e.target.closest ? e.target.closest('a[href^="#"]') : null;
            if (!link) return;
            var id = link.getAttribute('href').slice(1);
            if (!id) return;
            var target = document.getElementById(id);
            if (!target) return;
            e.preventDefault();
            // -88 clears the fixed nav's height so the anchor target's
            // own heading doesn't land underneath it.
            lenis.scrollTo(target, { offset: -88, duration: 1.3 });
        });

        window.__lenis = lenis;
    }

    function easeInOutCubic(t) {
        return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
    }

    var docLimit = 1;
    var docLimitCounter = 0;
    function refreshDocLimit() {
        docLimit = Math.max(document.documentElement.scrollHeight - window.innerHeight, 1);
    }
    refreshDocLimit();
    window.addEventListener('resize', refreshDocLimit);

    // Floor of 0.38 (not near-zero) is deliberate: the ribs must stay
    // clearly visible for the rest of the page, never fade close enough
    // to the base color to read as "solid black" next to the bright
    // hero -- that contrast is exactly what looked like a hard seam.
    var FADE_FLOOR = 0.38;
    var FADE_SWING = 1 - FADE_FLOOR;

    function computeIntensity(scrollY) {
        var vh = window.innerHeight;
        var heroT = Math.min(Math.max(scrollY / (vh * 1.5), 0), 1);
        var heroIntensity = 1 - easeInOutCubic(heroT) * FADE_SWING;

        var distFromBottom = docLimit - scrollY;
        var bottomWindow = vh * 1.3;
        var bottomT = 1 - Math.min(Math.max(distFromBottom / bottomWindow, 0), 1);
        var bottomIntensity = FADE_FLOOR + easeInOutCubic(bottomT) * FADE_SWING;

        return Math.max(heroIntensity, bottomIntensity);
    }

    var startTime = performance.now();
    function render(now) {
        var t = (now - startTime) / 1000;

        mouse[0] += (targetMouse[0] - mouse[0]) * 0.08;
        mouse[1] += (targetMouse[1] - mouse[1]) * 0.08;

        docLimitCounter++;
        if (docLimitCounter % 30 === 0) refreshDocLimit();

        var scrollY = window.scrollY || window.pageYOffset || 0;
        var intensity = computeIntensity(scrollY);

        gl.uniform2f(u_resolution, canvas.width, canvas.height);
        gl.uniform2f(u_mouse, mouse[0] * dpr, mouse[1] * dpr);
        gl.uniform1f(u_time, t);
        gl.uniform1f(u_intensity, intensity);
        gl.uniform1f(u_scroll, scrollY);
        gl.drawArrays(gl.TRIANGLES, 0, 3);

        requestAnimationFrame(render);
    }
    requestAnimationFrame(render);
})();
