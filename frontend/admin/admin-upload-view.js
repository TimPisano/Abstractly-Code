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
}
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _initUploadViewBindings);
} else {
    _initUploadViewBindings();
}
