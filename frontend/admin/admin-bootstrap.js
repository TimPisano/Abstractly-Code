/**
 * Admin dashboard bootstrap.
 *
 * Two independent jobs:
 *  1. Gate the page on a real, admin-role session (GET /auth/session) --
 *     redirect to the login page if it isn't authenticated OR isn't
 *     admin-role. This is real auth (see backend/app/auth.py), shared
 *     with the main app's login now (there is no separate admin-only
 *     login system anymore -- see DECISIONS.md).
 *  2. Register the "Access Requests" panel as a fourth view in the same
 *     router frontend/app/app.js already defines (registerView/showView),
 *     alongside 'dashboard' (admin-dashboard-view.js), 'upload'
 *     (admin-upload-view.js), and 'detail' (admin-detail-view.js) -- all
 *     four are wired into the same left sidebar (`.sidebar`/`.nav-item
 *     [data-view]`) frontend/app/index.html uses, via app.js's
 *     initSidebar()/showView(). The sidebar's other items (Alerts,
 *     Discrepancies, Portfolio Trends, Reports/Exports, Team, Activity)
 *     are plain links out to frontend/app/ instead of a fifth-through-
 *     tenth view registered here -- those features already exist there,
 *     fully built; duplicating them into this admin-only surface would
 *     mean maintaining two copies. See DECISIONS.md.
 *
 * Every request here that touches an admin-only route uses
 * `credentials: 'include'` and treats a 401 as "the session ended, go
 * back to the login page" -- see login.js's comment for why the cookie
 * needs `credentials: 'include'` at all (frontend and backend are
 * different origins in dev). Requests that go through Api (api.js) don't
 * need this -- /leases and friends aren't admin-gated, same as the
 * client app.
 *
 * API_BASE_URL comes from ../config.js. app.js (AppState, registerView,
 * showView, showToast, showError, escapeHtml, formatDate, init, ...) and
 * every view module are loaded as plain static <script> tags before this
 * one, in dashboard.html -- no dynamic script loading is needed here
 * (unlike the client app's access-gate.js): a view's own API calls only
 * ever fire from its load() method, which only ever runs once init()
 * (called at the bottom of this file) invokes showView(), so there's no
 * risk of a view fetching data before the session check below settles.
 */

// `treatAsSessionExpiry` defaults true: for nearly every route here, a
// 401 really does mean "the session ended, go back to the login page."
// POST /auth/change-password is the one exception -- it also returns
// 401 for "current password is incorrect" (see backend/app/api.py),
// which has nothing to do with the session and would otherwise silently
// bounce someone to the login page with no error shown, mid-typo, while
// still fully logged in. Callers for that route pass `false` to get the
// normal error-message path instead of the redirect.
async function adminFetch(path, options = {}, treatAsSessionExpiry = true) {
    let response;
    try {
        response = await fetch(`${API_BASE_URL}${path}`, { ...options, credentials: 'include' });
    } catch (networkErr) {
        throw new Error("Couldn't reach the server. Is the backend running?");
    }
    if (response.status === 401 && treatAsSessionExpiry) {
        window.location.href = 'index.html';
        // Never resolves -- the redirect above is already underway, and
        // nothing calling this should keep running against a session
        // that just turned out to be invalid.
        return new Promise(() => {});
    }
    if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.error || `Server returned ${response.status}`);
    }
    return response.json();
}

function accessStatusLabel(status) {
    if (status === 'approved') return 'Access Granted';
    if (status === 'denied') return 'Denied';
    return 'Pending Review';
}

const AccessRequests = {
    signups: [],

    load() {
        this.loadWaitlist();
    },

    async loadWaitlist() {
        const content = document.getElementById('waitlistContent');
        content.innerHTML = '<p class="admin-loading"><span class="spinner-small"></span> Loading...</p>';
        try {
            this.signups = await adminFetch('/waitlist');
            this.renderWaitlist();
        } catch (err) {
            content.innerHTML = `<p class="error-text">Failed to load access requests: ${escapeHtml(err.message)}</p>`;
        }
    },

    renderWaitlist() {
        const total = this.signups.length;
        const pending = this.signups.filter(s => s.status === 'pending').length;
        const approved = this.signups.filter(s => s.status === 'approved').length;
        document.getElementById('waitlistStats').innerHTML = `
            <div class="admin-stat-tile">
                <div class="admin-stat-value">${total}</div>
                <div class="admin-stat-label">Total requests</div>
            </div>
            <div class="admin-stat-tile">
                <div class="admin-stat-value">${pending}</div>
                <div class="admin-stat-label">Pending review</div>
            </div>
            <div class="admin-stat-tile">
                <div class="admin-stat-value">${approved}</div>
                <div class="admin-stat-label">Access granted</div>
            </div>
        `;

        const content = document.getElementById('waitlistContent');
        if (this.signups.length === 0) {
            content.innerHTML = '<p class="admin-empty">No access requests yet. Once someone requests access from the landing page, they\'ll show up here.</p>';
            return;
        }

        content.innerHTML = `
            <table class="admin-table">
                <thead>
                    <tr><th>Email</th><th>Requested</th><th>Status</th><th></th></tr>
                </thead>
                <tbody>
                    ${this.signups.map(s => `
                        <tr>
                            <td>${escapeHtml(s.email)}</td>
                            <td>${escapeHtml(formatDate(s.created_at))}</td>
                            <td><span class="status-pill status-${escapeHtml(s.status)}">${escapeHtml(accessStatusLabel(s.status))}</span></td>
                            <td>
                                <div class="admin-row-actions">
                                    <button class="btn-secondary approve-btn" data-id="${s.id}" ${s.status === 'approved' ? 'disabled' : ''}>
                                        ${s.status === 'approved' ? 'Granted' : 'Approve'}
                                    </button>
                                    <button class="btn-secondary btn-deny deny-btn" data-id="${s.id}" ${s.status === 'denied' ? 'disabled' : ''}>
                                        ${s.status === 'denied' ? 'Denied' : 'Deny'}
                                    </button>
                                </div>
                            </td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        `;

        content.querySelectorAll('.approve-btn:not(:disabled)').forEach(btn => {
            btn.addEventListener('click', () => this.decide(parseInt(btn.dataset.id, 10), 'approve'));
        });
        content.querySelectorAll('.deny-btn:not(:disabled)').forEach(btn => {
            btn.addEventListener('click', () => this.decide(parseInt(btn.dataset.id, 10), 'deny'));
        });
    },

    async decide(id, action) {
        const signup = this.signups.find(s => s.id === id);
        const who = signup ? signup.email : 'this request';

        // Approve grants access -- reversible by denying afterward, and
        // not destructive, so no confirmation. Deny is the one an admin
        // could easily misclick in a long list, and it turns away a real
        // prospective user -- confirm it, same as every other
        // destructive action in this app (bulk delete, single lease
        // delete).
        if (action === 'deny' && !(await confirmDialog({
            title: 'Deny access?',
            message: `${who} won't be able to sign in. You can approve them later if this was a mistake.`,
            confirmText: 'Deny access',
            danger: true,
        }))) {
            return;
        }

        try {
            await adminFetch(`/waitlist/${id}/${action}`, { method: 'POST' });
            if (signup) signup.status = action === 'approve' ? 'approved' : 'denied';
            this.renderWaitlist();
            showToast(action === 'approve' ? `Access granted to ${who}.` : `Denied ${who}.`, 'success');
        } catch (err) {
            showError(`Failed to ${action} this request: ${err.message}`);
        }
    },
};

registerView('access', AccessRequests);

/**
 * Settings view: just Change Password for now (POST /auth/change-
 * password, added by this session's real multi-user auth work -- any
 * logged-in role may change their own password). No team-member
 * management here since /team/members isn't a real backend route yet
 * -- see DECISIONS.md.
 */
const Settings = {
    load() {
        const form = document.getElementById('changePasswordForm');
        form.reset();
        const msg = document.getElementById('changePasswordMessage');
        msg.style.display = 'none';
        msg.classList.remove('is-error');
    },

    async changePassword(currentPassword, newPassword) {
        const msg = document.getElementById('changePasswordMessage');
        const btn = document.getElementById('changePasswordSubmitBtn');
        msg.style.display = 'none';
        msg.classList.remove('is-error');
        btn.disabled = true;
        btn.textContent = 'Updating...';
        try {
            await adminFetch('/auth/change-password', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
            }, false);
            document.getElementById('changePasswordForm').reset();
            showToast('Password updated.', 'success');
        } catch (err) {
            msg.textContent = err.message;
            msg.classList.add('is-error');
            msg.style.display = 'block';
        } finally {
            btn.disabled = false;
            btn.textContent = 'Update Password';
        }
    },
};

registerView('settings', Settings);

function _initSettingsViewBindings() {
    document.getElementById('changePasswordForm').addEventListener('submit', (e) => {
        e.preventDefault();
        const current = document.getElementById('currentPasswordInput').value;
        const next = document.getElementById('newPasswordInput').value;
        Settings.changePassword(current, next);
    });
}
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _initSettingsViewBindings);
} else {
    _initSettingsViewBindings();
}

async function initAdminDashboard() {
    let session;
    try {
        session = await fetch(`${API_BASE_URL}/auth/session`, { credentials: 'include' }).then(r => r.json());
    } catch (err) {
        session = { authenticated: false };
    }
    // Session is shared across every role now (/auth/session, not an
    // admin-only endpoint) -- this mini-SPA is still admin-only, so it
    // must check the role, not just "is anyone logged in". A logged-in
    // analyst/viewer navigating here directly gets sent back to the
    // login page exactly like an unauthenticated visitor would.
    if (!session.authenticated || session.role !== 'admin') {
        window.location.href = 'index.html';
        return;
    }

    document.getElementById('adminEmailLabel').textContent = session.email || '';
    document.getElementById('adminShell').style.display = 'flex';

    document.getElementById('refreshBtn').addEventListener('click', () => {
        const activeView = document.querySelector('.view.active');
        if (activeView) showView(activeView.id.replace('view-', ''));
    });

    document.getElementById('logoutBtn').addEventListener('click', async () => {
        try {
            await fetch(`${API_BASE_URL}/auth/logout`, { method: 'POST', credentials: 'include' });
        } catch (err) {
            // Even if the request fails, still send the operator back to
            // the login page -- there's nothing useful to do here besides
            // that regardless of why logout's own request failed.
        }
        window.location.href = 'index.html';
    });

    // app.js's init() wires every .nav-item[data-view] click, wires the
    // session-stats panel, and lands on whatever view the URL hash names
    // (falling back to 'dashboard' if there isn't one or it doesn't
    // match a registered view -- see app.js's own comment on that
    // fallback). That default is right for frontend/app/index.html
    // (where 'dashboard' IS the true landing view), but wrong here --
    // this page's home view is 'overview' ("Dashboard" in the sidebar),
    // with 'dashboard' now meaning the Leases & Rent Rolls table
    // specifically. Setting the hash before init() runs (only when the
    // page was opened with no hash already) reuses that same fallback
    // mechanism instead of duplicating or overriding init() itself.
    if (!location.hash) location.hash = 'overview';
    window.init();
}

initAdminDashboard();
