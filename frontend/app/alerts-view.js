/**
 * Alerts View: a dedicated feed for the proactive alerts the backend
 * generates (see backend/app/alerts.py) -- lease expirations, new
 * discrepancies, below-market rent, and tenant concentration risk.
 * Already sorted by the backend (severity, then most-recently-seen --
 * see database.list_alerts), so this view just renders that order.
 *
 * No scheduled generation exists on the backend yet (deliberately out
 * of scope there -- see DECISIONS.md), so this view calls
 * Api.generateAlerts() itself on load, best-effort, before listing --
 * generation is documented idempotent/safe to call as often as needed,
 * so this keeps the feed current without needing a cron job to exist
 * first. The same call also runs once at app boot (see
 * refreshAlertsBadge below) so the nav badge is never far from fresh
 * even before a visit to this view.
 *
 * "Unread" in this app maps onto the backend's real 'active' status --
 * there's no separate read/unread flag anywhere in the alerts table,
 * and inventing a client-only one would either drift from what the
 * team actually resolved or require its own fake persistence layer.
 * Dismissing an alert here IS marking it read: a real, permanent,
 * attributed action via POST /alerts/<id>/dismiss, not a local-only
 * flag.
 */
const Alerts = {
    all: [],
    filters: { showDismissed: false, severity: '', type: '' },

    async load() {
        document.getElementById('alertsFeedContent').innerHTML = '<p class="loading-inline"><span class="spinner-small"></span> Checking for new alerts...</p>';
        document.getElementById('alertsSummaryStrip').innerHTML = `
            <div class="health-metric"><div class="skeleton skeleton-text"></div><div class="health-metric-label">High</div></div>
            <div class="health-metric"><div class="skeleton skeleton-text"></div><div class="health-metric-label">Medium</div></div>
            <div class="health-metric"><div class="skeleton skeleton-text"></div><div class="health-metric-label">Low</div></div>
        `;
        try {
            await Api.generateAlerts().catch(() => { /* best-effort -- an empty portfolio or a transient error shouldn't block viewing whatever's already there */ });
            await Promise.all([this.fetchAndRender(), this.loadSummary()]);
        } catch (err) {
            document.getElementById('alertsFeedContent').innerHTML = `<p class="error-text">Failed to load alerts: ${escapeHtml(err.message)}</p>`;
        }
        refreshAlertsBadge();
    },

    // A quick-scan count strip above the filterable list -- with a
    // portfolio that's accumulated hundreds of alerts over time, a flat
    // unfiltered list reads as a raw dump; a by-severity count up top
    // (clickable straight into that filter) gives the "worth checking
    // daily" at-a-glance read the list alone can't.
    async loadSummary() {
        const strip = document.getElementById('alertsSummaryStrip');
        try {
            const summary = await Api.alertsSummary();
            const tiles = [
                { label: 'High', value: summary.by_severity.high, severity: 'high' },
                { label: 'Medium', value: summary.by_severity.medium, severity: 'medium' },
                { label: 'Low', value: summary.by_severity.low, severity: 'low' },
            ];
            strip.innerHTML = tiles.map(t => `
                <div class="health-metric alerts-summary-tile" data-severity="${t.severity}">
                    <div class="health-metric-value">${t.value}</div>
                    <div class="health-metric-label">${t.label} Severity</div>
                </div>
            `).join('');
            strip.querySelectorAll('.alerts-summary-tile').forEach(tile => {
                tile.addEventListener('click', () => {
                    this.filters.severity = tile.dataset.severity;
                    document.getElementById('alertsSeverityFilter').value = tile.dataset.severity;
                    this.fetchAndRender();
                });
            });
        } catch (err) {
            strip.innerHTML = '';
        }
    },

    async refresh() {
        const btn = document.getElementById('alertsRefreshBtn');
        btn.disabled = true;
        btn.textContent = 'Refreshing...';
        try {
            await Api.generateAlerts();
            await Promise.all([this.fetchAndRender(), this.loadSummary()]);
            refreshAlertsBadge();
            showToast('Alerts refreshed.', 'success');
        } catch (err) {
            showError(`Failed to refresh alerts: ${err.message}`);
        } finally {
            btn.disabled = false;
            btn.textContent = 'Refresh';
        }
    },

    async fetchAndRender() {
        const params = {};
        if (this.filters.severity) params.severity = this.filters.severity;
        if (this.filters.type) params.type = this.filters.type;
        if (!this.filters.showDismissed) params.status = 'active';
        const alerts = await Api.listAlerts(params);
        this.all = alerts;
        this.render(alerts);
    },

    render(alerts) {
        const el = document.getElementById('alertsFeedContent');
        if (alerts.length === 0) {
            el.innerHTML = `
                <div class="attention-clear">
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                    <span>${this.filters.showDismissed || this.filters.severity || this.filters.type ? 'No alerts match these filters.' : 'Nothing needs your attention right now — no active alerts.'}</span>
                </div>
            `;
            return;
        }

        el.innerHTML = `<div class="alerts-list">${alerts.map(a => this._cardHtml(a)).join('')}</div>`;

        el.querySelectorAll('.alert-card').forEach(card => {
            const alert = this.all.find(a => a.id === parseInt(card.dataset.alertId, 10));
            const leaseLink = card.querySelector('.alert-card-lease-link');
            if (leaseLink) leaseLink.addEventListener('click', (e) => { e.stopPropagation(); showLeaseDetail(alert.lease_id); });
            const dismissBtn = card.querySelector('.alert-card-dismiss-btn');
            if (dismissBtn) dismissBtn.addEventListener('click', (e) => { e.stopPropagation(); this.dismiss(alert.id); });
        });
    },

    _cardHtml(alert) {
        const typeLabels = {
            lease_expiration: 'Lease Expiration', new_discrepancy: 'New Discrepancy',
            below_market_rent: 'Below-Market Rent', tenant_concentration: 'Tenant Concentration',
        };
        const statusNote = alert.status === 'dismissed'
            ? `<span class="alert-card-status-tag">Dismissed${alert.dismissed_by ? ` by ${escapeHtml(alert.dismissed_by)}` : ''}</span>`
            : alert.status === 'auto_resolved'
                ? `<span class="alert-card-status-tag">Cleared automatically</span>`
                : '';

        return `
            <div class="alert-card alert-card-${alert.severity} ${alert.status !== 'active' ? 'alert-card-inactive' : ''}" data-alert-id="${alert.id}">
                <div class="alert-card-head">
                    ${severityBadgeHtml(alert.severity)}
                    <span class="alert-card-type">${typeLabels[alert.alert_type] || alert.alert_type}</span>
                    ${statusNote}
                    <span class="alert-card-time" title="${escapeHtml(formatDate(alert.last_seen_at))}">${timeAgo(alert.last_seen_at)}</span>
                </div>
                <h4 class="alert-card-title">${escapeHtml(alert.title)}</h4>
                <p class="alert-card-message">${escapeHtml(alert.message)}</p>
                ${alert.status === 'dismissed' && alert.dismissal_note ? `<p class="alert-card-dismissed-note">&ldquo;${escapeHtml(alert.dismissal_note)}&rdquo;</p>` : ''}
                <div class="alert-card-actions">
                    ${alert.lease_id != null ? `<button class="btn-text alert-card-lease-link" type="button">View Lease &rarr;</button>` : ''}
                    ${alert.status === 'active' ? `<button class="btn-secondary alert-card-dismiss-btn" type="button">Dismiss</button>` : ''}
                </div>
            </div>
        `;
    },

    async dismiss(alertId) {
        const name = (getUserIdentity().name || '').trim() || (prompt('Your name (for the record):') || '').trim();
        if (!name) return;
        setUserIdentity(name);
        try {
            await Api.dismissAlert(alertId, { dismissedBy: name });
            showToast('Alert dismissed.', 'success');
            await Promise.all([this.fetchAndRender(), this.loadSummary()]);
            refreshAlertsBadge();
        } catch (err) {
            showError(`Failed to dismiss: ${err.message}`);
        }
    },
};

/**
 * Keeps the sidebar's Alerts nav badge current -- called once at app
 * boot (see app.js's init()) and again after anything that could
 * change the active-alert count (a refresh, a dismiss). Best-effort:
 * a failure here just leaves the badge as it was, not worth an error
 * toast for a background count refresh.
 */
async function refreshAlertsBadge() {
    try {
        const summary = await Api.alertsSummary();
        const badge = document.getElementById('alertsNavBadge');
        if (summary.active_count > 0) {
            badge.textContent = summary.active_count > 99 ? '99+' : String(summary.active_count);
            badge.style.display = '';
        } else {
            badge.style.display = 'none';
        }
    } catch (err) { /* best-effort */ }
}

registerView('alerts', Alerts);

function _initAlertsViewBindings() {
    document.getElementById('alertsRefreshBtn').addEventListener('click', () => Alerts.refresh());
    document.getElementById('alertsShowDismissed').addEventListener('change', (e) => {
        Alerts.filters.showDismissed = e.target.checked;
        Alerts.fetchAndRender();
    });
    document.getElementById('alertsSeverityFilter').addEventListener('change', (e) => {
        Alerts.filters.severity = e.target.value;
        Alerts.fetchAndRender();
    });
    document.getElementById('alertsTypeFilter').addEventListener('change', (e) => {
        Alerts.filters.type = e.target.value;
        Alerts.fetchAndRender();
    });
}
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _initAlertsViewBindings);
} else {
    _initAlertsViewBindings();
}
