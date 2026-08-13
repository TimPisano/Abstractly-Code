/**
 * Admin waitlist view: lists signups and lets you flip a signup to
 * 'approved'. Talks to the unauthenticated /waitlist endpoints — see
 * the NOTE in index.html and backend/app/api.py about locking this
 * down before real launch.
 */

const API_BASE_URL = 'http://localhost:5000';

function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    const div = document.createElement('div');
    div.textContent = String(str);
    return div.innerHTML;
}

function formatDate(isoString) {
    if (!isoString) return '—';
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return isoString;
    return d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
}

const WaitlistAdmin = {
    signups: [],

    async load() {
        const content = document.getElementById('waitlistContent');
        try {
            const response = await fetch(`${API_BASE_URL}/waitlist`);
            if (!response.ok) throw new Error(`Server returned ${response.status}`);
            this.signups = await response.json();
            this.render();
        } catch (err) {
            content.innerHTML = `<p class="error-text">Failed to load waitlist: ${escapeHtml(err.message)}</p>`;
        }
    },

    render() {
        this.renderStats();

        const content = document.getElementById('waitlistContent');
        if (this.signups.length === 0) {
            content.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon">
                        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M18 18.72a9.094 9.094 0 003.741-.479 3 3 0 00-4.682-2.72m.94 3.198l.001.031c0 .225-.012.447-.037.666A11.944 11.944 0 0112 21c-2.17 0-4.207-.576-5.963-1.584A6.062 6.062 0 016 18.719m12 0a5.971 5.971 0 00-.941-3.197m0 0A5.995 5.995 0 0012 12.75a5.995 5.995 0 00-5.058 2.772m0 0a3 3 0 00-4.681 2.72 8.986 8.986 0 003.74.477m.94-3.197a5.971 5.971 0 00-.94 3.197M15 6.75a3 3 0 11-6 0 3 3 0 016 0zm6 3a2.25 2.25 0 11-4.5 0 2.25 2.25 0 014.5 0zm-13.5 0a2.25 2.25 0 11-4.5 0 2.25 2.25 0 014.5 0z"/></svg>
                    </div>
                    <p class="empty-state-title">No signups yet</p>
                    <p class="empty-state-hint">Once people join the waitlist from the landing page, they'll show up here.</p>
                </div>
            `;
            return;
        }

        content.innerHTML = `
            <table class="waitlist-table">
                <thead>
                    <tr>
                        <th>Email</th>
                        <th>Joined</th>
                        <th>Status</th>
                        <th></th>
                    </tr>
                </thead>
                <tbody>
                    ${this.signups.map(s => `
                        <tr>
                            <td>${escapeHtml(s.email)}</td>
                            <td>${escapeHtml(formatDate(s.created_at))}</td>
                            <td><span class="status-pill status-${escapeHtml(s.status)}">${escapeHtml(s.status)}</span></td>
                            <td>
                                <button class="btn-secondary approve-btn" data-id="${s.id}" ${s.status === 'approved' ? 'disabled' : ''}>
                                    ${s.status === 'approved' ? 'Approved' : 'Approve'}
                                </button>
                            </td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        `;

        content.querySelectorAll('.approve-btn:not(:disabled)').forEach(btn => {
            btn.addEventListener('click', () => this.approve(parseInt(btn.dataset.id, 10)));
        });
    },

    renderStats() {
        const total = this.signups.length;
        const approved = this.signups.filter(s => s.status === 'approved').length;
        const pending = total - approved;

        document.getElementById('adminStats').innerHTML = `
            <div class="admin-stat-tile">
                <div class="admin-stat-value">${total}</div>
                <div class="admin-stat-label">Total signups</div>
            </div>
            <div class="admin-stat-tile">
                <div class="admin-stat-value">${pending}</div>
                <div class="admin-stat-label">Pending</div>
            </div>
            <div class="admin-stat-tile">
                <div class="admin-stat-value">${approved}</div>
                <div class="admin-stat-label">Approved</div>
            </div>
        `;
    },

    async approve(id) {
        try {
            const response = await fetch(`${API_BASE_URL}/waitlist/${id}/approve`, { method: 'POST' });
            if (!response.ok) throw new Error(`Server returned ${response.status}`);
            const signup = this.signups.find(s => s.id === id);
            if (signup) signup.status = 'approved';
            this.render();
        } catch (err) {
            alert(`Failed to approve: ${err.message}`);
        }
    },
};

document.getElementById('refreshBtn').addEventListener('click', () => WaitlistAdmin.load());
WaitlistAdmin.load();
