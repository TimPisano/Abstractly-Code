/**
 * "Get started": name, work email, company -> POST /auth/signup, which
 * emails a 72-hour "Finish setting up your account" link. No account
 * exists until that link is used (finish-signup.html).
 *
 * The server answers the same "check your inbox" whether or not the
 * email already has an account (an existing account gets a "you already
 * have an account" email instead), so this page never reveals that.
 * "Send it again" re-posts the same details: a new link, and the old one
 * stops working.
 */
(function () {
    const form = document.getElementById('signupForm');
    const fields = {
        name: document.getElementById('name'),
        email: document.getElementById('email'),
        company: document.getElementById('company'),
    };
    const button = document.getElementById('submitButton');
    const statusEl = document.getElementById('formStatus');
    const resendButton = document.getElementById('resendButton');
    const resendStatus = document.getElementById('resendStatus');
    let lastSubmitted = null;

    // Off on this deployment -> say so, instead of a form that 404s.
    Auth.request('/auth/options').then(({ ok, data }) => {
        if (ok && !data.signup_enabled) Auth.showView('closed');
    }).catch(() => { /* the submit will report the network problem */ });

    Object.values(fields).forEach((input) => input.addEventListener('input', () => Auth.setFieldError(input, '')));

    // Typos in the domain are the #1 reason a signup email "never arrives".
    const DOMAIN_FIXES = {
        'gmial.com': 'gmail.com', 'gmai.com': 'gmail.com', 'gmail.co': 'gmail.com', 'gamil.com': 'gmail.com',
        'gnail.com': 'gmail.com', 'hotmial.com': 'hotmail.com', 'outlok.com': 'outlook.com',
        'yaho.com': 'yahoo.com', 'icloud.co': 'icloud.com',
    };
    fields.email.addEventListener('blur', () => {
        const value = fields.email.value.trim();
        const at = value.lastIndexOf('@');
        if (at < 1) return;
        const fix = DOMAIN_FIXES[value.slice(at + 1).toLowerCase()];
        if (fix) Auth.setFieldError(fields.email, `Did you mean ${value.slice(0, at + 1)}${fix}?`);
    });

    function validate(values) {
        let firstBad = null;
        const flag = (key, message) => {
            Auth.setFieldError(fields[key], message);
            if (!firstBad) firstBad = fields[key];
        };
        if (!values.name) flag('name', 'Enter your name.');
        if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(values.email)) flag('email', 'Enter a valid work email.');
        if (!values.company) flag('company', 'Enter your company.');
        if (firstBad) firstBad.focus();
        return !firstBad;
    }

    async function send(values, onSlowEl) {
        const { ok, status, data } = await Auth.request('/auth/signup', {
            method: 'POST',
            body: values,
            onSlow: () => Auth.setStatus(onSlowEl, 'Still working. The server may be waking up, which can take up to a minute.'),
        });
        if (status === 404) {
            Auth.showView('closed');
            return false;
        }
        if (!ok) {
            if (data.fields) {
                Object.entries(data.fields).forEach(([key, msg]) => fields[key] && Auth.setFieldError(fields[key], msg));
            }
            throw new Error(data.error || 'Something went wrong. Please try again.');
        }
        return true;
    }

    Auth.handleSubmit(form, button, 'Sending...', async () => {
        Auth.setStatus(statusEl, '');
        const values = {
            name: fields.name.value.trim(),
            email: fields.email.value.trim(),
            company: fields.company.value.trim(),
        };
        Object.values(fields).forEach((input) => Auth.setFieldError(input, ''));
        if (!validate(values)) return false;
        try {
            if (!(await send(values, statusEl))) return false;
            lastSubmitted = values;
            document.getElementById('sentEmail').textContent = values.email;
            Auth.setStatus(statusEl, '');
            Auth.showView('sent');
        } catch (err) {
            Auth.setStatus(statusEl, err.message, 'error');
        }
        return false;
    });

    resendButton.addEventListener('click', async () => {
        if (!lastSubmitted || resendButton.disabled) return;
        resendButton.disabled = true;
        Auth.setStatus(resendStatus, 'Sending...');
        try {
            await send(lastSubmitted, resendStatus);
            Auth.setStatus(resendStatus, 'Sent a fresh link. Only the newest one works.', 'success');
            // Cooldown: a second click would send a second email and kill
            // the link in the first one.
            setTimeout(() => { resendButton.disabled = false; }, 30000);
        } catch (err) {
            Auth.setStatus(resendStatus, err.message, 'error');
            resendButton.disabled = false;
        }
    });

    document.getElementById('startOverButton').addEventListener('click', () => {
        Auth.setStatus(resendStatus, '');
        Auth.showView('form');
        fields.email.focus();
        fields.email.select();
    });
})();
