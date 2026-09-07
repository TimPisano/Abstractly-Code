/**
 * Owner console login. Posts to the SAME /auth/login every role uses
 * (see backend/app/api.py) -- there is no separate owner auth system.
 * This page's own job is just rejecting a real, successful login for
 * a non-owner account, exactly the same pattern as
 * frontend/admin/login.js checking role !== 'admin' -- except this
 * checks is_owner, which is deliberately independent of role (see
 * backend/app/auth.py's require_owner docstring). The real security
 * boundary is server-side (require_owner() 404s every /owner/* route
 * for a non-owner) -- this client check is UX only, so a non-owner
 * gets a clear message instead of a confusing blank/broken console.
 *
 * credentials: 'include' is required -- frontend and backend are
 * different origins in this project's setup, so fetch omits cookies
 * cross-origin by default.
 */

// owner-app.js's ownerFetch sends people here as ?expired=1 on a 401
// that means the session ended mid-use -- same convention as
// frontend/app/login.js's ?expired=1. The param is stripped afterward
// so a refresh/bookmark doesn't keep re-asserting an expiry that
// happened once, minutes ago.
if (new URLSearchParams(window.location.search).get('expired') === '1') {
    const expiredMessageEl = document.getElementById('ownerLoginMessage');
    expiredMessageEl.textContent = 'Your session expired. Sign in again to continue.';
    expiredMessageEl.classList.add('is-error');
    window.history.replaceState({}, '', window.location.pathname);
}

document.getElementById('ownerLoginForm').addEventListener('submit', async (e) => {
    e.preventDefault();

    const emailInput = document.getElementById('ownerEmail');
    const passwordInput = document.getElementById('ownerPassword');
    const messageEl = document.getElementById('ownerLoginMessage');
    const submitBtn = document.getElementById('ownerLoginSubmitBtn');

    messageEl.textContent = '';
    messageEl.classList.remove('is-error', 'is-pending');
    submitBtn.disabled = true;
    submitBtn.textContent = 'Signing in...';

    // Render's free tier spins the backend down after 15 min idle, and
    // the first request after that takes 30-60s to wake it back up
    // (DEPLOYMENT.md's "Free-tier behavior you should know about").
    // Without this, that wait is indistinguishable from a hung page --
    // this only fires if the request below is still pending past the
    // point a warm backend would have already responded, so a normal
    // login never shows it.
    const coldStartHintTimer = setTimeout(() => {
        messageEl.textContent = 'Still working — the server may be waking up after being idle. This can take up to a minute.';
        messageEl.classList.add('is-pending');
    }, 5000);

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

        if (!data.is_owner) {
            throw new Error('This account does not have owner access.');
        }

        clearTimeout(coldStartHintTimer);
        window.location.href = 'index.html';
    } catch (err) {
        clearTimeout(coldStartHintTimer);
        messageEl.textContent = err.message;
        messageEl.classList.remove('is-pending');
        messageEl.classList.add('is-error');
        submitBtn.disabled = false;
        submitBtn.textContent = 'Sign In';
        passwordInput.value = '';
        passwordInput.focus();
    }
});
