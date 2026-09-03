/**
 * Lease Detail View: grouped field display (Parties / Financial Terms /
 * Dates & Term / Special Clauses) with inline editing, a risk-flags
 * panel, an amendments list/uploader, and a per-lease Q&A box.
 */

const LeaseDetail = {
    lease: null,
    fieldReliability: null,

    async load({ leaseId } = {}) {
        if (!leaseId) return;
        try {
            this.lease = await Api.getLease(leaseId);
            // Which field types the pipeline is historically weak at, so
            // a reviewer knows what to eyeball. Cached across leases;
            // never blocks the view if it fails.
            if (this.fieldReliability === null) {
                this.fieldReliability = await Api.extractionFieldReliability()
                    .then(r => r.fields || {})
                    .catch(() => ({}));
            }
            document.getElementById('detailTitle').textContent = this.lease.display_name || lease_filename(this.lease);
            const versionBadge = document.getElementById('detailVersionBadge');
            const versionCount = (this.lease.amendment_count || 0) + 1;
            if (versionCount > 1) {
                versionBadge.textContent = `Version ${versionCount}`;
                versionBadge.style.display = '';
            } else {
                versionBadge.style.display = 'none';
            }
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
            this.loadComments(leaseId);
            this.loadActivity(this.lease);

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
        // conf-<tier> drives the card's border/header emphasis (styles.css)
        // so low/medium-confidence found fields stand out in the grid.
        const confClass = found && fieldData.confidence ? ` conf-${fieldData.confidence}` : '';
        card.className = `result-card ${found ? 'found' : 'not-found'}${confClass}`;
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

        if (fieldData.manually_verified) {
            const editedBadge = document.createElement('span');
            editedBadge.className = 'edited-badge';
            editedBadge.textContent = found ? 'Manually Edited' : 'Manually Verified — Not Found';
            body.appendChild(editedBadge);
        }

        if (found && fieldData.source) {
            const sourceDiv = document.createElement('div');
            sourceDiv.className = 'field-source';
            // Two possible citation shapes: {page, quote} from the PDF
            // extractor, or {row, file, quote} from a rent roll import
            // (rent_roll_import.py) -- there's no PDF page for a
            // spreadsheet cell, so imported fields get a row/file
            // citation instead. Checking for `row` specifically (rather
            // than assuming "no page means row") keeps this forward-
            // compatible with a third source shape later needing its
            // own branch, instead of silently falling into the wrong one.
            const locationHtml = 'row' in fieldData.source
                ? `<div class="source-page">Row ${fieldData.source.row} of ${escapeHtml(fieldData.source.file)}</div>`
                : `<div class="source-page">Page ${fieldData.source.page}</div>`;
            sourceDiv.innerHTML = `
                ${locationHtml}
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

        // Historically-weak field type (from the extraction training
        // loop + real correction rates) -- a standing "check this by
        // eye" hint, independent of this particular extraction's own
        // confidence. Only shown when there's no per-field validation
        // note already saying something stronger, and only for found
        // values.
        const reliability = this.fieldReliability && this.fieldReliability[fieldKey];
        if (found && !fieldData.validation_note && reliability && reliability.reliability === 'weak' && reliability.advice) {
            const hint = document.createElement('div');
            hint.className = 'field-reliability-hint';
            hint.innerHTML = `
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/></svg>
                <span>${escapeHtml(reliability.advice)}</span>
            `;
            body.appendChild(hint);
        }

        card.appendChild(body);
        return card;
    },

    startInlineEdit(valueDiv, fieldKey, card) {
        if (valueDiv.querySelector('input')) return;

        const fieldData = this.lease.extracted_fields[fieldKey];
        const currentValue = fieldData.value != null ? String(fieldData.value) : '';
        const input = document.createElement('input');
        input.type = 'text';
        input.className = 'field-value-input';
        input.value = currentValue;

        valueDiv.textContent = '';
        valueDiv.appendChild(input);
        input.focus();
        input.select();

        let handled = false;
        const commit = async () => {
            if (handled) return;
            handled = true;
            const newValue = input.value.trim();

            if (newValue === currentValue) {
                card.replaceWith(this.createResultCard(fieldKey, fieldData));
                return;
            }

            input.disabled = true;
            try {
                const saved = await saveLeaseFieldEdit(this.lease.id, fieldKey, newValue === '' ? null : newValue);
                this.lease.extracted_fields[fieldKey] = saved;
                card.replaceWith(this.createResultCard(fieldKey, saved));
                showToast('Field saved.', 'success');
            } catch (err) {
                showError(`Failed to save: ${err.message}`);
                handled = false;
                input.disabled = false;
                input.focus();
            }
        };

        input.addEventListener('blur', commit);
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') { e.preventDefault(); input.blur(); }
            else if (e.key === 'Escape') { e.preventDefault(); input.value = currentValue; input.blur(); }
        });
    },

    async loadComments(leaseId) {
        const el = document.getElementById('detailCommentsThread');
        try {
            const comments = await Api.listLeaseComments(leaseId);
            if (!this.lease || this.lease.id !== leaseId) return; // navigated away while loading
            renderCommentsThread(el, comments, {
                onSubmit: (body) => Api.addLeaseComment(leaseId, body),
            });
        } catch (err) {
            el.innerHTML = `<p class="error-text">Failed to load notes: ${escapeHtml(err.message)}</p>`;
        }
    },

    // No lease_id/property filter exists on GET /activity -- filtered
    // here from a reasonably-sized recent batch. "Property" activity
    // covers every lease at the same building (normalizeBuildingAddress,
    // same suite-insensitive grouping trends-view.js already uses), not
    // just this one unit, since that's the more useful read of "what's
    // been happening at this property."
    async loadActivity(lease) {
        const el = document.getElementById('detailActivityContent');
        el.innerHTML = '<p class="loading-inline"><span class="spinner-small"></span> Loading...</p>';
        try {
            const [activity, leases] = await Promise.all([Api.recentActivity(50), Api.listLeases()]);
            if (!this.lease || this.lease.id !== lease.id) return;
            const address = fieldValue(lease, 'property_address');
            const normalized = normalizeBuildingAddress(address);
            const propertyLeaseIds = new Set(
                normalized
                    ? leases.filter(l => normalizeBuildingAddress(fieldValue(l, 'property_address')) === normalized).map(l => l.id)
                    : [lease.id]
            );
            const relevant = activity.filter(a => a.lease_id != null && propertyLeaseIds.has(a.lease_id)).slice(0, 8);

            if (relevant.length === 0) {
                el.innerHTML = '<p class="empty-inline">No recent activity at this property yet.</p>';
                return;
            }
            el.innerHTML = `
                <div class="activity-list">
                    ${relevant.map(a => `
                        <div class="activity-item ${a.lease_id ? 'clickable' : ''}" data-lease-id="${a.lease_id}">
                            <span class="activity-badge activity-badge-${escapeHtml(a.action_type)}">${activityTypeLabel(a.action_type)}</span>
                            <span class="activity-desc">${escapeHtml(a.description)}</span>
                            <span class="activity-time">${timeAgo(a.created_at)}</span>
                        </div>
                    `).join('')}
                </div>
            `;
            el.querySelectorAll('.activity-item.clickable').forEach(item => {
                item.addEventListener('click', () => showLeaseDetail(parseInt(item.dataset.leaseId, 10)));
            });
        } catch (err) {
            el.innerHTML = `<p class="error-text">Failed to load activity: ${escapeHtml(err.message)}</p>`;
        }
    },

    // Simple version list: the base lease is Version 1, each amendment
    // (already ordered oldest-first by GET /leases/<id>/amendments) is
    // Version 2, 3, ... -- the most recent is "Current" since
    // get_effective_fields() lets later uploads win per-field. Not a
    // real diff/comparison view, just "here's what's on file and when
    // it was added" -- the request explicitly said this doesn't need to
    // be fancy.
    renderAmendments(amendments) {
        const list = document.getElementById('amendmentsList');
        const versions = [
            { filename: lease_filename(this.lease), uploaded_at: this.lease.uploaded_at, isBase: true },
            ...(amendments || []),
        ];
        list.innerHTML = versions.map((v, i) => {
            const versionNum = i + 1;
            const isCurrent = i === versions.length - 1;
            return `
                <div class="amendment-item ${isCurrent ? 'amendment-item-current' : ''}">
                    <div class="amendment-item-head">
                        <span class="version-chip ${isCurrent ? 'version-chip-current' : ''}">Version ${versionNum}${v.isBase ? ' (original)' : ''}</span>
                        ${isCurrent ? '<span class="version-current-label">Current</span>' : ''}
                    </div>
                    <div class="amendment-filename">${escapeHtml(v.filename)}</div>
                    <div class="amendment-date">${formatDate(v.uploaded_at)}</div>
                </div>
            `;
        }).join('');
    },

    // Resubmit / Upload New Version: same backend mechanism as the old
    // "Add Amendment" button (POST /leases/<id>/amendments -- a full
    // re-extraction, later upload wins per-field, see
    // database.get_effective_fields), just reframed as version upload
    // with a before/after discrepancy check layered on top.
    async resubmit(file) {
        if (!this.lease) return;
        const status = document.getElementById('resubmitStatus');
        status.innerHTML = '<p class="loading-inline"><span class="spinner-small"></span> Processing new version…</p>';
        document.getElementById('resubmitResolutionsPanel').style.display = 'none';

        // Captured BEFORE the upload -- this is the actual "before" side
        // of the before/after comparison below, not something inferred
        // after the fact. Scoped to lease_risk_flag discrepancies only:
        // those are the ones sync_lease_risk_flags() actually
        // recomputes for this lease on the next risk fetch; a cross-
        // lease mismatch or rent-roll reconciliation discrepancy isn't
        // necessarily affected by re-uploading just this one document,
        // so including them here would risk suggesting a "resolved by
        // resubmission" that isn't really true.
        let beforeDiscrepancies = [];
        try {
            const all = await Api.listDiscrepancies({ leaseId: this.lease.id, status: 'open' });
            beforeDiscrepancies = all.filter(d => d.discrepancy_type === 'lease_risk_flag');
        } catch (err) { /* best-effort -- a failed pre-check just means no reconciliation suggestions after, not a blocked upload */ }

        try {
            const updatedLease = await Api.uploadAmendment(this.lease.id, file);
            status.innerHTML = '';
            showToast('New version uploaded — lease data updated.', 'success');
            await this.load({ leaseId: updatedLease.id });
            if (beforeDiscrepancies.length > 0) {
                await this.checkDiscrepanciesClearedByResubmission(updatedLease.id, beforeDiscrepancies);
            }
        } catch (err) {
            status.innerHTML = `<p class="error-text">Failed to upload new version: ${escapeHtml(err.message)}</p>`;
        }
    },

    // Real before/after comparison, not an automatic backend behavior
    // (no such thing exists yet -- discrepancies never auto-resolve on
    // their own, see DECISIONS.md). Api.leaseRisks() re-runs risk
    // analysis against the now-current (post-resubmission) effective
    // fields and re-syncs each flag's discrepancy_id via
    // sync_lease_risk_flags -- any `before` discrepancy whose id isn't
    // among the freshly-synced ones means that exact condition no
    // longer occurred on this recomputation. Each suggestion still
    // requires a real click against the real POST /discrepancies/<id>
    // /resolve endpoint -- this only pre-fills and surfaces it.
    async checkDiscrepanciesClearedByResubmission(leaseId, beforeDiscrepancies) {
        let freshFlags;
        try {
            freshFlags = await Api.leaseRisks(leaseId);
        } catch (err) {
            return;
        }
        const stillPresentIds = new Set((freshFlags || []).map(f => f.discrepancy_id).filter(id => id != null));
        const cleared = beforeDiscrepancies.filter(d => !stillPresentIds.has(d.id));
        if (cleared.length === 0) return;

        const panel = document.getElementById('resubmitResolutionsPanel');
        const list = document.getElementById('resubmitResolutionsList');
        list.innerHTML = cleared.map(d => `
            <div class="resubmit-resolution-item" data-discrepancy-id="${d.id}">
                <p class="resubmit-resolution-message">${escapeHtml(d.message)}</p>
                <button class="btn-secondary resubmit-resolution-confirm-btn" data-id="${d.id}" type="button">Confirm Resolved</button>
            </div>
        `).join('');
        panel.style.display = 'block';
        list.querySelectorAll('.resubmit-resolution-confirm-btn').forEach(btn => {
            btn.addEventListener('click', () => this.confirmResolvedByResubmission(parseInt(btn.dataset.id, 10)));
        });
    },

    async confirmResolvedByResubmission(discrepancyId) {
        const item = document.querySelector(`.resubmit-resolution-item[data-discrepancy-id="${discrepancyId}"]`);
        const btn = item ? item.querySelector('.resubmit-resolution-confirm-btn') : null;
        if (btn) { btn.disabled = true; btn.textContent = 'Resolving…'; }
        try {
            await Api.resolveDiscrepancy(discrepancyId, {
                correctSource: 'Resubmitted document',
                note: 'Resolved by resubmission — this condition no longer appears in the newly uploaded version.',
            });
            showToast('Discrepancy resolved.', 'success');
            if (item) item.remove();
            if (!document.querySelector('.resubmit-resolution-item')) {
                document.getElementById('resubmitResolutionsPanel').style.display = 'none';
            }
        } catch (err) {
            if (btn) { btn.disabled = false; btn.textContent = 'Confirm Resolved'; }
            showError(`Failed to resolve: ${err.message}`);
        }
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
        if (!(await confirmDialog({
            title: 'Delete this lease?',
            message: `${lease_filename(this.lease)} — this also removes any amendments linked to it. This can't be undone.`,
            confirmText: 'Delete',
            danger: true,
        }))) return;
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
    document.getElementById('detailExportReportBtn').addEventListener('click', () => {
        if (!LeaseDetail.lease) return;
        const address = fieldValue(LeaseDetail.lease, 'property_address');
        if (!address) {
            showError("This lease doesn't have a property address on file, so it can't be scoped to one property for a report -- try the portfolio-wide Export Report on the Dashboard instead.");
            return;
        }
        ExportModal.open({ scopeLabel: address, propertyAddress: address });
    });
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

    // Resubmit dropzone: same drag-and-drop pattern as the main Upload
    // view (dragover/dragleave/drop + click-to-browse via the same
    // hidden input), scoped to this one lease.
    const amendmentInput = document.getElementById('amendmentFileInput');
    const dropzone = document.getElementById('resubmitDropzone');
    dropzone.addEventListener('click', () => amendmentInput.click());
    dropzone.addEventListener('dragover', (e) => { e.preventDefault(); dropzone.classList.add('dragover'); });
    dropzone.addEventListener('dragleave', (e) => { e.preventDefault(); dropzone.classList.remove('dragover'); });
    dropzone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropzone.classList.remove('dragover');
        const file = e.dataTransfer.files[0];
        if (file) LeaseDetail.resubmit(file);
    });
    amendmentInput.addEventListener('change', (e) => {
        const file = e.target.files[0];
        amendmentInput.value = '';
        if (file) LeaseDetail.resubmit(file);
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
