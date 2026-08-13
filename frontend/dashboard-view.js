/**
 * Dashboard View: portfolio-wide metrics tiles + a sortable/filterable
 * table of every lease, with an inline risk indicator per row and an
 * optional multi-select mode for jumping into the comparison view.
 */

const Dashboard = {
    sortKey: 'filename',
    sortDir: 1,
    risksByLeaseId: {},

    async load() {
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
            tenant: fieldValue(lease, 'tenant') || '',
            landlord: fieldValue(lease, 'landlord') || '',
            address: fieldValue(lease, 'property_address') || '',
            rent: fieldValue(lease, 'rent_amount'),
            sqft: fieldValue(lease, 'square_footage'),
            endDate: fieldValue(lease, 'lease_end_date'),
            risks: this.risksByLeaseId[lease.id] || [],
        }));

        if (filterText) {
            rows = rows.filter(r =>
                r.tenant.toLowerCase().includes(filterText) ||
                r.landlord.toLowerCase().includes(filterText) ||
                r.address.toLowerCase().includes(filterText) ||
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
                    <td class="filename-cell">${escapeHtml(lease_filename(r.lease))}</td>
                    <td>${escapeHtml(r.tenant) || '<span class="muted">Not found</span>'}</td>
                    <td>${escapeHtml(r.landlord) || '<span class="muted">Not found</span>'}</td>
                    <td>${escapeHtml(r.rent) || '<span class="muted">—</span>'}</td>
                    <td>${escapeHtml(r.sqft) || '<span class="muted">—</span>'}</td>
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
                if (e.target.closest('.compare-checkbox') || e.target.closest('.view-lease-btn')) return;
                showLeaseDetail(parseInt(tr.dataset.leaseId, 10));
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
    },

    sortRows(rows) {
        const key = this.sortKey;
        const dir = this.sortDir;
        return rows.sort((a, b) => {
            let av, bv;
            if (key === 'filename') { av = lease_filename(a.lease); bv = lease_filename(b.lease); }
            else if (key === 'tenant') { av = a.tenant; bv = b.tenant; }
            else if (key === 'landlord') { av = a.landlord; bv = b.landlord; }
            else if (key === 'rent') { av = parseMoney(a.rent); bv = parseMoney(b.rent); }
            else if (key === 'sqft') { av = parseFloat((a.sqft || '').replace(/[^\d.]/g, '')) || 0; bv = parseFloat((b.sqft || '').replace(/[^\d.]/g, '')) || 0; }
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

document.addEventListener('DOMContentLoaded', () => {
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
});
