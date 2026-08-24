/**
 * Dashboard View: portfolio-wide metrics tiles + a sortable/filterable
 * table of every lease, with an inline risk indicator per row and an
 * optional multi-select mode for jumping into the comparison view.
 */

const Dashboard = {
    sortKey: 'name',
    sortDir: 1,
    risksByLeaseId: {},

    async load() {
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

        Api.portfolioTenantConcentration()
            .then(d => this.renderTenantConcentration(d))
            .catch(() => { document.getElementById('tenantConcentrationContent').innerHTML = '<p class="error-text">Failed to load tenant concentration.</p>'; });
        Api.portfolioRollover()
            .then(d => this.renderRollover(d))
            .catch(() => { document.getElementById('rolloverContent').innerHTML = '<p class="error-text">Failed to load rollover risk.</p>'; });
        Api.portfolioLossToLease()
            .then(d => this.renderLossToLease(d))
            .catch(() => { document.getElementById('lossToLeaseContent').innerHTML = '<p class="error-text">Failed to load loss-to-lease.</p>'; });
        Api.portfolioRentRollReconciliation()
            .then(d => this.renderReconciliation(d))
            .catch(() => { document.getElementById('reconciliationContent').innerHTML = '<p class="error-text">Failed to load rent roll reconciliation.</p>'; });
    },

    // "risk_level -> badge" mapping -- delegates to the shared
    // riskLevelBadgeHtml() in app.js (also used by trends-view.js) so
    // both places agree on what "moderate" looks like, rather than two
    // copies of the same mapping drifting apart.
    _riskBadgeHtml(level) {
        return riskLevelBadgeHtml(level);
    },

    renderTenantConcentration(data) {
        const el = document.getElementById('tenantConcentrationContent');
        if (data.tenant_count === 0) {
            el.innerHTML = `
                <div class="attention-group-title">Tenant Concentration</div>
                <p class="attention-empty-note">Not enough data yet — needs at least one lease with both a tenant name and rent.</p>
            `;
            return;
        }

        const topTenants = data.tenants.slice(0, 3).map((t, i) => `
            <div class="attention-item verify-item" data-tenant-index="${i}">${escapeHtml(t.tenant)} — ${t.pct_of_total.toFixed(1)}% of total rent ${verifyTriggerHtml()}</div>
        `).join('');

        el.innerHTML = `
            <div class="attention-group-title">
                Tenant Concentration ${this._riskBadgeHtml(data.concentration_level)}
            </div>
            <p class="attention-summary-line">Top tenant is <strong>${data.top_1_pct.toFixed(1)}%</strong> of total rent (HHI: ${data.hhi.toFixed(0)})</p>
            <div class="attention-items">${topTenants}</div>
        `;

        // No lease_id on a tenant-concentration row (a tenant can span
        // several leases, grouped by normalized name -- see
        // compute_tenant_concentration's own docstring) -- so this opens
        // the aggregate popover (every lease matching that tenant name)
        // rather than jumping straight to one lease the way a single-
        // lease row elsewhere in this panel does.
        el.querySelectorAll('.verify-item').forEach(item => {
            const t = data.tenants[parseInt(item.dataset.tenantIndex, 10)];
            const trigger = item.querySelector('.verify-trigger');
            const open = (e) => {
                e.stopPropagation();
                const norm = (s) => (s || '').toLowerCase().replace(/[.,]/g, '').replace(/\s+/g, ' ').trim();
                const matching = AppState.leases
                    .filter(l => norm(fieldValue(l, 'tenant')) === norm(t.tenant))
                    .map(l => ({ id: l.id, name: l.display_name || lease_filename(l), value: fieldValue(l, 'rent_amount') }));
                VerifyPopover.showAggregate(trigger, { title: `${t.tenant} — Rent by Lease`, leases: matching });
            };
            item.addEventListener('click', open);
        });
    },

    renderRollover(data) {
        const el = document.getElementById('rolloverContent');
        const { walt, rollover_schedule } = data;

        if (walt.walt_years === null) {
            el.innerHTML = `
                <div class="attention-group-title">WALT &amp; Rollover Risk</div>
                <p class="attention-empty-note">Not enough data yet — needs at least one lease with both a rent amount and a (not-yet-expired) end date.</p>
            `;
            return;
        }

        const year1 = rollover_schedule.buckets.year_1;
        el.innerHTML = `
            <div class="attention-group-title">
                WALT &amp; Rollover Risk ${this._riskBadgeHtml(rollover_schedule.rollover_risk_level)}
            </div>
            <p class="attention-summary-line">
                WALT: <strong>${walt.walt_years.toFixed(1)} years</strong> (rent-weighted) &mdash;
                <strong>${year1.pct_of_total_rent.toFixed(1)}%</strong> of rent rolls over in the next 12 months
            </p>
        `;
    },

    renderLossToLease(data) {
        const el = document.getElementById('lossToLeaseContent');
        if (data.lease_count === 0) {
            el.innerHTML = `
                <div class="attention-group-title">Loss to Lease</div>
                <p class="attention-empty-note">Not enough data yet — needs at least two leases at the same building to compare against each other (an internal comp, not external market data).</p>
            `;
            return;
        }

        const topOpportunities = data.leases.filter(l => l.monthly_upside > 0).slice(0, 3).map(l => `
            <div class="attention-item" data-lease-id="${l.lease_id}">${escapeHtml(l.display_name)} — $${l.monthly_upside.toLocaleString(undefined, {maximumFractionDigits: 0})}/mo upside (${l.loss_pct.toFixed(1)}% below this building's top rent)</div>
        `).join('');

        el.innerHTML = `
            <div class="attention-group-title">Loss to Lease</div>
            <p class="attention-summary-line">
                <strong>$${data.total_monthly_upside.toLocaleString(undefined, {maximumFractionDigits: 0})}/mo</strong>
                total upside vs. each building's own best-achieved rent
            </p>
            <div class="attention-items">${topOpportunities || '<div class="attention-item">Every unit is already at its building\'s top rate.</div>'}</div>
        `;
        el.querySelectorAll('.attention-item[data-lease-id]').forEach(item => {
            item.addEventListener('click', () => showLeaseDetail(parseInt(item.dataset.leaseId, 10)));
        });
    },

    renderReconciliation(data) {
        const el = document.getElementById('reconciliationContent');
        if (data.rent_roll_lease_count === 0) {
            el.innerHTML = `
                <div class="attention-group-title">Rent Roll Reconciliation</div>
                <p class="attention-empty-note">No rent roll imported yet — <a href="#" id="reconciliationImportLink">import one</a> to cross-check it against your lease documents.</p>
            `;
            // app.js's init() only wires up [data-goto] elements that
            // already existed in the DOM at page load -- this link is
            // injected later, well after that, so it needs its own
            // listener rather than relying on that one-time binding.
            document.getElementById('reconciliationImportLink').addEventListener('click', (e) => {
                e.preventDefault();
                showView('upload');
            });
            return;
        }

        // Each mismatch already carries its own resolution_status --
        // sync_rent_roll_reconciliation() (backend/app/discrepancies.py)
        // annotates it in place on every response, so a resolution from
        // a previous visit doesn't keep showing up as open here.
        const unresolved = data.mismatches.filter(m => m.resolution_status !== 'resolved');
        const resolvedCount = data.mismatches.length - unresolved.length;

        if (unresolved.length === 0) {
            el.innerHTML = `
                <div class="attention-clear">
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                    <span>Rent Roll Reconciliation — everything matches (${data.compared_pair_count} unit${data.compared_pair_count === 1 ? '' : 's'} checked against a lease document)${resolvedCount > 0 ? `, ${resolvedCount} resolved` : ''}.</span>
                </div>
            `;
            return;
        }

        const fieldLabels = { tenant: 'Tenant', rent_amount: 'Rent', lease_end_date: 'Lease end date' };
        const items = unresolved.slice(0, 5).map((m, i) => `
            <div class="attention-item attention-item-overdue" data-mismatch-index="${i}">
                ${escapeHtml(m.address || 'Unknown address')} — ${fieldLabels[m.field] || m.field}:
                rent roll says "${escapeHtml(m.rent_roll_value)}", lease document says "${escapeHtml(m.lease_document_value)}"
                <span class="discrepancy-resolve-hint">Click to resolve &rarr;</span>
            </div>
        `).join('');
        const more = unresolved.length > 5 ? `<p class="attention-more">+${unresolved.length - 5} more disagreement(s)</p>` : '';
        const resolvedNote = resolvedCount > 0 ? `<p class="attention-more">${resolvedCount} already resolved.</p>` : '';

        el.innerHTML = `
            <div class="attention-group-title">
                Rent Roll Reconciliation <span class="attention-count">${unresolved.length}</span>
            </div>
            <div class="attention-items">${items}</div>
            ${more}
            ${resolvedNote}
        `;
        el.querySelectorAll('.attention-item[data-mismatch-index]').forEach(item => {
            item.addEventListener('click', () => {
                const m = unresolved[parseInt(item.dataset.mismatchIndex, 10)];
                this._openReconciliationModal(m, data);
            });
        });
    },

    _openReconciliationModal(mismatch, data) {
        const rrLease = AppState.leases.find(l => l.id === mismatch.rent_roll_lease_id);
        const docLease = AppState.leases.find(l => l.id === mismatch.lease_document_id);
        const fieldLabels = { tenant: 'Tenant', rent_amount: 'Rent', lease_end_date: 'Lease end date' };
        const label = fieldLabels[mismatch.field] || mismatch.field;

        DiscrepancyModal.open({
            title: 'Resolve Discrepancy',
            subtitle: `${mismatch.address || 'Unknown address'} — ${label}`,
            discrepancyId: mismatch.discrepancy_id,
            resolutionStatus: mismatch.resolution_status,
            resolution: mismatch.resolution,
            sides: [
                {
                    key: 'rent_roll', label: 'Rent Roll', displayValue: mismatch.rent_roll_value,
                    source: rrLease && rrLease.extracted_fields[mismatch.field] && rrLease.extracted_fields[mismatch.field].source,
                },
                {
                    key: 'lease_document', label: 'Lease Document', displayValue: mismatch.lease_document_value,
                    source: docLease && docLease.extracted_fields[mismatch.field] && docLease.extracted_fields[mismatch.field].source,
                },
            ],
        }, { onResolved: () => Api.portfolioRentRollReconciliation().then(d => this.renderReconciliation(d)) });
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
        // fieldKey names which extracted field each tile rolls up, so its
        // number can be click-to-verified back to the leases that fed it
        // (see VerifyPopover.showAggregate) -- null for tiles that aren't
        // a rollup of one field (a plain lease count has nothing to cite).
        const tiles = [
            { label: 'Leases', value: metrics.lease_count, fieldKey: null },
            { label: 'Total Monthly Rent', value: fmtMoney(metrics.total_monthly_rent), fieldKey: 'rent_amount' },
            { label: 'Avg. Monthly Rent', value: fmtMoney(metrics.avg_monthly_rent), fieldKey: 'rent_amount' },
            { label: 'Avg. Rent / Sq Ft', value: metrics.avg_rent_per_sqft != null ? `$${metrics.avg_rent_per_sqft.toFixed(2)}` : '—', fieldKey: 'square_footage' },
            { label: 'Total CAM Exposure', value: fmtMoney(metrics.total_cam_exposure), fieldKey: 'cam_charges' },
            { label: 'Total Sq Ft', value: metrics.total_square_footage != null ? metrics.total_square_footage.toLocaleString() : '—', fieldKey: 'square_footage' },
        ];
        row.innerHTML = tiles.map(t => `
            <div class="metric-tile">
                <div class="metric-value">${t.value}${t.fieldKey ? verifyTriggerHtml() : ''}</div>
                <div class="metric-label">${t.label}</div>
            </div>
        `).join('');
        row.querySelectorAll('.metric-tile').forEach((tileEl, i) => {
            const t = tiles[i];
            const trigger = tileEl.querySelector('.verify-trigger');
            if (!trigger) return;
            trigger.addEventListener('click', () => {
                VerifyPopover.showAggregate(trigger, {
                    title: t.label,
                    leases: AppState.leases.map(l => ({ id: l.id, name: l.display_name || lease_filename(l), value: fieldValue(l, t.fieldKey) })),
                });
            });
        });
    },

    renderTable(leases) {
        const emptyState = document.getElementById('dashboardEmptyState');
        const tableWrap = document.querySelector('#view-dashboard .table-scroll');

        if (leases.length === 0) {
            emptyState.style.display = 'flex';
            tableWrap.style.display = 'none';
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

        document.querySelector('.compare-col').style.display = compareMode ? '' : 'none';

        const tbody = document.getElementById('leaseTableBody');
        tbody.innerHTML = rows.map(r => {
            const highestSeverity = worstSeverity(r.risks);
            return `
                <tr data-lease-id="${r.lease.id}">
                    <td class="compare-col" style="display:${compareMode ? '' : 'none'}">
                        <input type="checkbox" class="compare-checkbox" data-id="${r.lease.id}"
                            ${AppState.compareSelection.has(r.lease.id) ? 'checked' : ''}>
                    </td>
                    <td class="lease-name-cell">
                        <span class="lease-name-text editable-name" data-id="${r.lease.id}" title="Click to rename">${escapeHtml(r.name)}</span>
                        ${r.lease.looks_like_lease === false ? `<span class="non-lease-flag" title="Doesn't look like a lease — no tenant, landlord, rent, or dates were found">&#9888;</span>` : ''}
                        ${r.tags.length ? `<div class="lease-name-tags">${r.tags.map(t => `<span class="tag-chip-mini tag-chip-filter" data-tag="${escapeHtml(t)}" title="Filter by this tag">${escapeHtml(t)}</span>`).join('')}</div>` : ''}
                    </td>
                    <td>${escapeHtml(r.tenant) || '<span class="muted">Not found</span>'}</td>
                    <td>${escapeHtml(r.address) || '<span class="muted">Not found</span>'}</td>
                    <td>${escapeHtml(r.rent) || '<span class="muted">—</span>'}</td>
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
// Timeline view's "Expiring within 6 months" bucket already shows for
// the same lease.
const DAYS_PER_MONTH = 30.4375;
function leaseStatus(endDateStr) {
    const t = parseLeaseDate(endDateStr);
    if (t === null) return null;
    const monthsRemaining = (t - Date.now()) / (1000 * 60 * 60 * 24) / DAYS_PER_MONTH;
    if (monthsRemaining < 0) return 'expired';
    if (monthsRemaining < 6) return 'expiring_soon';
    return 'active';
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

// Loaded dynamically by access-gate.js after the gate passes, well after
// DOMContentLoaded already fired -- see the comment in app.js for why a
// readyState check is needed here instead of a plain addEventListener.
function _initDashboardViewBindings() {
    document.getElementById('dashboardFilter').addEventListener('input', () => {
        Dashboard.renderTable(AppState.leases);
    });

    document.getElementById('dashboardStatusFilter').addEventListener('change', () => {
        Dashboard.renderTable(AppState.leases);
    });
    document.getElementById('dashboardDateFrom').addEventListener('change', () => {
        Dashboard.renderTable(AppState.leases);
    });
    document.getElementById('dashboardDateTo').addEventListener('change', () => {
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

    document.getElementById('compareGoBtn').addEventListener('click', () => {
        showView('comparison', { preselect: Array.from(AppState.compareSelection) });
    });

    document.getElementById('bulkExportSheetsBtn').addEventListener('click', () => Dashboard.bulkExportToGoogleSheets());
    document.getElementById('bulkTagBtn').addEventListener('click', () => Dashboard.bulkTagSelected());
    document.getElementById('bulkDeleteBtn').addEventListener('click', () => Dashboard.bulkDeleteSelected());
}
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _initDashboardViewBindings);
} else {
    _initDashboardViewBindings();
}
