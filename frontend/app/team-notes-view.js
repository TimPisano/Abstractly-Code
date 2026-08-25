/**
 * Team Notes View: a portfolio-wide read feed across every comment left
 * on a lease or a discrepancy (see GET /comments/recent), most recent
 * first. Read-only browsing -- posting a NEW note still happens where
 * it always has (the Lease Detail sidebar, or a Discrepancy modal's
 * Discussion section), since a comment requires a specific lease or
 * discrepancy target and this feed spans many of both at once; this
 * view's job is "what has the team been saying, across everything,"
 * not a second place to compose from.
 *
 * Also renders a small "Team" roster above the feed -- who's actually
 * left a note, derived from this same response (no extra request).
 * NOT a real team-management/invite/roles feature: there's no user-
 * accounts system in this app at all (one shared admin login, self-
 * reported names everywhere -- see DECISIONS.md), so there's no real
 * roster to manage. This is honestly just "who this data has seen,"
 * which is what's real and buildable without that backend work.
 */
const TeamNotes = {
    async load() {
        document.getElementById('teamNotesFeedContent').innerHTML = '<p class="loading-inline"><span class="spinner-small"></span> Loading notes...</p>';
        document.getElementById('teamNotesRoster').innerHTML = '';
        try {
            const comments = await Api.recentComments(50);
            this.renderRoster(comments);
            this.render(comments);
        } catch (err) {
            document.getElementById('teamNotesFeedContent').innerHTML = `<p class="error-text">Failed to load team notes: ${escapeHtml(err.message)}</p>`;
        }
    },

    async refresh() {
        const btn = document.getElementById('teamNotesRefreshBtn');
        btn.disabled = true;
        btn.textContent = 'Refreshing...';
        try {
            const comments = await Api.recentComments(50);
            this.renderRoster(comments);
            this.render(comments);
            showToast('Team notes refreshed.', 'success');
        } catch (err) {
            showError(`Failed to refresh: ${err.message}`);
        } finally {
            btn.disabled = false;
            btn.textContent = 'Refresh';
        }
    },

    renderRoster(comments) {
        const el = document.getElementById('teamNotesRoster');
        if (comments.length === 0) {
            el.style.display = 'none';
            return;
        }
        el.style.display = '';
        const counts = new Map();
        comments.forEach(c => counts.set(c.author_name, (counts.get(c.author_name) || 0) + 1));
        const roster = Array.from(counts.entries()).sort((a, b) => b[1] - a[1]);

        el.innerHTML = `
            <div class="panel-header">
                <h2>Team</h2>
                <p class="view-subtitle" style="margin:0;">Who's shown up in the last ${comments.length} note${comments.length === 1 ? '' : 's'} — not managed accounts, just who's been contributing</p>
            </div>
            <div class="team-roster-list">
                ${roster.map(([name, count]) => `
                    <div class="team-roster-item">
                        ${avatarHtml(name, 'team-avatar-lg')}
                        <div>
                            <div class="team-roster-name">${escapeHtml(name)}</div>
                            <div class="team-roster-count">${count} note${count === 1 ? '' : 's'}</div>
                        </div>
                    </div>
                `).join('')}
            </div>
        `;
    },

    render(comments) {
        const el = document.getElementById('teamNotesFeedContent');
        if (comments.length === 0) {
            el.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon">
                        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M8 10h8m-8 4h5M7 3.5h10A2.5 2.5 0 0119.5 6v10.5a1 1 0 01-1.6.8l-2.9-2.175a2 2 0 00-1.2-.4H7A2.5 2.5 0 014.5 12V6A2.5 2.5 0 017 3.5z"/></svg>
                    </div>
                    <p class="empty-state-title">No team notes yet</p>
                    <p class="empty-state-hint">Notes left on a lease or a discrepancy will show up here, most recent first. Open any lease or discrepancy to leave the first one.</p>
                    <button class="btn-primary" data-goto="dashboard" type="button">Go to Dashboard</button>
                </div>
            `;
            const gotoBtn = el.querySelector('[data-goto]');
            if (gotoBtn) gotoBtn.addEventListener('click', () => showView(gotoBtn.dataset.goto));
            return;
        }

        el.innerHTML = `<div class="alerts-list">${comments.map(c => this._cardHtml(c)).join('')}</div>`;
        el.querySelectorAll('.team-note-lease-link').forEach(link => {
            link.addEventListener('click', () => showLeaseDetail(parseInt(link.dataset.leaseId, 10)));
        });
        el.querySelectorAll('.team-note-discrepancy-link').forEach(link => {
            link.addEventListener('click', () => showView('discrepancies'));
        });
    },

    _cardHtml(c) {
        let contextHtml = '';
        if (c.lease_id != null) {
            const name = c.lease_display_name || c.lease_filename || `Lease #${c.lease_id}`;
            contextHtml = `<button class="btn-text team-note-lease-link" data-lease-id="${c.lease_id}" type="button">${escapeHtml(name)} &rarr;</button>`;
        } else if (c.discrepancy_id != null) {
            const label = c.discrepancy_category ? c.discrepancy_category.replace(/_/g, ' ') : `Discrepancy #${c.discrepancy_id}`;
            contextHtml = `<button class="btn-text team-note-discrepancy-link" type="button">Discrepancy: ${escapeHtml(label)} &rarr;</button>`;
        } else {
            contextHtml = `<span class="alert-card-status-tag">Deleted lease</span>`;
        }

        return `
            <div class="alert-card alert-card-low team-note-card">
                ${avatarHtml(c.author_name)}
                <div class="comment-item-body">
                    <div class="alert-card-head">
                        <span class="comment-author">${escapeHtml(c.author_name)}</span>
                        <span class="alert-card-time" title="${escapeHtml(formatDate(c.created_at))}">${timeAgo(c.created_at)}</span>
                    </div>
                    <p class="alert-card-message">${escapeHtml(c.body)}</p>
                    <div class="alert-card-actions">${contextHtml}</div>
                </div>
            </div>
        `;
    },
};

registerView('teamnotes', TeamNotes);

function _initTeamNotesViewBindings() {
    document.getElementById('teamNotesRefreshBtn').addEventListener('click', () => TeamNotes.refresh());
}
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _initTeamNotesViewBindings);
} else {
    _initTeamNotesViewBindings();
}
