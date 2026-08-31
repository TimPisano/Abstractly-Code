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
        // credentials: 'include' is required now that most routes are
        // behind real per-user login (see backend/app/auth.py) -- fetch
        // omits cookies on a cross-origin request by default, and the
        // frontend (its own port) and backend API are different origins
        // in this project's dev setup, so the session cookie a login
        // sets would otherwise never be sent back on later requests.
        // `options` can still override this per-call if a route ever
        // needs to opt out, but no caller does today.
        response = await fetch(`${API_BASE_URL}${path}`, { credentials: 'include', ...options });
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

    // Directly overwrites one field's value on the document row passed
    // as leaseId -- callers must target whichever document (base lease
    // or amendment) currently governs the field's EFFECTIVE value (see
    // leaseFieldSource's effective_document_id), not necessarily the
    // base lease's own id, or the edit can be silently shadowed by an
    // amendment that already overrides the same field. taskId links the
    // edit to the task it happened under (surfaced back via
    // GET /tasks/<id>'s field_edits).
    updateLeaseField(leaseId, fieldName, { value, confidence, note, taskId } = {}) {
        const body = { value };
        if (confidence) body.confidence = confidence;
        if (note) body.note = note;
        if (taskId != null) body.task_id = taskId;
        return apiRequest(`/leases/${leaseId}/fields/${fieldName}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
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

    // ---- Team messaging (backend/app/messaging.py) ----
    listThreads() {
        return apiRequest('/threads');
    },
    createThread(threadType, participantUserIds, name) {
        const body = { thread_type: threadType, participant_user_ids: participantUserIds };
        if (name) body.name = name;
        return apiRequest('/threads', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    },
    getThreadMessages(threadId, since) {
        return apiRequest(`/threads/${threadId}/messages${since ? `?since=${encodeURIComponent(since)}` : ''}`);
    },
    sendThreadMessage(threadId, body) {
        return apiRequest(`/threads/${threadId}/messages`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ body }) });
    },
    markThreadRead(threadId) {
        return apiRequest(`/threads/${threadId}/read`, { method: 'POST' });
    },
    unreadMessageCount() {
        return apiRequest('/messages/unread-count');
    },

    // ---- Team members (backend/app/api.py, step 3) ----
    listTeamMembers() {
        return apiRequest('/team/members');
    },

    // ---- Assignments / Tasks (backend/app/assignments.py) ----
    listAssignments({ assignedTo, status, targetType } = {}) {
        const params = new URLSearchParams();
        if (assignedTo != null) params.set('assigned_to', assignedTo);
        if (status) params.set('status', status);
        if (targetType) params.set('target_type', targetType);
        const qs = params.toString();
        return apiRequest(`/assignments${qs ? `?${qs}` : ''}`);
    },
    createAssignment(targetType, target, assignedToUserId, note) {
        const body = { target_type: targetType, target, assigned_to_user_id: assignedToUserId };
        if (note) body.note = note;
        return apiRequest('/assignments', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    },
    updateAssignmentStatus(assignmentId, status) {
        return apiRequest(`/assignments/${assignmentId}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status }) });
    },
    deleteAssignment(assignmentId) {
        return apiRequest(`/assignments/${assignmentId}`, { method: 'DELETE' });
    },

    // ---- Today view (backend/app/assignments.py's compute_today_view) ----
    todayView(userId) {
        return apiRequest(`/today${userId != null ? `?user_id=${userId}` : ''}`);
    },

    // ---- Tasks (backend/app/tasks.py) -- distinct from assignments:
    // a task is a concrete to-do (title/description/due date), an
    // assignment is "who owns this record". ----
    getTask(taskId) {
        return apiRequest(`/tasks/${taskId}`);
    },
    listTasks({ assignedTo, status, dueBefore, dueAfter, leaseId, discrepancyId } = {}) {
        const params = new URLSearchParams();
        if (assignedTo != null) params.set('assigned_to', assignedTo);
        if (status) params.set('status', status);
        if (dueBefore) params.set('due_before', dueBefore);
        if (dueAfter) params.set('due_after', dueAfter);
        if (leaseId != null) params.set('lease_id', leaseId);
        if (discrepancyId != null) params.set('discrepancy_id', discrepancyId);
        const qs = params.toString();
        return apiRequest(`/tasks${qs ? `?${qs}` : ''}`);
    },
    createTask({ title, description, dueDate, assignedToUserId, leaseId, discrepancyId, propertyAddress } = {}) {
        const body = { title };
        if (description) body.description = description;
        if (dueDate) body.due_date = dueDate;
        if (assignedToUserId != null) body.assigned_to_user_id = assignedToUserId;
        if (leaseId != null) body.lease_id = leaseId;
        if (discrepancyId != null) body.discrepancy_id = discrepancyId;
        if (propertyAddress) body.property_address = propertyAddress;
        return apiRequest('/tasks', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    },
    createTaskFromDiscrepancy(discrepancyId, { assignedToUserId, dueDate } = {}) {
        const body = {};
        if (assignedToUserId != null) body.assigned_to_user_id = assignedToUserId;
        if (dueDate) body.due_date = dueDate;
        return apiRequest(`/tasks/from-discrepancy/${discrepancyId}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    },
    createTaskFromAlert(alertId, { assignedToUserId, dueDate } = {}) {
        const body = {};
        if (assignedToUserId != null) body.assigned_to_user_id = assignedToUserId;
        if (dueDate) body.due_date = dueDate;
        return apiRequest(`/tasks/from-alert/${alertId}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    },
    updateTask(taskId, fields) {
        return apiRequest(`/tasks/${taskId}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(fields) });
    },
    assignTask(taskId, assignedToUserId) {
        return apiRequest(`/tasks/${taskId}/assign`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ assigned_to_user_id: assignedToUserId }) });
    },
    // correctSource/note are only needed when completing ("done") a task
    // that's tied to a still-open discrepancy -- the backend resolves
    // that discrepancy (same real /discrepancies/<id>/resolve path a
    // direct resolve uses) and completes the task in one call, rejecting
    // with 400 if they're required but missing rather than silently
    // completing the task with the discrepancy left open.
    updateTaskStatus(taskId, status, { correctSource, note } = {}) {
        const body = { status };
        if (correctSource) body.correct_source = correctSource;
        if (note) body.note = note;
        return apiRequest(`/tasks/${taskId}/status`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    },
    deleteTask(taskId) {
        return apiRequest(`/tasks/${taskId}`, { method: 'DELETE' });
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

    // ---- Team management (admin-only on the backend -- see
    // app/auth.py's require_role('admin')). ----

    authSession() {
        return apiRequest('/auth/session');
    },

    listTeamMembers() {
        return apiRequest('/team/members');
    },

    createTeamMember({ name, email, role, password }) {
        return apiRequest('/team/members', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, email, role, password }),
        });
    },

    updateTeamMember(memberId, { name, role, status } = {}) {
        const body = {};
        if (name !== undefined) body.name = name;
        if (role !== undefined) body.role = role;
        if (status !== undefined) body.status = status;
        return apiRequest(`/team/members/${memberId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
    },

    resetTeamMemberPassword(memberId, password) {
        return apiRequest(`/team/members/${memberId}/reset-password`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ password }),
        });
    },
};
