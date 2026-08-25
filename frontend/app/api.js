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

    importRentRoll(file, propertyAddress) {
        const formData = new FormData();
        formData.append('file', file);
        if (propertyAddress) formData.append('property_address', propertyAddress);
        return apiRequest('/leases/import-rent-roll', { method: 'POST', body: formData });
    },

    t12Reconciliation(file, propertyAddress) {
        const formData = new FormData();
        formData.append('file', file);
        formData.append('property_address', propertyAddress);
        return apiRequest('/portfolio/t12-reconciliation', { method: 'POST', body: formData });
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

    // Distinct from portfolioHealth() above -- that's "what needs
    // attention today"; this is "how much can I trust the data itself"
    // (see backend/app/portfolio_health_score.py).
    portfolioHealthScore() {
        return apiRequest('/portfolio/health-score');
    },

    portfolioExpirationAlerts() {
        return apiRequest('/portfolio/expiration-alerts');
    },

    portfolioConfidenceSummary() {
        return apiRequest('/portfolio/confidence-summary');
    },

    portfolioTenantConcentration() {
        return apiRequest('/portfolio/tenant-concentration');
    },

    portfolioRollover() {
        return apiRequest('/portfolio/rollover');
    },

    portfolioLossToLease() {
        return apiRequest('/portfolio/loss-to-lease');
    },

    portfolioRentRollReconciliation() {
        return apiRequest('/portfolio/rent-roll-reconciliation');
    },

    // Discrepancies: a stable, persisted identity for a flag/mismatch
    // that's otherwise recomputed fresh on every request (risk flags,
    // cross-lease mismatches, rent-roll-vs-lease and rent-roll-vs-T12
    // reconciliation) -- see backend/app/discrepancies.py. The flag/
    // mismatch objects returned by /portfolio/risks, /leases/<id>/risks,
    // /portfolio/rent-roll-reconciliation, and /portfolio/t12-reconciliation
    // already carry discrepancy_id/resolution_status/resolution inline;
    // these are for acting on one directly.
    listDiscrepancies({ status, leaseId, type } = {}) {
        const params = new URLSearchParams();
        if (status) params.set('status', status);
        if (leaseId != null) params.set('lease_id', leaseId);
        if (type) params.set('type', type);
        const qs = params.toString();
        return apiRequest(`/discrepancies${qs ? `?${qs}` : ''}`);
    },

    getDiscrepancy(discrepancyId) {
        return apiRequest(`/discrepancies/${discrepancyId}`);
    },

    // Header-stat digest for a standalone Discrepancies tab -- counts by
    // status/severity/type across every discrepancy ever recorded, same
    // role /alerts/summary plays for the Alerts tab.
    discrepanciesSummary() {
        return apiRequest('/discrepancies/summary');
    },

    resolveDiscrepancy(discrepancyId, { correctSource, note, resolvedBy, resolvedByEmail }) {
        return apiRequest(`/discrepancies/${discrepancyId}/resolve`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ correct_source: correctSource, note, resolved_by: resolvedBy, resolved_by_email: resolvedByEmail }),
        });
    },

    reopenDiscrepancy(discrepancyId, { note, resolvedBy, resolvedByEmail }) {
        return apiRequest(`/discrepancies/${discrepancyId}/reopen`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ note, resolved_by: resolvedBy, resolved_by_email: resolvedByEmail }),
        });
    },

    // Full audit-trail source chain for one field -- effective value/source
    // plus every prior value this field held across amendments (see
    // backend/app/database.py's get_field_source_chain).
    leaseFieldSource(leaseId, fieldName) {
        return apiRequest(`/leases/${leaseId}/fields/${fieldName}/source`);
    },

    // Portfolio history & trends for one property (rent growth, tenant
    // turnover, historical rollover pattern) -- see
    // backend/app/portfolio_history.py.
    portfolioPropertyTrends(propertyAddress) {
        return apiRequest(`/portfolio/property-trends?property_address=${encodeURIComponent(propertyAddress)}`);
    },

    // Portfolio-wide sibling of the above -- every building's trends in
    // one response (server-side cached, see backend/app/cache.py),
    // replacing what used to require fetching property-trends once per
    // distinct building and merging client-side.
    portfolioTrends() {
        return apiRequest('/portfolio/trends');
    },

    // Team comments/notes -- visible to everyone (this app has no per-
    // account scoping yet), self-reported author identity same as
    // discrepancy resolutions.
    listLeaseComments(leaseId) {
        return apiRequest(`/leases/${leaseId}/comments`);
    },

    addLeaseComment(leaseId, { authorName, body, authorEmail }) {
        return apiRequest(`/leases/${leaseId}/comments`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ author_name: authorName, body, author_email: authorEmail }),
        });
    },

    listDiscrepancyComments(discrepancyId) {
        return apiRequest(`/discrepancies/${discrepancyId}/comments`);
    },

    // Portfolio-wide feed across BOTH leases and discrepancies, most
    // recent first -- what a standalone Team Notes tab needs, which
    // neither listLeaseComments nor listDiscrepancyComments (each
    // scoped to one target) can answer alone.
    recentComments(limit = 20) {
        return apiRequest(`/comments/recent?limit=${limit}`);
    },

    addDiscrepancyComment(discrepancyId, { authorName, body, authorEmail }) {
        return apiRequest(`/discrepancies/${discrepancyId}/comments`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ author_name: authorName, body, author_email: authorEmail }),
        });
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

    portfolioSummaryPdfUrl() {
        return `${API_BASE_URL}/portfolio/summary.pdf`;
    },

    portfolioMonthlyReportPdfUrl() {
        return `${API_BASE_URL}/portfolio/monthly-report.pdf`;
    },

    exportToGoogleSheets() {
        return apiRequest('/portfolio/export/google-sheets', { method: 'POST' });
    },

    leaseExportExcelUrl(leaseId) {
        return `${API_BASE_URL}/leases/${leaseId}/export.xlsx`;
    },

    leaseSummaryPdfUrl(leaseId) {
        return `${API_BASE_URL}/leases/${leaseId}/summary.pdf`;
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

    // Proactive alerts (see backend/app/alerts.py) -- lease expirations,
    // new discrepancies, below-market rent, tenant concentration. No
    // scheduled generation exists yet (explicitly out of scope on the
    // backend), so the frontend calls generateAlerts() itself on load
    // to keep the feed/badge current -- safe to call as often as
    // needed, idempotent against unchanged data.
    generateAlerts() {
        return apiRequest('/alerts/generate', { method: 'POST' });
    },

    listAlerts({ status, type, severity, leaseId } = {}) {
        const params = new URLSearchParams();
        if (status) params.set('status', status);
        if (type) params.set('type', type);
        if (severity) params.set('severity', severity);
        if (leaseId != null) params.set('lease_id', leaseId);
        const qs = params.toString();
        return apiRequest(`/alerts${qs ? `?${qs}` : ''}`);
    },

    alertsSummary() {
        return apiRequest('/alerts/summary');
    },

    dismissAlert(alertId, { dismissedBy, note }) {
        return apiRequest(`/alerts/${alertId}/dismiss`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ dismissed_by: dismissedBy, note }),
        });
    },

    // Investment memo export (PDF/Excel, per-property or whole-
    // portfolio -- see backend/app/investment_memo.py). POST because an
    // optional T12 file may be attached; content is fixed (key lease
    // terms, discrepancies + resolutions, T12 cross-check, rollover
    // risk) -- there's no section-level include/exclude on the backend,
    // only scope (property vs portfolio) and format. Returns the raw
    // Response (apiRequest passes non-JSON responses through
    // unmodified) so the caller can read filename off the
    // Content-Disposition header and call .blob() itself.
    exportInvestmentMemoPdf({ propertyAddress, t12File } = {}) {
        const formData = new FormData();
        if (propertyAddress) formData.append('property_address', propertyAddress);
        if (t12File) formData.append('t12_file', t12File);
        return apiRequest('/portfolio/investment-memo.pdf', { method: 'POST', body: formData });
    },

    exportInvestmentMemoExcel({ propertyAddress, t12File } = {}) {
        const formData = new FormData();
        if (propertyAddress) formData.append('property_address', propertyAddress);
        if (t12File) formData.append('t12_file', t12File);
        return apiRequest('/portfolio/investment-memo.xlsx', { method: 'POST', body: formData });
    },
};
