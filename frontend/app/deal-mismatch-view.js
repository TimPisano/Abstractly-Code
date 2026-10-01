/**
 * Deal Mismatch Report view: fetches the whole-portfolio report from
 * POST /portfolio/deal-mismatch-report (backend/app/deal_mismatch.py),
 * shows the summary strip + a severity-sorted discrepancy table, and
 * offers PDF/Excel downloads of the same data via
 * app/deal_mismatch_export.py's renderers.
 *
 * Modeled on discrepancies-view.js's summary-strip + table pattern and
 * export-modal.js's blob-download dance -- no new UI pattern invented
 * for this view. Whole-portfolio scope only for now (no property_address
 * picker); Api.dealMismatchReport/exportDealMismatchReportPdf/Excel all
 * already accept an optional propertyAddress for when a scoped view is
 * added later.
 */
const DISCREPANCY_TYPE_LABELS = {
    rent_mismatch: 'Rent Mismatch',
    expired_but_occupied: 'Expired but Occupied',
    unit_no_lease: 'Unit on Rent Roll, No Lease',
    lease_no_unit: 'Lease on File, Not on Rent Roll',
    concession_missing: 'Concession Missing from Rent Roll',
    dates_mismatch: 'Lease Dates Mismatch',
    tenant_mismatch: 'Tenant Name Mismatch',
    t12_income_gap: 'Rent Roll vs. T12 Income',
    t12_occupancy_mismatch: 'Rent Roll vs. T12 Occupancy',
    t12_concession_gap: 'T12 Concessions Reported',
    t12_bad_debt_trend: 'T12 Bad Debt Trend',
};

const _DM_SEVERITY_RANK = { high: 3, medium: 2, low: 1 };

const DealMismatch = {
    lastData: null,

    async load() {
        document.getElementById('dealMismatchContent').innerHTML = '<p class="loading-inline" role="status"><span class="spinner-small"></span> Checking rent roll against lease documents...</p>';
        document.getElementById('dealMismatchSummaryStrip').innerHTML = `
            <div class="health-metric"><div class="skeleton skeleton-text"></div><div class="health-metric-label">Units Checked</div></div>
            <div class="health-metric"><div class="skeleton skeleton-text"></div><div class="health-metric-label">Discrepancies</div></div>
            <div class="health-metric"><div class="skeleton skeleton-text"></div><div class="health-metric-label">Income Impact</div></div>
        `;
        try {
            const t12File = document.getElementById('dealMismatchT12File')?.files?.[0];
            const materialityPct = document.getElementById('dealMismatchMaterialityPct')?.value || '3.0';
            const data = await Api.dealMismatchReport({ t12File, materialityThresholdPct: materialityPct });
            this.lastData = data;
            this.renderSummary(data);
            this.renderTable(data);
            if (data.rent_roll_vs_actual_collections) {
                this.renderT12Section(data);
            }
        } catch (err) {
            document.getElementById('dealMismatchContent').innerHTML = `<p class="error-text">Failed to load the Deal Mismatch Report: ${escapeHtml(err.message)}</p>`;
        }
    },

    async refresh() {
        const btn = document.getElementById('dealMismatchRefreshBtn');
        btn.disabled = true;
        btn.textContent = 'Refreshing...';
        try {
            await this.load();
            showToast('Deal Mismatch Report refreshed.', 'success');
        } catch (err) {
            showError(`Failed to refresh: ${err.message}`);
        } finally {
            btn.disabled = false;
            btn.textContent = 'Refresh';
        }
    },

    renderSummary(data) {
        const impact = data.annual_income_overstatement;
        let impactLabel, impactValue;
        if (impact == null) {
            impactValue = '—';
            impactLabel = 'Income Impact';
        } else if (impact > 0) {
            impactValue = `+$${Math.round(impact).toLocaleString()}`;
            impactLabel = 'Rent Roll Overstates';
        } else if (impact < 0) {
            impactValue = `-$${Math.round(Math.abs(impact)).toLocaleString()}`;
            impactLabel = 'Rent Roll Understates';
        } else {
            impactValue = '$0';
            impactLabel = 'Income Impact';
        }

        const tiles = [
            { label: 'Units Checked', value: data.total_units_checked },
            { label: 'Discrepancies', value: data.total_discrepancies },
            { label: impactLabel, value: impactValue },
        ];
        document.getElementById('dealMismatchSummaryStrip').innerHTML = tiles.map(t => `
            <div class="health-metric">
                <div class="health-metric-value">${t.value}</div>
                <div class="health-metric-label">${escapeHtml(t.label)}</div>
            </div>
        `).join('');
    },

    _sourceLabel(source) {
        if (!source || !source.page) return '—';
        return `Page ${source.page}`;
    },

    _directionLabel(direction) {
        if (direction === 'overstate') return '<span class="alert-card-status-tag">Overstates</span>';
        if (direction === 'understate') return '<span class="alert-card-status-tag">Understates</span>';
        return '';
    },

    renderTable(data) {
        const el = document.getElementById('dealMismatchContent');
        const rows = data.discrepancies || [];
        if (rows.length === 0) {
            el.innerHTML = `
                <div class="attention-clear">
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                    <span>No discrepancies found between the rent roll and the lease documents on file.</span>
                </div>
            `;
            return;
        }

        const ordered = [...rows].sort((a, b) => {
            const rankDiff = (_DM_SEVERITY_RANK[b.severity] || 0) - (_DM_SEVERITY_RANK[a.severity] || 0);
            if (rankDiff !== 0) return rankDiff;
            return (a.unit || '').localeCompare(b.unit || '');
        });

        el.innerHTML = `
            <div class="table-scroll">
                <table class="data-table">
                    <thead>
                        <tr>
                            <th>Unit</th>
                            <th>Type</th>
                            <th>Rent Roll</th>
                            <th>Lease</th>
                            <th>Source</th>
                            <th>Severity</th>
                            <th>Annual Impact</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${ordered.map(row => this._rowHtml(row)).join('')}
                    </tbody>
                </table>
            </div>
        `;
    },

    _rowHtml(row) {
        const impact = row.annual_dollar_impact != null
            ? `$${Math.round(row.annual_dollar_impact).toLocaleString()} ${this._directionLabel(row.income_direction)}`
            : '—';
        return `
            <tr>
                <td>${escapeHtml(row.unit || '—')}</td>
                <td>${escapeHtml(DISCREPANCY_TYPE_LABELS[row.discrepancy_type] || row.discrepancy_type)}</td>
                <td>${escapeHtml(String(row.rent_roll_value ?? '—'))}</td>
                <td>${escapeHtml(String(row.lease_value ?? '—'))}</td>
                <td>${escapeHtml(this._sourceLabel(row.source))}</td>
                <td>${severityBadgeHtml(row.severity || 'low')}</td>
                <td>${impact}</td>
            </tr>
        `;
    },

    renderT12Section(data) {
        const el = document.getElementById('dealMismatchContent');
        const t12Rows = data.rent_roll_vs_actual_collections || [];
        if (!t12Rows || t12Rows.length === 0) {
            return;
        }

        const t12Overstatement = data.estimated_income_overstatement_from_t12;
        let headline;
        if (t12Overstatement == null) {
            headline = 'No dollar-quantified T12 findings.';
        } else if (t12Overstatement > 0) {
            headline = `Rent roll <b>overstates</b> actual collections by <b>$${Math.round(t12Overstatement).toLocaleString()}</b>.`;
        } else {
            headline = `Rent roll <b>understates</b> actual collections by <b>$${Math.round(Math.abs(t12Overstatement)).toLocaleString()}</b>.`;
        }

        const ordered = [...t12Rows].sort((a, b) => {
            const rankDiff = (_DM_SEVERITY_RANK[b.severity] || 0) - (_DM_SEVERITY_RANK[a.severity] || 0);
            if (rankDiff !== 0) return rankDiff;
            return (a.unit || '').localeCompare(b.unit || '');
        });

        const t12Html = `
            <div style="margin-top: 24px; padding-top: 24px; border-top: 1px solid var(--color-border, #ddd);">
                <h3 style="margin: 0 0 12px 0; font-size: 16px; font-weight: 600;">Rent Roll vs. Actual Collections (T12 Cross-Check)</h3>
                <p style="margin: 0 0 12px 0; font-size: 14px;">${headline}</p>
                <div class="table-scroll">
                    <table class="data-table">
                        <thead>
                            <tr>
                                <th>Unit</th>
                                <th>Type</th>
                                <th>Rent Roll</th>
                                <th>Lease/T12</th>
                                <th>Source</th>
                                <th>Severity</th>
                                <th>Annual Impact</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${ordered.map(row => this._rowHtml(row)).join('')}
                        </tbody>
                    </table>
                </div>
            </div>
        `;
        el.innerHTML += t12Html;
    },

    async _download(format) {
        const btnId = format === 'pdf' ? 'dealMismatchExportPdfBtn' : 'dealMismatchExportExcelBtn';
        const btn = document.getElementById(btnId);
        const originalText = btn.textContent;
        btn.disabled = true;
        btn.textContent = 'Generating...';
        try {
            const t12File = document.getElementById('dealMismatchT12File')?.files?.[0];
            const materialityPct = document.getElementById('dealMismatchMaterialityPct')?.value || '3.0';
            const response = format === 'pdf'
                ? await Api.exportDealMismatchReportPdf({ t12File, materialityThresholdPct: materialityPct })
                : await Api.exportDealMismatchReportExcel({ t12File, materialityThresholdPct: materialityPct });
            const blob = await response.blob();
            const ext = format === 'pdf' ? 'pdf' : 'xlsx';
            const fallbackName = `deal_mismatch_report_portfolio.${ext}`;
            const filename = filenameFromResponse(response, fallbackName);
            triggerBlobDownload(blob, filename);
            showToast('Report generated and downloaded.', 'success');
        } catch (err) {
            showError(`Failed to generate ${format.toUpperCase()}: ${err.message}`);
        } finally {
            btn.disabled = false;
            btn.textContent = originalText;
        }
    },
};

registerView('dealmismatch', DealMismatch);

function _initDealMismatchViewBindings() {
    document.getElementById('dealMismatchRefreshBtn').addEventListener('click', () => DealMismatch.refresh());
    document.getElementById('dealMismatchExportPdfBtn').addEventListener('click', () => DealMismatch._download('pdf'));
    document.getElementById('dealMismatchExportExcelBtn').addEventListener('click', () => DealMismatch._download('excel'));
}
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _initDealMismatchViewBindings);
} else {
    _initDealMismatchViewBindings();
}
