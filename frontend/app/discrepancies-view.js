/**
 * Discrepancies View: every discrepancy this app has ever recorded
 * (lease risk flags, cross-lease mismatches, rent-roll-vs-lease and
 * rent-roll-vs-T12 reconciliation -- see backend/app/discrepancies.py),
 * in one browsable, filterable feed with a universal resolve action.
 *
 * This is deliberately a SIMPLER resolve flow than DiscrepancyModal's
 * (discrepancy-modal.js) side-by-side comparison -- that modal needs
 * two well-defined "sides" with their own sourced values, which only
 * really exists for rent-roll-vs-lease/T12 mismatches (still reachable
 * from the Dashboard composition panel and the T12 cross-check panel,
 * unchanged). A lease_risk_flag or tenant_concentration discrepancy has
 * no natural "two sides" to compare -- this view instead shows the
 * discrepancy's own already-human-readable `message` and a plain
 * resolve form (what's correct, a note, who), which POST
 * /discrepancies/<id>/resolve accepts as free text regardless of type.
 * Same real backend endpoint either way; this is just the universal
 * path when a two-sided comparison doesn't apply.
 */
const Discrepancies = {
    all: [],
    filters: { showResolved: false, severity: '', type: '' },
    expandedId: null,

    async load() {
        document.getElementById('discrepanciesFeedContent').innerHTML = '<p class="loading-inline" role="status"><span class="spinner-small"></span> Loading discrepancies...</p>';
        document.getElementById('discrepanciesSummaryStrip').innerHTML = `
            <div class="health-metric"><div class="skeleton skeleton-text"></div><div class="health-metric-label">Open</div></div>
            <div class="health-metric"><div class="skeleton skeleton-text"></div><div class="health-metric-label">Resolved</div></div>
            <div class="health-metric"><div class="skeleton skeleton-text"></div><div class="health-metric-label">Total</div></div>
        `;
        try {
            await Promise.all([this.fetchAndRender(), this.loadSummary()]);
        } catch (err) {
            document.getElementById('discrepanciesFeedContent').innerHTML = `<p class="error-text">Failed to load discrepancies: ${escapeHtml(err.message)}</p>`;
        }
    },

    async refresh() {
        const btn = document.getElementById('discrepanciesRefreshBtn');
        btn.disabled = true;
        btn.textContent = 'Refreshing...';
        try {
            await Promise.all([this.fetchAndRender(), this.loadSummary()]);
            showToast('Discrepancies refreshed.', 'success');
        } catch (err) {
            showError(`Failed to refresh: ${err.message}`);
        } finally {
            btn.disabled = false;
            btn.textContent = 'Refresh';
        }
    },

    async loadSummary() {
        const strip = document.getElementById('discrepanciesSummaryStrip');
        try {
            const summary = await Api.discrepanciesSummary();
            const badge = document.getElementById('discrepanciesNavBadge');
            const navItem = document.querySelector('.nav-item-discrepancies');
            const openCount = summary.by_status.open || 0;
            navItem.classList.toggle('has-alerts', openCount > 0);
            if (openCount > 0) {
                badge.textContent = openCount > 99 ? '99+' : String(openCount);
                badge.style.display = '';
            } else {
                badge.style.display = 'none';
            }

            const tiles = [
                { label: 'Open', value: openCount },
                { label: 'Resolved', value: summary.by_status.resolved || 0 },
                { label: 'Total', value: summary.total },
            ];
            strip.innerHTML = tiles.map(t => `
                <div class="health-metric">
                    <div class="health-metric-value">${t.value}</div>
                    <div class="health-metric-label">${t.label}</div>
                </div>
            `).join('');
        } catch (err) {
            strip.innerHTML = '';
        }
    },

    async fetchAndRender() {
        const params = {};
        if (this.filters.type) params.type = this.filters.type;
        if (!this.filters.showResolved) params.status = 'open';
        let discrepancies = await Api.listDiscrepancies(params);
        // No severity filter on the backend for this list (unlike
        // /alerts) -- filtered here instead of adding a query param the
        // route doesn't support.
        if (this.filters.severity) {
            discrepancies = discrepancies.filter(d => d.severity === this.filters.severity);
        }
        this.all = discrepancies;
        this.render(discrepancies);
    },

    render(discrepancies) {
        const el = document.getElementById('discrepanciesFeedContent');
        if (discrepancies.length === 0) {
            el.innerHTML = `
                <div class="attention-clear">
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                    <span>${this.filters.showResolved || this.filters.severity || this.filters.type ? 'No discrepancies match these filters.' : 'No open discrepancies — everything checks out.'}</span>
                </div>
            `;
            return;
        }

        // See alerts-view.js's FEED_RENDER_CAP -- same reasoning, shared
        // constant.
        const capped = discrepancies.slice(0, FEED_RENDER_CAP);
        const capNote = discrepancies.length > FEED_RENDER_CAP
            ? `<p class="attention-more">Showing ${FEED_RENDER_CAP} of ${discrepancies.length} — narrow with the filters above to see more.</p>` : '';
        el.innerHTML = `<div class="alerts-list">${capped.map(d => this._cardHtml(d)).join('')}</div>${capNote}`;

        el.querySelectorAll('.alert-card').forEach(card => {
            const id = parseInt(card.dataset.discrepancyId, 10);
            const leaseLink = card.querySelector('.alert-card-lease-link');
            if (leaseLink) leaseLink.addEventListener('click', (e) => { e.stopPropagation(); showLeaseDetail(parseInt(leaseLink.dataset.leaseId, 10)); });
            const resolveBtn = card.querySelector('.discrepancy-row-resolve-btn');
            if (resolveBtn) resolveBtn.addEventListener('click', () => this.toggleResolveForm(id));
            const reopenBtn = card.querySelector('.discrepancy-row-reopen-btn');
            if (reopenBtn) reopenBtn.addEventListener('click', () => this.reopen(id));
            const confirmBtn = card.querySelector('.discrepancy-row-confirm-btn');
            if (confirmBtn) confirmBtn.addEventListener('click', () => this.submitResolve(id));
            const taskBtn = card.querySelector('.discrepancy-row-task-btn');
            if (taskBtn) taskBtn.addEventListener('click', () => Tasks.createFromDiscrepancy(id, taskBtn));
        });
    },

    toggleResolveForm(id) {
        this.expandedId = this.expandedId === id ? null : id;
        this.render(this.all);
    },

    _typeLabel(type) {
        return {
            lease_risk_flag: 'Lease Risk Flag', cross_lease_mismatch: 'Cross-Lease Mismatch',
            rent_roll_reconciliation: 'Rent Roll Reconciliation', t12_reconciliation: 'T12 Reconciliation',
            rent_roll_ai_validation: 'Rent Roll AI Validation',
        }[type] || type;
    },

    _cardHtml(d) {
        const leaseLink = d.lease_id != null
            ? `<button class="btn-text alert-card-lease-link" data-lease-id="${d.lease_id}" type="button">View Lease &rarr;</button>`
            : '';

        if (d.status === 'resolved') {
            const resolution = d.resolution; // present when fetched via a detail call; list rows may not carry it
            return `
                <div class="alert-card alert-card-${d.severity || 'low'} alert-card-inactive" data-discrepancy-id="${d.id}">
                    <div class="alert-card-head">
                        ${severityBadgeHtml(d.severity || 'low')}
                        <span class="alert-card-type">${this._typeLabel(d.discrepancy_type)}</span>
                        <span class="alert-card-status-tag">Resolved</span>
                        <span class="alert-card-time" title="${escapeHtml(formatDate(d.last_seen_at))}">${timeAgo(d.last_seen_at)}</span>
                    </div>
                    <p class="alert-card-message">${escapeHtml(d.message)}</p>
                    <div class="alert-card-actions">
                        ${leaseLink}
                        <button class="btn-secondary discrepancy-row-reopen-btn" type="button">Reopen</button>
                    </div>
                </div>
            `;
        }

        const isExpanded = this.expandedId === d.id;
        return `
            <div class="alert-card alert-card-${d.severity || 'low'}" data-discrepancy-id="${d.id}">
                <div class="alert-card-head">
                    ${severityBadgeHtml(d.severity || 'low')}
                    <span class="alert-card-type">${this._typeLabel(d.discrepancy_type)}</span>
                    <span class="alert-card-time" title="${escapeHtml(formatDate(d.last_seen_at))}">${timeAgo(d.last_seen_at)}</span>
                </div>
                <p class="alert-card-message">${escapeHtml(d.message)}</p>
                <div class="alert-card-actions">
                    ${leaseLink}
                    <button class="btn-text discrepancy-row-task-btn" data-id="${d.id}" type="button">+ Create Task</button>
                    <button class="btn-secondary discrepancy-row-resolve-btn" type="button">${isExpanded ? 'Cancel' : 'Resolve'}</button>
                </div>
                ${isExpanded ? this._resolveFormHtml() : ''}
            </div>
        `;
    },

    _resolveFormHtml() {
        const identity = getUserIdentity();
        return `
            <div class="discrepancy-row-resolve-form">
                <label>Your name</label>
                <input type="text" class="text-input discrepancy-row-name" placeholder="e.g. J. Alvarez" value="${escapeHtml(identity.name || '')}">
                <label>What's correct / how was this resolved?</label>
                <input type="text" class="text-input discrepancy-row-source" placeholder="e.g. Lease document, confirmed via 2nd amendment">
                <label>Note</label>
                <textarea class="text-input discrepancy-row-note" rows="2" placeholder="Why?"></textarea>
                <p class="discrepancy-row-error error-text" style="display:none;"></p>
                <button class="btn-primary discrepancy-row-confirm-btn" type="button">Mark Resolved</button>
            </div>
        `;
    },

    async submitResolve(id) {
        const card = document.querySelector(`.alert-card[data-discrepancy-id="${id}"]`);
        const name = card.querySelector('.discrepancy-row-name').value.trim();
        const source = card.querySelector('.discrepancy-row-source').value.trim();
        const note = card.querySelector('.discrepancy-row-note').value.trim();
        const errorEl = card.querySelector('.discrepancy-row-error');
        errorEl.style.display = 'none';

        if (!name || !source || !note) {
            errorEl.textContent = 'Your name, what\'s correct, and a note are all required.';
            errorEl.style.display = 'block';
            return;
        }

        const btn = card.querySelector('.discrepancy-row-confirm-btn');
        btn.disabled = true;
        btn.textContent = 'Saving...';
        try {
            await Api.resolveDiscrepancy(id, { correctSource: source, note, resolvedBy: name });
            setUserIdentity(name);
            showToast('Discrepancy resolved.', 'success');
            this.expandedId = null;
            await Promise.all([this.fetchAndRender(), this.loadSummary()]);
        } catch (err) {
            errorEl.textContent = err.message;
            errorEl.style.display = 'block';
            btn.disabled = false;
            btn.textContent = 'Mark Resolved';
        }
    },

    async reopen(id) {
        const name = (getUserIdentity().name || '').trim() || (prompt('Your name (for the record):') || '').trim();
        if (!name) return;
        const note = (prompt('Why are you reopening this?') || '').trim();
        if (!note) return;
        try {
            await Api.reopenDiscrepancy(id, { note, resolvedBy: name });
            setUserIdentity(name);
            showToast('Discrepancy reopened.', 'info');
            await Promise.all([this.fetchAndRender(), this.loadSummary()]);
        } catch (err) {
            showError(`Failed to reopen: ${err.message}`);
        }
    },
};

registerView('discrepancies', Discrepancies);

function _initDiscrepanciesViewBindings() {
    document.getElementById('discrepanciesRefreshBtn').addEventListener('click', () => Discrepancies.refresh());
    document.getElementById('discrepanciesShowResolved').addEventListener('change', (e) => {
        Discrepancies.filters.showResolved = e.target.checked;
        Discrepancies.fetchAndRender();
    });
    document.getElementById('discrepanciesSeverityFilter').addEventListener('change', (e) => {
        Discrepancies.filters.severity = e.target.value;
        Discrepancies.fetchAndRender();
    });
    document.getElementById('discrepanciesTypeFilter').addEventListener('change', (e) => {
        Discrepancies.filters.type = e.target.value;
        Discrepancies.fetchAndRender();
    });
}
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _initDiscrepanciesViewBindings);
} else {
    _initDiscrepanciesViewBindings();
}
