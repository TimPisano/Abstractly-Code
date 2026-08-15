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
        this.renderHealthSkeleton();
        this.renderActivitySkeleton();

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
        Api.portfolioHealth()
            .then(h => this.renderHealth(h))
            .catch(() => { document.getElementById('healthStrip').innerHTML = '<p class="error-text">Failed to load portfolio health.</p>'; });
        Api.recentActivity(10)
            .then(a => this.renderActivity(a))
            .catch(() => { document.getElementById('activityFeed').innerHTML = '<p class="error-text">Failed to load activity.</p>'; });
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
            return;
        }
        emptyState.style.display = 'none';
        tableWrap.style.display = 'block';

        const filterText = (document.getElementById('dashboardFilter').value || '').toLowerCase();
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
            else if (key === 'end_date') { av = a.endDate || ''; bv = b.endDate || ''; }
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
        const count = AppState.compareSelection.size;
        if (count === 0) {
            bar.style.display = 'none';
            return;
        }
        bar.style.display = 'flex';
        document.getElementById('compareCount').textContent = `${count} selected`;
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

function fmtMoney(value) {
    if (value === null || value === undefined) return '—';
    return `$${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

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

    document.getElementById('compareModeToggle').addEventListener('change', () => {
        AppState.compareSelection.clear();
        Dashboard.updateCompareBar();
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

    document.getElementById('compareGoBtn').addEventListener('click', () => {
        showView('comparison', { preselect: Array.from(AppState.compareSelection) });
    });
}
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _initDashboardViewBindings);
} else {
    _initDashboardViewBindings();
}
