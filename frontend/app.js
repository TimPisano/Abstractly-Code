/**
 * Lease Portfolio Intelligence - Main App Controller
 * View routing, shared app state, toast notifications, and the session
 * stats panel. Individual views (dashboard-view.js, upload-view.js, etc)
 * each expose a small object with a load()/show() entry point that this
 * router calls on navigation.
 */

const STATS_STORAGE_KEY = 'leaseAbstractionSessionStats';

const AppState = {
    leases: [],           // cached from Api.listLeases(), refreshed on dashboard load
    currentLeaseId: null,  // for the detail view
    compareSelection: new Set(),
};

const FIELD_GROUPS = [
    { name: 'Parties', fields: ['tenant', 'landlord', 'property_address'] },
    { name: 'Financial Terms', fields: ['rent_amount', 'security_deposit', 'cam_charges', 'rent_escalation', 'insurance_requirements', 'square_footage'] },
    { name: 'Dates & Term', fields: ['lease_start_date', 'lease_end_date', 'renewal_options', 'default_cure_period'] },
    { name: 'Special Clauses', fields: ['permitted_use', 'exclusivity_clause'] },
];

const FIELD_LABELS = {
    tenant: 'Tenant Name',
    landlord: 'Landlord Name',
    property_address: 'Property Address',
    rent_amount: 'Monthly Rent',
    security_deposit: 'Security Deposit',
    cam_charges: 'CAM Charges',
    rent_escalation: 'Rent Escalation',
    insurance_requirements: 'Insurance Requirements',
    square_footage: 'Square Footage',
    lease_start_date: 'Lease Start Date',
    lease_end_date: 'Lease End Date',
    renewal_options: 'Renewal Options',
    default_cure_period: 'Default / Cure Period',
    permitted_use: 'Permitted Use',
    exclusivity_clause: 'Exclusivity Clause',
};

/**
 * View router. Each view module registers itself in VIEW_HANDLERS with a
 * load() called every time that view becomes active, so data is always
 * fresh rather than stale from a previous visit.
 */
const VIEW_HANDLERS = {};

function registerView(name, handlers) {
    VIEW_HANDLERS[name] = handlers;
}

function showView(viewName, params) {
    document.querySelectorAll('.view').forEach(el => el.classList.remove('active'));
    const target = document.getElementById(`view-${viewName}`);
    if (target) target.classList.add('active');

    document.querySelectorAll('.nav-item').forEach(el => {
        el.classList.toggle('active', el.dataset.view === viewName);
    });

    const handler = VIEW_HANDLERS[viewName];
    if (handler && typeof handler.load === 'function') {
        handler.load(params);
    }
}

function showLeaseDetail(leaseId) {
    AppState.currentLeaseId = leaseId;
    showView('detail', { leaseId });
}

/**
 * Toast notifications: transient success/error banners, since a
 * multi-view app needs feedback that isn't tied to any one section.
 */
function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    container.appendChild(toast);

    requestAnimationFrame(() => toast.classList.add('show'));
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

function showError(message) {
    showToast(message, 'error');
}

/**
 * Session Stats: a lightweight running tally (persisted in localStorage)
 * of extraction results across documents uploaded this browser session.
 */
function recordStats(filename, extractedFields) {
    const fieldKeys = Object.keys(FIELD_LABELS);
    let foundCount = 0;
    const byConfidence = { high: 0, medium: 0, low: 0 };

    fieldKeys.forEach(key => {
        const field = extractedFields[key];
        if (!field) return;
        if (field.value !== null && field.value !== undefined) {
            foundCount += 1;
            if (field.confidence && byConfidence.hasOwnProperty(field.confidence)) {
                byConfidence[field.confidence] += 1;
            }
        }
    });

    const stats = loadStats();
    stats.push({
        filename,
        timestamp: new Date().toISOString(),
        foundCount,
        totalFields: fieldKeys.length,
        byConfidence,
    });
    saveStats(stats);
}

function loadStats() {
    try {
        const raw = localStorage.getItem(STATS_STORAGE_KEY);
        return raw ? JSON.parse(raw) : [];
    } catch (e) {
        return [];
    }
}

function saveStats(stats) {
    try {
        localStorage.setItem(STATS_STORAGE_KEY, JSON.stringify(stats));
    } catch (e) { /* localStorage unavailable — stats just won't persist */ }
}

function clearStats() {
    saveStats([]);
    renderStatsPanel();
}

function toggleStatsPanel() {
    const panel = document.getElementById('statsPanel');
    const isHidden = panel.style.display === 'none' || !panel.style.display;
    if (isHidden) {
        renderStatsPanel();
        panel.style.display = 'block';
    } else {
        panel.style.display = 'none';
    }
}

function renderStatsPanel() {
    const stats = loadStats();
    const content = document.getElementById('statsContent');

    if (stats.length === 0) {
        content.innerHTML = '<p class="stats-empty">No documents processed yet this session.</p>';
        return;
    }

    const totalDocs = stats.length;
    const avgFound = stats.reduce((sum, s) => sum + s.foundCount, 0) / totalDocs;
    const totalFields = stats[0].totalFields;
    const totalHigh = stats.reduce((sum, s) => sum + s.byConfidence.high, 0);
    const totalMedium = stats.reduce((sum, s) => sum + s.byConfidence.medium, 0);
    const totalLow = stats.reduce((sum, s) => sum + s.byConfidence.low, 0);

    let html = `
        <div class="stats-summary">
            <div class="stats-summary-item">
                <div class="stats-summary-value">${totalDocs}</div>
                <div class="stats-summary-label">Documents Processed</div>
            </div>
            <div class="stats-summary-item">
                <div class="stats-summary-value">${avgFound.toFixed(1)} / ${totalFields}</div>
                <div class="stats-summary-label">Avg. Fields Found</div>
            </div>
            <div class="stats-summary-item">
                <div class="stats-summary-value">${totalHigh}H / ${totalMedium}M / ${totalLow}L</div>
                <div class="stats-summary-label">Confidence Breakdown</div>
            </div>
        </div>
        <table class="stats-table">
            <thead><tr><th>File</th><th>Found</th><th>High</th><th>Medium</th><th>Low</th><th>When</th></tr></thead>
            <tbody>
    `;
    stats.slice().reverse().forEach(s => {
        html += `
            <tr>
                <td>${escapeHtml(s.filename)}</td>
                <td>${s.foundCount} / ${s.totalFields}</td>
                <td>${s.byConfidence.high}</td>
                <td>${s.byConfidence.medium}</td>
                <td>${s.byConfidence.low}</td>
                <td>${formatDate(s.timestamp)}</td>
            </tr>
        `;
    });
    html += '</tbody></table>';
    content.innerHTML = html;
}

/**
 * Shared utilities used across view modules.
 */
function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str == null ? '' : String(str);
    return div.innerHTML;
}

function formatDate(isoString) {
    const date = new Date(isoString);
    return date.toLocaleString();
}

function fieldValue(lease, fieldKey) {
    const field = lease.extracted_fields && lease.extracted_fields[fieldKey];
    return field ? field.value : null;
}

function confidenceBadgeHtml(confidence, found) {
    if (!found) return `<span class="confidence-badge confidence-none">Not Found</span>`;
    const level = confidence || 'unknown';
    const label = level.charAt(0).toUpperCase() + level.slice(1);
    return `<span class="confidence-badge confidence-${level}">${label} Confidence</span>`;
}

function severityBadgeHtml(severity) {
    const label = severity.charAt(0).toUpperCase() + severity.slice(1);
    return `<span class="severity-badge severity-${severity}">${label}</span>`;
}

/**
 * App initialization
 */
function init() {
    document.querySelectorAll('.nav-item[data-view]').forEach(btn => {
        btn.addEventListener('click', () => showView(btn.dataset.view));
    });
    document.querySelectorAll('[data-goto]').forEach(btn => {
        btn.addEventListener('click', () => showView(btn.dataset.goto));
    });

    document.getElementById('statsToggleBtn').addEventListener('click', toggleStatsPanel);
    document.getElementById('clearStatsBtn').addEventListener('click', clearStats);
    document.getElementById('closeStatsBtn').addEventListener('click', () => {
        document.getElementById('statsPanel').style.display = 'none';
    });

    // Kick off the initial view (dashboard, marked active in the HTML)
    showView('dashboard');
}

document.addEventListener('DOMContentLoaded', init);
