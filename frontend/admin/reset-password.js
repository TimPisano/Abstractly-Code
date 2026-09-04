/**
 * Admin "Choose a new password" page, reached only via the link in a
 * reset email requested from the admin login page (see
 * forgot-password.js's `surface: 'admin'`). The single-use token comes
 * in as a `?token=` query param and is posted to the same shared
 * /auth/reset-password every login surface uses (see
 * backend/app/api.py and frontend/app/reset-password.js), which
 * validates it (exists, not already used, under 1 hour old) and sets
 * the new password.
 *
 * Deliberately NOT pre-validating the token on page load -- same
 * reasoning as frontend/app/reset-password.js: a "check if this token
 * is good" endpoint would be a free oracle for testing stolen/guessed
 * tokens without consuming them, and the token is single-use, so a
 * pre-check either burns the token before the person types anything or
 * has to be non-consuming and thus abusable.
 *
 * API_BASE_URL comes from ../config.js, loaded before this script.
 */

const adminResetToken = new URLSearchParams(window.location.search).get('token');

const adminResetFormEl = document.getElementById('adminResetForm');
const adminResetMessageEl = document.getElementById('adminResetMessage');

if (!adminResetToken) {
    adminResetFormEl.hidden = true;
    adminResetMessageEl.textContent = 'This reset link is invalid or incomplete. Request a new one below.';
    adminResetMessageEl.classList.add('is-error');
    document.getElementById('adminResetRequestNewLink').hidden = false;
}

adminResetFormEl.addEventListener('submit', async (e) => {
    e.preventDefault();

    const passwordInput = document.getElementById('adminResetPassword');
    const confirmInput = document.getElementById('adminResetPasswordConfirm');
    const submitBtn = document.getElementById('adminResetSubmitBtn');

    const password = passwordInput.value;
    const confirmation = confirmInput.value;

    adminResetMessageEl.textContent = '';
    adminResetMessageEl.classList.remove('is-error');

    if (password !== confirmation) {
        adminResetMessageEl.textContent = "Those passwords don't match.";
        adminResetMessageEl.classList.add('is-error');
        confirmInput.value = '';
        confirmInput.focus();
        return;
    }
    if (password.length < 8) {
        adminResetMessageEl.textContent = 'New password must be at least 8 characters.';
        adminResetMessageEl.classList.add('is-error');
        passwordInput.focus();
        return;
    }

    submitBtn.disabled = true;
    submitBtn.textContent = 'Saving...';

    try {
        let response;
        try {
            response = await fetch(`${API_BASE_URL}/auth/reset-password`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ token: adminResetToken, new_password: password }),
            });
        } catch (networkErr) {
            throw new Error("Couldn't reach the server. Check your connection and try again.");
        }
        const data = await response.json().catch(() => ({}));

        if (!response.ok) {
            const err = new Error(data.error || 'Something went wrong. Please try again.');
            // A 400 here means the token itself is dead (invalid,
            // already used, or expired) -- retrying with the same link
            // can never succeed, so hide the form and offer a fresh
            // request instead of inviting another doomed attempt.
            err.tokenDead = response.status === 400 && !data.error?.includes('8 characters');
            throw err;
        }

        // Straight to the admin login form rather than showing a
        // success state here -- the person came to this page to get
        // back in, so hand them the sign-in form with their new
        // password already active. login.js reads ?reset=1 and shows
        // the confirmation there.
        window.location.href = 'index.html?reset=1';
    } catch (err) {
        adminResetMessageEl.textContent = err.message;
        adminResetMessageEl.classList.add('is-error');
        if (err.tokenDead) {
            adminResetFormEl.hidden = true;
            document.getElementById('adminResetRequestNewLink').hidden = false;
        } else {
            submitBtn.disabled = false;
            submitBtn.textContent = 'Set new password';
            passwordInput.value = '';
            confirmInput.value = '';
            passwordInput.focus();
        }
    }
});
