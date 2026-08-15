/**
 * Upload View: drag-and-drop or click-to-browse upload of one or more
 * PDF leases. Single file uses POST /leases; multiple files use
 * POST /leases/batch, which processes each independently so one
 * corrupted file in a batch doesn't fail the rest.
 *
 * One uploaded FILE can now produce more than one persisted LEASE — if
 * the backend detects the file bundles several distinct leases, it
 * splits them into separate, individually-accurate records instead of
 * one merged one (see DECISIONS.md). Both /leases and /leases/batch
 * responses reflect that: a successful file result always carries a
 * `leases` array (length 1 for an ordinary single-lease file), not a
 * single `lease` object.
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
        progressList.innerHTML = validFiles.map(f => `
            <div class="upload-progress-item" data-file="${escapeHtml(f.name)}">
                <span class="spinner-small"></span> ${escapeHtml(f.name)}
            </div>
        `).join('');

        try {
            let fileResults;
            if (validFiles.length === 1) {
                try {
                    const response = await Api.uploadLease(validFiles[0]);
                    response.leases.forEach(lease => recordStats(validFiles[0].name, lease.extracted_fields));
                    fileResults = [{ filename: validFiles[0].name, success: true, leases: response.leases, split_count: response.split_count }];
                } catch (err) {
                    fileResults = [{ filename: validFiles[0].name, success: false, error: err.message }];
                }
            } else {
                const batchResult = await Api.uploadLeasesBatch(validFiles);
                fileResults = batchResult.results;
                fileResults.forEach(r => {
                    if (r.success) r.leases.forEach(lease => recordStats(r.filename, lease.extracted_fields));
                });
            }

            document.getElementById('uploadProgress').style.display = 'none';
            this.showResults(fileResults);
        } catch (err) {
            document.getElementById('uploadProgress').style.display = 'none';
            showError(`Upload failed: ${err.message}`);
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
