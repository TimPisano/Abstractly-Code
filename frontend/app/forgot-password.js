/**
 * "Forgot password?" request page. Posts an email to
 * /auth/forgot-password, which ALWAYS responds with the same generic
 * success message whether or not that address has an account (see
 * backend/app/api.py) -- so this page shows the same confirmation
 * either way and never reveals whether an account exists.
 *
 * Shared by both the main app login (login.html) and the admin login
 * (../admin/index.html links here too). The actual new-password step
 * happens on reset-password.html, reached via the emailed link.
 *
 * API_BASE_URL comes from ../config.js, loaded before this script.
 */

document.getElementById('forgotForm').addEventListener('submit', async (e) => {
    e.preventDefault();

    const emailInput = document.getElementById('forgotEmail');
    const messageEl = document.getElementById('forgotMessage');
    const submitBtn = document.getElementById('forgotSubmitBtn');
    const form = document.getElementById('forgotForm');

    messageEl.textContent = '';
    messageEl.classList.remove('is-error');
    submitBtn.disabled = true;
    submitBtn.textContent = 'Sending...';

    try {
        let response;
        try {
            response = await fetch(`${API_BASE_URL}/auth/forgot-password`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email: emailInput.value.trim() }),
            });
        } catch (networkErr) {
            throw new Error("Couldn't reach the server. Check your connection and try again.");
        }
        const data = await response.json().catch(() => ({}));

        if (!response.ok) {
            // The only non-200 here is the rate limit (429).
            throw new Error(data.error || 'Something went wrong. Please try again.');
        }

        // Generic, account-existence-agnostic confirmation -- matches
        // what the backend returns for every valid-looking address.
        form.hidden = true;
        messageEl.textContent = data.message
            || 'If an account exists for that email, a reset link is on its way. Check your inbox (and spam).';
    } catch (err) {
        messageEl.textContent = err.message;
        messageEl.classList.add('is-error');
        submitBtn.disabled = false;
        submitBtn.textContent = 'Send reset link';
    }
});
