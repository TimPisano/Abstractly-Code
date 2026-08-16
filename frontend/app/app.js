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

function timeAgo(isoString) {
    const then = new Date(isoString).getTime();
    if (Number.isNaN(then)) return '';
    const diffSec = Math.max(0, Math.floor((Date.now() - then) / 1000));
    if (diffSec < 60) return 'just now';
    const diffMin = Math.floor(diffSec / 60);
    if (diffMin < 60) return `${diffMin}m ago`;
    const diffHr = Math.floor(diffMin / 60);
    if (diffHr < 24) return `${diffHr}h ago`;
    const diffDay = Math.floor(diffHr / 24);
    if (diffDay < 7) return `${diffDay}d ago`;
    return formatDate(isoString);
}

const MONTHS_MAP = {
    jan: 0, january: 0, feb: 1, february: 1, mar: 2, march: 2, apr: 3, april: 3,
    may: 4, jun: 5, june: 5, jul: 6, july: 6, aug: 7, august: 7,
    sep: 8, sept: 8, september: 8, oct: 9, october: 9, nov: 10, november: 10, dec: 11, december: 11,
};

/**
 * Parses the date display strings the extraction engine can produce
 * ("04/01/2025", "April 1, 2025", "1st day of January, 2026" — see
 * field_extractor.py's DATE_REGEX / normalize.py's parse_date, which
 * this deliberately mirrors so client-side sorting agrees with the
 * server's own date handling) into a millisecond timestamp usable for
 * comparison. Returns null for anything it can't parse, so a missing
 * or unrecognized date sorts as "unknown" rather than crashing the
 * sort or silently landing at an arbitrary position.
 */
function parseLeaseDate(value) {
    if (!value) return null;
    const str = value.trim();

    let m = str.match(/^(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})$/);
    if (m) {
        let [, month, day, year] = m;
        month = parseInt(month, 10); day = parseInt(day, 10); year = parseInt(year, 10);
        if (year < 100) year += year < 70 ? 2000 : 1900;
        const d = new Date(year, month - 1, day);
        return Number.isNaN(d.getTime()) ? null : d.getTime();
    }

    m = str.match(/^(\d{1,2})(?:st|nd|rd|th)?\s+day\s+of\s+([A-Za-z]+\.?),?\s+(\d{4})$/i);
    if (m) {
        const day = parseInt(m[1], 10);
        const month = MONTHS_MAP[m[2].toLowerCase().replace(/\.$/, '')];
        const year = parseInt(m[3], 10);
        if (month === undefined) return null;
        const d = new Date(year, month, day);
        return Number.isNaN(d.getTime()) ? null : d.getTime();
    }

    m = str.match(/^([A-Za-z]+\.?)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})$/i);
    if (m) {
        const month = MONTHS_MAP[m[1].toLowerCase().replace(/\.$/, '')];
        const day = parseInt(m[2], 10);
        const year = parseInt(m[3], 10);
        if (month === undefined) return null;
        const d = new Date(year, month, day);
        return Number.isNaN(d.getTime()) ? null : d.getTime();
    }

    return null;
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

/**
 * Shared confidence-summary panel markup, used on both the dashboard
 * (portfolio-wide) and the lease detail page (per-lease) so the two
 * can't visually drift apart -- same tiers, same bar, same legend,
 * built from whatever shape compute_lease_confidence_summary /
 * compute_portfolio_confidence_summary returned. `flaggedList` is an
 * optional array of human-readable field labels (only the per-lease
 * caller has a specific field list to show; the portfolio-wide summary
 * only has a count, not names, since a flagged field belongs to one
 * particular lease).
 */
function confidenceSummaryPanelHtml(summary, title, flaggedList) {
    if (!summary || summary.total_fields === 0) {
        return `
            <div class="panel-header"><h2>${escapeHtml(title)}</h2></div>
            <p class="empty-inline">No fields to summarize yet.</p>
        `;
    }

    const tiers = [
        { key: 'high', label: 'High' },
        { key: 'medium', label: 'Medium' },
        { key: 'low', label: 'Low' },
        { key: 'not_found', label: 'Not Found' },
    ];

    return `
        <div class="panel-header">
            <h2>${escapeHtml(title)}</h2>
        </div>
        <p class="confidence-summary-headline">
            <strong>${summary.high} of ${summary.total_fields}</strong> fields high-confidence
            ${summary.flagged_for_review > 0
                ? `&mdash; <strong class="confidence-summary-flagged">${summary.flagged_for_review} flagged for review</strong>`
                : '&mdash; nothing flagged for review'}
        </p>
        <div class="confidence-summary-bar">
            ${tiers.map(t => t.key === 'not_found' || summary[t.key] === 0 ? '' : `
                <div class="confidence-summary-segment confidence-summary-segment-${t.key}"
                     style="width:${(summary[t.key] / summary.total_fields) * 100}%"
                     title="${summary[t.key]} ${t.label}"></div>
            `).join('')}
        </div>
        <div class="confidence-summary-legend">
            ${tiers.map(t => `
                <span class="confidence-summary-legend-item">
                    <span class="confidence-summary-swatch confidence-summary-segment-${t.key}"></span>
                    ${summary[t.key]} ${t.label}
                </span>
            `).join('')}
        </div>
        ${flaggedList && flaggedList.length > 0 ? `
            <p class="confidence-summary-flagged-list">Flagged: ${flaggedList.map(escapeHtml).join(', ')}</p>
        ` : ''}
    `;
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

// init() is deliberately NOT self-invoked here (no DOMContentLoaded
// listener, no immediate call). It's called by access-gate.js's
// loadAppScripts() instead, only after every script in APP_SCRIPTS has
// finished loading -- including dashboard-view.js, upload-view.js, etc.
//
// Why that matters: init() calls showView('dashboard'), which looks up
// VIEW_HANDLERS.dashboard -- populated by dashboard-view.js calling
// registerView('dashboard', Dashboard) as a side effect of that script
// merely being loaded. app.js loads *before* dashboard-view.js in
// APP_SCRIPTS (view modules need `registerView`/`AppState`/etc. to
// already exist when THEY load). If init() ran as soon as app.js itself
// finished executing -- e.g. via a readyState check at the bottom of
// this file, which is what used to be here -- it would call
// showView('dashboard') before dashboard-view.js had registered
// anything, VIEW_HANDLERS.dashboard would be undefined, and the lookup
// would silently no-op: Dashboard.load() never runs, so metrics/
// attention/health/activity stay empty and the empty-state ("No leases
// uploaded yet" + its Upload button) never appears either, since even
// that is toggled by Dashboard.renderTable(). The page isn't broken,
// exactly -- the header "+ Upload Leases" button, the quick-actions
// bar's "Upload Lease" button, and the sidebar's "Upload Leases" nav
// item are all still present and clickable (they're wired earlier in
// this same init() call, against static HTML that doesn't depend on
// any other script) -- but the dashboard itself renders permanently
// blank until the user happens to navigate away and back, at which
// point every script has long since loaded and it works fine. This was
// exactly the LOCAL_DEV_MODE bug: real, not hypothetical, confirmed via
// jsdom against the live app before this fix.
window.init = init;
