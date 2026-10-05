/**
 * "Set your password" page for a brand-new team's first admin, reached
 * only via the setup link from POST /owner/teams (emailed, or copied
 * from the owner console if email isn't configured). The single-use,
 * 7-day token comes in as a `?token=` query param and is posted to
 * /auth/team-setup -- same validate-and-consume shape as
 * reset-password.js's /auth/reset-password, just a longer-lived token
 * (see that file's own comment for why the token isn't pre-validated
 * with its own round trip on page load -- identical reasoning here).
 *
 * API_BASE_URL comes from ../config.js, loaded before this script.
 */

const setupToken = new URLSearchParams(window.location.search).get('token');

const setupFormEl = document.getElementById('setupForm');
const setupMessageEl = document.getElementById('setupMessage');

if (!setupToken) {
    setupFormEl.hidden = true;
    setupMessageEl.textContent = 'This setup link is invalid or incomplete.';
    setupMessageEl.classList.add('is-error');
    document.getElementById('setupDeadLinkNote').hidden = false;
}

setupFormEl.addEventListener('submit', async (e) => {
    e.preventDefault();

    const passwordInput = document.getElementById('setupPassword');
    const confirmInput = document.getElementById('setupPasswordConfirm');
    const submitBtn = document.getElementById('setupSubmitBtn');

    const password = passwordInput.value;
    const confirmation = confirmInput.value;

    setupMessageEl.textContent = '';
    setupMessageEl.classList.remove('is-error');

    if (password !== confirmation) {
        setupMessageEl.textContent = "Those passwords don't match.";
        setupMessageEl.classList.add('is-error');
        confirmInput.value = '';
        confirmInput.focus();
        return;
    }
    if (password.length < 8) {
        setupMessageEl.textContent = 'Password must be at least 8 characters.';
        setupMessageEl.classList.add('is-error');
        passwordInput.focus();
        return;
    }

    submitBtn.disabled = true;
    submitBtn.textContent = 'Saving...';

    try {
        let response;
        try {
            response = await fetch(`${API_BASE_URL}/auth/team-setup`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ token: setupToken, new_password: password }),
            });
        } catch (networkErr) {
            throw new Error("Couldn't reach the server. Check your connection and try again.");
        }
        const data = await response.json().catch(() => ({}));

        if (!response.ok) {
            const err = new Error(data.error || 'Something went wrong. Please try again.');
            // A 400 here means the token itself is dead (invalid,
            // already used, or expired) -- retrying with the same link
            // can never succeed.
            err.tokenDead = response.status === 400 && !data.error?.includes('8 characters');
            throw err;
        }

        window.location.href = 'login.html?setup=1';
    } catch (err) {
        setupMessageEl.textContent = err.message;
        setupMessageEl.classList.add('is-error');
        if (err.tokenDead) {
            setupFormEl.hidden = true;
            document.getElementById('setupDeadLinkNote').hidden = false;
        } else {
            submitBtn.disabled = false;
            submitBtn.textContent = 'Set password and continue';
            passwordInput.value = '';
            confirmInput.value = '';
            passwordInput.focus();
        }
    }
});
