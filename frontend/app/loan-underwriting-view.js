/**
 * Loan Underwriting view: create and edit a loan request, upload the
 * T-12 operating statement it underwrites against, edit the six
 * underwriting assumptions/constraints, and view the full result --
 * NOI build-up, debt service, DSCR/LTV/debt yield/breakeven, maximum
 * loan by each constraint with the binding one marked, five stress
 * tests, and the DSCR sensitivity grid -- then download the Word credit
 * memo draft.
 *
 * Entirely feature-flagged: this view is unreachable unless
 * navItemLoanUnderwriting is shown, which only happens when GET /config
 * reports loan_underwriting_enabled (see app.js's applyFeatureFlags()).
 * Every Api.*LoanUnderwriting* call below hits a route that 404s
 * server-side when the backend flag is off, so even a stale/bookmarked
 * URL to this view can't do anything the backend won't allow.
 *
 * Modeled on deal-mismatch-view.js's load/render/download shape and
 * upload-view.js's file-upload handling -- no new UI pattern invented.
 * Two panels, toggled by display:none rather than full DOM teardown
 * (same approach export-modal.js and the discrepancy modal use): a LIST
 * panel (saved requests + the new-request form) and a DETAIL panel (one
 * request's terms, T-12, assumptions, and results).
 */

const LoanUnderwriting = {
    currentRequestId: null,
    currentRequest: null,
    currentResult: null,

    async load() {
        this.currentRequestId = null;
        this.showListPanel();
        await this.loadList();
    },

    showListPanel() {
        document.getElementById('loanUwListPanel').style.display = '';
        document.getElementById('loanUwDetailPanel').style.display = 'none';
        document.getElementById('loanUwListActions').style.display = '';
        document.getElementById('loanUwDetailActions').style.display = 'none';
    },

    showDetailPanel() {
        document.getElementById('loanUwListPanel').style.display = 'none';
        document.getElementById('loanUwDetailPanel').style.display = '';
        document.getElementById('loanUwListActions').style.display = 'none';
        document.getElementById('loanUwDetailActions').style.display = '';
    },

    // ---- money/percent/ratio formatting -- same inline style every
    // other view in this app uses (e.g. deal-mismatch-view.js's
    // Math.round(x).toLocaleString()), not a new shared helper nobody
    // else asked for. ----
    money(value) {
        if (value === null || value === undefined) return 'n/a';
        const sign = value < 0 ? '-' : '';
        return `${sign}$${Math.abs(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    },

    pct(value, places = 2) {
        if (value === null || value === undefined) return 'n/a';
        return `${value.toFixed(places)}%`;
    },

    ratio(value) {
        if (value === null || value === undefined) return 'n/a';
        return `${value.toFixed(2)}x`;
    },

    // ---- LIST PANEL ----

    async loadList() {
        const el = document.getElementById('loanUwListContent');
        el.innerHTML = '<p class="loading-inline" role="status"><span class="spinner-small"></span> Loading loan requests...</p>';
        try {
            const data = await Api.listLoanUnderwritingRequests();
            this.renderList(data.requests || []);
        } catch (err) {
            el.innerHTML = `<p class="error-text">Failed to load loan requests: ${escapeHtml(err.message)}</p>`;
        }
    },

    renderList(requests) {
        const el = document.getElementById('loanUwListContent');
        if (requests.length === 0) {
            el.innerHTML = `
                <div class="attention-clear">
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 9v3.75m0 3.75h.008M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                    <span>No loan requests yet. Click "New Loan Request" to start underwriting a deal.</span>
                </div>
            `;
            return;
        }

        const rows = requests.map(r => `
            <tr data-request-id="${r.id}">
                <td>${escapeHtml(r.deal_name || '(unnamed deal)')}</td>
                <td>${escapeHtml(r.property_address)}</td>
                <td>${this.money(r.loan_amount)}</td>
                <td>${this.pct(r.annual_rate_pct)}</td>
                <td>${escapeHtml((r.created_at || '').slice(0, 10))}</td>
            </tr>
        `).join('');

        el.innerHTML = `
            <div class="table-scroll">
                <table class="data-table">
                    <thead>
                        <tr>
                            <th>Deal</th><th>Property</th><th>Loan Amount</th><th>Rate</th><th>Created</th>
                        </tr>
                    </thead>
                    <tbody>${rows}</tbody>
                </table>
            </div>
        `;
        el.querySelectorAll('tbody tr').forEach(tr => {
            tr.addEventListener('click', () => this.openRequest(Number(tr.dataset.requestId)));
        });
    },

    // Field spec shared by the create form and the edit-terms form --
    // one source of truth for which fields exist, their labels, units,
    // and which are required, so the two forms can't quietly drift
    // apart on what a "loan term" is.
    TERM_FIELDS: [
        { key: 'deal_name', label: 'Deal Name', type: 'text', required: false },
        { key: 'property_address', label: 'Property Address', type: 'text', required: true },
        { key: 'loan_amount', label: 'Loan Amount ($)', type: 'number', required: true, step: '0.01' },
        { key: 'annual_rate_pct', label: 'Interest Rate (%)', type: 'number', required: true, step: '0.001' },
        { key: 'amortization_years', label: 'Amortization (years)', type: 'number', required: true, step: '1' },
        { key: 'term_years', label: 'Term (years)', type: 'number', required: false, step: '1' },
        { key: 'interest_only_months', label: 'Interest-Only Period (months)', type: 'number', required: false, step: '1' },
        { key: 'purchase_price', label: 'Purchase Price ($)', type: 'number', required: false, step: '0.01' },
        { key: 'appraised_value', label: 'Appraised Value ($)', type: 'number', required: false, step: '0.01' },
        { key: 'unit_count', label: 'Units', type: 'number', required: false, step: '1' },
    ],

    termsFormHtml(idPrefix, values) {
        const fields = this.TERM_FIELDS.map(f => {
            const value = values && values[f.key] !== undefined && values[f.key] !== null ? values[f.key] : '';
            return `
                <div class="loan-uw-field">
                    <label for="${idPrefix}_${f.key}">${escapeHtml(f.label)}${f.required ? ' *' : ''}</label>
                    <input type="${f.type}" id="${idPrefix}_${f.key}" class="text-input" step="${f.step || 'any'}"
                           value="${escapeHtml(String(value))}" ${f.required ? 'required' : ''}>
                </div>
            `;
        }).join('');
        return `
            <div class="loan-uw-form-grid">${fields}</div>
            <p class="view-subtitle">Provide a purchase price or an appraised value (or both) -- at least one is required for an LTV figure.</p>
            <div class="loan-uw-form-actions">
                <button class="btn-secondary" id="${idPrefix}_cancel" type="button">Cancel</button>
                <button class="btn-primary" id="${idPrefix}_save" type="button">Save</button>
            </div>
            <p class="error-text" id="${idPrefix}_error" style="display:none;"></p>
        `;
    },

    readTermsForm(idPrefix) {
        const terms = {};
        for (const f of this.TERM_FIELDS) {
            const input = document.getElementById(`${idPrefix}_${f.key}`);
            const raw = input.value.trim();
            if (raw === '') continue;
            terms[f.key] = f.type === 'number' ? Number(raw) : raw;
        }
        return terms;
    },

    toggleNewRequestForm() {
        const form = document.getElementById('loanUwNewRequestForm');
        const showing = form.style.display !== 'none';
        if (showing) {
            form.style.display = 'none';
            form.innerHTML = '';
            return;
        }
        form.innerHTML = this.termsFormHtml('loanUwNew', {});
        form.style.display = '';
        document.getElementById('loanUwNew_cancel').addEventListener('click', () => this.toggleNewRequestForm());
        document.getElementById('loanUwNew_save').addEventListener('click', () => this.submitNewRequest());
    },

    async submitNewRequest() {
        const errorEl = document.getElementById('loanUwNew_error');
        errorEl.style.display = 'none';
        const saveBtn = document.getElementById('loanUwNew_save');
        saveBtn.disabled = true;
        try {
            const terms = this.readTermsForm('loanUwNew');
            const created = await Api.createLoanUnderwritingRequest(terms);
            this.toggleNewRequestForm();
            showToast('Loan request created.', 'success');
            await this.openRequest(created.id);
        } catch (err) {
            errorEl.textContent = err.message;
            errorEl.style.display = '';
        } finally {
            saveBtn.disabled = false;
        }
    },

    // ---- DETAIL PANEL ----

    async openRequest(requestId) {
        this.currentRequestId = requestId;
        this.currentResult = null;
        this.showDetailPanel();
        document.getElementById('loanUwResultsSection').style.display = 'none';
        document.getElementById('loanUwSummaryStrip').innerHTML = `
            <div class="health-metric"><div class="skeleton skeleton-text"></div><div class="health-metric-label">Loading</div></div>
        `;
        try {
            this.currentRequest = await Api.getLoanUnderwritingRequest(requestId);
            this.renderTerms();
            this.renderAssumptionsForm();
            await this.tryLoadResult();
        } catch (err) {
            showError(`Failed to load loan request: ${err.message}`);
            this.showListPanel();
        }
    },

    renderTerms() {
        const r = this.currentRequest;
        document.getElementById('loanUwTermsForm').style.display = 'none';
        document.getElementById('loanUwTermsContent').innerHTML = `
            <div class="loan-uw-kv-list">
                <div class="loan-uw-kv-row"><span class="loan-uw-kv-label">Deal</span><span class="loan-uw-kv-value">${escapeHtml(r.deal_name || '(unnamed deal)')}</span></div>
                <div class="loan-uw-kv-row"><span class="loan-uw-kv-label">Property</span><span class="loan-uw-kv-value">${escapeHtml(r.property_address)}</span></div>
                <div class="loan-uw-kv-row"><span class="loan-uw-kv-label">Loan Amount</span><span class="loan-uw-kv-value">${this.money(r.loan_amount)}</span></div>
                <div class="loan-uw-kv-row"><span class="loan-uw-kv-label">Rate</span><span class="loan-uw-kv-value">${this.pct(r.annual_rate_pct)}</span></div>
                <div class="loan-uw-kv-row"><span class="loan-uw-kv-label">Amortization</span><span class="loan-uw-kv-value">${r.amortization_years} yrs</span></div>
                <div class="loan-uw-kv-row"><span class="loan-uw-kv-label">Term</span><span class="loan-uw-kv-value">${r.term_years != null ? r.term_years + ' yrs' : 'n/a'}</span></div>
                <div class="loan-uw-kv-row"><span class="loan-uw-kv-label">Interest-Only</span><span class="loan-uw-kv-value">${r.interest_only_months || 0} mo</span></div>
                <div class="loan-uw-kv-row"><span class="loan-uw-kv-label">Purchase Price</span><span class="loan-uw-kv-value">${this.money(r.purchase_price)}</span></div>
                <div class="loan-uw-kv-row"><span class="loan-uw-kv-label">Appraised Value</span><span class="loan-uw-kv-value">${this.money(r.appraised_value)}</span></div>
                <div class="loan-uw-kv-row"><span class="loan-uw-kv-label">Units</span><span class="loan-uw-kv-value">${r.unit_count != null ? r.unit_count : 'n/a'}</span></div>
            </div>
        `;
    },

    toggleEditTermsForm() {
        const form = document.getElementById('loanUwTermsForm');
        const showing = form.style.display !== 'none';
        if (showing) {
            form.style.display = 'none';
            return;
        }
        form.innerHTML = this.termsFormHtml('loanUwEdit', this.currentRequest);
        form.style.display = '';
        document.getElementById('loanUwEdit_cancel').addEventListener('click', () => this.toggleEditTermsForm());
        document.getElementById('loanUwEdit_save').addEventListener('click', () => this.submitEditTerms());
    },

    async submitEditTerms() {
        const errorEl = document.getElementById('loanUwEdit_error');
        errorEl.style.display = 'none';
        const saveBtn = document.getElementById('loanUwEdit_save');
        saveBtn.disabled = true;
        try {
            const terms = this.readTermsForm('loanUwEdit');
            this.currentRequest = await Api.updateLoanUnderwritingRequest(this.currentRequestId, terms);
            document.getElementById('loanUwTermsForm').style.display = 'none';
            this.renderTerms();
            showToast('Loan terms updated.', 'success');
            await this.tryLoadResult();
        } catch (err) {
            errorEl.textContent = err.message;
            errorEl.style.display = '';
        } finally {
            saveBtn.disabled = false;
        }
    },

    // The six assumptions/constraints, with their unit for display --
    // kept here rather than fetched from the backend's assumption_rows
    // on every render, since the form needs to exist (with the request's
    // current stored values) even before a T-12 upload makes
    // assumption_rows available at all.
    ASSUMPTION_FIELDS: [
        { key: 'vacancy_pct', label: 'Vacancy', unit: '%', kind: 'assumptions' },
        { key: 'management_fee_pct', label: 'Management Fee', unit: '% of EGI', kind: 'assumptions' },
        { key: 'replacement_reserves_per_unit', label: 'Replacement Reserves', unit: '$/unit/yr', kind: 'assumptions' },
        { key: 'target_dscr', label: 'Target DSCR', unit: 'x', kind: 'constraints' },
        { key: 'max_ltv_pct', label: 'Maximum LTV', unit: '%', kind: 'constraints' },
        { key: 'min_debt_yield_pct', label: 'Minimum Debt Yield', unit: '%', kind: 'constraints' },
    ],

    renderAssumptionsForm() {
        const r = this.currentRequest;
        const fields = this.ASSUMPTION_FIELDS.map(f => {
            const value = r[f.kind][f.key];
            return `
                <div class="loan-uw-field">
                    <label for="loanUwAssum_${f.key}">${escapeHtml(f.label)}<span class="loan-uw-field-hint">${escapeHtml(f.unit)}</span></label>
                    <input type="number" id="loanUwAssum_${f.key}" class="text-input" step="any" value="${value}">
                </div>
            `;
        }).join('');
        document.getElementById('loanUwAssumptionsForm').innerHTML = `
            <div class="loan-uw-form-grid">${fields}</div>
            <p class="error-text" id="loanUwAssum_error" style="display:none;"></p>
        `;
    },

    async submitAssumptions() {
        const errorEl = document.getElementById('loanUwAssum_error');
        errorEl.style.display = 'none';
        const saveBtn = document.getElementById('loanUwSaveAssumptionsBtn');
        saveBtn.disabled = true;
        try {
            const assumptions = {};
            const constraints = {};
            for (const f of this.ASSUMPTION_FIELDS) {
                const value = Number(document.getElementById(`loanUwAssum_${f.key}`).value);
                (f.kind === 'assumptions' ? assumptions : constraints)[f.key] = value;
            }
            this.currentRequest = await Api.updateLoanUnderwritingAssumptions(this.currentRequestId, { assumptions, constraints });
            showToast('Assumptions saved.', 'success');
            await this.tryLoadResult();
        } catch (err) {
            errorEl.textContent = err.message;
            errorEl.style.display = '';
        } finally {
            saveBtn.disabled = false;
        }
    },

    async uploadT12() {
        const fileInput = document.getElementById('loanUwT12FileInput');
        const file = fileInput.files[0];
        if (!file) {
            showError('Choose a T-12 file (.csv or .xlsx) first.');
            return;
        }
        const btn = document.getElementById('loanUwT12UploadBtn');
        btn.disabled = true;
        btn.textContent = 'Uploading...';
        try {
            const result = await Api.uploadLoanUnderwritingT12(this.currentRequestId, file);
            fileInput.value = '';
            this.renderT12Snapshot(result.snapshot, result.warnings || []);
            showToast('T-12 uploaded.', 'success');
            await this.tryLoadResult();
        } catch (err) {
            showError(`Failed to upload T-12: ${err.message}`);
        } finally {
            btn.disabled = false;
            btn.textContent = 'Upload T-12';
        }
    },

    renderT12Snapshot(snapshot, warnings) {
        const content = document.getElementById('loanUwT12Content');
        if (!snapshot) {
            content.innerHTML = '<p class="view-subtitle">No T-12 uploaded yet. Underwriting needs one to build the NOI.</p>';
        } else {
            content.innerHTML = `
                <div class="loan-uw-kv-list">
                    <div class="loan-uw-kv-row"><span class="loan-uw-kv-label">File</span><span class="loan-uw-kv-value">${escapeHtml(snapshot.filename)}</span></div>
                    <div class="loan-uw-kv-row"><span class="loan-uw-kv-label">Uploaded</span><span class="loan-uw-kv-value">${escapeHtml((snapshot.uploaded_at || '').slice(0, 10))}</span></div>
                </div>
            `;
        }
        const warningsEl = document.getElementById('loanUwT12Warnings');
        if (warnings && warnings.length) {
            warningsEl.innerHTML = `
                <div class="loan-uw-warning-list">
                    <strong>Parsing warnings:</strong>
                    <ul>${warnings.map(w => `<li>${escapeHtml(w)}</li>`).join('')}</ul>
                </div>
            `;
        } else {
            warningsEl.innerHTML = '';
        }
    },

    // Tries to load the full underwriting result; a 400 ("no T-12
    // uploaded yet") is an expected, unexceptional state here, not an
    // error to show the user as a failure -- it just means the results
    // section stays hidden until a T-12 is on file.
    async tryLoadResult() {
        try {
            this.currentResult = await Api.getLoanUnderwritingResult(this.currentRequestId);
            this.renderT12Snapshot(this.currentResult.t12_snapshot, this.currentResult.t12_snapshot ? this.currentResult.t12_snapshot.warnings : []);
            this.renderResults();
        } catch (err) {
            this.currentResult = null;
            document.getElementById('loanUwResultsSection').style.display = 'none';
            document.getElementById('loanUwSummaryStrip').innerHTML = `
                <div class="health-metric"><div class="health-metric-value">--</div><div class="health-metric-label">Upload a T-12 to underwrite</div></div>
            `;
            // No T-12 snapshot to show yet, either.
            if (!document.getElementById('loanUwT12Content').innerHTML) {
                this.renderT12Snapshot(null, []);
            }
        }
    },

    renderResults() {
        const result = this.currentResult;
        if (!result) return;

        const buildUp = result.noi_build_up;
        const ratios = result.ratios;
        const sizing = result.sizing;

        document.getElementById('loanUwSummaryStrip').innerHTML = `
            <div class="health-metric"><div class="health-metric-value">${this.money(buildUp.underwritten_noi)}</div><div class="health-metric-label">Underwritten NOI</div></div>
            <div class="health-metric"><div class="health-metric-value">${this.ratio(ratios.dscr)}</div><div class="health-metric-label">DSCR</div></div>
            <div class="health-metric"><div class="health-metric-value">${this.pct(ratios.ltv_pct)}</div><div class="health-metric-label">LTV</div></div>
            <div class="health-metric"><div class="health-metric-value">${this.pct(ratios.debt_yield_pct)}</div><div class="health-metric-label">Debt Yield</div></div>
            <div class="health-metric"><div class="health-metric-value">${this.pct(ratios.breakeven_occupancy_pct)}</div><div class="health-metric-label">Breakeven Occupancy</div></div>
            <div class="health-metric"><div class="health-metric-value">${escapeHtml(sizing.binding_constraint_label || 'n/a')}</div><div class="health-metric-label">Binding Constraint</div></div>
        `;

        document.getElementById('loanUwResultsSection').style.display = '';
        document.getElementById('loanUwResultsContent').innerHTML =
            this.noiTableHtml(buildUp) +
            this.ratiosTableHtml(result) +
            this.maxLoanTableHtml(sizing, result.constraints_used) +
            this.stressTableHtml(result.stress_tests || []) +
            this.sensitivityGridHtml(result.sensitivity_grid);
    },

    noiTableHtml(buildUp) {
        const rows = [
            ['Gross Potential Rent', this.money(buildUp.gross_potential_rent)],
            [`Less: Vacancy (${this.pct(buildUp.vacancy_pct)})`, `(${this.money(buildUp.vacancy_amount)})`],
            ['Less: Loss to Lease', `(${this.money(buildUp.loss_to_lease)})`],
            ['Less: Concessions', `(${this.money(buildUp.concessions)})`],
            ['Less: Bad Debt', `(${this.money(buildUp.bad_debt)})`],
            ['Effective Rental Income', this.money(buildUp.effective_rental_income)],
            ['Plus: Other Income', this.money(buildUp.other_income)],
            ['Effective Gross Income', this.money(buildUp.effective_gross_income)],
            ['Less: Operating Expenses (ex. mgmt)', `(${this.money(buildUp.operating_expenses_ex_management)})`],
            [`Less: Management Fee (${this.pct(buildUp.management_fee_pct)} of EGI)`, `(${this.money(buildUp.management_fee)})`],
            [`Less: Replacement Reserves (${this.money(buildUp.replacement_reserves_per_unit)}/unit)`, `(${this.money(buildUp.replacement_reserves)})`],
            ['Underwritten NOI', this.money(buildUp.underwritten_noi)],
        ];
        return this.simpleTableHtml('Underwritten NOI Build-Up', ['Line', 'Amount'], rows, rows.length - 1);
    },

    // Human-readable labels for the engine's value_basis_source values
    // (see app/loan_underwriting.py's compute_value_basis) -- the API
    // returns the raw field name ("purchase_price"/"appraised_value"),
    // which reads as a bug to anyone outside the codebase if shown
    // verbatim in the UI.
    LTV_BASIS_LABELS: { purchase_price: 'purchase price', appraised_value: 'appraised value' },

    ratiosTableHtml(result) {
        const ratios = result.ratios;
        const ds = result.debt_service;
        const basisLabel = this.LTV_BASIS_LABELS[ratios.ltv_basis] || ratios.ltv_basis || 'n/a';
        const rows = [
            ['DSCR (fully amortizing)', this.ratio(ratios.dscr)],
            ['DSCR (year one, as paid)', this.ratio(ratios.dscr_year_one)],
            ['DSCR (interest-only)', this.ratio(ratios.dscr_interest_only)],
            ['LTV', `${this.pct(ratios.ltv_pct)} (vs. ${escapeHtml(basisLabel)})`],
            ['Debt Yield', this.pct(ratios.debt_yield_pct)],
            ['Breakeven Occupancy', this.pct(ratios.breakeven_occupancy_pct)],
            ['Annual Debt Service (amortizing)', this.money(ds.annual_debt_service_amortizing)],
        ];
        return this.simpleTableHtml('Ratios', ['Ratio', 'Value'], rows);
    },

    maxLoanTableHtml(sizing, constraints) {
        const binding = sizing.binding_constraint;
        const rows = [
            { key: 'dscr', label: 'Target DSCR', test: `${constraints.target_dscr}x`, value: sizing.max_loan_by_dscr },
            { key: 'ltv', label: 'Maximum LTV', test: this.pct(constraints.max_ltv_pct), value: sizing.max_loan_by_ltv },
            { key: 'debt_yield', label: 'Minimum Debt Yield', test: this.pct(constraints.min_debt_yield_pct), value: sizing.max_loan_by_debt_yield },
        ];
        const bodyRows = rows.map(r => `
            <tr class="${r.key === binding ? 'loan-uw-binding-row' : ''}">
                <td>${escapeHtml(r.label)}</td><td>${escapeHtml(r.test)}</td><td>${this.money(r.value)}</td>
                <td>${r.key === binding ? 'BINDS' : ''}</td>
            </tr>
        `).join('');
        return `
            <h3 class="loan-uw-section-heading">Maximum Loan by Constraint</h3>
            <div class="table-scroll">
                <table class="data-table">
                    <thead><tr><th>Constraint</th><th>Test</th><th>Maximum Loan</th><th>Binds?</th></tr></thead>
                    <tbody>${bodyRows}</tbody>
                </table>
            </div>
            <p class="view-subtitle">Maximum supportable loan: <strong>${this.money(sizing.maximum_loan)}</strong></p>
        `;
    },

    stressTableHtml(cases) {
        const rows = cases.map(c => `
            <tr>
                <td>${escapeHtml(c.label)}</td>
                <td>${this.money(c.underwritten_noi)}</td>
                <td class="${c.dscr !== null && c.dscr < 1.0 ? 'loan-uw-below-breakeven' : ''}">${this.ratio(c.dscr)}</td>
                <td>${this.pct(c.debt_yield_pct)}</td>
                <td>${this.pct(c.breakeven_occupancy_pct)}</td>
                <td>${this.money(c.maximum_loan)}</td>
                <td>${escapeHtml(c.binding_constraint || '')}</td>
            </tr>
        `).join('');
        return `
            <h3 class="loan-uw-section-heading">Stress Tests</h3>
            <div class="table-scroll">
                <table class="data-table">
                    <thead><tr><th>Case</th><th>NOI</th><th>DSCR</th><th>Debt Yield</th><th>Breakeven Occ.</th><th>Max Loan</th><th>Binds</th></tr></thead>
                    <tbody>${rows}</tbody>
                </table>
            </div>
        `;
    },

    sensitivityGridHtml(grid) {
        if (!grid) return '';
        const header = `<th>Rate \\ Occupancy</th>` + grid.occupancy_levels_pct.map(o => `<th>${o.toFixed(0)}%</th>`).join('');
        const rows = grid.rows.map(row => {
            const deltaLabel = row.rate_delta_bps ? `${row.rate_delta_bps > 0 ? '+' : ''}${row.rate_delta_bps}bp` : 'base';
            const cells = row.cells.map(cell => {
                const below = cell.dscr !== null && cell.dscr < 1.0;
                return `<td class="${below ? 'loan-uw-below-breakeven' : ''}">${this.ratio(cell.dscr)}</td>`;
            }).join('');
            return `<tr><td>${row.annual_rate_pct.toFixed(2)}% (${deltaLabel})</td>${cells}</tr>`;
        }).join('');
        return `
            <h3 class="loan-uw-section-heading">DSCR Sensitivity: Rate vs. Occupancy</h3>
            <div class="table-scroll">
                <table class="data-table">
                    <thead><tr>${header}</tr></thead>
                    <tbody>${rows}</tbody>
                </table>
            </div>
            <p class="view-subtitle">Cells below 1.00x DSCR (the property does not cover its debt service) are highlighted.</p>
        `;
    },

    simpleTableHtml(title, headers, rows, boldLastRow) {
        const bodyRows = rows.map((row, i) => `
            <tr${boldLastRow !== undefined && i === boldLastRow ? ' class="loan-uw-binding-row"' : ''}>
                ${row.map(cell => `<td>${escapeHtml(String(cell))}</td>`).join('')}
            </tr>
        `).join('');
        return `
            <h3 class="loan-uw-section-heading">${escapeHtml(title)}</h3>
            <div class="table-scroll">
                <table class="data-table">
                    <thead><tr>${headers.map(h => `<th>${escapeHtml(h)}</th>`).join('')}</tr></thead>
                    <tbody>${bodyRows}</tbody>
                </table>
            </div>
        `;
    },

    async downloadCreditMemo() {
        const btn = document.getElementById('loanUwExportMemoBtn');
        btn.disabled = true;
        btn.textContent = 'Generating...';
        try {
            const response = await Api.exportLoanUnderwritingCreditMemo(this.currentRequestId);
            const blob = await response.blob();
            const dealSlug = (this.currentRequest.deal_name || this.currentRequest.property_address || 'loan_request')
                .replace(/[^A-Za-z0-9_.-]/g, '_');
            const fallbackName = `credit_memo_${dealSlug}.docx`;
            const filename = filenameFromResponse(response, fallbackName);
            triggerBlobDownload(blob, filename);
            showToast('Credit memo generated and downloaded.', 'success');
        } catch (err) {
            showError(`Failed to generate credit memo: ${err.message}`);
        } finally {
            btn.disabled = false;
            btn.textContent = 'Download Credit Memo (Word)';
        }
    },
};

registerView('loanunderwriting', LoanUnderwriting);

function _initLoanUnderwritingViewBindings() {
    document.getElementById('loanUwRefreshBtn').addEventListener('click', () => LoanUnderwriting.loadList());
    document.getElementById('loanUwNewRequestBtn').addEventListener('click', () => LoanUnderwriting.toggleNewRequestForm());
    document.getElementById('loanUwBackBtn').addEventListener('click', () => LoanUnderwriting.load());
    document.getElementById('loanUwEditTermsBtn').addEventListener('click', () => LoanUnderwriting.toggleEditTermsForm());
    document.getElementById('loanUwT12UploadBtn').addEventListener('click', () => LoanUnderwriting.uploadT12());
    document.getElementById('loanUwSaveAssumptionsBtn').addEventListener('click', () => LoanUnderwriting.submitAssumptions());
    document.getElementById('loanUwRefreshResultBtn').addEventListener('click', () => LoanUnderwriting.tryLoadResult());
    document.getElementById('loanUwExportMemoBtn').addEventListener('click', () => LoanUnderwriting.downloadCreditMemo());
}
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _initLoanUnderwritingViewBindings);
} else {
    _initLoanUnderwritingViewBindings();
}
