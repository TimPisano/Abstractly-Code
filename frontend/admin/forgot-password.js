/**
 * Admin "Forgot password?" request page. Posts to the same shared
 * /auth/forgot-password every login surface uses (see
 * backend/app/api.py and frontend/app/forgot-password.js), with
 * `surface: 'admin'` so the emailed link points back to this admin
 * section's own reset-password.html instead of the main app's. The
 * endpoint ALWAYS responds with the same generic success message
 * whether or not the address has an account, so this page shows that
 * same confirmation either way and never reveals whether an account
 * exists.
 *
 * API_BASE_URL comes from ../config.js, loaded before this script.
 */

document.getElementById('adminForgotForm').addEventListener('submit', async (e) => {
    e.preventDefault();

    const emailInput = document.getElementById('adminForgotEmail');
    const messageEl = document.getElementById('adminForgotMessage');
    const submitBtn = document.getElementById('adminForgotSubmitBtn');
    const form = document.getElementById('adminForgotForm');

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
                body: JSON.stringify({ email: emailInput.value.trim(), surface: 'admin' }),
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
