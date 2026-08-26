/**
 * Admin Dashboard View: portfolio-wide metrics tiles + a sortable/
 * filterable table of every lease, with an inline risk indicator per row
 * and an optional multi-select mode for jumping into the comparison view.
 *
 * Copied from frontend/app/dashboard-view.js (the customer app's
 * Dashboard) rather than shared, per this project's existing pattern of
 * keeping the admin surface and the customer app intentionally
 * independent (see DECISIONS.md "Access gate uses self-reported email,
 * not real auth"). Deliberate differences from the customer app's own
 * Dashboard: a Status column (Verified / Needs Review / Doesn't Look
 * Like A Lease, derived from confidence_summary + looks_like_lease) and
 * an Uploaded column, since an admin reviewing the whole portfolio
 * needs "is this record trustworthy" and "when did this land" at a
 * glance in a way an individual tenant browsing their own leases
 * doesn't; and client-side pagination (see currentPage/pageSize below),
 * since an admin portfolio is the one place in this app expected to
 * realistically reach 100+ leases.
 */

const Dashboard = {
    sortKey: 'name',
    sortDir: 1,
    risksByLeaseId: {},
    currentPage: 1,
    pageSize: 25,

    async load() {
        this.currentPage = 1;
        this.renderHealthScoreSkeleton();
        this.renderMetricsSkeleton();
        this.renderAttentionSkeleton();
        this.renderExpirationAlertsSkeleton();
        this.renderHealthSkeleton();
        this.renderActivitySkeleton();
        document.getElementById('portfolioConfidenceSummaryPanel').innerHTML = '<p class="loading-inline"><span class="spinner-small"></span> Loading...</p>';
        document.getElementById('dashboardExportExcelBtn').href = Api.rentRollExcelUrl();
        document.getElementById('dashboardSummaryMemoBtn').href = Api.portfolioSummaryPdfUrl();
        document.getElementById('dashboardExportStatus').innerHTML = '';

        try {
            const [leases, metrics, risks] = await Promise.all([
                Api.listLeases(),
                Api.portfolioSummary(),
                Api.portfolioRisks(),
            ]);
            AppState.leases = leases;
            this.risksByLeaseId = {};
            risks.forEach(r => { this.risksByLeaseId[r.lease_id] = r.flags; });

            this.renderMetrics(metrics);
            this.renderTable(leases);
        } catch (err) {
            showError(`Failed to load dashboard: ${err.message}`);
        }

        // Independent of the block above and of each other — one
        // panel's data being briefly unavailable shouldn't block or
        // blank out the rest of the dashboard.
        Api.portfolioHealthScore()
            .then(h => this.renderHealthScore(h))
            .catch(err => { document.getElementById('healthScorePanel').innerHTML = `<p class="error-text">Failed to load health score: ${escapeHtml(err.message)}</p>`; });
        Api.portfolioAttention()
            .then(a => this.renderAttention(a))
            .catch(() => { document.getElementById('attentionContent').innerHTML = '<p class="error-text">Failed to load.</p>'; });
        Api.portfolioExpirationAlerts()
            .then(a => this.renderExpirationAlerts(a))
            .catch(() => { document.getElementById('expirationAlertsContent').innerHTML = '<p class="error-text">Failed to load.</p>'; });
        Api.portfolioConfidenceSummary()
            .then(s => { document.getElementById('portfolioConfidenceSummaryPanel').innerHTML = confidenceSummaryPanelHtml(s, 'Portfolio Confidence'); })
            .catch(() => { document.getElementById('portfolioConfidenceSummaryPanel').innerHTML = '<p class="error-text">Failed to load confidence summary.</p>'; });
        Api.portfolioHealth()
            .then(h => this.renderHealth(h))
            .catch(() => { document.getElementById('healthStrip').innerHTML = '<p class="error-text">Failed to load portfolio health.</p>'; });
        Api.recentActivity(10)
            .then(a => this.renderActivity(a))
            .catch(() => { document.getElementById('activityFeed').innerHTML = '<p class="error-text">Failed to load activity.</p>'; });
    },

    // ===================== Portfolio Health Score =====================
    // Ported verbatim from frontend/app/dashboard-view.js (same real
    // backend endpoint, same markup/behavior) -- this admin dashboard
    // never had it before. Distinct from renderHealth()/healthStrip
    // below (that's "what needs attention today"; this is "how much can
    // I trust the data right now" -- see backend/app/portfolio_health_
    // score.py). Deliberately the first panel on the page, above the
    // fold. One difference from the app/ version: the breakdown's
    // "Review in Alerts" action navigates to the full app (../app/
    // #alerts) instead of calling showView('alerts'), since this page
    // has no local Alerts view -- it links out (see DECISIONS.md).

    renderHealthScoreSkeleton() {
        document.getElementById('healthScorePanel').innerHTML = `
            <div class="health-score-card">
                <div class="skeleton" style="width:120px;height:120px;border-radius:50%;flex-shrink:0;"></div>
                <div class="health-score-info">
                    <div class="skeleton skeleton-text" style="width:40%;margin-bottom:0.5rem;"></div>
                    <div class="skeleton skeleton-text" style="width:60%;"></div>
                </div>
            </div>
        `;
    },

    _healthScoreRatingClass(rating) {
        if (rating === 'Excellent' || rating === 'Good') return 'health-score-good';
        if (rating === 'Fair') return 'health-score-fair';
        if (rating === 'Poor' || rating === 'Critical') return 'health-score-poor';
        return 'health-score-none';
    },

    renderHealthScore(data) {
        const panel = document.getElementById('healthScorePanel');

        if (data.score === null) {
            panel.innerHTML = `
                <div class="health-score-card health-score-none">
                    <div class="health-score-empty-icon">
                        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                    </div>
                    <div class="health-score-info">
                        <h2>Portfolio Health Score</h2>
                        <p class="health-score-subtitle">Upload your first lease to see how much you can trust your portfolio's data.</p>
                    </div>
                </div>
            `;
            return;
        }

        const ratingClass = this._healthScoreRatingClass(data.rating);
        const r = 52;
        const circumference = 2 * Math.PI * r;
        const offset = circumference * (1 - data.score / 100);

        panel.innerHTML = `
            <div class="health-score-card ${ratingClass}">
                <div class="health-score-ring-wrap">
                    <svg class="health-score-ring" viewBox="0 0 120 120">
                        <circle class="health-score-ring-bg" cx="60" cy="60" r="${r}" />
                        <circle class="health-score-ring-fg" cx="60" cy="60" r="${r}"
                            stroke-dasharray="${circumference.toFixed(1)}"
                            stroke-dashoffset="${offset.toFixed(1)}" />
                    </svg>
                    <div class="health-score-ring-label">
                        <div class="health-score-value">${Math.round(data.score)}</div>
                        <div class="health-score-max">/ 100</div>
                    </div>
                </div>
                <div class="health-score-info">
                    <span class="health-score-rating-badge">${escapeHtml(data.rating)}</span>
                    <h2>Portfolio Health Score</h2>
                    <p class="health-score-subtitle">${data.lease_count} lease${data.lease_count === 1 ? '' : 's'} · how much you can trust the data right now</p>
                    <button class="btn-text" id="healthScoreToggleBtn" type="button">See what's driving this score &rarr;</button>
                </div>
            </div>
            <div class="health-score-breakdown" id="healthScoreBreakdown" style="display:none;"></div>
        `;

        document.getElementById('healthScoreToggleBtn').addEventListener('click', (e) => {
            const breakdown = document.getElementById('healthScoreBreakdown');
            const isHidden = breakdown.style.display === 'none';
            breakdown.style.display = isHidden ? 'block' : 'none';
            e.target.textContent = isHidden ? 'Hide breakdown ↑' : "See what's driving this score →";
            if (isHidden && !breakdown.dataset.rendered) {
                breakdown.innerHTML = this._healthScoreBreakdownHtml(data.components);
                breakdown.dataset.rendered = '1';
                breakdown.querySelectorAll('.health-score-goto-alerts').forEach(btn => {
                    btn.addEventListener('click', () => { window.location.href = '../app/#alerts'; });
                });
            }
        });
    },

    // Ordered by how much each component is actually dragging the
    // overall score down (weight * gap-from-100), not by a fixed order
    // -- the biggest real driver reads first, which is the whole point
    // of a "what's driving this" breakdown.
    _healthScoreBreakdownHtml(components) {
        const defs = [
            {
                key: 'confidence_distribution', label: 'Confidence Distribution',
                detail: (c) => `${c.high} high, ${c.medium} medium, ${c.low} low, and ${c.not_found} not-found, out of ${c.total_fields} fields checked across the portfolio.`,
                suggestion: 'Review low-confidence and not-found fields on the affected leases and correct them against their source citation.',
            },
            {
                key: 'source_verification', label: 'Source Verification',
                detail: (c) => `${c.fully_verified_count} of ${c.total_count} lease${c.total_count === 1 ? '' : 's'} have every core field found (tenant, landlord, rent, dates) with nothing flagged.`,
                suggestion: 'Fill in missing core fields, or double-check flagged ones, on the leases pulling this down.',
            },
            {
                key: 'unresolved_discrepancies', label: 'Unresolved Discrepancies',
                detail: (c) => `${c.open_count} open discrepanc${c.open_count === 1 ? 'y' : 'ies'} across the portfolio (${c.discrepancies_per_lease ?? 0} per lease on average).`,
                suggestion: 'Resolve open discrepancies to improve this.',
                action: c => c.open_count > 0 ? `<button class="btn-secondary health-score-goto-alerts" type="button">Review in Alerts &rarr;</button>` : '',
            },
            {
                key: 'data_freshness', label: 'Data Freshness',
                detail: (c) => `${c.fresh_count} of ${c.total_count} lease${c.total_count === 1 ? '' : 's'} refreshed within the last ${c.threshold_months} month${c.threshold_months === 1 ? '' : 's'}; ${c.stale_count} ${c.stale_count === 1 ? 'is' : 'are'} stale.`,
                suggestion: 'Re-upload or amend leases that haven’t been touched in a while so their data reflects reality.',
            },
        ];

        const drag = (c) => (100 - c.score) * c.weight;
        const rows = defs
            .map(def => ({ def, c: components[def.key] }))
            .filter(({ c }) => c.score !== null)
            .sort((a, b) => drag(b.c) - drag(a.c));

        return rows.map(({ def, c }) => `
            <div class="health-score-component">
                <div class="health-score-component-head">
                    <span class="health-score-component-label">${def.label}</span>
                    <span class="health-score-component-weight">${Math.round(c.weight * 100)}% of score</span>
                    <span class="health-score-component-score ${this._healthScoreRatingClass(this._healthScoreScoreRating(c.score))}">${Math.round(c.score)}</span>
                </div>
                <p class="health-score-component-detail">${escapeHtml(def.detail(c))}</p>
                ${c.score < 80 ? `
                    <p class="health-score-component-suggestion">${escapeHtml(def.suggestion)}</p>
                    ${def.action ? def.action(c) : ''}
                ` : ''}
            </div>
        `).join('');
    },

    _healthScoreScoreRating(score) {
        if (score >= 90) return 'Excellent';
        if (score >= 75) return 'Good';
        if (score >= 60) return 'Fair';
        if (score >= 40) return 'Poor';
        return 'Critical';
    },

    renderAttentionSkeleton() {
        document.getElementById('attentionContent').innerHTML = `
            <div class="attention-skeleton">
                <div class="skeleton skeleton-text-sm" style="width:40%;margin-bottom:0.75rem;"></div>
                <div class="skeleton skeleton-text-sm" style="width:70%;margin-bottom:0.5rem;"></div>
                <div class="skeleton skeleton-text-sm" style="width:55%;"></div>
            </div>
        `;
    },

    renderAttention(attention) {
        const { expiring_soon, missing_data, unusual_terms } = attention;
        const totalItems = expiring_soon.length + missing_data.length + unusual_terms.length;
        const content = document.getElementById('attentionContent');

        if (totalItems === 0) {
            content.innerHTML = `
                <div class="attention-clear">
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                    <span>Nothing needs your attention right now — the whole portfolio is in good shape.</span>
                </div>
            `;
            return;
        }

        const groups = [
            {
                key: 'expiring_soon', label: 'Expiring Soon', items: expiring_soon,
                render: e => `${escapeHtml(e.display_name || e.filename)} &mdash; ${e.days_remaining} day${e.days_remaining === 1 ? '' : 's'} left`,
            },
            {
                key: 'missing_data', label: 'Missing Data', items: missing_data,
                render: e => `${escapeHtml(e.display_name || e.filename)} &mdash; missing ${e.missing_fields.map(f => FIELD_LABELS[f] || f).join(', ')}`,
            },
            {
                key: 'unusual_terms', label: 'Unusual Terms', items: unusual_terms,
                render: e => `${escapeHtml(e.display_name || e.filename)} &mdash; ${escapeHtml(e.flags[0].message)}${e.flags.length > 1 ? ` (+${e.flags.length - 1} more)` : ''}`,
            },
        ];

        content.innerHTML = groups.filter(g => g.items.length > 0).map(g => `
            <div class="attention-group">
                <h4 class="attention-group-title">${g.label} <span class="attention-count">${g.items.length}</span></h4>
                <div class="attention-items">
                    ${g.items.slice(0, 5).map(item => `
                        <div class="attention-item" data-lease-id="${item.lease_id}">${g.render(item)}</div>
                    `).join('')}
                </div>
                ${g.items.length > 5 ? `<p class="attention-more">+${g.items.length - 5} more</p>` : ''}
            </div>
        `).join('');

        content.querySelectorAll('.attention-item[data-lease-id]').forEach(el => {
            el.addEventListener('click', () => showLeaseDetail(parseInt(el.dataset.leaseId, 10)));
        });
    },

    renderExpirationAlertsSkeleton() {
        document.getElementById('expirationAlertsContent').innerHTML = `
            <div class="attention-skeleton">
                <div class="skeleton skeleton-text-sm" style="width:40%;margin-bottom:0.75rem;"></div>
                <div class="skeleton skeleton-text-sm" style="width:70%;margin-bottom:0.5rem;"></div>
                <div class="skeleton skeleton-text-sm" style="width:55%;"></div>
            </div>
        `;
    },

    renderExpirationAlerts(alerts) {
        const { expiring, renewal_deadlines } = alerts;
        const content = document.getElementById('expirationAlertsContent');

        if (expiring.length === 0 && renewal_deadlines.length === 0) {
            content.innerHTML = `
                <div class="attention-clear">
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                    <span>Nothing expiring and no renewal deadlines in the next 90 days.</span>
                </div>
            `;
            return;
        }

        const dayLabel = (n) => `${n} day${n === 1 ? '' : 's'}`;
        const groups = [
            {
                key: 'expiring', label: '30 / 60 / 90-Day Expirations', items: expiring,
                render: e => `${escapeHtml(e.display_name || e.filename)} &mdash; expires ${escapeHtml(e.lease_end_date)} (${dayLabel(e.days_remaining)} left)`,
            },
            {
                key: 'renewal_deadlines', label: 'Renewal Notice Deadlines', items: renewal_deadlines,
                render: e => e.bucket === 'overdue'
                    ? `${escapeHtml(e.display_name || e.filename)} &mdash; renewal notice window closed ${dayLabel(Math.abs(e.days_remaining))} ago`
                    : `${escapeHtml(e.display_name || e.filename)} &mdash; renewal notice due in ${dayLabel(e.days_remaining)} (${e.notice_days}-day notice)`,
            },
        ];

        content.innerHTML = groups.filter(g => g.items.length > 0).map(g => `
            <div class="attention-group">
                <h4 class="attention-group-title">${g.label} <span class="attention-count">${g.items.length}</span></h4>
                <div class="attention-items">
                    ${g.items.slice(0, 5).map(item => `
                        <div class="attention-item ${item.bucket === 'overdue' ? 'attention-item-overdue' : ''}" data-lease-id="${item.lease_id}">${g.render(item)}</div>
                    `).join('')}
                </div>
                ${g.items.length > 5 ? `<p class="attention-more">+${g.items.length - 5} more</p>` : ''}
            </div>
        `).join('');

        content.querySelectorAll('.attention-item[data-lease-id]').forEach(el => {
            el.addEventListener('click', () => showLeaseDetail(parseInt(el.dataset.leaseId, 10)));
        });
    },

    renderHealthSkeleton() {
        const strip = document.getElementById('healthStrip');
        const labels = ['Fully Verified', 'Avg. Days to Next Expiration', 'Rent Expiring in 6 Months', 'Rent Expiring in 12 Months'];
        strip.innerHTML = labels.map(label => `
            <div class="health-metric">
                <div class="skeleton skeleton-text"></div>
                <div class="health-metric-label">${label}</div>
            </div>
        `).join('');
    },

    renderHealth(health) {
        const strip = document.getElementById('healthStrip');
        const pct = health.fully_verified_pct;
        const tiles = [
            {
                label: 'Fully Verified', value: pct != null ? `${pct}%` : '—',
                sub: health.total_leases ? `${health.fully_verified_count} of ${health.total_leases} leases` : null,
            },
            {
                label: 'Avg. Days to Next Expiration',
                value: health.avg_days_to_expiration != null ? Math.round(health.avg_days_to_expiration) : '—',
            },
            {
                label: 'Rent Expiring in 6 Months',
                value: health.monthly_rent_expiring_6mo != null ? fmtMoney(health.monthly_rent_expiring_6mo) : '—',
            },
            {
                label: 'Rent Expiring in 12 Months',
                value: health.monthly_rent_expiring_12mo != null ? fmtMoney(health.monthly_rent_expiring_12mo) : '—',
            },
        ];
        strip.innerHTML = tiles.map(t => `
            <div class="health-metric">
                <div class="health-metric-value">${t.value}</div>
                <div class="health-metric-label">${t.label}</div>
                ${t.sub ? `<div class="health-metric-sub">${escapeHtml(t.sub)}</div>` : ''}
            </div>
        `).join('');
    },

    renderActivitySkeleton() {
        document.getElementById('activityFeed').innerHTML = '<p class="loading-inline"><span class="spinner-small"></span> Loading...</p>';
    },

    renderActivity(activity) {
        const feed = document.getElementById('activityFeed');
        if (!activity || activity.length === 0) {
            feed.innerHTML = '<p class="empty-inline">No activity yet — uploads, comparisons, and exports will show up here.</p>';
            return;
        }
        feed.innerHTML = `
            <div class="activity-list">
                ${activity.map(a => `
                    <div class="activity-item ${a.lease_id ? 'clickable' : ''}" ${a.lease_id ? `data-lease-id="${a.lease_id}"` : ''}>
                        <span class="activity-badge activity-badge-${escapeHtml(a.action_type)}">${activityTypeLabel(a.action_type)}</span>
                        <span class="activity-desc">${escapeHtml(a.description)}</span>
                        <span class="activity-time">${timeAgo(a.created_at)}</span>
                    </div>
                `).join('')}
            </div>
        `;
        feed.querySelectorAll('.activity-item.clickable').forEach(el => {
            el.addEventListener('click', () => showLeaseDetail(parseInt(el.dataset.leaseId, 10)));
        });
    },

    renderMetricsSkeleton() {
        const row = document.getElementById('metricsRow');
        const labels = ['Leases', 'Total Monthly Rent', 'Avg. Monthly Rent', 'Avg. Rent / Sq Ft', 'Total CAM Exposure', 'Total Sq Ft'];
        row.innerHTML = labels.map(label => `
            <div class="metric-tile">
                <div class="skeleton skeleton-text"></div>
                <div class="metric-label">${label}</div>
            </div>
        `).join('');
    },

    renderMetrics(metrics) {
        const row = document.getElementById('metricsRow');
        const tiles = [
            { label: 'Leases', value: metrics.lease_count },
            { label: 'Total Monthly Rent', value: fmtMoney(metrics.total_monthly_rent) },
            { label: 'Avg. Monthly Rent', value: fmtMoney(metrics.avg_monthly_rent) },
            { label: 'Avg. Rent / Sq Ft', value: metrics.avg_rent_per_sqft != null ? `$${metrics.avg_rent_per_sqft.toFixed(2)}` : '—' },
            { label: 'Total CAM Exposure', value: fmtMoney(metrics.total_cam_exposure) },
            { label: 'Total Sq Ft', value: metrics.total_square_footage != null ? metrics.total_square_footage.toLocaleString() : '—' },
        ];
        row.innerHTML = tiles.map(t => `
            <div class="metric-tile">
                <div class="metric-value">${t.value}</div>
                <div class="metric-label">${t.label}</div>
            </div>
        `).join('');
    },

    renderTable(leases) {
        const emptyState = document.getElementById('dashboardEmptyState');
        const tableWrap = document.querySelector('#view-dashboard .table-scroll');

        if (leases.length === 0) {
            emptyState.style.display = 'flex';
            tableWrap.style.display = 'none';
            this.renderPagination(0, 1);
            return;
        }
        emptyState.style.display = 'none';
        tableWrap.style.display = 'block';

        const filterText = (document.getElementById('dashboardFilter').value || '').toLowerCase();
        const statusFilter = document.getElementById('dashboardStatusFilter').value;
        const dateFromStr = document.getElementById('dashboardDateFrom').value;
        const dateToStr = document.getElementById('dashboardDateTo').value;
        const compareMode = document.getElementById('compareModeToggle').checked;

        let rows = leases.map(lease => ({
            lease,
            name: lease.display_name || lease_filename(lease),
            tenant: fieldValue(lease, 'tenant') || '',
            landlord: fieldValue(lease, 'landlord') || '',
            address: fieldValue(lease, 'property_address') || '',
            rent: fieldValue(lease, 'rent_amount'),
            sqft: fieldValue(lease, 'square_footage'),
            endDate: fieldValue(lease, 'lease_end_date'),
            uploadedAt: lease.uploaded_at,
            reviewStatus: leaseReviewStatus(lease),
            tags: lease.tags || [],
            risks: this.risksByLeaseId[lease.id] || [],
        }));

        if (filterText) {
            rows = rows.filter(r =>
                r.name.toLowerCase().includes(filterText) ||
                r.tenant.toLowerCase().includes(filterText) ||
                r.landlord.toLowerCase().includes(filterText) ||
                r.address.toLowerCase().includes(filterText) ||
                r.tags.some(tag => tag.toLowerCase().includes(filterText)) ||
                lease_filename(r.lease).toLowerCase().includes(filterText)
            );
        }

        if (statusFilter) {
            rows = rows.filter(r => leaseStatus(r.endDate) === statusFilter);
        }

        if (dateFromStr || dateToStr) {
            // Leases with no parseable end date can't match a date-range
            // filter one way or the other -- exclude them rather than
            // guessing, same reasoning as the status filter above.
            const fromTime = dateFromStr ? new Date(dateFromStr + 'T00:00:00').getTime() : null;
            const toTime = dateToStr ? new Date(dateToStr + 'T23:59:59').getTime() : null;
            rows = rows.filter(r => {
                const t = parseLeaseDate(r.endDate);
                if (t === null) return false;
                if (fromTime !== null && t < fromTime) return false;
                if (toTime !== null && t > toTime) return false;
                return true;
            });
        }

        rows = this.sortRows(rows);

        // Paginate AFTER filtering/sorting, so a page always reflects
        // the current filtered/sorted view rather than the raw list --
        // filtering to fewer rows than fit on one page must clamp back
        // to page 1, not leave the table showing an empty later page.
        const totalRows = rows.length;
        const totalPages = Math.max(1, Math.ceil(totalRows / this.pageSize));
        if (this.currentPage > totalPages) this.currentPage = totalPages;
        const pageStart = (this.currentPage - 1) * this.pageSize;
        const pageRows = rows.slice(pageStart, pageStart + this.pageSize);
        this.renderPagination(totalRows, totalPages);

        document.querySelector('.compare-col').style.display = compareMode ? '' : 'none';

        const tbody = document.getElementById('leaseTableBody');
        tbody.innerHTML = pageRows.map(r => {
            const highestSeverity = worstSeverity(r.risks);
            return `
                <tr data-lease-id="${r.lease.id}">
                    <td class="compare-col" style="display:${compareMode ? '' : 'none'}">
                        <input type="checkbox" class="compare-checkbox" data-id="${r.lease.id}"
                            ${AppState.compareSelection.has(r.lease.id) ? 'checked' : ''}>
                    </td>
                    <td class="lease-name-cell">
                        <span class="lease-name-text editable-name" data-id="${r.lease.id}" title="Click to rename">${escapeHtml(r.name)}</span>
                        ${r.tags.length ? `<div class="lease-name-tags">${r.tags.map(t => `<span class="tag-chip-mini tag-chip-filter" data-tag="${escapeHtml(t)}" title="Filter by this tag">${escapeHtml(t)}</span>`).join('')}</div>` : ''}
                    </td>
                    <td>${statusPillHtml(r.reviewStatus)}</td>
                    <td>${escapeHtml(r.tenant) || '<span class="muted">Not found</span>'}</td>
                    <td>${escapeHtml(r.address) || '<span class="muted">Not found</span>'}</td>
                    <td>${escapeHtml(r.rent) || '<span class="muted">—</span>'}</td>
                    <td>${r.uploadedAt ? escapeHtml(formatDate(r.uploadedAt)) : '<span class="muted">—</span>'}</td>
                    <td>${escapeHtml(r.endDate) || '<span class="muted">—</span>'}</td>
                    <td>${riskCellHtml(r.risks, highestSeverity)}</td>
                    <td><button class="btn-text view-lease-btn" data-id="${r.lease.id}">View →</button></td>
                </tr>
            `;
        }).join('');

        tbody.querySelectorAll('.view-lease-btn').forEach(btn => {
            btn.addEventListener('click', () => showLeaseDetail(parseInt(btn.dataset.id, 10)));
        });
        tbody.querySelectorAll('tr[data-lease-id]').forEach(tr => {
            tr.addEventListener('click', (e) => {
                if (e.target.closest('.compare-checkbox') || e.target.closest('.view-lease-btn')
                    || e.target.closest('.editable-name') || e.target.closest('.tag-chip-filter')) return;
                showLeaseDetail(parseInt(tr.dataset.leaseId, 10));
            });
        });
        tbody.querySelectorAll('.tag-chip-filter').forEach(chip => {
            chip.addEventListener('click', (e) => {
                e.stopPropagation();
                const filterInput = document.getElementById('dashboardFilter');
                filterInput.value = chip.dataset.tag;
                filterInput.dispatchEvent(new Event('input'));
            });
        });
        tbody.querySelectorAll('.compare-checkbox').forEach(cb => {
            cb.addEventListener('click', (e) => e.stopPropagation());
            cb.addEventListener('change', () => {
                const id = parseInt(cb.dataset.id, 10);
                if (cb.checked) AppState.compareSelection.add(id);
                else AppState.compareSelection.delete(id);
                Dashboard.updateCompareBar();
                Dashboard.updateSelectionSummary();
            });
        });
        tbody.querySelectorAll('.editable-name').forEach(el => {
            el.addEventListener('click', (e) => {
                e.stopPropagation();
                this.startRenameInline(el, parseInt(el.dataset.id, 10));
            });
        });
    },

    // Hidden entirely at 1 page (0 or 1 lease, or a filtered-down result
    // that fits on one page) so it never clutters the small-portfolio
    // case -- only shows up once there's actually something to page
    // through.
    renderPagination(totalRows, totalPages) {
        const container = document.getElementById('dashboardPagination');
        if (!container) return;

        if (totalRows === 0 || totalPages <= 1) {
            container.innerHTML = '';
            return;
        }

        const rangeStart = (this.currentPage - 1) * this.pageSize + 1;
        const rangeEnd = Math.min(this.currentPage * this.pageSize, totalRows);

        container.innerHTML = `
            <span class="table-pagination-info">${rangeStart}&ndash;${rangeEnd} of ${totalRows}</span>
            <button class="btn-text" id="dashboardPrevPageBtn" type="button" ${this.currentPage <= 1 ? 'disabled' : ''}>&larr; Prev</button>
            <span class="table-pagination-page">Page ${this.currentPage} of ${totalPages}</span>
            <button class="btn-text" id="dashboardNextPageBtn" type="button" ${this.currentPage >= totalPages ? 'disabled' : ''}>Next &rarr;</button>
        `;

        const prevBtn = document.getElementById('dashboardPrevPageBtn');
        const nextBtn = document.getElementById('dashboardNextPageBtn');
        if (prevBtn) prevBtn.addEventListener('click', () => {
            if (this.currentPage > 1) { this.currentPage -= 1; this.renderTable(AppState.leases); }
        });
        if (nextBtn) nextBtn.addEventListener('click', () => {
            if (this.currentPage < totalPages) { this.currentPage += 1; this.renderTable(AppState.leases); }
        });
    },

    startRenameInline(nameEl, leaseId) {
        if (nameEl.querySelector('input')) return;
        const currentValue = nameEl.textContent.trim();

        const input = document.createElement('input');
        input.type = 'text';
        input.className = 'lease-name-input';
        input.value = currentValue;
        nameEl.textContent = '';
        nameEl.appendChild(input);
        input.focus();
        input.select();

        const commit = async () => {
            const newValue = input.value.trim();
            if (!newValue || newValue === currentValue) {
                nameEl.textContent = currentValue;
                return;
            }
            try {
                await Api.renameLease(leaseId, newValue);
                const cached = AppState.leases.find(l => l.id === leaseId);
                if (cached) cached.display_name = newValue;
                nameEl.textContent = newValue;
                showToast('Lease renamed.', 'success');
            } catch (err) {
                nameEl.textContent = currentValue;
                showError(`Failed to rename: ${err.message}`);
            }
        };

        input.addEventListener('click', (e) => e.stopPropagation());
        input.addEventListener('blur', commit);
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') { e.preventDefault(); input.blur(); }
            else if (e.key === 'Escape') { e.preventDefault(); input.value = currentValue; input.blur(); }
        });
    },

    sortRows(rows) {
        const key = this.sortKey;
        const dir = this.sortDir;
        return rows.sort((a, b) => {
            let av, bv;
            if (key === 'name') { av = a.name; bv = b.name; }
            else if (key === 'tenant') { av = a.tenant; bv = b.tenant; }
            else if (key === 'address') { av = a.address; bv = b.address; }
            else if (key === 'rent') { av = parseMoney(a.rent); bv = parseMoney(b.rent); }
            else if (key === 'status') { av = statusSortRank(a.reviewStatus); bv = statusSortRank(b.reviewStatus); }
            else if (key === 'uploaded') {
                const at = a.uploadedAt ? new Date(a.uploadedAt).getTime() : null;
                const bt = b.uploadedAt ? new Date(b.uploadedAt).getTime() : null;
                if (at === null && bt === null) return 0;
                if (at === null) return 1;
                if (bt === null) return -1;
                return (at - bt) * dir;
            }
            else if (key === 'end_date') {
                // A missing/unparseable date sorts to the end
                // regardless of direction -- "unknown" isn't
                // meaningfully "before" or "after" anything, and
                // shouldn't jump to the top just because the sort was
                // reversed.
                const at = parseLeaseDate(a.endDate);
                const bt = parseLeaseDate(b.endDate);
                if (at === null && bt === null) return 0;
                if (at === null) return 1;
                if (bt === null) return -1;
                return (at - bt) * dir;
            }
            else if (key === 'risk') { av = a.risks.length; bv = b.risks.length; }
            else { av = ''; bv = ''; }

            if (typeof av === 'string') av = av.toLowerCase();
            if (typeof bv === 'string') bv = bv.toLowerCase();
            if (av < bv) return -1 * dir;
            if (av > bv) return 1 * dir;
            return 0;
        });
    },

    updateCompareBar() {
        const bar = document.getElementById('compareBar');
        const ids = Array.from(AppState.compareSelection);
        if (ids.length === 0) {
            bar.style.display = 'none';
            return;
        }
        bar.style.display = 'flex';
        document.getElementById('compareCount').textContent = `${ids.length} selected`;
        document.getElementById('bulkExportExcelBtn').href = Api.bulkExportExcelUrl(ids);
    },

    async bulkExportToGoogleSheets() {
        const ids = Array.from(AppState.compareSelection);
        if (ids.length === 0) return;
        const btn = document.getElementById('bulkExportSheetsBtn');
        const status = document.getElementById('bulkActionStatus');
        btn.disabled = true;
        btn.textContent = 'Exporting...';
        status.innerHTML = '';

        try {
            const result = await Api.bulkExportGoogleSheets(ids);
            status.innerHTML = `
                <div class="export-status export-status-success">
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                    <span>Exported ${ids.length} selected lease${ids.length === 1 ? '' : 's'} to Google Sheets. <a href="${escapeHtml(result.url)}" target="_blank" rel="noopener noreferrer">Open the sheet &rarr;</a></span>
                </div>
            `;
        } catch (err) {
            status.innerHTML = `
                <div class="export-status export-status-error">
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z"/></svg>
                    <span>${escapeHtml(err.message)}</span>
                </div>
            `;
        } finally {
            btn.disabled = false;
            btn.textContent = 'Export to Google Sheets';
        }
    },

    async bulkTagSelected() {
        const ids = Array.from(AppState.compareSelection);
        if (ids.length === 0) return;
        const tag = (prompt(`Add a tag to ${ids.length} selected lease${ids.length === 1 ? '' : 's'}:`) || '').trim();
        if (!tag) return;

        try {
            const result = await Api.bulkTagLeases(ids, tag);
            showToast(`Tagged ${result.tagged.length} lease${result.tagged.length === 1 ? '' : 's'} "${tag}".`, 'success');
            this.load();
        } catch (err) {
            showError(`Failed to tag selected leases: ${err.message}`);
        }
    },

    async bulkDeleteSelected() {
        const ids = Array.from(AppState.compareSelection);
        if (ids.length === 0) return;
        if (!confirm(`Delete ${ids.length} selected lease${ids.length === 1 ? '' : 's'}? This can't be undone.`)) return;

        try {
            const result = await Api.bulkDeleteLeases(ids);
            AppState.compareSelection.clear();
            this.updateCompareBar();
            this.updateSelectionSummary();
            showToast(`Deleted ${result.deleted.length} lease${result.deleted.length === 1 ? '' : 's'}.`, 'success');
            this.load();
        } catch (err) {
            showError(`Failed to delete selected leases: ${err.message}`);
        }
    },

    _selectionSummaryToken: 0,

    async updateSelectionSummary() {
        const panel = document.getElementById('selectionSummaryPanel');
        const ids = Array.from(AppState.compareSelection);

        if (ids.length === 0) {
            panel.style.display = 'none';
            return;
        }

        panel.style.display = 'block';
        document.getElementById('selectionSummaryCount').textContent = ids.length;

        const tiles = document.getElementById('selectionSummaryTiles');
        tiles.innerHTML = SELECTION_SUMMARY_TILE_DEFS.map(() => `
            <div class="metric-tile">
                <div class="metric-value"><span class="skeleton skeleton-text"></span></div>
                <div class="metric-label"></div>
            </div>
        `).join('');

        // A rapid string of checkbox clicks fires this repeatedly;
        // only the response for the MOST RECENT selection should ever
        // reach the DOM, or a slow earlier request could overwrite a
        // faster later one with stale totals.
        const token = ++this._selectionSummaryToken;
        try {
            const metrics = await Api.selectionSummary(ids);
            if (token !== this._selectionSummaryToken) return;
            this.renderSelectionSummaryTiles(metrics);
        } catch (err) {
            if (token !== this._selectionSummaryToken) return;
            tiles.innerHTML = `<p class="empty-inline">Couldn't load totals for the selected leases: ${escapeHtml(err.message)}</p>`;
        }
    },

    renderSelectionSummaryTiles(metrics) {
        const tiles = document.getElementById('selectionSummaryTiles');
        tiles.innerHTML = SELECTION_SUMMARY_TILE_DEFS.map(def => `
            <div class="metric-tile">
                <div class="metric-value">${def.format(metrics)}</div>
                <div class="metric-label">${def.label}</div>
            </div>
        `).join('');
    },

    async exportToGoogleSheets() {
        const btn = document.getElementById('dashboardExportSheetsBtn');
        const status = document.getElementById('dashboardExportStatus');
        btn.disabled = true;
        btn.textContent = 'Exporting...';
        status.innerHTML = '';

        try {
            const result = await Api.exportToGoogleSheets();
            status.innerHTML = `
                <div class="export-status export-status-success">
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                    <span>Exported to Google Sheets. <a href="${escapeHtml(result.url)}" target="_blank" rel="noopener noreferrer">Open the sheet &rarr;</a></span>
                </div>
            `;
        } catch (err) {
            status.innerHTML = `
                <div class="export-status export-status-error">
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z"/></svg>
                    <span>${escapeHtml(err.message)}</span>
                </div>
            `;
        } finally {
            btn.disabled = false;
            btn.textContent = 'Export to Google Sheets';
        }
    },
};

function lease_filename(lease) {
    return lease.filename || `Lease #${lease.id}`;
}

function parseMoney(str) {
    if (!str) return 0;
    const match = String(str).match(/\$?\s?([\d,]+(?:\.\d+)?)/);
    return match ? parseFloat(match[1].replace(/,/g, '')) : 0;
}

// Mirrors portfolio.py's compute_expiration_timeline bucket thresholds
// exactly (same DAYS_PER_MONTH constant, same "< 0" / "< 6" cutoffs) so
// this dashboard filter's "Expiring soon" can't disagree with what the
// customer app's own Timeline view shows for the same lease.
const DAYS_PER_MONTH = 30.4375;
function leaseStatus(endDateStr) {
    const t = parseLeaseDate(endDateStr);
    if (t === null) return null;
    const monthsRemaining = (t - Date.now()) / (1000 * 60 * 60 * 24) / DAYS_PER_MONTH;
    if (monthsRemaining < 0) return 'expired';
    if (monthsRemaining < 6) return 'expiring_soon';
    return 'active';
}

// Admin-only: extraction/record-quality status, distinct from
// leaseStatus() above (which is about the lease's own expiration
// timeline). Deliberately does NOT invent a persisted "pending" state --
// upload is synchronous (a failed extraction never gets saved as a row
// at all), so every lease that reaches this table has already either
// been fully processed or is being reprocessed live in the Upload tab.
// "Needs Review" means some fields were flagged low-confidence by the
// extractor, not that anything failed.
function leaseReviewStatus(lease) {
    if (lease.looks_like_lease === false) {
        return { label: "Doesn't Look Like A Lease", cls: 'status-denied', rank: 0 };
    }
    const summary = lease.confidence_summary;
    if (summary && summary.flagged_for_review > 0) {
        return { label: `Needs Review (${summary.flagged_for_review})`, cls: 'status-pending', rank: 1 };
    }
    if (summary) {
        return { label: 'Verified', cls: 'status-approved', rank: 2 };
    }
    return { label: '—', cls: '', rank: 3 };
}

function statusSortRank(reviewStatus) {
    return reviewStatus ? reviewStatus.rank : 3;
}

function statusPillHtml(reviewStatus) {
    if (!reviewStatus || !reviewStatus.cls) return '<span class="muted">—</span>';
    return `<span class="status-pill ${reviewStatus.cls}">${escapeHtml(reviewStatus.label)}</span>`;
}

function fmtMoney(value) {
    if (value === null || value === undefined) return '—';
    return `$${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

// Same metric vocabulary as the portfolio-wide tiles in renderMetrics()
// above, computed over just the checkbox-selected leases instead of the
// whole portfolio -- deliberately not a different set of numbers, so
// "select all" would read the same as the portfolio-wide row.
const SELECTION_SUMMARY_TILE_DEFS = [
    { label: 'Total Monthly Rent', format: m => fmtMoney(m.total_monthly_rent) },
    { label: 'Total Sq Ft', format: m => m.total_square_footage != null ? m.total_square_footage.toLocaleString() : '—' },
    { label: 'Total CAM Exposure', format: m => fmtMoney(m.total_cam_exposure) },
    { label: 'Avg. Rent / Sq Ft', format: m => m.avg_rent_per_sqft != null ? `$${m.avg_rent_per_sqft.toFixed(2)}` : '—' },
    { label: 'Avg. Security Deposit', format: m => fmtMoney(m.avg_security_deposit) },
];

const ACTIVITY_TYPE_LABELS = {
    lease_uploaded: 'Upload',
    batch_upload: 'Upload',
    amendment_uploaded: 'Amendment',
    lease_deleted: 'Delete',
    comparison_run: 'Comparison',
    rent_roll_exported: 'Export',
    google_sheets_exported: 'Export',
};

function activityTypeLabel(actionType) {
    return ACTIVITY_TYPE_LABELS[actionType] || 'Activity';
}

function worstSeverity(flags) {
    if (!flags || flags.length === 0) return null;
    if (flags.some(f => f.severity === 'high')) return 'high';
    if (flags.some(f => f.severity === 'medium')) return 'medium';
    return 'low';
}

function riskCellHtml(flags, worst) {
    if (!flags || flags.length === 0) {
        return `<span class="risk-indicator risk-none">None</span>`;
    }
    return `<span class="risk-indicator risk-${worst}">${flags.length} flag${flags.length > 1 ? 's' : ''}</span>`;
}

registerView('dashboard', Dashboard);

// Loaded statically by admin-bootstrap.js, after admin/session has
// already confirmed a real authenticated admin -- see the comment in
// app.js for why a readyState check is still needed here regardless
// (these scripts finish loading after DOMContentLoaded has long since
// fired).
function _initDashboardViewBindings() {
    // Every filter control resets to page 1 -- the result set's
    // composition just changed, so staying on (say) page 4 could land on
    // an empty page even though matching rows exist earlier on. Sort and
    // the compare-mode toggle deliberately do NOT reset the page, since
    // the row count doesn't change from either of those.
    document.getElementById('dashboardFilter').addEventListener('input', () => {
        Dashboard.currentPage = 1;
        Dashboard.renderTable(AppState.leases);
    });

    document.getElementById('dashboardStatusFilter').addEventListener('change', () => {
        Dashboard.currentPage = 1;
        Dashboard.renderTable(AppState.leases);
    });
    document.getElementById('dashboardDateFrom').addEventListener('change', () => {
        Dashboard.currentPage = 1;
        Dashboard.renderTable(AppState.leases);
    });
    document.getElementById('dashboardDateTo').addEventListener('change', () => {
        Dashboard.currentPage = 1;
        Dashboard.renderTable(AppState.leases);
    });

    document.getElementById('compareModeToggle').addEventListener('change', () => {
        AppState.compareSelection.clear();
        Dashboard.updateCompareBar();
        Dashboard.updateSelectionSummary();
        Dashboard.renderTable(AppState.leases);
    });

    document.querySelectorAll('#leaseTable th[data-sort]').forEach(th => {
        th.addEventListener('click', () => {
            const key = th.dataset.sort;
            if (Dashboard.sortKey === key) {
                Dashboard.sortDir *= -1;
            } else {
                Dashboard.sortKey = key;
                Dashboard.sortDir = 1;
            }
            Dashboard.renderTable(AppState.leases);
        });
    });

    document.getElementById('dashboardExportSheetsBtn').addEventListener('click', () => Dashboard.exportToGoogleSheets());

    document.getElementById('bulkExportSheetsBtn').addEventListener('click', () => Dashboard.bulkExportToGoogleSheets());
    document.getElementById('bulkTagBtn').addEventListener('click', () => Dashboard.bulkTagSelected());
    document.getElementById('bulkDeleteBtn').addEventListener('click', () => Dashboard.bulkDeleteSelected());
}
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _initDashboardViewBindings);
} else {
    _initDashboardViewBindings();
}
