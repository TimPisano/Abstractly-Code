/**
 * Lease Abstraction Tool - Frontend JavaScript
 * Handles file upload, API calls, result rendering, inline editing,
 * JSON export, and a simple session accuracy-stats panel.
 */

// Configuration
const API_BASE_URL = 'http://localhost:5000';
const STATS_STORAGE_KEY = 'leaseAbstractionSessionStats';

// Field grouping and display labels
const FIELD_GROUPS = [
    {
        name: 'Parties',
        fields: ['tenant', 'landlord', 'property_address'],
    },
    {
        name: 'Financial Terms',
        fields: ['rent_amount', 'security_deposit', 'cam_charges', 'rent_escalation', 'insurance_requirements'],
    },
    {
        name: 'Dates & Term',
        fields: ['lease_start_date', 'lease_end_date', 'renewal_options', 'default_cure_period'],
    },
    {
        name: 'Special Clauses',
        fields: ['permitted_use', 'exclusivity_clause'],
    },
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
    lease_start_date: 'Lease Start Date',
    lease_end_date: 'Lease End Date',
    renewal_options: 'Renewal Options',
    default_cure_period: 'Default / Cure Period',
    permitted_use: 'Permitted Use',
    exclusivity_clause: 'Exclusivity Clause',
};

// State
let currentData = null;
let currentFileName = null;

// DOM Elements
const uploadBox = document.getElementById('uploadBox');
const fileInput = document.getElementById('fileInput');
const loadingSection = document.getElementById('loadingSection');
const errorSection = document.getElementById('errorSection');
const errorMessage = document.getElementById('errorMessage');
const resultsSection = document.getElementById('resultsSection');
const resultsGroups = document.getElementById('resultsGroups');
const exportBtn = document.getElementById('exportBtn');
const fileName = document.getElementById('fileName');
const pageCount = document.getElementById('pageCount');
const extractedAt = document.getElementById('extractedAt');
const statsToggleBtn = document.getElementById('statsToggleBtn');
const statsPanel = document.getElementById('statsPanel');
const statsContent = document.getElementById('statsContent');
const clearStatsBtn = document.getElementById('clearStatsBtn');

// Initialize event listeners
function init() {
    uploadBox.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', handleFileSelect);
    uploadBox.addEventListener('dragover', handleDragOver);
    uploadBox.addEventListener('dragleave', handleDragLeave);
    uploadBox.addEventListener('drop', handleDrop);
    exportBtn.addEventListener('click', exportJSON);
    statsToggleBtn.addEventListener('click', toggleStatsPanel);
    clearStatsBtn.addEventListener('click', clearStats);
}

function handleFileSelect(event) {
    const file = event.target.files[0];
    if (file) {
        processFile(file);
    }
}

function handleDragOver(event) {
    event.preventDefault();
    uploadBox.classList.add('dragover');
}

function handleDragLeave(event) {
    event.preventDefault();
    uploadBox.classList.remove('dragover');
}

function handleDrop(event) {
    event.preventDefault();
    uploadBox.classList.remove('dragover');

    const file = event.dataTransfer.files[0];
    if (file) {
        if (file.type !== 'application/pdf') {
            showError('Please upload a PDF file');
            return;
        }
        if (file.size > 16 * 1024 * 1024) {
            showError('File size exceeds 16MB limit');
            return;
        }
        processFile(file);
    }
}

/**
 * Process uploaded PDF file
 */
async function processFile(file) {
    hideAllSections();
    showLoading();
    currentFileName = file.name;

    try {
        const formData = new FormData();
        formData.append('file', file);

        const response = await fetch(`${API_BASE_URL}/extract`, {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || 'Failed to process file');
        }

        currentData = data;
        displayResults(data);
        recordStats(file.name, data);

    } catch (error) {
        showError(error.message);
    } finally {
        hideLoading();
    }
}

/**
 * Display extraction results, grouped into logical sections
 */
function displayResults(data) {
    fileName.textContent = `File: ${currentFileName || 'Lease Document'}`;
    pageCount.textContent = 'Processing complete';
    extractedAt.textContent = `Extracted: ${formatDate(new Date().toISOString())}`;

    resultsGroups.innerHTML = '';

    FIELD_GROUPS.forEach(group => {
        const groupFieldsPresent = group.fields.filter(key => data.hasOwnProperty(key));
        if (groupFieldsPresent.length === 0) return;

        const section = document.createElement('div');
        section.className = 'field-group';

        const heading = document.createElement('h3');
        heading.className = 'field-group-title';
        heading.textContent = group.name;
        section.appendChild(heading);

        const grid = document.createElement('div');
        grid.className = 'results-grid';

        groupFieldsPresent.forEach(fieldKey => {
            const card = createResultCard(fieldKey, data[fieldKey]);
            grid.appendChild(card);
        });

        section.appendChild(grid);
        resultsGroups.appendChild(section);
    });

    resultsSection.style.display = 'block';
}

/**
 * Create a result card for one field: value (inline-editable), confidence
 * badge, and source (page + quote).
 */
function createResultCard(fieldKey, fieldData) {
    const found = fieldData.value !== null && fieldData.value !== undefined;

    const card = document.createElement('div');
    card.className = `result-card ${found ? 'found' : 'not-found'}`;
    card.dataset.field = fieldKey;

    // Header: label + confidence badge
    const header = document.createElement('div');
    header.className = 'card-header';

    const title = document.createElement('h4');
    title.textContent = FIELD_LABELS[fieldKey] || fieldKey;
    header.appendChild(title);
    header.appendChild(createConfidenceBadge(fieldData.confidence, found));
    card.appendChild(header);

    // Body: editable value + source
    const body = document.createElement('div');
    body.className = 'card-body';

    const valueDiv = document.createElement('div');
    valueDiv.className = found ? 'field-value editable' : 'field-value editable not-found-value';
    valueDiv.textContent = found ? fieldData.value : 'Not Found — click to enter a value';
    valueDiv.title = 'Click to edit';
    valueDiv.addEventListener('click', () => startInlineEdit(valueDiv, fieldKey, card));
    body.appendChild(valueDiv);

    if (fieldData.edited) {
        const editedBadge = document.createElement('span');
        editedBadge.className = 'edited-badge';
        editedBadge.textContent = 'Manually Edited';
        body.appendChild(editedBadge);
    }

    if (found && fieldData.source) {
        const sourceDiv = document.createElement('div');
        sourceDiv.className = 'field-source';

        const pageLabel = document.createElement('div');
        pageLabel.className = 'source-page';
        pageLabel.textContent = `Page ${fieldData.source.page}`;

        const quoteLabel = document.createElement('div');
        quoteLabel.className = 'source-quote';
        quoteLabel.textContent = `"${fieldData.source.quote}"`;

        sourceDiv.appendChild(pageLabel);
        sourceDiv.appendChild(quoteLabel);
        body.appendChild(sourceDiv);
    }

    card.appendChild(body);
    return card;
}

function createConfidenceBadge(confidence, found) {
    const badge = document.createElement('span');
    if (!found) {
        badge.className = 'confidence-badge confidence-none';
        badge.textContent = 'Not Found';
        return badge;
    }
    const level = confidence || 'unknown';
    badge.className = `confidence-badge confidence-${level}`;
    badge.textContent = level.charAt(0).toUpperCase() + level.slice(1) + ' Confidence';
    return badge;
}

/**
 * Turn a value display into an editable text input. Saves back into
 * currentData on blur/Enter, and marks the field as manually edited so
 * the JSON export and UI can reflect the correction.
 */
function startInlineEdit(valueDiv, fieldKey, card) {
    if (valueDiv.querySelector('input')) return; // already editing

    const currentValue = currentData[fieldKey].value || '';
    const input = document.createElement('input');
    input.type = 'text';
    input.className = 'field-value-input';
    input.value = currentValue;

    valueDiv.textContent = '';
    valueDiv.appendChild(input);
    input.focus();
    input.select();

    const commit = () => {
        const newValue = input.value.trim();
        const wasFound = currentData[fieldKey].value !== null && currentData[fieldKey].value !== undefined;
        const changed = newValue !== (wasFound ? String(currentData[fieldKey].value) : '');

        if (newValue === '') {
            currentData[fieldKey].value = null;
        } else {
            currentData[fieldKey].value = newValue;
        }

        if (changed) {
            currentData[fieldKey].edited = true;
        }

        // Re-render just this card so found/not-found styling and the
        // "edited" indicator stay correct.
        const newCard = createResultCard(fieldKey, currentData[fieldKey]);
        card.replaceWith(newCard);
    };

    input.addEventListener('blur', commit);
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            input.blur();
        } else if (e.key === 'Escape') {
            e.preventDefault();
            input.value = currentValue;
            input.blur();
        }
    });
}

/**
 * Export current data (including any manual edits and confidence scores)
 * as JSON
 */
function exportJSON() {
    if (!currentData) return;

    const dataStr = JSON.stringify(currentData, null, 2);
    const blob = new Blob([dataStr], { type: 'application/json' });
    const url = URL.createObjectURL(blob);

    const link = document.createElement('a');
    link.href = url;
    link.download = `lease_extraction_${Date.now()}.json`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);

    URL.revokeObjectURL(url);
}

/**
 * Session Stats: a lightweight running tally (persisted in localStorage)
 * of extraction results across documents processed in this browser
 * session, to spot-check accuracy trends across validation runs.
 */
function recordStats(filename, data) {
    const fieldKeys = Object.keys(FIELD_LABELS);
    let foundCount = 0;
    const byConfidence = { high: 0, medium: 0, low: 0 };

    fieldKeys.forEach(key => {
        const field = data[key];
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
    renderStatsPanel();
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
    } catch (e) {
        // localStorage unavailable (e.g. private browsing) — stats just won't persist
    }
}

function clearStats() {
    saveStats([]);
    renderStatsPanel();
}

function toggleStatsPanel() {
    const isHidden = statsPanel.style.display === 'none' || !statsPanel.style.display;
    if (isHidden) {
        renderStatsPanel();
        statsPanel.style.display = 'block';
    } else {
        statsPanel.style.display = 'none';
    }
}

function renderStatsPanel() {
    const stats = loadStats();

    if (stats.length === 0) {
        statsContent.innerHTML = '<p class="stats-empty">No documents processed yet this session.</p>';
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
            <thead>
                <tr><th>File</th><th>Found</th><th>High</th><th>Medium</th><th>Low</th><th>When</th></tr>
            </thead>
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
    statsContent.innerHTML = html;
}

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

/**
 * UI State Management
 */
function hideAllSections() {
    loadingSection.style.display = 'none';
    errorSection.style.display = 'none';
    resultsSection.style.display = 'none';
}

function showLoading() {
    loadingSection.style.display = 'block';
}

function hideLoading() {
    loadingSection.style.display = 'none';
}

function showError(message) {
    errorMessage.textContent = message;
    errorSection.style.display = 'block';
}

/**
 * Utility Functions
 */
function formatDate(isoString) {
    const date = new Date(isoString);
    return date.toLocaleString();
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', init);
