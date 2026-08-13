/**
 * Lease Portfolio Intelligence - API Client
 * Thin fetch wrappers for every backend endpoint. No state, no DOM —
 * just request/response plumbing shared by every view.
 */

const API_BASE_URL = 'http://localhost:5000';

/**
 * Shared request helper. Throws an Error with the backend's own error
 * message (falling back to statusText) so callers can surface it
 * directly without re-deriving what went wrong.
 */
async function apiRequest(path, options = {}) {
    const response = await fetch(`${API_BASE_URL}${path}`, options);

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

    async portfolioReportHtml() {
        const response = await apiRequest('/portfolio/report');
        return response.text();
    },

    health() {
        return apiRequest('/health');
    },
};
