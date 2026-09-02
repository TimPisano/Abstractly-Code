/**
 * Owner console. Deliberately a small, standalone script -- does NOT
 * pull in frontend/app/app.js's registerView/showView router (that's
 * built around the main app's much larger view set); two tabs don't
 * need it. Every request uses credentials:'include' (cross-origin
 * cookie, same as admin/login.js and admin/admin-bootstrap.js) and
 * treats a 401 as "session ended, back to login" the same way
 * adminFetch does; a non-owner 404 is shown as a plain access error
 * rather than assumed to be a real 404 (this page only ever calls
 * /owner/* routes, so any 404 here means "not an owner", not "bad
 * URL").
 */

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str == null ? '' : String(str);
    return div.innerHTML;
}

function formatMoney(n) {
    const sign = n < 0 ? '-' : '';
    return `${sign}$${Math.abs(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function formatDate(iso) {
    if (!iso) return '—';
    const d = new Date(iso);
    if (isNaN(d)) return iso;
    return d.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
}

async function ownerFetch(path, options = {}) {
    let response;
    try {
        response = await fetch(`${API_BASE_URL}${path}`, { ...options, credentials: 'include' });
    } catch (networkErr) {
        throw new Error("Couldn't reach the server. Is the backend running?");
    }
    if (response.status === 401) {
        window.location.href = 'login.html';
        return new Promise(() => {});
    }
    if (response.status === 404) {
        // Every route this page calls is /owner/* -- a 404 here always
        // means "this session isn't an owner" (see require_owner's
        // deliberate 401-vs-404 design), never a real missing route.
        throw new Error('This account does not have owner access.');
    }
    if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.error || `Server returned ${response.status}`);
    }
    if (response.status === 204) return null;
    return response.json();
}

function showToast(message, kind = 'success') {
    const el = document.createElement('div');
    el.textContent = message;
    el.style.cssText = `position:fixed;bottom:1.5rem;right:1.5rem;padding:0.75rem 1.25rem;border-radius:8px;font-size:0.875rem;color:#fff;z-index:200;box-shadow:0 4px 12px rgba(0,0,0,0.2);background:${kind === 'error' ? '#9a3b3b' : '#2f6b4f'};`;
    document.body.appendChild(el);
    setTimeout(() => el.remove(), 3500);
}

/* ===================== Accounts panel ===================== */

const Accounts = {
    accounts: [],

    async load() {
        const content = document.getElementById('accountsContent');
        content.innerHTML = '<p class="loading-inline"><span class="spinner-small"></span> Loading accounts…</p>';
        try {
            const params = new URLSearchParams();
            const email = document.getElementById('filterEmail').value.trim();
            const status = document.getElementById('filterStatus').value;
            const after = document.getElementById('filterSignupAfter').value;
            const before = document.getElementById('filterSignupBefore').value;
            if (email) params.set('email', email);
            if (status) params.set('status', status);
            if (after) params.set('signup_after', after);
            if (before) params.set('signup_before', before);

            this.accounts = await ownerFetch(`/owner/accounts?${params.toString()}`);
            this.render();
        } catch (err) {
            content.innerHTML = `<p class="error-text">Failed to load accounts: ${escapeHtml(err.message)}</p>`;
        }
    },

    render() {
        const content = document.getElementById('accountsContent');
        if (this.accounts.length === 0) {
            content.innerHTML = '<p class="owner-empty">No accounts match these filters.</p>';
            return;
        }
        content.innerHTML = `
            <table class="owner-table">
                <thead>
                    <tr><th>Email</th><th>Role</th><th>Status</th><th>Signed up</th><th>Last login</th><th>Activity</th></tr>
                </thead>
                <tbody>
                    ${this.accounts.map(a => `
                        <tr>
                            <td><span class="owner-row-link" data-id="${a.id}">${escapeHtml(a.email)}</span></td>
                            <td>${escapeHtml(a.role)}</td>
                            <td><span class="owner-status-pill owner-status-${escapeHtml(a.status)}">${escapeHtml(a.status)}</span></td>
                            <td>${escapeHtml(formatDate(a.created_at))}</td>
                            <td>${escapeHtml(formatDate(a.last_login_at))}</td>
                            <td>${a.usage.tasks_created + a.usage.tasks_assigned + a.usage.field_edits + a.usage.discrepancies_resolved + a.usage.comments_posted} actions</td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        `;
        content.querySelectorAll('.owner-row-link').forEach(el => {
            el.addEventListener('click', () => this.openDetail(parseInt(el.dataset.id, 10)));
        });
    },

    async openDetail(id) {
        const overlay = document.getElementById('accountModalOverlay');
        const body = document.getElementById('accountModalContent');
        overlay.style.display = 'flex';
        body.innerHTML = '<p class="loading-inline"><span class="spinner-small"></span> Loading…</p>';
        try {
            const account = await ownerFetch(`/owner/accounts/${id}`);
            this.renderDetail(account);
        } catch (err) {
            body.innerHTML = `<p class="error-text">${escapeHtml(err.message)}</p>`;
        }
    },

    renderDetail(a) {
        const body = document.getElementById('accountModalContent');
        const u = a.usage;
        body.innerHTML = `
            <h2>${escapeHtml(a.name)} &lt;${escapeHtml(a.email)}&gt;</h2>
            <p>Role: <strong>${escapeHtml(a.role)}</strong> &middot; Status: <span class="owner-status-pill owner-status-${escapeHtml(a.status)}">${escapeHtml(a.status)}</span></p>
            <p>Signed up ${escapeHtml(formatDate(a.created_at))} &middot; Last login ${escapeHtml(formatDate(a.last_login_at))}</p>
            <div class="owner-modal-stats">
                <div class="owner-modal-stat"><div class="owner-modal-stat-value">${u.tasks_created}</div><div class="owner-modal-stat-label">Tasks created</div></div>
                <div class="owner-modal-stat"><div class="owner-modal-stat-value">${u.tasks_assigned}</div><div class="owner-modal-stat-label">Tasks assigned</div></div>
                <div class="owner-modal-stat"><div class="owner-modal-stat-value">${u.tasks_completed}</div><div class="owner-modal-stat-label">Tasks completed</div></div>
                <div class="owner-modal-stat"><div class="owner-modal-stat-value">${u.field_edits}</div><div class="owner-modal-stat-label">Field edits made</div></div>
                <div class="owner-modal-stat"><div class="owner-modal-stat-value">${u.discrepancies_resolved}</div><div class="owner-modal-stat-label">Discrepancies resolved</div></div>
                <div class="owner-modal-stat"><div class="owner-modal-stat-value">${u.comments_posted}</div><div class="owner-modal-stat-label">Comments posted</div></div>
            </div>
            <p class="owner-entry-row-meta">These counts are per-login activity, not per-customer usage -- this app has no separate customer/tenant data yet, and there's no record of which login uploaded a given lease or rent roll.</p>
            <div class="owner-modal-actions">
                ${a.status === 'active'
                    ? `<button class="btn-danger" id="suspendBtn">Suspend Account</button>`
                    : `<button class="btn-secondary" id="reactivateBtn">Reactivate Account</button>`}
                <div class="owner-reset-pw-row">
                    <input type="password" id="resetPwInput" class="text-input" placeholder="New password (8+ chars)">
                    <button class="btn-secondary" id="resetPwBtn">Reset Password</button>
                </div>
            </div>
        `;

        const suspendBtn = document.getElementById('suspendBtn');
        if (suspendBtn) {
            suspendBtn.addEventListener('click', async () => {
                if (!confirm(`Suspend ${a.email}? They will not be able to log in until reactivated.`)) return;
                try {
                    await ownerFetch(`/owner/accounts/${a.id}/suspend`, { method: 'POST' });
                    showToast(`${a.email} suspended.`);
                    this.closeModal();
                    this.load();
                } catch (err) {
                    showToast(err.message, 'error');
                }
            });
        }
        const reactivateBtn = document.getElementById('reactivateBtn');
        if (reactivateBtn) {
            reactivateBtn.addEventListener('click', async () => {
                try {
                    await ownerFetch(`/owner/accounts/${a.id}/reactivate`, { method: 'POST' });
                    showToast(`${a.email} reactivated.`);
                    this.closeModal();
                    this.load();
                } catch (err) {
                    showToast(err.message, 'error');
                }
            });
        }
        document.getElementById('resetPwBtn').addEventListener('click', async () => {
            const pw = document.getElementById('resetPwInput').value;
            if (!pw || pw.length < 8) {
                showToast('New password must be at least 8 characters.', 'error');
                return;
            }
            if (!confirm(`Reset the password for ${a.email}?`)) return;
            try {
                await ownerFetch(`/owner/accounts/${a.id}/reset-password`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ new_password: pw }),
                });
                showToast(`Password reset for ${a.email}.`);
                this.closeModal();
            } catch (err) {
                showToast(err.message, 'error');
            }
        });
    },

    closeModal() {
        document.getElementById('accountModalOverlay').style.display = 'none';
    },
};

/* ===================== Finance panel ===================== */

const Finance = {
    revenue: [],
    expenses: [],

    async load() {
        try {
            const [summary, revenue, expenses] = await Promise.all([
                ownerFetch('/owner/finance/summary'),
                ownerFetch('/owner/revenue'),
                ownerFetch('/owner/expenses'),
            ]);
            this.revenue = revenue;
            this.expenses = expenses;
            this.renderTotals(summary);
            this.renderTrend(summary.monthly_trend);
            this.renderEntries();
        } catch (err) {
            showToast(`Failed to load finance data: ${err.message}`, 'error');
        }
    },

    renderTotals(summary) {
        const profitClass = summary.profit >= 0 ? 'is-positive' : 'is-negative';
        document.getElementById('financeTotals').innerHTML = `
            <div class="owner-total-tile">
                <div class="owner-total-value">${formatMoney(summary.total_revenue)}</div>
                <div class="owner-total-label">Total revenue</div>
            </div>
            <div class="owner-total-tile">
                <div class="owner-total-value">${formatMoney(summary.total_expenses)}</div>
                <div class="owner-total-label">Total expenses</div>
            </div>
            <div class="owner-total-tile is-profit">
                <div class="owner-total-value ${profitClass}">${formatMoney(summary.profit)}</div>
                <div class="owner-total-label">Profit</div>
            </div>
        `;
    },

    renderTrend(trend) {
        const el = document.getElementById('financeTrend');
        if (!trend || trend.length === 0) {
            el.innerHTML = '<p class="owner-empty">No entries yet -- add a revenue or expense entry below to see a trend.</p>';
            return;
        }
        const maxVal = Math.max(1, ...trend.map(t => Math.max(t.revenue, t.expenses)));
        el.innerHTML = `
            <div class="owner-trend-legend">
                <span><span class="owner-trend-legend-dot" style="background:var(--success-color)"></span>Revenue</span>
                <span><span class="owner-trend-legend-dot" style="background:var(--error-color)"></span>Expenses</span>
            </div>
            ${trend.map(t => `
                <div class="owner-trend-row">
                    <span>${escapeHtml(t.month)}</span>
                    <div>
                        <div class="owner-trend-bar-track"><div class="owner-trend-bar rev" style="width:${(t.revenue / maxVal * 100).toFixed(1)}%"></div></div>
                        <div class="owner-trend-bar-track" style="margin-top:3px;"><div class="owner-trend-bar exp" style="width:${(t.expenses / maxVal * 100).toFixed(1)}%"></div></div>
                    </div>
                    <span>${formatMoney(t.profit)}</span>
                </div>
            `).join('')}
        `;
    },

    renderEntries() {
        const revList = document.getElementById('revenueList');
        revList.innerHTML = this.revenue.length === 0
            ? '<p class="owner-empty">No revenue entries yet.</p>'
            : this.revenue.map(r => `
                <div class="owner-entry-row">
                    <div>
                        <strong>${formatMoney(r.amount)}</strong> — ${escapeHtml(r.source)}
                        <div class="owner-entry-row-meta">${escapeHtml(formatDate(r.entry_date))}${r.note ? ' · ' + escapeHtml(r.note) : ''}</div>
                    </div>
                    <button class="owner-entry-delete" data-kind="revenue" data-id="${r.id}">Delete</button>
                </div>
            `).join('');

        const expList = document.getElementById('expenseList');
        expList.innerHTML = this.expenses.length === 0
            ? '<p class="owner-empty">No expense entries yet.</p>'
            : this.expenses.map(e => `
                <div class="owner-entry-row">
                    <div>
                        <strong>${formatMoney(e.amount)}</strong> — ${escapeHtml(e.category)}
                        <div class="owner-entry-row-meta">${escapeHtml(formatDate(e.entry_date))}${e.note ? ' · ' + escapeHtml(e.note) : ''}</div>
                    </div>
                    <button class="owner-entry-delete" data-kind="expense" data-id="${e.id}">Delete</button>
                </div>
            `).join('');

        document.querySelectorAll('.owner-entry-delete').forEach(btn => {
            btn.addEventListener('click', async () => {
                const kind = btn.dataset.kind;
                const id = btn.dataset.id;
                if (!confirm('Delete this entry?')) return;
                try {
                    await ownerFetch(`/owner/${kind === 'revenue' ? 'revenue' : 'expenses'}/${id}`, { method: 'DELETE' });
                    this.load();
                } catch (err) {
                    showToast(err.message, 'error');
                }
            });
        });
    },
};

/* ===================== Tabs ===================== */

function switchTab(tab) {
    document.querySelectorAll('.owner-tab').forEach(el => el.classList.toggle('active', el.dataset.tab === tab));
    document.querySelectorAll('.owner-panel').forEach(el => el.classList.toggle('active', el.id === `panel-${tab}`));
    if (tab === 'accounts') Accounts.load();
    if (tab === 'finance') Finance.load();
}

/* ===================== Bootstrap ===================== */

async function initOwnerConsole() {
    let session;
    try {
        session = await fetch(`${API_BASE_URL}/auth/session`, { credentials: 'include' }).then(r => r.json());
    } catch (err) {
        session = { authenticated: false };
    }
    if (!session.authenticated || !session.is_owner) {
        window.location.href = 'login.html';
        return;
    }

    document.getElementById('ownerEmailLabel').textContent = session.email || '';
    document.getElementById('ownerShell').style.display = 'flex';

    document.querySelectorAll('.owner-tab').forEach(el => {
        el.addEventListener('click', () => switchTab(el.dataset.tab));
    });

    document.getElementById('clearFiltersBtn').addEventListener('click', () => {
        document.getElementById('filterEmail').value = '';
        document.getElementById('filterStatus').value = '';
        document.getElementById('filterSignupAfter').value = '';
        document.getElementById('filterSignupBefore').value = '';
        Accounts.load();
    });
    ['filterEmail', 'filterStatus', 'filterSignupAfter', 'filterSignupBefore'].forEach(id => {
        document.getElementById(id).addEventListener('change', () => Accounts.load());
    });
    document.getElementById('filterEmail').addEventListener('keyup', (e) => {
        if (e.key === 'Enter') Accounts.load();
    });

    document.getElementById('accountModalClose').addEventListener('click', () => Accounts.closeModal());
    document.getElementById('accountModalOverlay').addEventListener('click', (e) => {
        if (e.target.id === 'accountModalOverlay') Accounts.closeModal();
    });

    document.getElementById('revenueForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        try {
            await ownerFetch('/owner/revenue', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    date: document.getElementById('revenueDate').value,
                    amount: parseFloat(document.getElementById('revenueAmount').value),
                    source: document.getElementById('revenueSource').value.trim(),
                    note: document.getElementById('revenueNote').value.trim(),
                }),
            });
            document.getElementById('revenueForm').reset();
            showToast('Revenue entry added.');
            Finance.load();
        } catch (err) {
            showToast(err.message, 'error');
        }
    });

    document.getElementById('expenseForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        try {
            await ownerFetch('/owner/expenses', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    date: document.getElementById('expenseDate').value,
                    amount: parseFloat(document.getElementById('expenseAmount').value),
                    category: document.getElementById('expenseCategory').value,
                    note: document.getElementById('expenseNote').value.trim(),
                }),
            });
            document.getElementById('expenseForm').reset();
            showToast('Expense entry added.');
            Finance.load();
        } catch (err) {
            showToast(err.message, 'error');
        }
    });

    document.getElementById('logoutBtn').addEventListener('click', async () => {
        try {
            await fetch(`${API_BASE_URL}/auth/logout`, { method: 'POST', credentials: 'include' });
        } catch (err) {
            // Still navigate away regardless.
        }
        window.location.href = 'login.html';
    });

    Accounts.load();
}

initOwnerConsole();
