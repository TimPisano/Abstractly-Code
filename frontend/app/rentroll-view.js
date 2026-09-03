/**
 * Portfolio Rent Roll View: every lease aggregated into one rollup
 * table (unit/tenant, address, sq ft, rent, rent/sqft, term dates)
 * with a totals row at the bottom. Read-only summary of the same data
 * the Dashboard's Lease Library shows per-lease, EXCEPT the data
 * columns are directly editable in place (see startCellEdit) using the
 * same real save path (saveLeaseFieldEdit, app.js) as the lease detail
 * page and the task modal -- a correction made here is a correction to
 * the actual lease record, not a cosmetic overlay on this table.
 *
 * The Excel/CSV/Sheets export buttons here hit the exact same
 * portfolio export endpoints as the Dashboard's -- the backend now
 * always includes this same rollup as a separate "Portfolio Summary"
 * tab, so there's nothing rent-roll-specific to wire up beyond reusing
 * them.
 *
 * "Replace" per row is a real Canvas-style resubmission (POST
 * /leases/<id>/resubmit, see Api.resubmitLease) -- the uploaded file
 * becomes a brand-new lease row and the old one is marked superseded
 * (archived, excluded from GET /leases and this rollup, but still
 * reachable at its own id forever), same mechanism the in-task editing
 * work already relies on for version redirection. Not the older
 * amendment mechanism (POST /leases/<id>/amendments) the lease detail
 * page's own "Resubmit" button still uses -- see DECISIONS.md.
 */

function parseSqft(str) {
    if (!str) return null;
    const match = String(str).match(/([\d,]+(?:\.\d+)?)/);
    return match ? parseFloat(match[1].replace(/,/g, '')) : null;
}

const RentRoll = {
    _replaceTargetLeaseId: null,

    async load() {
        document.getElementById('rentRollExportCsvBtn').href = Api.rentRollCsvUrl();
        document.getElementById('rentRollExportExcelBtn').href = Api.rentRollExcelUrl();
        document.getElementById('rentRollExportStatus').innerHTML = '';
        document.getElementById('rentRollReplaceStatus').innerHTML = '';

        const tbody = document.getElementById('rentRollTableBody');
        tbody.innerHTML = `<tr><td colspan="8" class="loading-inline"><span class="spinner-small"></span> Loading...</td></tr>`;

        try {
            const leases = await Api.listLeases();
            AppState.leases = leases;
            this.render(leases);
        } catch (err) {
            tbody.innerHTML = `<tr><td colspan="8" class="error-text">Failed to load rent roll: ${escapeHtml(err.message)}</td></tr>`;
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

        // Totals below are computed over the FULL `leases` array regardless
        // of the render cap -- only the <tr> HTML generation is capped, so
        // the totals row never desyncs from what the portfolio actually
        // contains. See dashboard-view.js's TABLE_RENDER_CAP.
        const noteEl = document.getElementById('rentRollTableNote');
        if (leases.length > TABLE_RENDER_CAP) {
            noteEl.textContent = `Showing ${TABLE_RENDER_CAP} of ${leases.length} leases — totals below reflect the full portfolio.`;
            noteEl.style.display = '';
        } else {
            noteEl.style.display = 'none';
        }

        const parsed = leases.map(lease => {
            const rentStr = fieldValue(lease, 'rent_amount');
            const sqftStr = fieldValue(lease, 'square_footage');
            const rent = rentStr ? parseMoney(rentStr) : null;
            const sqft = sqftStr ? parseSqft(sqftStr) : null;
            if (sqft !== null) totalSqft += sqft;
            if (rent !== null) totalRent += rent;
            if (rent !== null && sqft !== null) { weightedRent += rent; weightedSqft += sqft; }
            return { lease, rent, sqft };
        });

        const rows = parsed.slice(0, TABLE_RENDER_CAP).map(({ lease, rent, sqft }) => {
            const name = fieldValue(lease, 'tenant') || lease.display_name || lease_filename(lease);
            const address = fieldValue(lease, 'property_address');
            const psf = (rent !== null && sqft) ? rent / sqft : null;
            const versionBadge = (lease.version_number || 1) > 1 ? `<span class="rent-roll-version-badge" title="This lease has been resubmitted">v${lease.version_number}</span>` : '';

            return `
                <tr data-lease-id="${lease.id}">
                    <td>${this._editableCellHtml(lease, 'tenant', escapeHtml(name))}${versionBadge}</td>
                    <td>${this._editableCellHtml(lease, 'property_address', escapeHtml(address) || '<span class="muted">Not found</span>')}${cellVerifyTriggerHtml(lease, 'property_address')}</td>
                    <td>${this._editableCellHtml(lease, 'square_footage', sqft !== null ? sqft.toLocaleString() : '<span class="muted">—</span>')}${cellVerifyTriggerHtml(lease, 'square_footage')}</td>
                    <td>${this._editableCellHtml(lease, 'rent_amount', rent !== null ? fmtMoney(rent) : '<span class="muted">—</span>')}${cellVerifyTriggerHtml(lease, 'rent_amount')}</td>
                    <td>${psf !== null ? `$${psf.toFixed(2)}` : '<span class="muted">—</span>'}</td>
                    <td>${this._editableCellHtml(lease, 'lease_start_date', escapeHtml(fieldValue(lease, 'lease_start_date')) || '<span class="muted">—</span>')}${cellVerifyTriggerHtml(lease, 'lease_start_date')}</td>
                    <td>${this._editableCellHtml(lease, 'lease_end_date', escapeHtml(fieldValue(lease, 'lease_end_date')) || '<span class="muted">—</span>')}${cellVerifyTriggerHtml(lease, 'lease_end_date')}</td>
                    <td><button class="btn-text rent-roll-replace-btn" data-lease-id="${lease.id}" type="button">Replace</button></td>
                </tr>
            `;
        }).join('');

        document.getElementById('rentRollTableBody').innerHTML = rows;
        document.querySelectorAll('#rentRollTableBody tr[data-lease-id]').forEach(tr => {
            tr.addEventListener('click', () => showLeaseDetail(parseInt(tr.dataset.leaseId, 10)));
        });
        bindCellVerifyTriggers('#rentRollTableBody');
        document.querySelectorAll('.rent-roll-cell-editable').forEach(span => {
            span.addEventListener('click', (e) => {
                e.stopPropagation();
                this.startCellEdit(span);
            });
        });
        document.querySelectorAll('.rent-roll-replace-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                this.startReplace(parseInt(btn.dataset.leaseId, 10));
            });
        });

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
                <td></td>
            </tr>
        `;
    },

    // ---- Inline editing ----

    _editableCellHtml(lease, fieldKey, displayHtml) {
        return `<span class="rent-roll-cell-editable" data-lease-id="${lease.id}" data-field="${fieldKey}" title="Click to edit">${displayHtml}</span>`;
    },

    startCellEdit(span) {
        if (span.querySelector('input')) return;
        const leaseId = parseInt(span.dataset.leaseId, 10);
        const fieldKey = span.dataset.field;
        const lease = AppState.leases.find(l => l.id === leaseId);
        if (!lease) return;
        const fieldData = lease.extracted_fields[fieldKey];
        const currentValue = fieldData && fieldData.value != null ? String(fieldData.value) : '';

        const input = document.createElement('input');
        input.type = 'text';
        input.className = 'field-value-input rent-roll-cell-input';
        input.value = currentValue;
        span.textContent = '';
        span.appendChild(input);
        input.focus();
        input.select();

        let handled = false;
        const commit = async () => {
            if (handled) return;
            handled = true;
            const newValue = input.value.trim();
            if (newValue === currentValue) {
                this.render(AppState.leases);
                return;
            }
            input.disabled = true;
            try {
                await saveLeaseFieldEdit(leaseId, fieldKey, newValue === '' ? null : newValue);
                // Re-fetch this one lease (not the whole rent roll) --
                // cheaper than a full reload, and its manually_verified/
                // confidence state needs to reflect what the backend
                // actually stored, not just the raw string just typed.
                const updated = await Api.getLease(leaseId);
                const idx = AppState.leases.findIndex(l => l.id === leaseId);
                if (idx !== -1) AppState.leases[idx] = updated;
                showToast('Field saved.', 'success');
                this.render(AppState.leases);
            } catch (err) {
                showError(`Failed to save: ${err.message}`);
                handled = false;
                input.disabled = false;
                input.focus();
            }
        };

        input.addEventListener('blur', commit);
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') { e.preventDefault(); input.blur(); }
            else if (e.key === 'Escape') { e.preventDefault(); input.value = currentValue; input.blur(); }
        });
    },

    // ---- Replace / Resubmit ----

    startReplace(leaseId) {
        this._replaceTargetLeaseId = leaseId;
        document.getElementById('rentRollReplaceFileInput').click();
    },

    async handleReplaceFile(file) {
        const leaseId = this._replaceTargetLeaseId;
        if (!leaseId || !file) return;
        this._replaceTargetLeaseId = null;

        const status = document.getElementById('rentRollReplaceStatus');
        status.innerHTML = `<p class="loading-inline" role="status"><span class="spinner-small"></span> Uploading and processing new version…</p>`;

        try {
            const result = await Api.resubmitLease(leaseId, file);
            status.innerHTML = `
                <div class="export-status export-status-success">
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                    <span>Replaced — now Version ${result.version_number}. The previous version is archived (still viewable in the lease's version history).${result.discrepancies_auto_resolved ? ` ${result.discrepancies_auto_resolved} discrepancy${result.discrepancies_auto_resolved === 1 ? '' : 'ies'} no longer detected and auto-resolved.` : ''}</span>
                </div>
            `;
            showToast(`Lease replaced — Version ${result.version_number} is now current.`, 'success');
            await this.load();
        } catch (err) {
            status.innerHTML = `
                <div class="export-status export-status-error">
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z"/></svg>
                    <span>${escapeHtml(err.message)}</span>
                </div>
            `;
        }
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
    const replaceInput = document.getElementById('rentRollReplaceFileInput');
    replaceInput.addEventListener('change', (e) => {
        const file = e.target.files[0];
        replaceInput.value = '';
        if (file) RentRoll.handleReplaceFile(file);
    });
}
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _initRentRollViewBindings);
} else {
    _initRentRollViewBindings();
}
