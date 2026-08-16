/**
 * Lease Portfolio Intelligence - API Client
 * Thin fetch wrappers for every backend endpoint. No state, no DOM —
 * just request/response plumbing shared by every view.
 *
 * API_BASE_URL comes from ../config.js, loaded before this script (see
 * access-gate.js's APP_SCRIPTS list) and before access-gate.js itself.
 */

/**
 * Shared request helper. Throws an Error with the backend's own error
 * message (falling back to statusText) so callers can surface it
 * directly without re-deriving what went wrong.
 *
 * A raw `fetch()` failure (backend unreachable, DNS/network down, CORS)
 * is caught and re-thrown with one consistent, human-readable message
 * instead of letting the browser's own technical error text (e.g.
 * "Failed to fetch" in Chrome, "fetch failed" in Node/some environments)
 * propagate to a view's `catch (err) { showError(err.message) }` and end
 * up on screen verbatim. This is the one place every API call passes
 * through, so fixing it here covers every caller — a per-call-site
 * `err.message || "fallback"` doesn't work, since a raw network error's
 * `message` is a non-empty string and always wins over the fallback.
 */
async function apiRequest(path, options = {}) {
    let response;
    try {
        response = await fetch(`${API_BASE_URL}${path}`, options);
    } catch (networkErr) {
        throw new Error("Couldn't reach the server. Check your connection and try again.");
    }

    const contentType = response.headers.get('content-type') || '';
    if (!response.ok) {
        let message = response.statusText;
        if (contentType.includes('application/json')) {
            try {
                const data = await response.json();
                message = data.error || message;
            } catch (e) { /* fall through to statusText */ }
        }
        throw new Error(message);
    }

    if (contentType.includes('application/json')) {
        return response.json();
    }
    return response;
}

const Api = {
    // Stateless single-document extraction (no persistence)
    extract(file) {
        const formData = new FormData();
        formData.append('file', file);
        return apiRequest('/extract', { method: 'POST', body: formData });
    },

    // Leases (persisted)
    uploadLease(file) {
        const formData = new FormData();
        formData.append('file', file);
        return apiRequest('/leases', { method: 'POST', body: formData });
    },

    uploadLeasesBatch(files) {
        const formData = new FormData();
        for (const file of files) formData.append('files', file);
        return apiRequest('/leases/batch', { method: 'POST', body: formData });
    },

    listLeases() {
        return apiRequest('/leases');
    },

    getLease(leaseId) {
        return apiRequest(`/leases/${leaseId}`);
    },

    deleteLease(leaseId) {
        return apiRequest(`/leases/${leaseId}`, { method: 'DELETE' });
    },

    renameLease(leaseId, displayName) {
        return apiRequest(`/leases/${leaseId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ display_name: displayName }),
        });
    },

    listLeaseTags(leaseId) {
        return apiRequest(`/leases/${leaseId}/tags`);
    },

    addLeaseTag(leaseId, tag) {
        return apiRequest(`/leases/${leaseId}/tags`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ tag }),
        });
    },

    removeLeaseTag(leaseId, tag) {
        return apiRequest(`/leases/${leaseId}/tags/${encodeURIComponent(tag)}`, { method: 'DELETE' });
    },

    listAllTags() {
        return apiRequest('/tags');
    },

    listLeasesByTag(tag) {
        return apiRequest(`/leases?tag=${encodeURIComponent(tag)}`);
    },

    uploadAmendment(leaseId, file) {
        const formData = new FormData();
        formData.append('file', file);
        return apiRequest(`/leases/${leaseId}/amendments`, { method: 'POST', body: formData });
    },

    listAmendments(leaseId) {
        return apiRequest(`/leases/${leaseId}/amendments`);
    },

    // Portfolio analysis
    portfolioSummary() {
        return apiRequest('/portfolio/summary');
    },

    portfolioTimeline() {
        return apiRequest('/portfolio/timeline');
    },

    portfolioRisks() {
        return apiRequest('/portfolio/risks');
    },

    portfolioAttention() {
        return apiRequest('/portfolio/attention');
    },

    portfolioHealth() {
        return apiRequest('/portfolio/health');
    },

    portfolioExpirationAlerts() {
        return apiRequest('/portfolio/expiration-alerts');
    },

    recentActivity(limit = 10) {
        return apiRequest(`/activity?limit=${limit}`);
    },

    leaseRisks(leaseId) {
        return apiRequest(`/leases/${leaseId}/risks`);
    },

    askQuestion(question, leaseId) {
        const body = { question };
        if (leaseId !== undefined && leaseId !== null) body.lease_id = leaseId;
        return apiRequest('/qa', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
    },

    compareLeases(leaseIds) {
        return apiRequest(`/leases/compare?ids=${leaseIds.join(',')}`);
    },

    selectionSummary(leaseIds) {
        return apiRequest(`/leases/selection-summary?ids=${leaseIds.join(',')}`);
    },

    bulkExportExcelUrl(leaseIds) {
        return `${API_BASE_URL}/leases/export.xlsx?ids=${leaseIds.join(',')}`;
    },

    bulkExportGoogleSheets(leaseIds) {
        return apiRequest('/leases/export/google-sheets', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ids: leaseIds }),
        });
    },

    bulkTagLeases(leaseIds, tag) {
        return apiRequest('/leases/bulk-tag', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ids: leaseIds, tag }),
        });
    },

    bulkDeleteLeases(leaseIds) {
        return apiRequest('/leases/bulk-delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ids: leaseIds }),
        });
    },

    leaseBenchmark(leaseId) {
        return apiRequest(`/leases/${leaseId}/benchmark`);
    },

    rentRollCsvUrl() {
        return `${API_BASE_URL}/portfolio/rent-roll.csv`;
    },

    rentRollExcelUrl() {
        return `${API_BASE_URL}/portfolio/rent-roll.xlsx`;
    },

    portfolioReportUrl() {
        return `${API_BASE_URL}/portfolio/report`;
    },

    exportToGoogleSheets() {
        return apiRequest('/portfolio/export/google-sheets', { method: 'POST' });
    },

    leaseExportExcelUrl(leaseId) {
        return `${API_BASE_URL}/leases/${leaseId}/export.xlsx`;
    },

    exportLeaseToGoogleSheets(leaseId) {
        return apiRequest(`/leases/${leaseId}/export/google-sheets`, { method: 'POST' });
    },

    async portfolioReportHtml() {
        const response = await apiRequest('/portfolio/report');
        return response.text();
    },

    health() {
        return apiRequest('/health');
    },
};
