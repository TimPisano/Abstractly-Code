/**
 * "Choose a new password" -- reached only from a reset email's link.
 *
 * Same shape as finish-signup.js: the token leaves the address bar, is
 * checked with POST /auth/link-status so a dead link gets a friendly
 * screen up front, and POST /auth/reset-password both sets the password
 * and logs this browser in. The reset signs out every other session
 * (server side, see database.bump_session_version), so the page says so.
 *
 * (An earlier version deliberately skipped the up-front check, worried it
 * was a token-guessing oracle. It isn't one: the token is 256 random
 * bits, and anyone holding a live one could simply use it. Telling an
 * honest person their link expired before they type a password is worth
 * more.)
 */
(function () {
    const TOKEN_KEY = 'abstractly.resetToken';
    const token = Auth.takeLinkToken(TOKEN_KEY);
    const form = document.getElementById('resetForm');
    const passwordInput = document.getElementById('password');
    const button = document.getElementById('submitButton');
    const statusEl = document.getElementById('formStatus');
    let person = { email: '', name: '' };

    const passwordField = Auth.setupPasswordField({
        input: passwordInput,
        toggle: document.getElementById('passwordToggle'),
        rulesList: document.getElementById('passwordRules'),
        context: () => person,
    });
    passwordInput.addEventListener('input', () => Auth.setFieldError(passwordInput, ''));

    function dead(status) {
        if (status !== 'expired' && status !== 'superseded' && status !== 'used') Auth.forgetLinkToken(TOKEN_KEY);
        Auth.showDeadLink('reset', status, token);
    }

    (async function check() {
        if (!token) return dead('invalid');
        try {
            const { ok, data } = await Auth.request('/auth/link-status', {
                // POST, not a query string: the token must never reach server logs.
                method: 'POST',
                body: { kind: 'reset', token },
                onSlow: () => Auth.setStatus(document.getElementById('loadingSlow'), 'The server may be waking up. This can take up to a minute.'),
            });
            if (!ok) throw new Error(data.error || 'Something went wrong. Please refresh the page.');
            if (data.status !== 'valid') return dead(data.status);
            person = { email: data.email || '', name: data.first_name || '' };
            document.getElementById('username').value = person.email;
            if (data.first_name && data.first_name !== 'there') {
                document.getElementById('greeting').textContent =
                    `Hi ${data.first_name}. Pick a new password. This also signs you out on your other devices.`;
            }
            passwordField.refresh();
            Auth.showView('form');
            passwordInput.focus();
        } catch (err) {
            Auth.setStatus(document.getElementById('loadingSlow'), err.message, 'error');
        }
    })();

    Auth.handleSubmit(form, button, 'Saving...', async () => {
        Auth.setStatus(statusEl, '');
        if (!passwordField.check()) {
            Auth.setFieldError(passwordInput, 'Pick a password that meets the rules above.');
            passwordInput.focus();
            return false;
        }
        try {
            const { ok, data } = await Auth.request('/auth/reset-password', {
                method: 'POST',
                body: { token, new_password: passwordInput.value, remember: document.getElementById('remember').checked },
                onSlow: () => Auth.setStatus(statusEl, 'Still working. The server may be waking up, which can take up to a minute.'),
            });
            if (ok) {
                Auth.forgetLinkToken(TOKEN_KEY);
                if (data.logged_in && data.token) {
                    Auth.finishLogin(data);
                    return true;
                }
                Auth.clearToken();
                Auth.showView('done');
                return false;
            }
            if (data.link_status) {
                dead(data.link_status);
                return false;
            }
            Auth.setFieldError(passwordInput, data.error || 'Something went wrong. Please try again.');
            passwordInput.focus();
        } catch (err) {
            Auth.setStatus(statusEl, err.message, 'error');
        }
        return false;
    });
})();
