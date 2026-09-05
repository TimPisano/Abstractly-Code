/**
 * Admin login page behavior. Uses the same shared /auth/login every
 * role logs in through (see backend/app/api.py) -- this page's own
 * job is just rejecting a real, successful login for a non-admin
 * account, since this specific page is the admin-only surface.
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

// reset-password.js sends people here as ?reset=1 after a successful
// password change. Confirm it on arrival so the trip ends with visible
// proof it worked, rather than dropping them on an ordinary login form
// with no indication anything happened. Same convention as
// frontend/app/login.js. The param is stripped from the URL afterward
// so a refresh (or a bookmark) doesn't keep re-asserting a reset that
// happened once, minutes ago.
if (new URLSearchParams(window.location.search).get('reset') === '1') {
    const resetMessageEl = document.getElementById('adminLoginMessage');
    resetMessageEl.textContent = 'Password updated. Sign in with your new password.';
    resetMessageEl.classList.add('is-success');
    window.history.replaceState({}, '', window.location.pathname);
}

// admin-bootstrap.js's adminFetch sends people here as ?expired=1 on a
// 401 that means the session ended mid-use. Same convention as
// ?reset=1 above.
if (new URLSearchParams(window.location.search).get('expired') === '1') {
    const expiredMessageEl = document.getElementById('adminLoginMessage');
    expiredMessageEl.textContent = 'Your session expired. Sign in again to continue.';
    expiredMessageEl.classList.add('is-error');
    window.history.replaceState({}, '', window.location.pathname);
}

document.getElementById('adminLoginForm').addEventListener('submit', async (e) => {
    e.preventDefault();

    const emailInput = document.getElementById('adminEmail');
    const passwordInput = document.getElementById('adminPassword');
    const messageEl = document.getElementById('adminLoginMessage');
    const submitBtn = document.getElementById('adminLoginSubmitBtn');

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

        // /auth/login is shared across every role now -- this page is
        // still the admin-only surface, so a real, correct login for a
        // non-admin account must still be rejected here rather than
        // redirecting to dashboard.html (which would immediately bounce
        // them back anyway, but with a less clear message).
        if (data.role !== 'admin') {
            throw new Error('This account does not have admin access.');
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
