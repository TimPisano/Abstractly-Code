/**
 * "Choose a password" -- reached only from the signup email's link.
 *
 * On load: the token is taken out of the address bar (Auth.takeLinkToken)
 * and checked with POST /auth/link-status, so an expired, used, replaced
 * or broken link shows a friendly explanation (with a one-click "Send me
 * a new link") BEFORE anyone types a password.
 *
 * On submit: POST /auth/complete-signup creates the team and the user,
 * and returns a login, so they land in the dashboard already signed in.
 * If the link died between page load and submit (another tab used it, it
 * expired while the page sat open), the same friendly screen appears.
 */
(function () {
    const TOKEN_KEY = 'abstractly.signupToken';
    const token = Auth.takeLinkToken(TOKEN_KEY);
    const form = document.getElementById('finishForm');
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
        // A used link means the account exists; the stored token is no
        // longer useful for anything, so don't keep it around.
        if (status !== 'expired' && status !== 'superseded') Auth.forgetLinkToken(TOKEN_KEY);
        Auth.showDeadLink('signup', status, token);
    }

    (async function check() {
        if (!token) return dead('invalid');
        try {
            const { ok, status, data } = await Auth.request('/auth/link-status', {
                // POST, not a query string: the token must never reach server logs.
                method: 'POST',
                body: { kind: 'signup', token },
                onSlow: () => Auth.setStatus(document.getElementById('loadingSlow'), 'The server may be waking up. This can take up to a minute.'),
            });
            if (status === 404) return dead('invalid');
            if (!ok) throw new Error(data.error || 'Something went wrong. Please refresh the page.');
            if (data.status !== 'valid') return dead(data.status);

            person = { email: data.email || '', name: data.first_name || '' };
            document.getElementById('username').value = person.email;
            const greeting = document.getElementById('greeting');
            greeting.textContent = '';
            const hello = data.first_name && data.first_name !== 'there' ? `Hi ${data.first_name}. ` : '';
            greeting.append(`${hello}You're setting up Abstractly for `);
            const strong = document.createElement('strong');
            strong.textContent = data.company;
            greeting.append(strong, '.');
            passwordField.refresh();
            Auth.showView('form');
            passwordInput.focus();
        } catch (err) {
            Auth.setStatus(document.getElementById('loadingSlow'), err.message, 'error');
        }
    })();

    Auth.handleSubmit(form, button, 'Creating your account...', async () => {
        Auth.setStatus(statusEl, '');
        if (!passwordField.check()) {
            Auth.setFieldError(passwordInput, 'Pick a password that meets the rules above.');
            passwordInput.focus();
            return false;
        }
        try {
            const { ok, data } = await Auth.request('/auth/complete-signup', {
                method: 'POST',
                body: { token, password: passwordInput.value, remember: document.getElementById('remember').checked },
                onSlow: () => Auth.setStatus(statusEl, 'Still working. The server may be waking up, which can take up to a minute.'),
            });
            if (ok) {
                Auth.forgetLinkToken(TOKEN_KEY);
                Auth.finishLogin(data);
                return true;
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
