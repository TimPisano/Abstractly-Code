/**
 * Expiration Timeline View: visualizes lease renewal risk by bucketing
 * every lease into how soon it expires, most-urgent first.
 */

const Timeline = {
    async load() {
        const container = document.getElementById('timelineContent');
        container.innerHTML = '<p class="loading-inline" role="status"><span class="spinner-small"></span> Loading...</p>';
        try {
            const timeline = await Api.portfolioTimeline();
            this.render(timeline);
        } catch (err) {
            container.innerHTML = `<p class="error-text">Failed to load timeline: ${escapeHtml(err.message)}</p>`;
        }
    },

    render(timeline) {
        const buckets = [
            { key: 'expiring_0_6_months', label: 'Expiring within 6 months', urgency: 'urgent' },
            { key: 'expiring_6_12_months', label: 'Expiring in 6–12 months', urgency: 'soon' },
            { key: 'expiring_12_24_months', label: 'Expiring in 12–24 months', urgency: 'later' },
            { key: 'expiring_24_plus_months', label: 'Expiring in 24+ months', urgency: 'later' },
            { key: 'already_expired', label: 'Already expired', urgency: 'urgent' },
            { key: 'unknown_expiration', label: 'Unknown expiration date', urgency: 'unknown' },
        ];

        const totalLeases = buckets.reduce((sum, b) => sum + (timeline[b.key] || []).length, 0);
        if (totalLeases === 0) {
            document.getElementById('timelineContent').innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon">
                        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                    </div>
                    <p class="empty-state-title">No leases uploaded yet</p>
                    <p class="empty-state-hint">Once you've uploaded a few leases, this view will surface the ones expiring soonest.</p>
                    <button class="btn-primary" data-goto="upload" type="button">Upload your first lease</button>
                </div>
            `;
            document.querySelector('#timelineContent [data-goto]').addEventListener('click', (e) => showView(e.target.dataset.goto));
            return;
        }

        const html = buckets.map(bucket => {
            const entries = timeline[bucket.key] || [];
            if (entries.length === 0) return '';
            return `
                <div class="timeline-bucket timeline-bucket-${bucket.urgency}">
                    <h2>${bucket.label} <span class="bucket-count">${entries.length}</span></h2>
                    <div class="timeline-entries">
                        ${entries.map(e => `
                            <div class="timeline-entry" data-lease-id="${e.lease_id}">
                                <div class="timeline-entry-main">
                                    <span class="timeline-entry-tenant">${escapeHtml(e.display_name || e.filename)}</span>
                                    <span class="timeline-entry-file">${escapeHtml(e.tenant || 'Tenant not found')}</span>
                                </div>
                                <div class="timeline-entry-date">
                                    ${e.lease_end_date ? escapeHtml(e.lease_end_date) : 'No date on file'}
                                    ${e.months_remaining !== null && e.months_remaining !== undefined ? `<span class="months-remaining">${e.months_remaining.toFixed(1)} mo</span>` : ''}
                                </div>
                            </div>
                        `).join('')}
                    </div>
                </div>
            `;
        }).join('');

        document.getElementById('timelineContent').innerHTML = html;
        document.querySelectorAll('.timeline-entry').forEach(el => {
            el.addEventListener('click', () => showLeaseDetail(parseInt(el.dataset.leaseId, 10)));
        });
    },
};

registerView('timeline', Timeline);
