/**
 * Admin login page behavior.
 *
 * Every request here uses `credentials: 'include'` -- fetch omits
 * cookies on a cross-origin request by default, and the frontend
 * (served on its own port) and backend API are different origins in
 * this project's dev setup, so the session cookie the backend sets on
 * a successful login would otherwise never actually be sent back on
 * later requests. See backend/app/api.py's CORS/session config for
 * the matching server-side half of this (supports_credentials=True,
 * an explicit origin allowlist, SameSite=None; Secure).
 *
 * API_BASE_URL comes from ../config.js, loaded before this script.
 */

/**
 * This page never checks for or acts on an existing session -- it
 * always renders the credentials form, unconditionally, on every visit,
 * with no auto-continue/bypass path of any kind. An earlier version
 * showed a "you're already signed in, Continue?" shortcut for a valid
 * session; that's deliberately gone now (see DECISIONS.md) -- landing
 * on /admin/ must always mean "type your email and password," full
 * stop, regardless of what cookie is or isn't already sitting in the
 * browser. Normal session persistence for someone who navigates
 * directly to dashboard.html with an already-valid session is
 * unaffected -- that's dashboard.html's own concern, not this page's.
 */

document.getElementById('adminLoginForm').addEventListener('submit', async (e) => {
    e.preventDefault();

    const emailInput = document.getElementById('adminEmail');
    const passwordInput = document.getElementById('adminPassword');
    const messageEl = document.getElementById('adminLoginMessage');
    const submitBtn = document.getElementById('adminLoginSubmitBtn');

    messageEl.textContent = '';
    messageEl.classList.remove('is-error');
    submitBtn.disabled = true;
    submitBtn.textContent = 'Signing in...';

    try {
        let response;
        try {
            response = await fetch(`${API_BASE_URL}/admin/login`, {
                method: 'POST',
                credentials: 'include',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email: emailInput.value.trim(), password: passwordInput.value }),
            });
        } catch (networkErr) {
            throw new Error("Couldn't reach the server. Check your connection and try again.");
        }
        const data = await response.json().catch(() => ({}));

        if (!response.ok) {
            throw new Error(data.error || 'Something went wrong. Please try again.');
        }

        window.location.href = 'dashboard.html';
    } catch (err) {
        messageEl.textContent = err.message;
        messageEl.classList.add('is-error');
        submitBtn.disabled = false;
        submitBtn.textContent = 'Sign In';
        passwordInput.value = '';
        passwordInput.focus();
    }
});
