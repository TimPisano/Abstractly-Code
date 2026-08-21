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
            document.getElementById('detailTitle').textContent = this.lease.display_name || lease_filename(this.lease);
            const tenant = fieldValue(this.lease, 'tenant') || 'Tenant not found';
            const landlord = fieldValue(this.lease, 'landlord') || 'Landlord not found';
            let subtitle = `${tenant} — ${landlord}`;
            subtitle += ` · from ${lease_filename(this.lease)}`;
            if (this.lease.source_page_start != null) {
                subtitle += this.lease.source_page_start === this.lease.source_page_end
                    ? ` (page ${this.lease.source_page_start})`
                    : ` (pages ${this.lease.source_page_start}–${this.lease.source_page_end})`;
            }
            document.getElementById('detailSubtitle').textContent = subtitle;
            document.getElementById('detailExportExcelBtn').href = Api.leaseExportExcelUrl(this.lease.id);
            document.getElementById('detailSummaryMemoBtn').href = Api.leaseSummaryPdfUrl(this.lease.id);
            document.getElementById('detailExportStatus').innerHTML = '';
            document.getElementById('detailNonLeaseWarning').innerHTML = this.lease.looks_like_lease === false ? `
                <div class="upload-result-warning detail-non-lease-warning">
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z"/></svg>
                    <span>This doesn't look like a lease — no tenant, landlord, rent, or dates were found anywhere in the document. Double-check this is the right file before relying on it.</span>
                </div>
            ` : '';

            this.renderConfidenceSummary(this.lease.confidence_summary);
            this.renderFields();
            this.renderTags(this.lease.tags || []);
            document.getElementById('detailQaHistory').innerHTML = '';

            const [risks, amendments] = await Promise.all([
                Api.leaseRisks(leaseId).catch(() => []),
                Api.listAmendments(leaseId).catch(() => []),
            ]);
            this.renderRisks(risks);
            this.renderAmendments(amendments);

            // Best-effort: powers the tag-input autocomplete, not
            // essential to the page working if it fails.
            Api.listAllTags().then(populateTagDatalist).catch(() => {});
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

    renderConfidenceSummary(summary) {
        const panel = document.getElementById('detailConfidenceSummaryPanel');
        const flaggedList = summary && summary.flagged_fields && summary.flagged_fields.length > 0
            ? summary.flagged_fields.map(f => FIELD_LABELS[f] || f)
            : null;
        panel.innerHTML = confidenceSummaryPanelHtml(summary, 'Confidence Summary', flaggedList);
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

        if (fieldData.validation_note) {
            const noteDiv = document.createElement('div');
            noteDiv.className = 'field-validation-note';
            noteDiv.innerHTML = `
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z"/></svg>
                <span>${escapeHtml(fieldData.validation_note)}</span>
            `;
            body.appendChild(noteDiv);
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

    async exportToGoogleSheets() {
        if (!this.lease) return;
        const btn = document.getElementById('detailExportSheetsBtn');
        const status = document.getElementById('detailExportStatus');
        btn.disabled = true;
        btn.textContent = 'Exporting...';
        status.innerHTML = '';

        try {
            const result = await Api.exportLeaseToGoogleSheets(this.lease.id);
            status.innerHTML = `
                <div class="export-status export-status-success">
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                    <span>Exported to Google Sheets. <a href="${escapeHtml(result.url)}" target="_blank" rel="noopener noreferrer">Open the sheet &rarr;</a></span>
                </div>
            `;
        } catch (err) {
            status.innerHTML = `
                <div class="export-status export-status-error">
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z"/></svg>
                    <span>${escapeHtml(err.message)}</span>
                </div>
            `;
        } finally {
            btn.disabled = false;
            btn.textContent = 'Export to Google Sheets';
        }
    },

    renderTags(tags) {
        const list = document.getElementById('detailTagsList');
        if (!tags || tags.length === 0) {
            list.innerHTML = '<p class="empty-inline">No tags yet.</p>';
            return;
        }
        list.innerHTML = tags.map(tag => `
            <span class="tag-chip">
                ${escapeHtml(tag)}
                <button type="button" class="tag-chip-remove" data-tag="${escapeHtml(tag)}" title="Remove tag" aria-label="Remove tag ${escapeHtml(tag)}">&times;</button>
            </span>
        `).join('');
        list.querySelectorAll('.tag-chip-remove').forEach(btn => {
            btn.addEventListener('click', () => this.removeTag(btn.dataset.tag));
        });
    },

    async addTag(tag) {
        if (!tag || !this.lease) return;
        try {
            const updatedTags = await Api.addLeaseTag(this.lease.id, tag);
            this.lease.tags = updatedTags;
            this.renderTags(updatedTags);
        } catch (err) {
            showError(`Failed to add tag: ${err.message}`);
        }
    },

    async removeTag(tag) {
        if (!this.lease) return;
        try {
            const updatedTags = await Api.removeLeaseTag(this.lease.id, tag);
            this.lease.tags = updatedTags;
            this.renderTags(updatedTags);
        } catch (err) {
            showError(`Failed to remove tag: ${err.message}`);
        }
    },

    startRenameTitle() {
        const titleEl = document.getElementById('detailTitle');
        if (!this.lease || titleEl.querySelector('input')) return;
        const currentValue = titleEl.textContent.trim();

        const input = document.createElement('input');
        input.type = 'text';
        input.className = 'detail-title-input';
        input.value = currentValue;
        titleEl.textContent = '';
        titleEl.appendChild(input);
        input.focus();
        input.select();

        const commit = async () => {
            const newValue = input.value.trim();
            if (!newValue || newValue === currentValue) {
                titleEl.textContent = currentValue;
                return;
            }
            try {
                const updated = await Api.renameLease(this.lease.id, newValue);
                this.lease.display_name = updated.display_name;
                titleEl.textContent = updated.display_name;
                showToast('Lease renamed.', 'success');
            } catch (err) {
                titleEl.textContent = currentValue;
                showError(`Failed to rename: ${err.message}`);
            }
        };

        input.addEventListener('blur', commit);
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') { e.preventDefault(); input.blur(); }
            else if (e.key === 'Escape') { e.preventDefault(); input.value = currentValue; input.blur(); }
        });
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

function populateTagDatalist(allTags) {
    const datalist = document.getElementById('allTagsList');
    if (!datalist) return;
    datalist.innerHTML = allTags.map(tag => `<option value="${escapeHtml(tag)}"></option>`).join('');
}

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
    document.getElementById('detailExportSheetsBtn').addEventListener('click', () => LeaseDetail.exportToGoogleSheets());
    document.getElementById('detailDeleteBtn').addEventListener('click', () => LeaseDetail.deleteLease());
    document.getElementById('detailTitle').addEventListener('click', () => LeaseDetail.startRenameTitle());

    const tagInput = document.getElementById('detailTagInput');
    const addTag = () => {
        const tag = tagInput.value.trim();
        if (!tag) return;
        LeaseDetail.addTag(tag);
        tagInput.value = '';
    };
    document.getElementById('detailAddTagBtn').addEventListener('click', addTag);
    tagInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); addTag(); } });

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
