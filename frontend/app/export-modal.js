/**
 * Export Report: a small options screen for the investment-memo export
 * (backend/app/investment_memo.py) -- pick a format (PDF or Excel),
 * optionally attach a fresh T12 for a property-scoped export, generate,
 * and download. Opened from the Dashboard (whole-portfolio scope, no
 * property_address) and the Lease Detail view (scoped to that lease's
 * own property_address).
 *
 * There is no section-level include/exclude on the backend -- every
 * export always contains key lease terms, discrepancies + resolutions,
 * a T12 cross-check summary, and a rollover risk summary (see that
 * module's own docstring). The options screen is honest about that
 * rather than showing decorative checkboxes that don't actually change
 * anything: the only real choices are format, scope (fixed per entry
 * point), and an optional T12 attachment.
 *
 * Reuses the `.discrepancy-modal-*` shell classes from
 * discrepancy-modal.js -- a generic modal dialog, not something
 * specific to discrepancies, same "reuse existing classes" precedent
 * this app already follows elsewhere rather than inventing a second
 * modal skin.
 */
const ExportModal = {
    scopeLabel: null,
    propertyAddress: null,
    t12File: null,

    ensureContainer() {
        let el = document.getElementById('exportModalContainer');
        if (!el) {
            el = document.createElement('div');
            el.id = 'exportModalContainer';
            document.body.appendChild(el);
        }
        return el;
    },

    close() {
        const el = document.getElementById('exportModalContainer');
        if (el) el.innerHTML = '';
        document.removeEventListener('keydown', this._escHandler, true);
        this.t12File = null;
    },

    /** `propertyAddress` omitted/null for a whole-portfolio export. */
    open({ scopeLabel, propertyAddress } = {}) {
        this.scopeLabel = scopeLabel || 'Whole Portfolio';
        this.propertyAddress = propertyAddress || null;
        this.t12File = null;
        this._renderOptions();

        this._escHandler = (e) => { if (e.key === 'Escape') this.close(); };
        document.addEventListener('keydown', this._escHandler, true);
    },

    _renderOptions() {
        const container = this.ensureContainer();
        container.innerHTML = `
            <div class="discrepancy-modal-backdrop" id="exportModalBackdrop">
                <div class="discrepancy-modal export-modal" role="dialog" aria-modal="true" aria-label="Export report">
                    <div class="discrepancy-modal-header">
                        <div>
                            <h2>Export Report</h2>
                            <p class="discrepancy-modal-subtitle">${escapeHtml(this.scopeLabel)}</p>
                        </div>
                        <button type="button" class="verify-popover-close discrepancy-modal-close" aria-label="Close">&times;</button>
                    </div>

                    <p class="export-modal-includes">
                        Includes: key lease terms, flagged discrepancies with their resolutions, a T12 cross-check summary, and a rollover risk summary.
                    </p>

                    ${this.propertyAddress ? `
                        <div class="export-modal-t12-row">
                            <label for="exportT12FileInput">Attach a fresh T12 for this property (optional)</label>
                            <input type="file" id="exportT12FileInput" accept=".csv,.xlsx" class="text-input">
                            <p class="export-modal-t12-hint">Without one, the T12 section falls back to the last cross-check on file for this property, if any.</p>
                        </div>
                    ` : ''}

                    <div class="export-modal-format-row">
                        <button class="btn-primary export-format-btn" type="button" data-format="pdf">
                            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
                            Download as PDF
                        </button>
                        <button class="btn-secondary export-format-btn" type="button" data-format="excel">
                            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 13h6m-3-3v6m5 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
                            Download as Excel
                        </button>
                    </div>

                    <div class="discrepancy-modal-actions">
                        <button class="btn-secondary" id="exportCancelBtn" type="button">Cancel</button>
                    </div>
                </div>
            </div>
        `;

        container.querySelector('.discrepancy-modal-close').addEventListener('click', () => this.close());
        container.querySelector('#exportCancelBtn').addEventListener('click', () => this.close());
        container.querySelector('#exportModalBackdrop').addEventListener('click', (e) => {
            if (e.target.id === 'exportModalBackdrop') this.close();
        });
        const t12Input = document.getElementById('exportT12FileInput');
        if (t12Input) t12Input.addEventListener('change', () => { this.t12File = t12Input.files[0] || null; });

        container.querySelectorAll('.export-format-btn').forEach(btn => {
            btn.addEventListener('click', () => this._generate(btn.dataset.format));
        });
    },

    _renderLoading(format) {
        const container = this.ensureContainer();
        container.innerHTML = `
            <div class="discrepancy-modal-backdrop">
                <div class="discrepancy-modal export-modal">
                    <div class="export-modal-loading">
                        <span class="spinner-small"></span>
                        <p>Generating your ${format.toUpperCase()} report&hellip;</p>
                        <p class="export-modal-loading-hint">This can take a few seconds for a large portfolio.</p>
                    </div>
                </div>
            </div>
        `;
    },

    _renderSuccess(filename) {
        const container = this.ensureContainer();
        container.innerHTML = `
            <div class="discrepancy-modal-backdrop" id="exportModalBackdrop">
                <div class="discrepancy-modal export-modal">
                    <div class="export-modal-success">
                        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                        <h3>Downloaded</h3>
                        <p>${escapeHtml(filename)} has been saved to your downloads.</p>
                    </div>
                    <div class="discrepancy-modal-actions">
                        <button class="btn-secondary" id="exportAnotherBtn" type="button">Generate Another</button>
                        <button class="btn-primary" id="exportDoneBtn" type="button">Done</button>
                    </div>
                </div>
            </div>
        `;
        container.querySelector('#exportDoneBtn').addEventListener('click', () => this.close());
        container.querySelector('#exportAnotherBtn').addEventListener('click', () => this._renderOptions());
        container.querySelector('#exportModalBackdrop').addEventListener('click', (e) => {
            if (e.target.id === 'exportModalBackdrop') this.close();
        });
    },

    _renderError(message) {
        const container = this.ensureContainer();
        const existingBody = container.querySelector('.discrepancy-modal');
        if (existingBody) {
            let errorEl = existingBody.querySelector('.export-modal-error');
            if (!errorEl) {
                errorEl = document.createElement('p');
                errorEl.className = 'export-modal-error error-text';
                existingBody.insertBefore(errorEl, existingBody.querySelector('.discrepancy-modal-actions'));
            }
            errorEl.textContent = message;
        }
    },

    async _generate(format) {
        const t12File = this.t12File;
        this._renderLoading(format);

        try {
            const response = format === 'pdf'
                ? await Api.exportInvestmentMemoPdf({ propertyAddress: this.propertyAddress, t12File })
                : await Api.exportInvestmentMemoExcel({ propertyAddress: this.propertyAddress, t12File });
            const blob = await response.blob();
            // Content-Disposition isn't readable here -- it's a
            // cross-origin request (frontend on :8000, backend on :5000)
            // and the backend's CORS setup doesn't list it in
            // Access-Control-Expose-Headers, so filenameFromResponse's
            // header read comes back null every time (confirmed live,
            // not assumed). Building the same scope-labeled name the
            // backend would have sent client-side instead, from data
            // already on hand, rather than a generic fallback -- same
            // sanitization the backend applies (investment_memo_pdf/api.py's
            // safe_name), just done here since the real header can't be
            // read.
            const ext = format === 'pdf' ? 'pdf' : 'xlsx';
            const scopeSlug = this.scopeLabel.replace(/[^A-Za-z0-9_.-]/g, '_');
            const fallbackName = `investment_memo_${scopeSlug}.${ext}`;
            const filename = filenameFromResponse(response, fallbackName);
            triggerBlobDownload(blob, filename);
            this._renderSuccess(filename);
            showToast('Report generated and downloaded.', 'success');
        } catch (err) {
            this._renderOptions();
            this._renderError(err.message);
        }
    },
};
