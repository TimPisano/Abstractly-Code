/**
 * Upload View: drag-and-drop or click-to-browse upload of one or more
 * PDF leases.
 *
 * Files are uploaded one at a time (POST /leases per file, sequential,
 * not the /leases/batch endpoint) specifically so each file's own
 * progress row can flip from "Processing..." to done/error as soon as
 * THAT file's extraction finishes, instead of every row sitting on a
 * spinner until the slowest file in the batch is done too. A large
 * multi-page PDF next to several small ones would otherwise make the
 * small ones look stuck even though they finished in a second — this
 * way the UI reflects what's actually happening, file by file, and
 * never blocks on the whole set before showing anything. One file
 * failing (corrupted, wrong type, extraction error) doesn't stop the
 * rest from continuing to upload, same guarantee /leases/batch made.
 *
 * One uploaded FILE can still produce more than one persisted LEASE —
 * if the backend detects the file bundles several distinct leases, it
 * splits them into separate, individually-accurate records instead of
 * one merged one (see DECISIONS.md). A successful file result always
 * carries a `leases` array (length 1 for an ordinary single-lease
 * file), not a single `lease` object.
 */

const Upload = {
    load() {
        this.reset();
    },

    reset() {
        document.getElementById('uploadProgress').style.display = 'none';
        document.getElementById('uploadResults').style.display = 'none';
        document.getElementById('uploadProgressList').innerHTML = '';
        document.getElementById('uploadResultsList').innerHTML = '';
        const fileInput = document.getElementById('fileInput');
        if (fileInput) fileInput.value = '';
        RentRollImport.reset();
        T12CrossCheck.reset();
    },

    async handleFiles(fileList) {
        const files = Array.from(fileList).filter(f => f.type === 'application/pdf' || f.name.toLowerCase().endsWith('.pdf'));
        if (files.length === 0) {
            showError('Please select PDF files only.');
            return;
        }

        const oversized = files.filter(f => f.size > 16 * 1024 * 1024);
        if (oversized.length > 0) {
            showError(`${oversized.length} file(s) exceed the 16MB limit and were skipped.`);
        }
        const validFiles = files.filter(f => f.size <= 16 * 1024 * 1024);
        if (validFiles.length === 0) return;

        document.getElementById('uploadResults').style.display = 'none';
        document.getElementById('uploadProgress').style.display = 'block';
        const progressList = document.getElementById('uploadProgressList');
        progressList.innerHTML = validFiles.map((f, i) => `
            <div class="upload-progress-item pending" data-file="${escapeHtml(f.name)}" id="uploadProgressItem-${i}">
                <span class="upload-progress-status-icon"><span class="spinner-small"></span></span>
                <span class="upload-progress-name">${escapeHtml(f.name)}</span>
                <span class="upload-progress-status-text">Waiting&hellip;</span>
            </div>
        `).join('');

        const fileResults = [];
        for (let i = 0; i < validFiles.length; i++) {
            const file = validFiles[i];
            const itemEl = document.getElementById(`uploadProgressItem-${i}`);
            const stopReassurance = this.setProgressItemProcessing(itemEl);

            let result;
            try {
                const response = await Api.uploadLease(file);
                response.leases.forEach(lease => recordStats(file.name, lease.extracted_fields));
                result = { filename: file.name, success: true, leases: response.leases, split_count: response.split_count };
            } catch (err) {
                result = { filename: file.name, success: false, error: err.message };
            }
            stopReassurance();
            fileResults.push(result);
            this.setProgressItemDone(itemEl, result);
        }

        this.showResults(fileResults);
    },

    // A large or multi-lease PDF can genuinely take tens of seconds to
    // process (OCR fallback especially), with no server-side progress
    // to report mid-request -- so instead of one static "Processing…"
    // message the whole time, the text itself escalates over time,
    // so a long-running upload reads as "still working on something
    // big" rather than "did this freeze?" Returns a cleanup function
    // that stops the escalation once the file finishes.
    setProgressItemProcessing(itemEl) {
        if (!itemEl) return () => {};
        itemEl.classList.remove('pending');
        itemEl.classList.add('processing');
        const textEl = itemEl.querySelector('.upload-progress-status-text');
        const messages = [
            [0, 'Processing (running OCR / extracting fields)…'],
            [6000, 'Still working — larger or scanned PDFs take longer…'],
            [15000, 'Still working — a multi-lease PDF can take up to a minute to split and extract…'],
        ];
        textEl.textContent = messages[0][1];
        const timers = messages.slice(1).map(([delay, text]) => setTimeout(() => { textEl.textContent = text; }, delay));
        return () => timers.forEach(clearTimeout);
    },

    setProgressItemDone(itemEl, result) {
        if (!itemEl) return;
        itemEl.classList.remove('pending', 'processing');
        const iconEl = itemEl.querySelector('.upload-progress-status-icon');
        const textEl = itemEl.querySelector('.upload-progress-status-text');

        if (result.success) {
            itemEl.classList.add('done');
            iconEl.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M4.5 12.75l6 6 9-13.5"/></svg>';
            const count = result.split_count || result.leases.length;
            textEl.textContent = count > 1 ? `Done — split into ${count} leases` : 'Done';
        } else {
            itemEl.classList.add('error');
            iconEl.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M6 18L18 6M6 6l12 12"/></svg>';
            textEl.textContent = result.error;
        }
    },

    showResults(fileResults) {
        const succeededFiles = fileResults.filter(r => r.success);
        const failedFiles = fileResults.filter(r => !r.success);
        const totalLeasesCreated = succeededFiles.reduce((sum, r) => sum + (r.split_count || r.leases.length), 0);

        const container = document.getElementById('uploadResultsList');
        container.innerHTML = `
            <p class="upload-summary">
                <strong>${totalLeasesCreated}</strong> lease(s) created from <strong>${succeededFiles.length}</strong> file(s)
                &mdash; <strong>${failedFiles.length}</strong> file(s) failed (${fileResults.length} total)
            </p>
        ` + fileResults.map(r => this.resultRowsHtml(r)).join('');

        document.getElementById('uploadResults').style.display = 'block';

        if (totalLeasesCreated > 0) {
            showToast(`${totalLeasesCreated} lease(s) added to your portfolio.`, 'success');
        }
    },

    resultRowsHtml(r) {
        if (!r.success) {
            return `
                <div class="upload-result-item failure">
                    <span class="upload-result-icon">✗</span>
                    <span class="upload-result-name">${escapeHtml(r.filename)}</span>
                    <span class="upload-result-detail error-text">${escapeHtml(r.error)}</span>
                </div>
            `;
        }

        if (r.leases.length > 1) {
            // Split into several leases: a header row naming the source
            // file, then one indented row per lease it was split into
            // -- each independently named, so it's clear at a glance
            // this file became several distinct portfolio entries, not
            // one.
            const header = `
                <div class="upload-result-item success">
                    <span class="upload-result-icon">✓</span>
                    <span class="upload-result-name">${escapeHtml(r.filename)}</span>
                    <span class="upload-result-detail">Split into ${r.leases.length} separate leases</span>
                </div>
            `;
            const children = r.leases.map(lease => `
                <div class="upload-result-item success upload-result-split-child">
                    <span class="upload-result-icon">&#8618;</span>
                    <span class="upload-result-name">${escapeHtml(lease.display_name)}</span>
                    <span class="upload-result-detail">pages ${lease.source_page_start}&ndash;${lease.source_page_end}</span>
                </div>
                ${this.nonLeaseWarningHtml(lease)}
            `).join('');
            return header + children;
        }

        const lease = r.leases[0];
        return `
            <div class="upload-result-item success">
                <span class="upload-result-icon">✓</span>
                <span class="upload-result-name">${escapeHtml(lease.display_name)}</span>
                <span class="upload-result-detail">${escapeHtml(fieldValue(lease, 'tenant') || 'Tenant not found')}</span>
            </div>
            ${this.nonLeaseWarningHtml(lease)}
        `;
    },

    // looks_like_lease is false only when NONE of tenant/landlord/rent/
    // start/end date were found -- real extraction, real text, just
    // nothing that reads as a lease. Surfaced right where the upload
    // result already is, not buried -- silently filing it as a normal
    // (if very sparse) lease would hide exactly the kind of mistake
    // this warning exists to catch (wrong file picked, a cover page
    // instead of the lease itself, a non-lease PDF entirely).
    nonLeaseWarningHtml(lease) {
        if (lease.looks_like_lease !== false) return '';
        return `
            <div class="upload-result-warning">
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z"/></svg>
                <span>This doesn't look like a lease — no tenant, landlord, rent, or dates were found. Double-check the file before relying on it.</span>
            </div>
        `;
    },
};

/**
 * Rent roll import: a single .csv/.xlsx file, parsed with no fixed
 * column format assumed (see backend/app/rent_roll_import.py) into the
 * same lease shape a PDF upload produces. Deliberately a separate flow
 * from the PDF Upload object above rather than unified with it -- the
 * two have genuinely different semantics (one file in, one lease out
 * vs. one file in, potentially many leases out; an optional property
 * address input that only makes sense here; a different accepted file
 * type) and forcing them into one shared code path would make both
 * harder to follow for what's actually a small amount of logic each.
 */
const RentRollImport = {
    reset() {
        document.getElementById('rentRollResults').style.display = 'none';
        document.getElementById('rentRollProgress').style.display = 'none';
        const fileInput = document.getElementById('rentRollFileInput');
        if (fileInput) fileInput.value = '';
    },

    async handleFile(file) {
        const name = file.name.toLowerCase();
        if (!name.endsWith('.csv') && !name.endsWith('.xlsx')) {
            showError('Please select a .csv or .xlsx rent roll file.');
            return;
        }

        document.getElementById('rentRollResults').style.display = 'none';
        document.getElementById('rentRollProgress').style.display = 'block';

        const propertyAddress = document.getElementById('rentRollPropertyAddress').value.trim();

        try {
            const response = await Api.importRentRoll(file, propertyAddress);
            this.showResults(file.name, response);
            if (response.imported_count > 0) {
                showToast(`${response.imported_count} lease(s) imported from ${file.name}.`, 'success');
            }
        } catch (err) {
            showError(`Couldn't import ${file.name}: ${err.message}`);
        } finally {
            document.getElementById('rentRollProgress').style.display = 'none';
        }
    },

    showResults(filename, response) {
        const container = document.getElementById('rentRollResultsList');
        const skipped = response.skipped_rows || [];

        let html = `
            <p class="upload-summary">
                <strong>${response.imported_count}</strong> lease(s) imported from <strong>${escapeHtml(filename)}</strong>
                ${skipped.length > 0 ? `&mdash; <strong>${skipped.length}</strong> row(s) skipped` : ''}
            </p>
        `;

        html += response.leases.map(lease => `
            <div class="upload-result-item success">
                <span class="upload-result-icon">✓</span>
                <span class="upload-result-name">${escapeHtml(lease.display_name)}</span>
                <span class="upload-result-detail">${escapeHtml(fieldValue(lease, 'tenant') || 'Tenant not found')}</span>
            </div>
        `).join('');

        // Every skipped row is shown, not just a count -- a real broker
        // file commonly has several vacant/total rows, and a user
        // relying on this import wants to see WHY a row they expected
        // to see isn't there, not just a number that might mean
        // anything.
        if (skipped.length > 0) {
            html += `
                <div class="upload-result-item" style="margin-top:0.75rem;">
                    <span class="upload-result-detail">Skipped rows:</span>
                </div>
            ` + skipped.map(s => `
                <div class="upload-result-item">
                    <span class="upload-result-icon">&mdash;</span>
                    <span class="upload-result-name">Row ${s.row}</span>
                    <span class="upload-result-detail">${escapeHtml(s.reason)}</span>
                </div>
            `).join('');
        }

        container.innerHTML = html;
        document.getElementById('rentRollResults').style.display = 'block';
    },
};

// Stateless -- a T12 upload never creates a lease record (see
// DECISIONS.md's "Rent-roll-vs-T12 cross-check" entry for why: a T12
// isn't a lease, and treating it like a rent-roll import would corrupt
// every other per-lease computation). So this object has no "reset on
// success" list to maintain the way RentRollImport does -- just the
// most recent single result, shown until the next check replaces it.
const T12CrossCheck = {
    reset() {
        document.getElementById('t12Results').style.display = 'none';
        document.getElementById('t12Progress').style.display = 'none';
        const fileInput = document.getElementById('t12FileInput');
        if (fileInput) fileInput.value = '';
    },

    async handleFile(file) {
        const name = file.name.toLowerCase();
        if (!name.endsWith('.csv') && !name.endsWith('.xlsx')) {
            showError('Please select a .csv or .xlsx T12 statement.');
            return;
        }

        const propertyAddress = document.getElementById('t12PropertyAddress').value.trim();
        if (!propertyAddress) {
            showError('Enter the property address this T12 is for before uploading -- a T12 covers one property, and without it there\'s nothing to compare against.');
            return;
        }

        document.getElementById('t12Results').style.display = 'none';
        document.getElementById('t12Progress').style.display = 'block';

        try {
            const response = await Api.t12Reconciliation(file, propertyAddress);
            this.showResult(file.name, response);
        } catch (err) {
            showError(`Couldn't check ${file.name}: ${err.message}`);
        } finally {
            document.getElementById('t12Progress').style.display = 'none';
        }
    },

    _money(value) {
        return value == null ? '—' : `$${value.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
    },

    lastResponse: null,
    lastFilename: null,

    showResult(filename, response) {
        this.lastResponse = response;
        this.lastFilename = filename;
        const container = document.getElementById('t12ResultContent');

        if (response.matched_lease_count === 0) {
            container.innerHTML = `
                <p class="upload-summary">No leases found at <strong>${escapeHtml(response.property_address)}</strong> to compare against.</p>
                <p class="upload-result-detail">This T12's actual rental income is <strong>${this._money(response.t12_annual_rental_income)}</strong>/year, but nothing on file matches that property address yet -- upload a rent roll or lease PDFs for it first, or check the address matches exactly how it appears elsewhere in this app.</p>
            `;
            document.getElementById('t12Results').style.display = 'block';
            return;
        }

        const isResolved = response.resolution_status === 'resolved';
        const badge = isResolved
            ? '<span class="severity-badge severity-low">Resolved</span>'
            : response.flagged
                ? '<span class="severity-badge severity-high">Discrepancy Flagged</span>'
                : '<span class="severity-badge severity-low">Matches</span>';

        const directionText = {
            rent_roll_higher: 'the rent roll is higher than the T12\'s actual income',
            t12_higher: 'the T12\'s actual income is higher than the rent roll',
            agree: 'they agree exactly',
        }[response.direction] || '';

        container.innerHTML = `
            <p class="upload-summary">${badge} &mdash; <strong>${escapeHtml(response.property_address)}</strong></p>
            <div class="health-strip">
                <div class="health-metric">
                    <div class="health-metric-value">${this._money(response.rent_roll_annual_rent)}${verifyTriggerHtml('t12-rentroll-verify')}</div>
                    <div class="health-metric-label">Rent roll (annualized)</div>
                    <div class="health-metric-sub">${response.matched_lease_count} lease(s)${response.excluded_lease_count ? `, ${response.excluded_lease_count} excluded (no usable rent)` : ''}</div>
                </div>
                <div class="health-metric">
                    <div class="health-metric-value">${this._money(response.t12_annual_rental_income)}</div>
                    <div class="health-metric-label">T12 actual rental income</div>
                    <div class="health-metric-sub">from &ldquo;${escapeHtml(response.t12_source.quote)}&rdquo;, ${escapeHtml(filename)}</div>
                </div>
                <div class="health-metric">
                    <div class="health-metric-value">${this._money(Math.abs(response.difference))} (${response.difference_pct}%)</div>
                    <div class="health-metric-label">Difference</div>
                    <div class="health-metric-sub">${directionText}</div>
                </div>
            </div>
            ${response.discrepancy_id != null ? `
                <button class="btn-secondary" id="t12ResolveBtn" type="button">${isResolved ? 'View Resolution' : 'Resolve Discrepancy'}</button>
            ` : ''}
        `;
        document.getElementById('t12Results').style.display = 'block';

        const verifyBtn = container.querySelector('.t12-rentroll-verify');
        if (verifyBtn) {
            verifyBtn.addEventListener('click', async () => {
                const leases = await Api.listLeases().catch(() => AppState.leases);
                AppState.leases = leases;
                const normalizedTarget = normalizeBuildingAddress(response.property_address);
                const matching = leases
                    .filter(l => normalizeBuildingAddress(fieldValue(l, 'property_address')) === normalizedTarget)
                    .map(l => ({ id: l.id, name: l.display_name || lease_filename(l), value: fieldValue(l, 'rent_amount') }));
                VerifyPopover.showAggregate(verifyBtn, { title: 'Rent Roll (Annualized) — Contributing Leases', leases: matching });
            });
        }

        const resolveBtn = document.getElementById('t12ResolveBtn');
        if (resolveBtn) resolveBtn.addEventListener('click', () => this._openResolveModal());
    },

    _openResolveModal() {
        const response = this.lastResponse;
        DiscrepancyModal.open({
            title: 'Resolve Discrepancy',
            subtitle: `${response.property_address} — Annual Rental Income`,
            discrepancyId: response.discrepancy_id,
            resolutionStatus: response.resolution_status,
            resolution: response.resolution,
            sides: [
                {
                    key: 'rent_roll', label: 'Rent Roll', displayValue: this._money(response.rent_roll_annual_rent),
                    sourceNote: `Aggregated across ${response.matched_lease_count} lease(s) at this property — use the "Rent roll (annualized)" verify icon on the result panel for the per-lease breakdown.`,
                },
                {
                    key: 't12', label: 'T12', displayValue: this._money(response.t12_annual_rental_income),
                    source: response.t12_source,
                },
            ],
        }, { onResolved: (updated) => {
            this.lastResponse = { ...response, resolution_status: updated.status, resolution: updated.latest_resolution || response.resolution };
            this.showResult(this.lastFilename, this.lastResponse);
        } });
    },
};

registerView('upload', Upload);

// Loaded dynamically by access-gate.js after the gate passes, well after
// DOMContentLoaded already fired -- see the comment in app.js for why a
// readyState check is needed here instead of a plain addEventListener.
function _initUploadViewBindings() {
    const uploadBox = document.getElementById('uploadBox');
    const fileInput = document.getElementById('fileInput');

    uploadBox.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) Upload.handleFiles(e.target.files);
    });

    uploadBox.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadBox.classList.add('dragover');
    });
    uploadBox.addEventListener('dragleave', (e) => {
        e.preventDefault();
        uploadBox.classList.remove('dragover');
    });
    uploadBox.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadBox.classList.remove('dragover');
        if (e.dataTransfer.files.length > 0) Upload.handleFiles(e.dataTransfer.files);
    });

    const rentRollBox = document.getElementById('rentRollUploadBox');
    const rentRollInput = document.getElementById('rentRollFileInput');

    rentRollBox.addEventListener('click', () => rentRollInput.click());
    rentRollInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) RentRollImport.handleFile(e.target.files[0]);
    });

    rentRollBox.addEventListener('dragover', (e) => {
        e.preventDefault();
        rentRollBox.classList.add('dragover');
    });
    rentRollBox.addEventListener('dragleave', (e) => {
        e.preventDefault();
        rentRollBox.classList.remove('dragover');
    });
    rentRollBox.addEventListener('drop', (e) => {
        e.preventDefault();
        rentRollBox.classList.remove('dragover');
        if (e.dataTransfer.files.length > 0) RentRollImport.handleFile(e.dataTransfer.files[0]);
    });

    const t12Box = document.getElementById('t12UploadBox');
    const t12Input = document.getElementById('t12FileInput');

    t12Box.addEventListener('click', () => t12Input.click());
    t12Input.addEventListener('change', (e) => {
        if (e.target.files.length > 0) T12CrossCheck.handleFile(e.target.files[0]);
    });

    t12Box.addEventListener('dragover', (e) => {
        e.preventDefault();
        t12Box.classList.add('dragover');
    });
    t12Box.addEventListener('dragleave', (e) => {
        e.preventDefault();
        t12Box.classList.remove('dragover');
    });
    t12Box.addEventListener('drop', (e) => {
        e.preventDefault();
        t12Box.classList.remove('dragover');
        if (e.dataTransfer.files.length > 0) T12CrossCheck.handleFile(e.dataTransfer.files[0]);
    });
}
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _initUploadViewBindings);
} else {
    _initUploadViewBindings();
}
