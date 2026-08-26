/**
 * Main app login page behavior. Same shared /auth/login every role
 * logs in through (see backend/app/api.py and frontend/admin/login.js,
 * which uses the identical pattern for the admin mini-SPA) -- this
 * page just doesn't reject any particular role, unlike admin/login.js.
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
 * This page never checks for or acts on an existing session -- it
 * always renders the credentials form, unconditionally, on every
 * visit, same convention as admin/login.js (see that file's comment
 * for why). Someone who navigates directly to index.html with an
 * already-valid session is unaffected -- that's access-gate.js's own
 * concern, not this page's.
 *
 * API_BASE_URL comes from ../config.js, loaded before this script.
 */

document.getElementById('loginForm').addEventListener('submit', async (e) => {
    e.preventDefault();

    const emailInput = document.getElementById('loginEmail');
    const passwordInput = document.getElementById('loginPassword');
    const messageEl = document.getElementById('loginMessage');
    const submitBtn = document.getElementById('loginSubmitBtn');

    messageEl.textContent = '';
    messageEl.classList.remove('is-error');
    submitBtn.disabled = true;
    submitBtn.textContent = 'Signing in...';

    try {
        let response;
        try {
            response = await fetch(`${API_BASE_URL}/auth/login`, {
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

        window.location.href = 'index.html';
    } catch (err) {
        messageEl.textContent = err.message;
        messageEl.classList.add('is-error');
        submitBtn.disabled = false;
        submitBtn.textContent = 'Sign In';
        passwordInput.value = '';
        passwordInput.focus();
    }
});
