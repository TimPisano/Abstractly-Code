/**
 * Sign-in page for the customer app. Posts to /auth/login (the same
 * route admin/ and owner/ use) and hands the returned token to
 * Auth.finishLogin, which stores it per "Keep me signed in" and goes to
 * the dashboard.
 *
 * Always shows the form, even if a session already exists -- a login
 * page must never silently skip its own credentials form (same
 * convention as admin/login.js). Someone with a live session who opens
 * index.html directly is let straight in by access-gate.js.
 *
 * Arrival notices (one-shot; the query param is stripped so a refresh
 * or bookmark doesn't repeat them):
 *   ?expired=1  -- api.js sends people here on any 401
 *   ?reset=1    -- older reset links / admin flow, password changed
 *   ?setup=1    -- team-setup.js, after an invited admin sets a password
 *   ?signedout=1 -- after signing out
 */
(function () {
    const form = document.getElementById('loginForm');
    const emailInput = document.getElementById('email');
    const passwordInput = document.getElementById('password');
    const rememberInput = document.getElementById('remember');
    const button = document.getElementById('submitButton');
    const statusEl = document.getElementById('formStatus');
    const notice = document.getElementById('loginNotice');

    const NOTICES = {
        expired: ['Your session ended. Sign in again to pick up where you left off.', 'error'],
        reset: ['Password updated. Sign in with your new password.', 'success'],
        setup: ["You're all set. Sign in with the password you just created.", 'success'],
        signedout: ["You're signed out.", 'success'],
    };
    const params = new URLSearchParams(window.location.search);
    // Set by api.js when a session ends mid-use: the screen to return to.
    // A bare view name only (validated again in Auth.finishLogin).
    const returnTo = /^[a-z0-9-]{1,40}$/.test(params.get('next') || '') ? params.get('next') : '';
    for (const [key, [text, kind]] of Object.entries(NOTICES)) {
        if (params.get(key) === '1') {
            notice.textContent = text;
            notice.classList.toggle('is-error', kind === 'error');
            notice.hidden = false;
            window.history.replaceState(null, '', window.location.pathname);
            break;
        }
    }

    Auth.setupRevealToggle(passwordInput, document.getElementById('passwordToggle'));

    // Only advertise signup where it's switched on (SELF_SERVE_SIGNUP_ENABLED).
    Auth.request('/auth/options').then(({ ok, data }) => {
        if (ok && data.signup_enabled) {
            document.getElementById('getStartedAlt').hidden = false;
            document.getElementById('topGetStarted').hidden = false;
        }
    }).catch(() => { /* offline: just don't show it */ });

    emailInput.addEventListener('input', () => Auth.setFieldError(emailInput, ''));
    passwordInput.addEventListener('input', () => Auth.setFieldError(passwordInput, ''));

    Auth.handleSubmit(form, button, 'Signing in...', async () => {
        Auth.setStatus(statusEl, '');
        notice.hidden = true;
        const email = emailInput.value.trim();
        const password = passwordInput.value;
        if (!email) {
            Auth.setFieldError(emailInput, 'Enter your email.');
            emailInput.focus();
            return false;
        }
        if (!password) {
            Auth.setFieldError(passwordInput, 'Enter your password.');
            passwordInput.focus();
            return false;
        }

        try {
            const { ok, data } = await Auth.request('/auth/login', {
                method: 'POST',
                body: { email, password, remember: rememberInput.checked },
                onSlow: () => Auth.setStatus(statusEl, 'Still working. The server may be waking up, which can take up to a minute.'),
            });
            if (!ok) throw new Error(data.error || 'Something went wrong. Please try again.');
            Auth.finishLogin(data, returnTo);
            return true;
        } catch (err) {
            Auth.setStatus(statusEl, err.message, 'error');
            passwordInput.value = '';
            passwordInput.focus();
            return false;
        }
    });
})();
