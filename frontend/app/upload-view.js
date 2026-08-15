/**
 * Upload View: drag-and-drop or click-to-browse upload of one or more
 * PDF leases. Single file uses POST /leases; multiple files use
 * POST /leases/batch, which processes each independently so one
 * corrupted file in a batch doesn't fail the rest.
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
            let results;
            if (validFiles.length === 1) {
                try {
                    const lease = await Api.uploadLease(validFiles[0]);
                    recordStats(validFiles[0].name, lease.extracted_fields);
                    results = [{ filename: validFiles[0].name, success: true, lease }];
                } catch (err) {
                    results = [{ filename: validFiles[0].name, success: false, error: err.message }];
                }
            } else {
                const batchResult = await Api.uploadLeasesBatch(validFiles);
                results = batchResult.results;
                results.forEach(r => {
                    if (r.success) recordStats(r.filename, r.lease.extracted_fields);
                });
            }

            document.getElementById('uploadProgress').style.display = 'none';
            this.showResults(results);
        } catch (err) {
            document.getElementById('uploadProgress').style.display = 'none';
            showError(`Upload failed: ${err.message}`);
        }
    },

    showResults(results) {
        const succeeded = results.filter(r => r.success);
        const failed = results.filter(r => !r.success);

        const container = document.getElementById('uploadResultsList');
        container.innerHTML = `
            <p class="upload-summary">
                <strong>${succeeded.length}</strong> succeeded, <strong>${failed.length}</strong> failed
                (${results.length} total)
            </p>
        ` + results.map(r => `
            <div class="upload-result-item ${r.success ? 'success' : 'failure'}">
                <span class="upload-result-icon">${r.success ? '✓' : '✗'}</span>
                <span class="upload-result-name">${escapeHtml(r.filename)}</span>
                ${r.success
                    ? `<span class="upload-result-detail">${escapeHtml(fieldValue(r.lease, 'tenant') || 'Tenant not found')}</span>`
                    : `<span class="upload-result-detail error-text">${escapeHtml(r.error)}</span>`}
            </div>
        `).join('');

        document.getElementById('uploadResults').style.display = 'block';

        if (succeeded.length > 0) {
            showToast(`${succeeded.length} lease(s) added to your portfolio.`, 'success');
        }
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
