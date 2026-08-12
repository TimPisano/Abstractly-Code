/**
 * Lease Abstraction Tool - Frontend JavaScript
 * Handles file upload, API calls, and UI updates
 */

// Configuration
const API_BASE_URL = 'http://localhost:5000';

// State
let currentData = null;

// DOM Elements
const uploadBox = document.getElementById('uploadBox');
const fileInput = document.getElementById('fileInput');
const loadingSection = document.getElementById('loadingSection');
const errorSection = document.getElementById('errorSection');
const errorMessage = document.getElementById('errorMessage');
const resultsSection = document.getElementById('resultsSection');
const resultsGrid = document.getElementById('resultsGrid');
const exportBtn = document.getElementById('exportBtn');
const fileName = document.getElementById('fileName');
const pageCount = document.getElementById('pageCount');
const extractedAt = document.getElementById('extractedAt');

// Initialize event listeners
function init() {
    // Click to open file dialog
    uploadBox.addEventListener('click', () => fileInput.click());

    // File input change
    fileInput.addEventListener('change', handleFileSelect);

    // Drag and drop
    uploadBox.addEventListener('dragover', handleDragOver);
    uploadBox.addEventListener('dragleave', handleDragLeave);
    uploadBox.addEventListener('drop', handleDrop);

    // Export button
    exportBtn.addEventListener('click', exportJSON);
}

/**
 * Handle file selection from input
 */
function handleFileSelect(event) {
    const file = event.target.files[0];
    if (file) {
        processFile(file);
    }
}

/**
 * Handle drag over event
 */
function handleDragOver(event) {
    event.preventDefault();
    uploadBox.classList.add('dragover');
}

/**
 * Handle drag leave event
 */
function handleDragLeave(event) {
    event.preventDefault();
    uploadBox.classList.remove('dragover');
}

/**
 * Handle file drop
 */
function handleDrop(event) {
    event.preventDefault();
    uploadBox.classList.remove('dragover');

    const file = event.dataTransfer.files[0];
    if (file) {
        // Validate file type
        if (file.type !== 'application/pdf') {
            showError('Please upload a PDF file');
            return;
        }

        // Validate file size (16MB max)
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
    // Reset UI state
    hideAllSections();
    showLoading();

    try {
        // Create form data
        const formData = new FormData();
        formData.append('file', file);

        // Send to API
        const response = await fetch(`${API_BASE_URL}/extract`, {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || 'Failed to process file');
        }

        // Store data and display results
        currentData = data;
        displayResults(data);

    } catch (error) {
        showError(error.message);
    } finally {
        hideLoading();
    }
}

/**
 * Display extraction results
 */
function displayResults(data) {
    // Update metadata - use current date since backend doesn't provide it
    fileName.textContent = `File: Lease Document`;
    pageCount.textContent = `Processing complete`;
    extractedAt.textContent = `Extracted: ${formatDate(new Date().toISOString())}`;

    // Clear previous results
    resultsGrid.innerHTML = '';

    // Field labels for display - map backend field names to friendly labels
    const fieldLabels = {
        'tenant': 'Tenant Name',
        'rent_amount': 'Monthly Rent',
        'lease_start_date': 'Lease Start Date',
        'lease_end_date': 'Lease End Date'
    };

    // Create result cards for each field
    // Backend returns fields directly, not nested under "fields"
    Object.entries(data).forEach(([fieldKey, fieldData]) => {
        // Skip non-field entries
        if (typeof fieldData !== 'object' || !fieldData.hasOwnProperty('value')) {
            return;
        }

        // Convert backend format to frontend format
        const normalizedData = {
            found: fieldData.value !== null,
            value: fieldData.value,
            source: fieldData.source
        };

        const card = createResultCard(
            fieldLabels[fieldKey] || fieldKey,
            normalizedData
        );
        resultsGrid.appendChild(card);
    });

    // Show results section
    resultsSection.style.display = 'block';
}

/**
 * Create a result card element
 */
function createResultCard(label, fieldData) {
    const card = document.createElement('div');
    card.className = `result-card ${fieldData.found ? 'found' : 'not-found'}`;

    // Card header
    const header = document.createElement('div');
    header.className = 'card-header';

    const title = document.createElement('h3');
    title.textContent = label;

    const status = document.createElement('span');
    status.className = `status-badge ${fieldData.found ? 'status-found' : 'status-not-found'}`;
    status.textContent = fieldData.found ? 'Found' : 'Not Found';

    header.appendChild(title);
    header.appendChild(status);

    // Card body
    const body = document.createElement('div');
    body.className = 'card-body';

    if (fieldData.found) {
        // Display value
        const valueDiv = document.createElement('div');
        valueDiv.className = 'field-value';
        valueDiv.textContent = fieldData.value;
        body.appendChild(valueDiv);

        // Display source
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
    } else {
        // Not found message
        const notFoundMsg = document.createElement('div');
        notFoundMsg.className = 'not-found-message';
        notFoundMsg.textContent = 'This field was not found in the document';
        body.appendChild(notFoundMsg);
    }

    card.appendChild(header);
    card.appendChild(body);

    return card;
}

/**
 * Export current data as JSON
 */
function exportJSON() {
    if (!currentData) return;

    // Create downloadable JSON file
    const dataStr = JSON.stringify(currentData, null, 2);
    const blob = new Blob([dataStr], { type: 'application/json' });
    const url = URL.createObjectURL(blob);

    // Create download link and trigger
    const link = document.createElement('a');
    link.href = url;
    link.download = `lease_extraction_${Date.now()}.json`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);

    // Clean up
    URL.revokeObjectURL(url);
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
