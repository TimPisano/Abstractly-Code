/**
 * Lease Detail View: grouped field display (Parties / Financial Terms /
 * Dates & Term / Special Clauses) with inline editing, a risk-flags
 * panel, an amendments list/uploader, and a per-lease Q&A box.
 */

const LeaseDetail = {
    lease: null,

    async load({ leaseId } = {}) {
        if (!leaseId) return;
        try {
            this.lease = await Api.getLease(leaseId);
            document.getElementById('detailTitle').textContent = lease_filename(this.lease);
            const tenant = fieldValue(this.lease, 'tenant') || 'Tenant not found';
            const landlord = fieldValue(this.lease, 'landlord') || 'Landlord not found';
            document.getElementById('detailSubtitle').textContent = `${tenant} — ${landlord}`;

            this.renderFields();
            document.getElementById('detailQaHistory').innerHTML = '';

            const [risks, amendments] = await Promise.all([
                Api.leaseRisks(leaseId).catch(() => []),
                Api.listAmendments(leaseId).catch(() => []),
            ]);
            this.renderRisks(risks);
            this.renderAmendments(amendments);
        } catch (err) {
            showError(`Failed to load lease: ${err.message}`);
        }
    },

    renderRisks(risks) {
        const panel = document.getElementById('detailRiskPanel');
        if (!risks || risks.length === 0) {
            panel.innerHTML = `
                <h3>Risk Flags</h3>
                <p class="empty-inline">No red flags found for this lease.</p>
            `;
            return;
        }
        panel.innerHTML = `
            <h3>Risk Flags <span class="risk-count-badge">${risks.length}</span></h3>
            <div class="risk-list">
                ${risks.map(flag => `
                    <div class="risk-item risk-item-${flag.severity}">
                        <div class="risk-item-head">
                            ${severityBadgeHtml(flag.severity)}
                            <span class="risk-item-message">${escapeHtml(flag.message)}</span>
                        </div>
                        <p class="risk-item-explanation">${escapeHtml(flag.explanation)}</p>
                    </div>
                `).join('')}
            </div>
        `;
    },

    renderFields() {
        const container = document.getElementById('detailResultsGroups');
        container.innerHTML = '';
        const data = this.lease.extracted_fields;

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
                grid.appendChild(this.createResultCard(fieldKey, data[fieldKey]));
            });
            section.appendChild(grid);
            container.appendChild(section);
        });
    },

    createResultCard(fieldKey, fieldData) {
        const found = fieldData.value !== null && fieldData.value !== undefined;

        const card = document.createElement('div');
        card.className = `result-card ${found ? 'found' : 'not-found'}`;
        card.dataset.field = fieldKey;

        const header = document.createElement('div');
        header.className = 'card-header';
        const title = document.createElement('h4');
        title.textContent = FIELD_LABELS[fieldKey] || fieldKey;
        header.appendChild(title);
        const badgeWrapper = document.createElement('div');
        badgeWrapper.innerHTML = confidenceBadgeHtml(fieldData.confidence, found);
        header.appendChild(badgeWrapper.firstElementChild);
        card.appendChild(header);

        const body = document.createElement('div');
        body.className = 'card-body';

        const valueDiv = document.createElement('div');
        valueDiv.className = found ? 'field-value editable' : 'field-value editable not-found-value';
        valueDiv.textContent = found ? fieldData.value : 'Not Found — click to enter a value';
        valueDiv.title = 'Click to edit';
        valueDiv.addEventListener('click', () => this.startInlineEdit(valueDiv, fieldKey, card));
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
            sourceDiv.innerHTML = `
                <div class="source-page">Page ${fieldData.source.page}</div>
                <div class="source-quote">"${escapeHtml(fieldData.source.quote)}"</div>
            `;
            body.appendChild(sourceDiv);
        }

        card.appendChild(body);
        return card;
    },

    startInlineEdit(valueDiv, fieldKey, card) {
        if (valueDiv.querySelector('input')) return;

        const fieldData = this.lease.extracted_fields[fieldKey];
        const currentValue = fieldData.value || '';
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
            const wasFound = fieldData.value !== null && fieldData.value !== undefined;
            const changed = newValue !== (wasFound ? String(fieldData.value) : '');

            fieldData.value = newValue === '' ? null : newValue;
            if (changed) fieldData.edited = true;

            const newCard = this.createResultCard(fieldKey, fieldData);
            card.replaceWith(newCard);
        };

        input.addEventListener('blur', commit);
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') { e.preventDefault(); input.blur(); }
            else if (e.key === 'Escape') { e.preventDefault(); input.value = currentValue; input.blur(); }
        });
    },

    renderAmendments(amendments) {
        const list = document.getElementById('amendmentsList');
        if (!amendments || amendments.length === 0) {
            list.innerHTML = '<p class="empty-inline">No amendments on file.</p>';
            return;
        }
        list.innerHTML = amendments.map(a => `
            <div class="amendment-item">
                <div class="amendment-filename">${escapeHtml(a.filename)}</div>
                <div class="amendment-date">${formatDate(a.uploaded_at)}</div>
            </div>
        `).join('');
    },

    exportJson() {
        if (!this.lease) return;
        const dataStr = JSON.stringify(this.lease.extracted_fields, null, 2);
        const blob = new Blob([dataStr], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `${lease_filename(this.lease).replace(/\.pdf$/i, '')}_extraction.json`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
    },

    async deleteLease() {
        if (!this.lease) return;
        if (!confirm(`Delete ${lease_filename(this.lease)}? This also removes any amendments linked to it.`)) return;
        try {
            await Api.deleteLease(this.lease.id);
            showToast('Lease deleted.', 'success');
            showView('dashboard');
        } catch (err) {
            showError(`Failed to delete lease: ${err.message}`);
        }
    },

    async askAboutThisLease(question) {
        const history = document.getElementById('detailQaHistory');
        const pendingId = `qa-pending-${Date.now()}`;
        history.insertAdjacentHTML('beforeend', `
            <div class="qa-exchange">
                <div class="qa-question">${escapeHtml(question)}</div>
                <div class="qa-answer" id="${pendingId}"><span class="spinner-small"></span> Thinking...</div>
            </div>
        `);
        history.scrollTop = history.scrollHeight;

        try {
            const result = await Api.askQuestion(question, this.lease.id);
            document.getElementById(pendingId).outerHTML = qaAnswerHtml(result);
        } catch (err) {
            document.getElementById(pendingId).outerHTML = `<div class="qa-answer qa-answer-error">Error: ${escapeHtml(err.message)}</div>`;
        }
    },
};

function qaAnswerHtml(result) {
    const confidenceClass = result.confidence === 'answered' ? 'answered' : (result.confidence === 'partial' ? 'partial' : 'unsupported');
    let html = `<div class="qa-answer qa-answer-${confidenceClass}">${escapeHtml(result.answer).replace(/\n/g, '<br>')}</div>`;
    if (result.citations && result.citations.length > 0) {
        html += `<div class="qa-citations">`;
        result.citations.forEach(c => {
            html += `<div class="qa-citation">📄 ${escapeHtml(c.filename)}, page ${c.page}: "${escapeHtml(c.quote)}"</div>`;
        });
        html += `</div>`;
    }
    return html;
}

registerView('detail', LeaseDetail);

// Loaded dynamically by access-gate.js after the gate passes, well after
// DOMContentLoaded already fired -- see the comment in app.js for why a
// readyState check is needed here instead of a plain addEventListener.
function _initDetailViewBindings() {
    document.getElementById('detailExportBtn').addEventListener('click', () => LeaseDetail.exportJson());
    document.getElementById('detailDeleteBtn').addEventListener('click', () => LeaseDetail.deleteLease());

    const amendmentInput = document.getElementById('amendmentFileInput');
    document.getElementById('addAmendmentBtn').addEventListener('click', () => amendmentInput.click());
    amendmentInput.addEventListener('change', async (e) => {
        const file = e.target.files[0];
        if (!file || !LeaseDetail.lease) return;
        try {
            const updatedLease = await Api.uploadAmendment(LeaseDetail.lease.id, file);
            showToast('Amendment added — lease terms updated.', 'success');
            LeaseDetail.load({ leaseId: updatedLease.id });
        } catch (err) {
            showError(`Failed to upload amendment: ${err.message}`);
        } finally {
            amendmentInput.value = '';
        }
    });

    const askBtn = document.getElementById('detailQaBtn');
    const qaInput = document.getElementById('detailQaInput');
    const ask = () => {
        const question = qaInput.value.trim();
        if (!question) return;
        LeaseDetail.askAboutThisLease(question);
        qaInput.value = '';
    };
    askBtn.addEventListener('click', ask);
    qaInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') ask(); });
}
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _initDetailViewBindings);
} else {
    _initDetailViewBindings();
}
