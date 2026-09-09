/**
 * Single source of truth for the backend API's base URL.
 *
 * Previously each of landing.js, app/access-gate.js, app/api.js, and
 * admin/waitlist/admin.js independently declared its own
 * `const API_BASE_URL = 'http://localhost:5000'` — four copies of the
 * same hardcoded value, in four separate files, with no way to point
 * the frontend at a real deployed backend without editing all four and
 * risking missing one. Loaded as the first <script> in every HTML
 * entry point (landing, /app/, /admin/) specifically so this
 * one declaration is visible to all of them — classic <script> tags in
 * one document share a single top-level lexical scope, so a later
 * script can reference this const by name with no import needed.
 *
 * Environment-aware rather than a single hardcoded value, specifically
 * so this ONE file (and this repo) works unchanged for both local dev
 * and the real deployment — nobody has to remember to flip this back
 * and forth, and a local `git pull` on the deployed server (or vice
 * versa) can never accidentally ship the wrong backend URL. Detected
 * by hostname, not by guessing from the port or protocol, since
 * that's the one thing that's reliably different between "this is
 * localhost" and "this is the real deployed static site."
 */
const API_BASE_URL = (() => {
    const host = window.location.hostname;
    if (host === 'localhost' || host === '127.0.0.1') {
        // Local-dev override -- point the frontend at a backend on a
        // different port or host WITHOUT editing this committed file.
        // Set it once from the browser devtools console:
        //   localStorage.setItem('abstractly.apiBaseOverride', 'http://localhost:5001')
        // and undo with localStorage.removeItem('abstractly.apiBaseOverride').
        // Needed mainly because macOS (Monterey+) binds :5000 to the
        // AirPlay Receiver, so a local backend often runs on :5001.
        // Honored ONLY when this page is itself served from localhost,
        // so it can never redirect API calls on the deployed site.
        try {
            const override = localStorage.getItem('abstractly.apiBaseOverride');
            if (override) return override.trim().replace(/\/+$/, '');
        } catch (e) { /* localStorage blocked -- fall through to the default */ }
        return 'http://localhost:5000';
    }
    // The demo deployment's static site talks to its own separate
    // backend/database (see app/demo_seed.py and DEPLOYMENT.md's
    // "Demo deployment" section for why it's a separate service
    // rather than a user inside the production database). Update
    // both hostnames here if either demo service is ever recreated
    // and gets a different Render-assigned suffix.
    if (host === 'abstractly-demo.onrender.com') {
        return 'https://abstractly-demo-api.onrender.com';
    }
    // The real deployed backend -- see render.yaml and DEPLOYMENT.md
    // for exactly how this URL is provisioned and why it's this
    // specific name.
    return 'https://abstractly-api.onrender.com';
})();
