/**
 * "Choose a new password" page, reached only via the link in a reset
 * email. The single-use token comes in as a `?token=` query param and
 * is posted to /auth/reset-password, which validates it (exists, not
 * already used, under 1 hour old -- see
 * database.consume_password_reset_token) and sets the new password.
 *
 * The token is deliberately NOT pre-validated with its own round trip
 * on page load. A "check if this token is good" endpoint would be a
 * free oracle for testing stolen/guessed tokens without consuming
 * them, and the token is single-use -- so a pre-check either burns the
 * token before the person types anything, or has to be non-consuming
 * and thus abusable. Instead the token is submitted once, together
 * with the new password, and an invalid/expired one is reported in the
 * same response. The only thing checked up front is that a token is
 * present at all, which needs no server round trip.
 *
 * The two password fields are compared client-side purely as an
 * immediate typo check -- the backend only ever receives one password
 * and enforces the real minimum-length rule itself.
 *
 * API_BASE_URL comes from ../config.js, loaded before this script.
 */

const resetToken = new URLSearchParams(window.location.search).get('token');

const resetFormEl = document.getElementById('resetForm');
const resetMessageEl = document.getElementById('resetMessage');

// No token in the URL at all -- someone opened this page directly, or
// a mail client mangled the link. Say so immediately rather than
// letting them type a password into a form that can only fail.
if (!resetToken) {
    resetFormEl.hidden = true;
    resetMessageEl.textContent = 'This reset link is invalid or incomplete. Request a new one below.';
    resetMessageEl.classList.add('is-error');
    document.getElementById('resetRequestNewLink').hidden = false;
}

resetFormEl.addEventListener('submit', async (e) => {
    e.preventDefault();

    const passwordInput = document.getElementById('resetPassword');
    const confirmInput = document.getElementById('resetPasswordConfirm');
    const submitBtn = document.getElementById('resetSubmitBtn');

    const password = passwordInput.value;
    const confirmation = confirmInput.value;

    resetMessageEl.textContent = '';
    resetMessageEl.classList.remove('is-error');

    if (password !== confirmation) {
        resetMessageEl.textContent = "Those passwords don't match.";
        resetMessageEl.classList.add('is-error');
        confirmInput.value = '';
        confirmInput.focus();
        return;
    }
    if (password.length < 8) {
        resetMessageEl.textContent = 'New password must be at least 8 characters.';
        resetMessageEl.classList.add('is-error');
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
                body: JSON.stringify({ token: resetToken, new_password: password }),
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

        // Straight to login rather than showing a success state here --
        // the person came to this page to get back in, so hand them the
        // sign-in form with their new password already active. login.js
        // reads ?reset=1 and shows the confirmation there.
        window.location.href = 'login.html?reset=1';
    } catch (err) {
        resetMessageEl.textContent = err.message;
        resetMessageEl.classList.add('is-error');
        if (err.tokenDead) {
            resetFormEl.hidden = true;
            document.getElementById('resetRequestNewLink').hidden = false;
        } else {
            submitBtn.disabled = false;
            submitBtn.textContent = 'Set new password';
            passwordInput.value = '';
            confirmInput.value = '';
            passwordInput.focus();
        }
    }
});
