/**
 * "Set your password" page, reached two ways:
 *
 *  - Setup (`?token=`): a brand-new team's first admin, via the setup
 *    link from POST /owner/teams (emailed, or copied from the owner
 *    console if email isn't configured). The single-use, 7-day token is
 *    posted to /auth/team-setup -- same validate-and-consume shape as
 *    reset-password.js's /auth/reset-password, just a longer-lived token.
 *    Not pre-validated on page load; on success, on to the login page.
 *
 *  - Invite (`?kind=invite&token=`): a teammate a team admin invited
 *    (POST /team/invites). The 72-hour token is taken out of the address
 *    bar at once (Auth.takeLinkToken), checked with /auth/invite-status
 *    so a dead link gets a clear message before anyone types a password,
 *    then posted to /auth/accept-invite, which joins the team and signs
 *    them straight in.
 *
 * API_BASE_URL comes from ../config.js; Auth from auth-common.js. Both
 * are loaded before this script.
 */

const isInvite = new URLSearchParams(window.location.search).get('kind') === 'invite';
const INVITE_TOKEN_KEY = 'inviteToken';
const setupToken = isInvite ? Auth.takeLinkToken(INVITE_TOKEN_KEY) : new URLSearchParams(window.location.search).get('token');

const setupFormEl = document.getElementById('setupForm');
const setupMessageEl = document.getElementById('setupMessage');
const deadLinkNoteEl = document.getElementById('setupDeadLinkNote');

// The invitee, from /auth/invite-status -- for the "not your email or
// name" password rule and the password manager's username.
let invitee = { email: '', name: '' };

function showDeadLink(message) {
    setupFormEl.hidden = true;
    setupMessageEl.textContent = message;
    setupMessageEl.classList.add('is-error');
    deadLinkNoteEl.hidden = false;
}

const INVITE_DEAD_LINK_MESSAGES = {
    expired: 'This invite link has expired.',
    used: 'This invite link has already been used. If you set your password, sign in instead.',
    superseded: 'A newer invite was sent, so this link no longer works. Use the link in the newest email.',
    invalid: "This invite link isn't valid. It may have been revoked, or copied incompletely.",
};

const PASSWORD_PROBLEM_MESSAGES = {
    length: `Use at least ${Auth.MIN_LENGTH} characters.`,
    too_long: 'That password is too long. Use 72 characters or fewer.',
    common: "That password is too common. Try a short phrase that's easy for you to remember.",
    personal: "Don't use your email or name as your password.",
};

async function checkInviteLink() {
    try {
        const { ok, data } = await Auth.request('/auth/invite-status', { method: 'POST', body: { token: setupToken } });
        if (!ok) throw new Error(data.error || 'Something went wrong. Please try again.');
        if (data.status !== 'valid') {
            Auth.forgetLinkToken(INVITE_TOKEN_KEY);
            showDeadLink(INVITE_DEAD_LINK_MESSAGES[data.status] || INVITE_DEAD_LINK_MESSAGES.invalid);
            return;
        }
        invitee = { email: data.email || '', name: data.first_name && data.first_name !== 'there' ? data.first_name : '' };
        document.getElementById('username').value = invitee.email;
        document.getElementById('setupHeading').textContent = data.team_name ? `Join ${data.team_name}` : 'Join your team';
        const greeting = invitee.name ? `Hi ${invitee.name}. ` : '';
        document.getElementById('setupSubtitle').textContent =
            `${greeting}Choose a password for ${invitee.email} to join your team on Abstractly. At least ${Auth.MIN_LENGTH} characters. Nobody at Abstractly will see it.`;
    } catch (err) {
        // Network trouble: leave the form up; submitting re-checks the link anyway.
        setupMessageEl.textContent = err.message;
        setupMessageEl.classList.add('is-error');
    }
}

if (isInvite) {
    deadLinkNoteEl.textContent = 'Ask your team admin to send you a new invite.';
    document.getElementById('setupSubmitBtn').textContent = 'Join team';
    if (setupToken) {
        checkInviteLink();
    } else {
        showDeadLink(INVITE_DEAD_LINK_MESSAGES.invalid);
    }
} else if (!setupToken) {
    showDeadLink('This setup link is invalid or incomplete.');
}

async function submitInvite(password) {
    const { ok, data } = await Auth.request('/auth/accept-invite', {
        method: 'POST',
        body: { token: setupToken, new_password: password, remember: false },
        onSlow: () => { setupMessageEl.textContent = 'Still working. The server may be waking up, which can take up to a minute.'; },
    });
    if (ok) {
        Auth.forgetLinkToken(INVITE_TOKEN_KEY);
        Auth.finishLogin(data);
        return;
    }
    const err = new Error(data.error || 'Something went wrong. Please try again.');
    if (data.link_status) {
        Auth.forgetLinkToken(INVITE_TOKEN_KEY);
        err.deadMessage = INVITE_DEAD_LINK_MESSAGES[data.link_status] || INVITE_DEAD_LINK_MESSAGES.invalid;
    }
    throw err;
}

setupFormEl.addEventListener('submit', async (e) => {
    e.preventDefault();

    const passwordInput = document.getElementById('setupPassword');
    const confirmInput = document.getElementById('setupPasswordConfirm');
    const submitBtn = document.getElementById('setupSubmitBtn');
    if (submitBtn.disabled) return;
    const idleLabel = isInvite ? 'Join team' : 'Set password and continue';

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
    // Same rules the server applies (password_rules.py) for both kinds of
    // link, so a too-short password is caught here, not by the server.
    const problems = Auth.passwordProblems(password, invitee.email, invitee.name);
    if (problems.length) {
        setupMessageEl.textContent = PASSWORD_PROBLEM_MESSAGES[problems[0]];
        setupMessageEl.classList.add('is-error');
        passwordInput.focus();
        return;
    }

    submitBtn.disabled = true;
    submitBtn.textContent = 'Saving...';

    try {
        if (isInvite) {
            await submitInvite(password);
            return;
        }

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
            // Only the server's `link_status` means the link itself is
            // dead (invalid, used, expired) -- retrying it can never
            // succeed. Any other 400 is about the password: the link
            // still works, so the form stays up. (Deciding this from the
            // error text once sent people with a 9-character password to
            // a "this link is dead" screen.)
            err.tokenDead = Boolean(data.link_status);
            throw err;
        }

        window.location.href = 'login.html?setup=1';
    } catch (err) {
        if (err.deadMessage) {
            showDeadLink(err.deadMessage);
            return;
        }
        setupMessageEl.textContent = err.message;
        setupMessageEl.classList.add('is-error');
        if (err.tokenDead) {
            setupFormEl.hidden = true;
            deadLinkNoteEl.hidden = false;
        } else {
            submitBtn.disabled = false;
            submitBtn.textContent = idleLabel;
            passwordInput.value = '';
            confirmInput.value = '';
            passwordInput.focus();
        }
    }
});
