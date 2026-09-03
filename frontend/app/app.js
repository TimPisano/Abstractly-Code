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

let currentViewName = 'dashboard';

/**
 * Contextual top toolbar: the actions shown change with the active
 * section instead of the same fixed 4 buttons appearing everywhere.
 * Every action here is a navigation (data-goto, same mechanism every
 * other "go to X" button in this app already uses), so one delegated
 * listener on the container (bound once, see initContextualToolbar())
 * handles all of them regardless of how many times the inner HTML gets
 * replaced -- no per-render rebinding needed.
 *
 * A view not listed here falls back to the dashboard's own set rather
 * than rendering an empty bar, so a new view added later doesn't
 * silently lose its quick actions until someone remembers to add an
 * entry.
 */
const TOOLBAR_ICON_PATHS = {
    upload: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 7.5m0 0L7.5 12M12 7.5v9"/>',
    compare: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M7.5 21L3 16.5m0 0L7.5 12M3 16.5h18M16.5 3L21 7.5m0 0L16.5 12M21 7.5H3"/>',
    report: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>',
    calendar: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"/>',
    alert: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M14.857 17.082a23.848 23.848 0 005.454-1.31A8.967 8.967 0 0118 9.75V9A6 6 0 006 9v.75a8.967 8.967 0 01-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 01-5.714 0m5.714 0a3 3 0 11-5.714 0"/>',
    discrepancy: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9.75 9.75l4.5 4.5m0-4.5l-4.5 4.5M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>',
    dashboard: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M3 3h8v8H3V3zm10 0h8v5h-8V3zm0 8h8v10h-8V11zM3 14h8v7H3v-7z"/>',
    rentroll: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M3 10h18M3 14h18M7 6h10a2 2 0 012 2v8a2 2 0 01-2 2H7a2 2 0 01-2-2V8a2 2 0 012-2z"/>',
    task: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>',
};

const CONTEXTUAL_TOOLBAR_ACTIONS = {
    dashboard: [
        { label: 'Upload Lease', icon: 'upload', goto: 'upload' },
        { label: 'Run Comparison', icon: 'compare', goto: 'comparison' },
        { label: 'Generate Report', icon: 'report', goto: 'report' },
        { label: 'View Expirations', icon: 'calendar', goto: 'timeline' },
    ],
    alerts: [
        { label: 'View Discrepancies', icon: 'discrepancy', goto: 'discrepancies' },
        { label: 'Upload Lease', icon: 'upload', goto: 'upload' },
    ],
    discrepancies: [
        { label: 'View Alerts', icon: 'alert', goto: 'alerts' },
        { label: 'Upload Lease', icon: 'upload', goto: 'upload' },
    ],
    trends: [
        { label: 'Upload Lease', icon: 'upload', goto: 'upload' },
        { label: 'View Expirations', icon: 'calendar', goto: 'timeline' },
    ],
    upload: [
        { label: 'Go to Dashboard', icon: 'dashboard', goto: 'dashboard' },
    ],
    timeline: [
        { label: 'Upload Lease', icon: 'upload', goto: 'upload' },
        { label: 'Generate Report', icon: 'report', goto: 'report' },
    ],
    rentroll: [
        { label: 'Upload Lease', icon: 'upload', goto: 'upload' },
        { label: 'Run Comparison', icon: 'compare', goto: 'comparison' },
    ],
    comparison: [
        { label: 'Upload Lease', icon: 'upload', goto: 'upload' },
    ],
    qa: [
        { label: 'Go to Dashboard', icon: 'dashboard', goto: 'dashboard' },
        { label: 'View Discrepancies', icon: 'discrepancy', goto: 'discrepancies' },
    ],
    report: [
        { label: 'Upload Lease', icon: 'upload', goto: 'upload' },
    ],
    teamnotes: [
        { label: 'View Discrepancies', icon: 'discrepancy', goto: 'discrepancies' },
        { label: 'View Alerts', icon: 'alert', goto: 'alerts' },
    ],
    team: [
        { label: 'Go to Dashboard', icon: 'dashboard', goto: 'dashboard' },
    ],
    tasks: [
        { label: 'Upload Lease', icon: 'upload', goto: 'upload' },
        { label: 'View Discrepancies', icon: 'discrepancy', goto: 'discrepancies' },
    ],
    detail: [
        { label: 'Go to Dashboard', icon: 'dashboard', goto: 'dashboard' },
        { label: 'Upload Lease', icon: 'upload', goto: 'upload' },
    ],
};

function renderContextualToolbar(viewName) {
    const bar = document.getElementById('quickActionsBar');
    if (!bar) return; // e.g. frontend/admin/dashboard.html, which keeps its own static bar
    const actions = CONTEXTUAL_TOOLBAR_ACTIONS[viewName] || CONTEXTUAL_TOOLBAR_ACTIONS.dashboard;
    bar.innerHTML = actions.map(a => `
        <button class="quick-action" data-goto="${a.goto}" type="button">
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">${TOOLBAR_ICON_PATHS[a.icon] || ''}</svg>
            ${escapeHtml(a.label)}
        </button>
    `).join('');
}

// One delegated listener, bound once at boot (see init()) -- survives
// every renderContextualToolbar() re-render since it's on the
// container, not the buttons themselves.
function initContextualToolbar() {
    const bar = document.getElementById('quickActionsBar');
    if (!bar) return;
    bar.addEventListener('click', (e) => {
        const btn = e.target.closest('[data-goto]');
        if (btn) showView(btn.dataset.goto);
    });
}

function showView(viewName, params) {
    document.querySelectorAll('.view').forEach(el => el.classList.remove('active'));
    const target = document.getElementById(`view-${viewName}`);
    if (target) target.classList.add('active');

    document.querySelectorAll('.nav-item').forEach(el => {
        el.classList.toggle('active', el.dataset.view === viewName);
    });

    currentViewName = viewName;
    renderContextualToolbar(viewName);
    hideLiveUpdateBanner(); // whatever prompted it, navigating anywhere already re-fetches fresh data for the view you land on

    const handler = VIEW_HANDLERS[viewName];
    if (handler && typeof handler.load === 'function') {
        handler.load(params);
    }
}

/**
 * "Live-feeling" updates: this app has no websocket/SSE channel, and no
 * per-user session to know who else is even connected -- so this is
 * honestly a poll, not real-time push, exactly as scoped ("even a 'new
 * activity' banner that refreshes the view is fine"). Every 30s, checks
 * whether the single most recent /activity entry has changed since the
 * last check; if so, shows a persistent banner (not a toast -- this
 * shouldn't silently disappear before someone notices it) rather than
 * yanking the current view's content out from under whoever's reading
 * it. Navigating to any view (see showView above) also dismisses it,
 * since arriving anywhere already re-fetches fresh data for that view.
 */
let _lastSeenActivityKey = null;
let _liveActivityPollTimer = null;

function startLiveActivityPolling() {
    if (_liveActivityPollTimer) return;
    checkForLiveActivity(); // prime the baseline immediately, don't wait a full interval to start noticing changes
    _liveActivityPollTimer = setInterval(checkForLiveActivity, 30000);
}

async function checkForLiveActivity() {
    try {
        const recent = await Api.recentActivity(1);
        if (!recent.length) return;
        const key = `${recent[0].id}:${recent[0].created_at}`;
        if (_lastSeenActivityKey !== null && key !== _lastSeenActivityKey) {
            showLiveUpdateBanner();
        }
        _lastSeenActivityKey = key;
    } catch (err) { /* best-effort -- a failed background poll isn't worth surfacing */ }
}

// Null-checked -- app.js is shared with frontend/admin/dashboard.html,
// which has no #liveUpdateBanner (that page links out to /app/ for
// collaboration features rather than duplicating them; see
// DECISIONS.md). Without the guard, init()'s unconditional call to
// showLiveUpdateBanner/hideLiveUpdateBanner's DOM lookups threw on that
// page and broke its entire boot -- showView('dashboard') in init()
// never completed, so nothing on the admin dashboard ever rendered.
function showLiveUpdateBanner() {
    const el = document.getElementById('liveUpdateBanner');
    if (el) el.style.display = 'flex';
}

function hideLiveUpdateBanner() {
    const el = document.getElementById('liveUpdateBanner');
    if (el) el.style.display = 'none';
}

/**
 * Sidebar collapse/expand + collapsed-mode hover tooltips. The sidebar
 * itself is never re-rendered by any of this -- only a `.collapsed`
 * class toggling on the one persistent <nav> element, and a single
 * shared tooltip element created once and repositioned per hover. See
 * the `.sidebar`/`.nav-label`/`.sidebar-tooltip` CSS for how each of
 * those reacts to the class.
 */
const SIDEBAR_COLLAPSED_KEY = 'leaseAbstractionSidebarCollapsed';

function initSidebar() {
    const sidebar = document.getElementById('sidebar');
    const toggleBtn = document.getElementById('sidebarCollapseToggle');

    let collapsed = false;
    try { collapsed = localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === '1'; } catch (e) { /* localStorage unavailable -- just won't persist */ }
    setSidebarCollapsed(collapsed);

    toggleBtn.addEventListener('click', () => {
        setSidebarCollapsed(!sidebar.classList.contains('collapsed'));
    });

    document.querySelectorAll('.sidebar .nav-item[data-tooltip]').forEach(item => {
        item.addEventListener('mouseenter', () => {
            if (!sidebar.classList.contains('collapsed')) return;
            showSidebarTooltip(item, item.dataset.tooltip);
        });
        item.addEventListener('mouseleave', hideSidebarTooltip);
        item.addEventListener('click', hideSidebarTooltip);
    });

    // A fixed-position tooltip stays visually "attached" to its trigger
    // only until the trigger scrolls -- hide rather than let it drift.
    const navScroll = document.querySelector('.nav-scroll');
    if (navScroll) navScroll.addEventListener('scroll', hideSidebarTooltip);
}

function setSidebarCollapsed(collapsed) {
    const sidebar = document.getElementById('sidebar');
    const toggleBtn = document.getElementById('sidebarCollapseToggle');
    sidebar.classList.toggle('collapsed', collapsed);
    toggleBtn.setAttribute('aria-expanded', String(!collapsed));
    const label = collapsed ? 'Expand sidebar' : 'Collapse sidebar';
    toggleBtn.setAttribute('aria-label', label);
    toggleBtn.dataset.tooltip = label;
    hideSidebarTooltip();
    try { localStorage.setItem(SIDEBAR_COLLAPSED_KEY, collapsed ? '1' : '0'); } catch (e) { /* ignore */ }
}

let _sidebarTooltipEl = null;

function showSidebarTooltip(triggerEl, text) {
    if (!_sidebarTooltipEl) {
        _sidebarTooltipEl = document.createElement('div');
        _sidebarTooltipEl.className = 'sidebar-tooltip';
        document.body.appendChild(_sidebarTooltipEl);
    }
    const el = _sidebarTooltipEl;
    el.classList.remove('show');
    el.textContent = text;
    const rect = triggerEl.getBoundingClientRect();
    el.style.left = `${rect.right + 10}px`;
    // Vertically centered on the trigger -- measured after textContent
    // is set so offsetHeight reflects this tooltip's real rendered size,
    // not the previous one's.
    el.style.top = `${rect.top + rect.height / 2 - el.offsetHeight / 2}px`;
    requestAnimationFrame(() => el.classList.add('show'));
}

function hideSidebarTooltip() {
    if (_sidebarTooltipEl) _sidebarTooltipEl.classList.remove('show');
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
 * Styled replacement for window.confirm() — a real in-app dialog instead
 * of the browser's OS chrome. Returns a Promise<boolean>. Keyboard:
 * Escape / backdrop click cancel, Tab is trapped inside, focus starts on
 * the safe (Cancel) button and is restored to the trigger on close.
 *
 *   if (!(await confirmDialog({ message: 'Delete this?', danger: true }))) return;
 */
function confirmDialog({ title = 'Are you sure?', message = '', confirmText = 'Confirm', cancelText = 'Cancel', danger = false } = {}) {
    return new Promise((resolve) => {
        const lastFocused = document.activeElement;

        const backdrop = document.createElement('div');
        backdrop.className = 'confirm-backdrop';

        const dialog = document.createElement('div');
        dialog.className = 'confirm-dialog';
        dialog.setAttribute('role', 'alertdialog');
        dialog.setAttribute('aria-modal', 'true');

        const titleId = 'confirmTitle_' + Math.random().toString(36).slice(2);
        dialog.setAttribute('aria-labelledby', titleId);

        const h = document.createElement('h2');
        h.id = titleId;
        h.textContent = title;
        dialog.appendChild(h);

        if (message) {
            const p = document.createElement('p');
            p.textContent = message;
            dialog.appendChild(p);
        }

        const actions = document.createElement('div');
        actions.className = 'confirm-dialog-actions';
        const cancelBtn = document.createElement('button');
        cancelBtn.type = 'button';
        cancelBtn.className = 'btn-secondary';
        cancelBtn.textContent = cancelText;
        const confirmBtn = document.createElement('button');
        confirmBtn.type = 'button';
        confirmBtn.className = danger ? 'btn-danger' : 'btn-primary';
        confirmBtn.textContent = confirmText;
        actions.append(cancelBtn, confirmBtn);
        dialog.appendChild(actions);
        backdrop.appendChild(dialog);
        document.body.appendChild(backdrop);

        requestAnimationFrame(() => backdrop.classList.add('show'));

        const focusable = [cancelBtn, confirmBtn];
        function onKeydown(e) {
            if (e.key === 'Escape') { e.preventDefault(); close(false); }
            else if (e.key === 'Tab') {
                // only two stops — keep focus bouncing between them
                e.preventDefault();
                const i = focusable.indexOf(document.activeElement);
                const next = e.shiftKey ? (i <= 0 ? focusable.length - 1 : i - 1) : (i + 1) % focusable.length;
                focusable[next].focus();
            }
        }

        function close(result) {
            document.removeEventListener('keydown', onKeydown, true);
            backdrop.classList.remove('show');
            const done = () => {
                backdrop.remove();
                if (lastFocused && typeof lastFocused.focus === 'function') lastFocused.focus();
                resolve(result);
            };
            const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
            if (reduced) done();
            else backdrop.addEventListener('transitionend', function te(e) {
                if (e.target === backdrop) { backdrop.removeEventListener('transitionend', te); done(); }
            });
        }

        cancelBtn.addEventListener('click', () => close(false));
        confirmBtn.addEventListener('click', () => close(true));
        backdrop.addEventListener('mousedown', (e) => { if (e.target === backdrop) close(false); });
        document.addEventListener('keydown', onKeydown, true);
        cancelBtn.focus();
    });
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

/**
 * Triggers a real browser download for an in-memory blob, the same
 * createObjectURL + temporary-<a> + revoke pattern detail-view.js's
 * exportJson() already used for a client-built JSON blob -- shared
 * here since the investment-memo export (export-modal.js) needs the
 * identical dance for a server-returned PDF/Excel blob.
 */
function triggerBlobDownload(blob, filename) {
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
}

/** Reads the filename out of a fetch Response's Content-Disposition header, falling back if the header's missing/unparseable. */
function filenameFromResponse(response, fallback) {
    const header = response.headers.get('content-disposition') || '';
    const match = header.match(/filename="?([^";]+)"?/i);
    return match ? match[1] : fallback;
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

/**
 * Persists an edit to one extracted field's value -- the one real save
 * path behind every inline field editor in the app (lease detail page,
 * in-task lease editing), so a manual correction actually lands in the
 * database instead of only mutating in-memory state that a reload would
 * throw away.
 *
 * Resolves which document row currently governs the field's EFFECTIVE
 * value first (base lease, or whichever amendment most recently
 * overrode it -- see backend/app/database.py's get_field_source_chain)
 * so the edit lands on the row that actually wins the merge, instead of
 * being silently shadowed by an amendment that already set this same
 * field. `taskId`, when given, links the edit to the task it happened
 * under (see GET /tasks/<id>'s `field_edits`).
 */
async function saveLeaseFieldEdit(baseLeaseId, fieldName, value, { taskId } = {}) {
    let targetId = baseLeaseId;
    try {
        const chain = await Api.leaseFieldSource(baseLeaseId, fieldName);
        if (chain && chain.effective_document_id != null) targetId = chain.effective_document_id;
    } catch (err) { /* best-effort -- fall back to editing the base lease directly */ }
    const result = await Api.updateLeaseField(targetId, fieldName, { value, taskId });
    return result.field; // {value, source, confidence, manually_verified}
}

// Confidence glyphs — a redundant, non-color cue so the tier is
// readable in grayscale / for colorblind reviewers (green-high vs
// red-low is the exact pair that fails deuteranopia). aria-hidden
// because the badge's own text ("High Confidence" etc.) already
// carries the meaning for assistive tech.
const CONFIDENCE_ICON = {
    high: '<svg viewBox="0 0 16 16" width="12" height="12" aria-hidden="true" focusable="false"><path fill="currentColor" d="M6.4 11.2 3.2 8l1.1-1.1 2.1 2.1 5.3-5.3L12.8 4.8z"/></svg>',
    medium: '<svg viewBox="0 0 16 16" width="12" height="12" aria-hidden="true" focusable="false"><path fill="currentColor" d="M8 1.5 15 14H1zM7.1 6v3.6h1.8V6zm0 4.8v1.8h1.8v-1.8z"/></svg>',
    low: '<svg viewBox="0 0 16 16" width="12" height="12" aria-hidden="true" focusable="false"><path fill="currentColor" d="M7.1 2h1.8v7H7.1zm0 9h1.8v1.8H7.1z"/></svg>',
    none: '<svg viewBox="0 0 16 16" width="12" height="12" aria-hidden="true" focusable="false"><path fill="currentColor" d="M3 7.1h10v1.8H3z"/></svg>',
};

function confidenceBadgeHtml(confidence, found) {
    if (!found) return `<span class="confidence-badge confidence-none">${CONFIDENCE_ICON.none}Not Found</span>`;
    const level = confidence || 'unknown';
    const label = level.charAt(0).toUpperCase() + level.slice(1);
    const icon = CONFIDENCE_ICON[level] || '';
    return `<span class="confidence-badge confidence-${level}">${icon}${label} Confidence</span>`;
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
 * Same badge family as severityBadgeHtml above, but for the "high" /
 * "moderate" / "low" risk-level vocabulary portfolio.py's rollover and
 * tenant-concentration functions use (note "moderate", not "medium").
 * Shared by dashboard-view.js's composition panel and trends-view.js's
 * rollover chart so both agree on what each level looks like.
 */
function riskLevelBadgeHtml(level) {
    const cls = level === 'high' ? 'severity-high' : level === 'moderate' ? 'severity-medium' : 'severity-low';
    const label = level === 'high' ? 'High' : level === 'moderate' ? 'Moderate' : 'Low';
    return `<span class="severity-badge ${cls}">${label}</span>`;
}

// Deterministic per-name color from the existing token palette (not new
// arbitrary hex colors) so the same self-reported name always renders
// the same avatar color across sessions/devices, without needing a
// real per-user account to store a color/photo against.
const AVATAR_PALETTE = ['var(--lux-accent)', 'var(--success-color)', 'var(--warning-color)', 'var(--error-color)', 'var(--slate-600)', 'var(--slate-500)'];

function _avatarColorFor(name) {
    let hash = 0;
    const str = name || '?';
    for (let i = 0; i < str.length; i++) hash = (hash * 31 + str.charCodeAt(i)) >>> 0;
    return AVATAR_PALETTE[hash % AVATAR_PALETTE.length];
}

function _initialsFor(name) {
    const trimmed = (name || '').trim();
    if (!trimmed) return '?';
    const parts = trimmed.split(/\s+/);
    return parts.length === 1 ? parts[0].slice(0, 2).toUpperCase() : (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

/**
 * A small initials avatar for a self-reported name (comment author,
 * discrepancy resolver, alert dismisser) -- there's no real per-user
 * account to attach a photo to, so this is generated client-side from
 * the name itself, same honesty-about-what-exists posture as the rest
 * of this app's "self-reported identity" convention. `sizeClass`:
 * '' (default, 1.75rem), 'team-avatar-sm', or 'team-avatar-lg'.
 */
function avatarHtml(name, sizeClass) {
    return `<span class="team-avatar ${sizeClass || ''}" style="background-color:${_avatarColorFor(name)}" title="${escapeHtml(name || 'Unknown')}">${escapeHtml(_initialsFor(name))}</span>`;
}

/**
 * Shared self-reported identity: one name/email cached across the
 * whole app (discrepancy resolutions, team comments), not a separate
 * localStorage key per feature -- "who you are" shouldn't need
 * retyping every time you touch a different feature. Same self-
 * reported convention the access gate already uses; there's no real
 * per-user login in this app yet.
 */
const USER_IDENTITY_KEY = 'leaseAbstractionUserIdentity';

function getUserIdentity() {
    try {
        return JSON.parse(localStorage.getItem(USER_IDENTITY_KEY) || '{}');
    } catch (e) {
        return {};
    }
}

function setUserIdentity(name, email) {
    try {
        localStorage.setItem(USER_IDENTITY_KEY, JSON.stringify({ name: name || '', email: email || '' }));
    } catch (e) { /* localStorage unavailable -- just won't persist across reloads */ }
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
    initContextualToolbar();

    document.getElementById('statsToggleBtn').addEventListener('click', toggleStatsPanel);
    document.getElementById('clearStatsBtn').addEventListener('click', clearStats);
    document.getElementById('closeStatsBtn').addEventListener('click', () => {
        document.getElementById('statsPanel').style.display = 'none';
    });

    initSidebar();

    // Same null-guard reasoning as showLiveUpdateBanner/hideLiveUpdateBanner above -- these two buttons don't exist on admin/dashboard.html.
    const liveUpdateRefreshBtn = document.getElementById('liveUpdateRefreshBtn');
    if (liveUpdateRefreshBtn) {
        liveUpdateRefreshBtn.addEventListener('click', () => {
            hideLiveUpdateBanner();
            showView(currentViewName);
        });
    }
    const liveUpdateDismissBtn = document.getElementById('liveUpdateDismissBtn');
    if (liveUpdateDismissBtn) liveUpdateDismissBtn.addEventListener('click', hideLiveUpdateBanner);

    // Kick off the initial view -- dashboard by default (marked active in
    // the HTML), unless the URL names a registered view via a hash (e.g.
    // admin/dashboard.html's sidebar links out to here as `#alerts`,
    // `#discrepancies`, etc. -- see DECISIONS.md "Admin dashboard: real
    // left sidebar, not a top-tab bar"). Only honored if that view is
    // actually registered, so a stale/typo'd hash falls back to Dashboard
    // instead of showing a blank page with no matching `.view` toggled
    // active.
    const hashView = location.hash.slice(1);
    showView(hashView && VIEW_HANDLERS[hashView] ? hashView : 'dashboard');

    // Best-effort, non-blocking: regenerate + refresh the Alerts nav
    // badge right at boot, not only after a visit to the Alerts view
    // itself -- see alerts-view.js's own comment for why generation is
    // triggered client-side at all (no scheduled backend job exists
    // yet).
    Api.generateAlerts().catch(() => {}).then(() => refreshAlertsBadge());

    startLiveActivityPolling();
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
