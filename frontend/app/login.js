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

// reset-password.js sends people here as ?reset=1 after a successful
// password change. Confirm it on arrival so the trip ends with visible
// proof it worked, rather than dropping them on an ordinary login form
// with no indication anything happened. The param is stripped from the
// URL afterward so a refresh (or a bookmark) doesn't keep re-asserting
// a reset that happened once, minutes ago.
if (new URLSearchParams(window.location.search).get('reset') === '1') {
    const messageEl = document.getElementById('loginMessage');
    messageEl.textContent = 'Password updated. Sign in with your new password.';
    messageEl.classList.add('is-success');
    window.history.replaceState({}, '', window.location.pathname);
}

// api.js's apiRequest sends people here as ?expired=1 on any 401 (see
// its own comment for why that always means session expiry in this
// app). Same pattern as ?reset=1 above -- land with a clear reason
// instead of an unexplained bare login form, and strip the param so a
// refresh/bookmark doesn't keep re-asserting an expiry that happened
// once, minutes ago.
if (new URLSearchParams(window.location.search).get('expired') === '1') {
    const messageEl = document.getElementById('loginMessage');
    messageEl.textContent = 'Your session expired. Sign in again to continue.';
    messageEl.classList.add('is-error');
    window.history.replaceState({}, '', window.location.pathname);
}

document.getElementById('loginForm').addEventListener('submit', async (e) => {
    e.preventDefault();

    const emailInput = document.getElementById('loginEmail');
    const passwordInput = document.getElementById('loginPassword');
    const messageEl = document.getElementById('loginMessage');
    const submitBtn = document.getElementById('loginSubmitBtn');

    messageEl.textContent = '';
    // Both, not just is-error: a leftover is-success from the
    // post-reset banner above would otherwise still be on the element
    // and paint a subsequent login *error* in the success color.
    messageEl.classList.remove('is-error', 'is-success');
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
