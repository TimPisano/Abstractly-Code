/**
 * Portfolio Rent Roll View: every lease aggregated into one rollup
 * table (unit/tenant, address, sq ft, rent, rent/sqft, term dates)
 * with a totals row at the bottom. Read-only summary of the same data
 * the Dashboard's Lease Library shows per-lease -- this view's job is
 * the aggregate, not another way to browse individual leases.
 *
 * The Excel/Sheets export buttons here hit the exact same portfolio
 * export endpoints as the Dashboard's -- the backend now always
 * includes this same rollup as a separate "Portfolio Summary" tab, so
 * there's nothing rent-roll-specific to wire up beyond reusing them.
 */

function parseSqft(str) {
    if (!str) return null;
    const match = String(str).match(/([\d,]+(?:\.\d+)?)/);
    return match ? parseFloat(match[1].replace(/,/g, '')) : null;
}

const RentRoll = {
    async load() {
        document.getElementById('rentRollExportExcelBtn').href = Api.rentRollExcelUrl();
        document.getElementById('rentRollExportStatus').innerHTML = '';

        const tbody = document.getElementById('rentRollTableBody');
        tbody.innerHTML = `<tr><td colspan="7" class="loading-inline"><span class="spinner-small"></span> Loading...</td></tr>`;

        try {
            const leases = await Api.listLeases();
            AppState.leases = leases;
            this.render(leases);
        } catch (err) {
            tbody.innerHTML = `<tr><td colspan="7" class="error-text">Failed to load rent roll: ${escapeHtml(err.message)}</td></tr>`;
        }
    },

    render(leases) {
        const emptyState = document.getElementById('rentRollEmptyState');
        const tableWrap = document.querySelector('#view-rentroll .table-scroll');

        if (leases.length === 0) {
            emptyState.style.display = 'flex';
            tableWrap.style.display = 'none';
            return;
        }
        emptyState.style.display = 'none';
        tableWrap.style.display = 'block';

        let totalSqft = 0, totalRent = 0, weightedSqft = 0, weightedRent = 0;

        const rows = leases.map(lease => {
            const name = fieldValue(lease, 'tenant') || lease.display_name || lease_filename(lease);
            const address = fieldValue(lease, 'property_address');
            const rentStr = fieldValue(lease, 'rent_amount');
            const sqftStr = fieldValue(lease, 'square_footage');
            const rent = rentStr ? parseMoney(rentStr) : null;
            const sqft = sqftStr ? parseSqft(sqftStr) : null;
            const psf = (rent !== null && sqft) ? rent / sqft : null;

            if (sqft !== null) totalSqft += sqft;
            if (rent !== null) totalRent += rent;
            if (rent !== null && sqft !== null) { weightedRent += rent; weightedSqft += sqft; }

            return `
                <tr data-lease-id="${lease.id}">
                    <td>${escapeHtml(name)}</td>
                    <td>${escapeHtml(address) || '<span class="muted">Not found</span>'}</td>
                    <td>${sqft !== null ? sqft.toLocaleString() : '<span class="muted">—</span>'}${cellVerifyTriggerHtml(lease, 'square_footage')}</td>
                    <td>${rent !== null ? fmtMoney(rent) : '<span class="muted">—</span>'}${cellVerifyTriggerHtml(lease, 'rent_amount')}</td>
                    <td>${psf !== null ? `$${psf.toFixed(2)}` : '<span class="muted">—</span>'}</td>
                    <td>${escapeHtml(fieldValue(lease, 'lease_start_date')) || '<span class="muted">—</span>'}${cellVerifyTriggerHtml(lease, 'lease_start_date')}</td>
                    <td>${escapeHtml(fieldValue(lease, 'lease_end_date')) || '<span class="muted">—</span>'}${cellVerifyTriggerHtml(lease, 'lease_end_date')}</td>
                </tr>
            `;
        }).join('');

        document.getElementById('rentRollTableBody').innerHTML = rows;
        document.querySelectorAll('#rentRollTableBody tr[data-lease-id]').forEach(tr => {
            tr.addEventListener('click', () => showLeaseDetail(parseInt(tr.dataset.leaseId, 10)));
        });
        bindCellVerifyTriggers('#rentRollTableBody');

        const weightedAvgPsf = weightedSqft > 0 ? weightedRent / weightedSqft : null;
        document.getElementById('rentRollTableFoot').innerHTML = `
            <tr class="rent-roll-totals-row">
                <td>TOTAL (${leases.length} unit${leases.length === 1 ? '' : 's'})</td>
                <td></td>
                <td>${totalSqft > 0 ? totalSqft.toLocaleString() : '—'}</td>
                <td>${totalRent > 0 ? fmtMoney(totalRent) : '—'}</td>
                <td>${weightedAvgPsf !== null ? `$${weightedAvgPsf.toFixed(2)}` : '—'}</td>
                <td></td>
                <td></td>
            </tr>
        `;
    },

    async exportToGoogleSheets() {
        const btn = document.getElementById('rentRollExportSheetsBtn');
        const status = document.getElementById('rentRollExportStatus');
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

registerView('rentroll', RentRoll);

function _initRentRollViewBindings() {
    document.getElementById('rentRollExportSheetsBtn').addEventListener('click', () => RentRoll.exportToGoogleSheets());
}
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _initRentRollViewBindings);
} else {
    _initRentRollViewBindings();
}
