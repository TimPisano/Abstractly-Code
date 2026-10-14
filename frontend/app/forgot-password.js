/**
 * "Forgot password?" -- one field. POST /auth/forgot-password always
 * answers the same way whether or not the email has an account, so this
 * page always says "If an account exists for that email, we just sent a
 * reset link." and never reveals which.
 *
 * Shared by the app login and the admin login (admin/forgot-password.html
 * is the admin's own copy). The new-password step is reset-password.html.
 */
(function () {
    const form = document.getElementById('forgotForm');
    const emailInput = document.getElementById('email');
    const button = document.getElementById('submitButton');
    const statusEl = document.getElementById('formStatus');
    const resendButton = document.getElementById('resendButton');
    const resendStatus = document.getElementById('resendStatus');
    let lastEmail = '';

    emailInput.addEventListener('input', () => Auth.setFieldError(emailInput, ''));

    async function send(email, slowEl) {
        const { ok, data } = await Auth.request('/auth/forgot-password', {
            method: 'POST',
            body: { email },
            onSlow: () => Auth.setStatus(slowEl, 'Still working. The server may be waking up, which can take up to a minute.'),
        });
        if (!ok) throw new Error(data.error || 'Something went wrong. Please try again.');
        return data.message;
    }

    Auth.handleSubmit(form, button, 'Sending...', async () => {
        Auth.setStatus(statusEl, '');
        const email = emailInput.value.trim();
        if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
            Auth.setFieldError(emailInput, 'Enter the email you sign in with.');
            emailInput.focus();
            return false;
        }
        try {
            const message = await send(email, statusEl);
            lastEmail = email;
            if (message) document.getElementById('sentMessage').textContent = message;
            Auth.setStatus(statusEl, '');
            Auth.showView('sent');
        } catch (err) {
            Auth.setStatus(statusEl, err.message, 'error');
        }
        return false;
    });

    resendButton.addEventListener('click', async () => {
        if (!lastEmail || resendButton.disabled) return;
        resendButton.disabled = true;
        Auth.setStatus(resendStatus, 'Sending...');
        try {
            await send(lastEmail, resendStatus);
            Auth.setStatus(resendStatus, 'Sent again. Only the newest link works.', 'success');
            setTimeout(() => { resendButton.disabled = false; }, 30000);
        } catch (err) {
            Auth.setStatus(resendStatus, err.message, 'error');
            resendButton.disabled = false;
        }
    });
})();
