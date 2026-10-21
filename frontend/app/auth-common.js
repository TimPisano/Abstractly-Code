/**
 * Shared behavior for the account pages (login, signup, finish-signup,
 * forgot-password, reset-password). Exposes one global, `Auth`.
 *
 * The things every one of those pages has to get right, in one place:
 *  - Double clicks: a form can't be submitted again while its request is
 *    in flight (`Auth.handleSubmit`).
 *  - The back button: Safari and Chrome restore pages from the
 *    back/forward cache with buttons still frozen in "Saving...", so a
 *    restored page is un-frozen and its password fields cleared.
 *  - Slow servers: Render's free tier takes 30-60s to wake up; after 5s
 *    the page says so instead of looking hung, and gives up after 70s.
 *  - Link tokens: taken out of the address bar as soon as the page loads
 *    (so they don't sit in history, screenshots or a shared URL), kept in
 *    sessionStorage so a refresh still works.
 *  - "Keep me signed in": the login token goes to localStorage (stays
 *    across browser restarts, 30-day token) or sessionStorage (gone when
 *    the tab or browser closes, 12-hour token). See api.js.
 *
 * API_BASE_URL comes from ../config.js, loaded before this script.
 */
(function () {
    // Mirrors backend/app/password_rules.py -- tests/test_auth_flow.py
    // fails if these drift apart. The server is the authority; this is
    // only so the checklist can turn green as you type.
    const MIN_LENGTH = 10;
    const MAX_BYTES = 72;
    const COMMON_PASSWORDS = new Set(`
1234567890 12345678910 123456789a 1234567890a 0123456789 0987654321
1q2w3e4r5t 1qaz2wsx3edc qwertyuiop qwerty1234 qwerty12345 asdfghjkl1
asdfghjkl; zxcvbnm123 1q2w3e4r5t6y qazwsxedc123 password12 password123
password1234 password01 password1! password!1 passw0rd12 p@ssword12
p@ssw0rd12 p@ssw0rd123 iloveyou12 iloveyou123 sunshine12 princess12
football12 baseball12 welcome123 welcome1234 letmein123 abc1234567
abcdefghij aaaaaaaaaa 1111111111 0000000000 1212121212 1234554321
abstractly abstractly1 abstractly123 changeme123 trustno1234 superman12
dragon1234 monkey1234 michael123 jennifer12 starwars12 whatever12
computer12 internet12 administrator admin12345 admin123456 rootroot12
realestate realestate1 multifamily apartments rentroll123 qwerty123456
`.split(/\s+/).filter(Boolean));

    const TOKEN_KEY = 'authToken';
    const SLOW_AFTER_MS = 5000;
    const GIVE_UP_AFTER_MS = 70000;

    function safeStorage(kind) {
        try {
            const s = window[kind];
            const probe = '__abstractly_probe__';
            s.setItem(probe, '1');
            s.removeItem(probe);
            return s;
        } catch (e) {
            return null; // Storage disabled (some private modes / strict settings).
        }
    }
    const local = safeStorage('localStorage');
    const sess = safeStorage('sessionStorage');

    function getToken() {
        return (sess && sess.getItem(TOKEN_KEY)) || (local && local.getItem(TOKEN_KEY)) || null;
    }

    function clearToken() {
        if (sess) sess.removeItem(TOKEN_KEY);
        if (local) local.removeItem(TOKEN_KEY);
    }

    /**
     * Store a fresh login and go to the app. replace(), not assign(): the
     * page we're leaving (a used link, a submitted password form) should
     * not be one Back press away.
     */
    function finishLogin(data, returnToView) {
        // Write the new token straight over the old one, never clear-then-
        // set: other open tabs watch the shared (localStorage) slot, and a
        // momentary "empty" there reads to them as "signed out".
        if (data.remember) {
            if (sess) sess.removeItem(TOKEN_KEY);
            if (data.token && local) local.setItem(TOKEN_KEY, data.token);
        } else {
            if (local) local.removeItem(TOKEN_KEY);
            if (data.token && sess) sess.setItem(TOKEN_KEY, data.token);
        }
        const view = /^[a-z0-9-]{1,40}$/.test(returnToView || '') ? `#${returnToView}` : '';
        window.location.replace(`index.html${view}`);
    }

    /**
     * fetch() with the slow-server hint, a hard timeout, and one friendly
     * message for every way the network can fail. Resolves to
     * {ok, status, data}; rejects only on network failure/timeout.
     */
    async function request(path, { method = 'GET', body, onSlow } = {}) {
        const controller = new AbortController();
        const slowTimer = onSlow ? setTimeout(onSlow, SLOW_AFTER_MS) : null;
        const giveUpTimer = setTimeout(() => controller.abort(), GIVE_UP_AFTER_MS);
        let response;
        try {
            response = await fetch(`${API_BASE_URL}${path}`, {
                method,
                credentials: 'include',
                headers: body ? { 'Content-Type': 'application/json' } : {},
                body: body ? JSON.stringify(body) : undefined,
                signal: controller.signal,
            });
        } catch (err) {
            throw new Error(err && err.name === 'AbortError'
                ? 'The server is taking too long to respond. Please try again in a minute.'
                : "Couldn't reach the server. Check your connection and try again.");
        } finally {
            clearTimeout(slowTimer);
            clearTimeout(giveUpTimer);
        }
        const data = await response.json().catch(() => ({}));
        return { ok: response.ok, status: response.status, data };
    }

    // ---- buttons, statuses, views --------------------------------------

    function setBusy(button, busyLabel) {
        if (!button.dataset.label) button.dataset.label = button.textContent.trim();
        button.disabled = true;
        button.setAttribute('aria-busy', 'true');
        button.textContent = '';
        const spinner = document.createElement('span');
        spinner.className = 'auth-spinner';
        spinner.setAttribute('aria-hidden', 'true');
        button.append(spinner, document.createTextNode(busyLabel));
    }

    function clearBusy(button) {
        button.disabled = false;
        button.removeAttribute('aria-busy');
        if (button.dataset.label) button.textContent = button.dataset.label;
    }

    function setStatus(el, message, kind) {
        el.classList.remove('is-error', 'is-success');
        if (kind) el.classList.add(`is-${kind}`);
        el.textContent = message || '';
    }

    function showView(name) {
        document.querySelectorAll('[data-view]').forEach((el) => {
            el.hidden = el.dataset.view !== name;
        });
        const shown = document.querySelector(`[data-view="${name}"]`);
        // Move focus to the new view's heading so screen readers announce
        // it and keyboard users aren't left on a now-hidden button.
        const heading = shown && shown.querySelector('h1');
        if (heading) {
            heading.setAttribute('tabindex', '-1');
            heading.focus({ preventScroll: true });
        }
        window.scrollTo(0, 0);
    }

    function setFieldError(input, message) {
        const errorEl = document.getElementById(`${input.id}Error`);
        if (errorEl) errorEl.textContent = message || '';
        if (message) input.setAttribute('aria-invalid', 'true');
        else input.removeAttribute('aria-invalid');
    }

    /**
     * Wires a form's submit to `handler(event)` with double-submit
     * protection. The handler returns true once it has started a
     * navigation away (so the button stays disabled until the page
     * changes); anything else re-enables the button.
     */
    function handleSubmit(form, button, busyLabel, handler) {
        form.addEventListener('submit', async (event) => {
            event.preventDefault();
            if (form.dataset.busy === '1') return;
            form.dataset.busy = '1';
            setBusy(button, busyLabel);
            let navigating = false;
            try {
                navigating = (await handler(event)) === true;
            } finally {
                if (!navigating) {
                    form.dataset.busy = '';
                    clearBusy(button);
                }
            }
        });
    }

    // Back/forward cache: a page restored from it keeps its frozen
    // "Saving..." button and whatever was typed. Un-freeze it, and never
    // leave a typed password sitting there.
    window.addEventListener('pageshow', (event) => {
        if (!event.persisted) return;
        document.querySelectorAll('form[data-busy="1"]').forEach((f) => { f.dataset.busy = ''; });
        document.querySelectorAll('button[aria-busy="true"]').forEach(clearBusy);
        document.querySelectorAll('input[type="password"], input[data-password]').forEach((i) => { i.value = ''; i.dispatchEvent(new Event('input')); });
    });

    // ---- link tokens -----------------------------------------------------

    // Tokens are secrets.token_urlsafe(32): letters, digits, "-" and "_",
    // 43 characters. Links copied out of a sentence often pick up a
    // trailing "." or ")" (or a space from a wrapped line); keep the
    // leading token-shaped run instead of calling the whole link broken.
    function cleanLinkToken(raw) {
        const match = /^[A-Za-z0-9_-]+/.exec((raw || '').trim());
        return match && match[0].length >= 40 ? match[0] : (raw || '').trim();
    }

    function takeLinkToken(storageKey) {
        const params = new URLSearchParams(window.location.search);
        const fromUrl = params.get('token') ? cleanLinkToken(params.get('token')) : null;
        if (fromUrl) {
            if (sess) sess.setItem(storageKey, fromUrl);
            params.delete('token');
            const rest = params.toString();
            window.history.replaceState(null, '', window.location.pathname + (rest ? `?${rest}` : ''));
            return fromUrl;
        }
        return sess ? sess.getItem(storageKey) : null;
    }

    function forgetLinkToken(storageKey) {
        if (sess) sess.removeItem(storageKey);
    }

    // ---- password field --------------------------------------------------

    function utf8Length(text) {
        return new TextEncoder().encode(text).length;
    }

    function passwordProblems(password, email, name) {
        const problems = [];
        if (password.length < MIN_LENGTH) problems.push('length');
        if (utf8Length(password) > MAX_BYTES) problems.push('too_long');
        const lowered = password.trim().toLowerCase();
        if (COMMON_PASSWORDS.has(lowered) || (lowered && new Set(lowered).size === 1)) problems.push('common');

        const personal = new Set();
        email = (email || '').trim().toLowerCase();
        if (email) {
            personal.add(email);
            const local = email.split('@')[0];
            if (local.length >= 4) personal.add(local);
        }
        const nameParts = (name || '').toLowerCase().split(/\s+/).filter(Boolean);
        nameParts.forEach((p) => { if (p.length >= 4) personal.add(p); });
        const fullName = nameParts.join('');
        if (fullName.length >= 4) personal.add(fullName);
        const compact = lowered.replace(/\s+/g, '').replace(/[0-9!@#$%^&*.]+$/, '');
        if ((email && lowered.includes(email)) || personal.has(compact)) problems.push('personal');
        return problems;
    }

    /**
     * Live checklist under a new-password field, plus the show/hide
     * toggle. `context()` returns {email, name} for the "not your email
     * or name" rule. Returns {check()}: true if OK, else marks the
     * failing rules red and returns false.
     */
    function setupPasswordField({ input, toggle, rulesList, context }) {
        const items = {};
        rulesList.querySelectorAll('[data-rule]').forEach((li) => { items[li.dataset.rule] = li; });
        const lengthLabel = items.length ? items.length.textContent : '';

        function render(markFailures) {
            const { email, name } = context ? context() : {};
            const problems = passwordProblems(input.value, email, name);
            const tooLong = problems.includes('too_long');
            if (items.length) {
                items.length.textContent = tooLong ? '72 characters or fewer' : lengthLabel;
            }
            Object.entries(items).forEach(([rule, li]) => {
                const broken = rule === 'length' ? (problems.includes('length') || tooLong) : problems.includes(rule);
                const met = input.value.length > 0 && !broken;
                li.classList.toggle('is-met', met);
                li.classList.toggle('is-failed', broken && (markFailures || (tooLong && rule === 'length')));
            });
            return problems.length === 0;
        }

        input.addEventListener('input', () => render(false));

        if (toggle) {
            toggle.addEventListener('click', () => {
                const showing = input.type === 'text';
                input.type = showing ? 'password' : 'text';
                toggle.textContent = showing ? 'Show' : 'Hide';
                toggle.setAttribute('aria-pressed', String(!showing));
                toggle.setAttribute('aria-label', showing ? 'Show password' : 'Hide password');
                // Keep typing where you were -- tapping the toggle on a
                // phone shouldn't dismiss the keyboard mid-password.
                const end = input.value.length;
                input.focus();
                try { input.setSelectionRange(end, end); } catch (e) { /* not all types support it */ }
            });
        }

        render(false);
        return { check: () => render(true), refresh: () => render(false) };
    }

    function setupRevealToggle(input, toggle) {
        setupPasswordField({ input, toggle, rulesList: document.createElement('ul') });
    }

    // ---- dead links ------------------------------------------------------

    const DEAD_LINK_COPY = {
        signup: {
            expired: {
                title: 'This link has expired',
                body: 'Setup links work for 72 hours. We can send a fresh one to the same email.',
                resend: true,
            },
            superseded: {
                title: "There's a newer link",
                body: 'You asked for another link after this one, so this one no longer works. Use the newest email, or we can send a fresh one.',
                resend: true,
            },
            used: {
                title: "You're already set up",
                body: 'This link was already used to create your account. Sign in with the password you chose.',
                signIn: true,
            },
            account_exists: {
                title: 'You already have an account',
                body: 'There is already an Abstractly account with this email. Sign in, or reset your password if you have forgotten it.',
                signIn: true,
            },
            invalid: {
                title: "This link doesn't work",
                body: 'It may have been cut off when it was copied. Try the button in the email again, or start over.',
                startOver: { href: 'signup.html', label: 'Start over' },
            },
        },
        reset: {
            expired: {
                title: 'This link has expired',
                body: 'Reset links work for 1 hour. We can send a fresh one to the same email.',
                resend: true,
            },
            superseded: {
                title: "There's a newer link",
                body: 'You asked for another reset link after this one, so this one no longer works. Use the newest email, or we can send a fresh one.',
                resend: true,
            },
            used: {
                title: 'This link was already used',
                body: 'Your password was already changed with this link. Sign in with your new password, or get a fresh link.',
                signIn: true,
                resend: true,
            },
            invalid: {
                title: "This link doesn't work",
                body: 'It may have been cut off when it was copied. Try the button in the email again, or request a new link.',
                startOver: { href: 'forgot-password.html', label: 'Request a new link' },
            },
        },
    };

    // Static, trusted SVG markup (no user data), one per link state.
    const svg = (paths) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths}</svg>`;
    const DEAD_LINK_ICONS = {
        expired: svg('<circle cx="12" cy="12" r="9"/><path d="M12 7.5v5l3 2"/>'),
        superseded: svg('<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3.5 6.5l8.5 6.5 8.5-6.5"/>'),
        used: svg('<path d="M5 12.5l4.5 4.5L19 7.5"/>'),
        account_exists: svg('<circle cx="12" cy="8" r="3.5"/><path d="M5 20c1.2-3.5 4-5 7-5s5.8 1.5 7 5"/>'),
        invalid: svg('<path d="M10 14a4 4 0 005.66 0l3-3a4 4 0 00-5.66-5.66l-1 1"/><path d="M14 10a4 4 0 00-5.66 0l-3 3a4 4 0 005.66 5.66l1-1"/><path d="M4 4l16 16"/>'),
    };

    /**
     * Fills the page's `data-view="dead"` card for a link that can't be
     * used, and wires "Send me a new link" to /auth/resend-link (which
     * sends to the address the old link went to, so nothing is retyped).
     */
    function showDeadLink(kind, status, token) {
        const copy = DEAD_LINK_COPY[kind][status] || DEAD_LINK_COPY[kind].invalid;
        const view = document.querySelector('[data-view="dead"]');
        const icon = view.querySelector('.auth-icon');
        if (icon) icon.innerHTML = DEAD_LINK_ICONS[status] || DEAD_LINK_ICONS.invalid;
        view.querySelector('[data-dead="title"]').textContent = copy.title;
        view.querySelector('[data-dead="body"]').textContent = copy.body;
        const actions = view.querySelector('[data-dead="actions"]');
        const statusEl = view.querySelector('[data-dead="status"]');
        actions.textContent = '';
        setStatus(statusEl, '');

        const loggedIn = Boolean(getToken());
        if (copy.signIn) {
            const a = document.createElement('a');
            a.className = 'auth-button';
            a.href = loggedIn ? 'index.html' : 'login.html';
            a.textContent = loggedIn ? 'Go to your dashboard' : 'Sign in';
            actions.append(a);
        }
        if (copy.resend && token) {
            const button = document.createElement('button');
            button.type = 'button';
            button.className = copy.signIn ? 'auth-button is-secondary' : 'auth-button';
            button.textContent = 'Send me a new link';
            button.addEventListener('click', async () => {
                if (button.disabled) return;
                setBusy(button, 'Sending...');
                try {
                    const { ok, data } = await request('/auth/resend-link', {
                        method: 'POST',
                        body: { kind, token },
                        onSlow: () => setStatus(statusEl, 'Still working. The server may be waking up, which can take up to a minute.'),
                    });
                    if (!ok) throw new Error(data.error || 'Something went wrong. Please try again.');
                    setStatus(statusEl, data.message || 'Sent. Check your inbox for the new link.', 'success');
                    clearBusy(button);
                    // A short cooldown: enough to stop a second click
                    // sending a second email (which would kill the first
                    // link), short enough to retry if nothing arrives.
                    button.disabled = true;
                    button.textContent = 'Sent';
                    setTimeout(() => { button.disabled = false; button.textContent = 'Send another link'; }, 30000);
                } catch (err) {
                    clearBusy(button);
                    setStatus(statusEl, err.message, 'error');
                }
            });
            actions.append(button);
        }
        if (copy.signIn && kind === 'signup') {
            const a = document.createElement('a');
            a.className = 'auth-button is-secondary';
            a.href = 'forgot-password.html';
            a.textContent = 'Forgot your password?';
            actions.append(a);
        }
        if (copy.startOver) {
            const a = document.createElement('a');
            a.className = 'auth-button';
            a.href = copy.startOver.href;
            a.textContent = copy.startOver.label;
            actions.append(a);
        }
        showView('dead');
    }

    window.Auth = {
        MIN_LENGTH,
        request,
        getToken,
        clearToken,
        finishLogin,
        setBusy,
        clearBusy,
        setStatus,
        showView,
        setFieldError,
        handleSubmit,
        takeLinkToken,
        forgetLinkToken,
        passwordProblems,
        setupPasswordField,
        setupRevealToggle,
        showDeadLink,
    };
})();
