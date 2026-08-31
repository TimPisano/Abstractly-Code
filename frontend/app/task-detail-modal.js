/**
 * Task Detail Modal: opened from a task row (Tasks page or the Today
 * Briefing panel) so an analyst can work a task without leaving the
 * page it was clicked from. For a lease-linked task, the lease's
 * extracted fields render directly inside the modal -- click any field
 * to edit and save it for real (see saveLeaseFieldEdit in app.js), the
 * same persistence path the full lease detail page now uses too. For a
 * discrepancy-linked task, resolving the discrepancy here uses the same
 * correct-source/note resolve flow as the Discrepancies page's own
 * single-sided resolve form, and completing the task is gated behind
 * that resolution -- see renderCompleteBar/resolveDiscrepancyAndComplete
 * below for why.
 */
const TaskDetailModal = {
    task: null,
    _onChange: null,
    _escHandler: null,

    ensureContainer() {
        let el = document.getElementById('taskModalContainer');
        if (!el) {
            el = document.createElement('div');
            el.id = 'taskModalContainer';
            document.body.appendChild(el);
        }
        return el;
    },

    close() {
        const el = document.getElementById('taskModalContainer');
        if (el) el.innerHTML = '';
        document.removeEventListener('keydown', this._escHandler, true);
        this.task = null;
        this._onChange = null;
    },

    // onChange(task) fires whenever this modal completes an action that
    // could affect the caller's own list (task completed/reopened,
    // discrepancy resolved) -- same callback shape DiscrepancyModal
    // already uses for onResolved, so the Tasks page / Today Briefing
    // can refresh or remove their own row without this modal needing to
    // know which one opened it.
    async open(taskId, { onChange } = {}) {
        this._onChange = onChange;
        const container = this.ensureContainer();
        container.innerHTML = `
            <div class="task-modal-backdrop" id="taskModalBackdrop">
                <div class="task-modal" role="dialog" aria-modal="true" aria-label="Task detail">
                    <p class="loading-inline"><span class="spinner-small"></span> Loading task...</p>
                </div>
            </div>
        `;
        container.querySelector('#taskModalBackdrop').addEventListener('click', (e) => {
            if (e.target.id === 'taskModalBackdrop') this.close();
        });
        this._escHandler = (e) => { if (e.key === 'Escape') this.close(); };
        document.addEventListener('keydown', this._escHandler, true);

        try {
            const task = await Api.getTask(taskId);
            if (!document.getElementById('taskModalBackdrop')) return; // closed while loading
            this.task = task;
            this.render();
        } catch (err) {
            const modal = container.querySelector('.task-modal');
            if (modal) modal.innerHTML = `<p class="error-text">Failed to load task: ${escapeHtml(err.message)}</p>`;
        }
    },

    render() {
        const modal = document.querySelector('.task-modal');
        if (!modal || !this.task) return;
        const t = this.task;

        modal.innerHTML = `
            <div class="discrepancy-modal-header">
                <div>
                    <h2>${escapeHtml(t.title)}</h2>
                    <p class="discrepancy-modal-subtitle">${this._metaLine(t)}</p>
                </div>
                <button type="button" class="verify-popover-close discrepancy-modal-close" aria-label="Close">&times;</button>
            </div>

            ${t.description ? `<p class="task-modal-description">${escapeHtml(t.description)}</p>` : ''}

            ${t.lease_redirected_from_id ? `
                <p class="task-modal-redirect-notice">
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z"/></svg>
                    <span>This task was linked to an earlier version of this lease — showing the current version below.</span>
                </p>
            ` : ''}

            ${t.discrepancy ? this._discrepancySectionHtml(t.discrepancy) : ''}

            <div id="taskModalCompleteBar" class="task-modal-complete-bar"></div>

            ${t.lease ? `
                <div class="task-modal-lease-section">
                    <div class="task-modal-lease-header">
                        <h3>${escapeHtml(t.lease.display_name || t.lease.filename)}</h3>
                        <button class="btn-text" id="taskModalOpenLeaseBtn" type="button">Open full lease page &rarr;</button>
                    </div>
                    <p class="task-modal-lease-hint">Click any field below to correct it. Changes save immediately.</p>
                    <div id="taskModalFieldGroups"></div>
                </div>
            ` : `<p class="empty-inline">This task isn't linked to a lease.</p>`}
        `;

        modal.querySelector('.discrepancy-modal-close').addEventListener('click', () => this.close());
        const openLeaseBtn = document.getElementById('taskModalOpenLeaseBtn');
        if (openLeaseBtn) openLeaseBtn.addEventListener('click', () => {
            const leaseId = t.lease.id;
            this.close();
            showLeaseDetail(leaseId);
        });

        this.renderCompleteBar();
        if (t.discrepancy) this.bindDiscrepancySection();
        if (t.lease) this.renderFieldGroups();
    },

    _metaLine(t) {
        const bits = [];
        bits.push(t.status === 'done' ? 'Completed' : (t.due_date ? `Due ${formatDate(t.due_date)}` : 'No due date'));
        bits.push(t.assigned_to ? `Assigned to ${t.assigned_to.name}` : 'Unassigned');
        return bits.join(' · ');
    },

    // ---- Completion (requirement 4, gated per requirement 5) ----

    renderCompleteBar() {
        const bar = document.getElementById('taskModalCompleteBar');
        if (!bar) return;
        const t = this.task;

        if (t.status === 'done') {
            bar.innerHTML = `
                <div class="task-modal-done-banner">
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                    <span>Completed${t.completed_at ? ` ${timeAgo(t.completed_at)}` : ''}.</span>
                    <button class="btn-text" id="taskModalReopenBtn" type="button">Reopen</button>
                </div>
            `;
            document.getElementById('taskModalReopenBtn').addEventListener('click', () => this.setStatus('open'));
            return;
        }

        // A task tied to a still-open discrepancy can't be completed
        // from a bare "Mark Complete" click -- that would let someone
        // close out the task while silently leaving the underlying
        // discrepancy open, which is exactly what requirement 5 says
        // not to do. The discrepancy section's own resolve form (below)
        // is the only completion path in that case; see
        // resolveDiscrepancyAndComplete.
        if (t.discrepancy && t.discrepancy.status !== 'resolved') {
            bar.innerHTML = `<p class="task-modal-gate-note">This task is tied to an open discrepancy — resolve it above to complete the task.</p>`;
            return;
        }

        bar.innerHTML = `<button class="btn-primary" id="taskModalCompleteBtn" type="button">Mark Complete</button>`;
        document.getElementById('taskModalCompleteBtn').addEventListener('click', () => this.setStatus('done'));
    },

    async setStatus(status) {
        const btn = document.getElementById('taskModalCompleteBtn') || document.getElementById('taskModalReopenBtn');
        if (btn) { btn.disabled = true; }
        try {
            const updated = await Api.updateTaskStatus(this.task.id, status);
            this.task = updated;
            showToast(status === 'done' ? 'Task completed.' : 'Task reopened.', 'success');
            this.renderCompleteBar();
            if (this._onChange) this._onChange(this.task);
        } catch (err) {
            showError(`Failed to update task: ${err.message}`);
            if (btn) btn.disabled = false;
        }
    },

    // ---- Linked discrepancy ----

    _discrepancySectionHtml(d) {
        if (d.status === 'resolved') {
            return `
                <div class="task-modal-discrepancy task-modal-discrepancy-resolved">
                    <div class="task-modal-discrepancy-head">
                        ${severityBadgeHtml(d.severity || 'low')}
                        <span>Discrepancy resolved</span>
                    </div>
                    <p class="alert-card-message">${escapeHtml(d.message)}</p>
                </div>
            `;
        }
        return `
            <div class="task-modal-discrepancy">
                <div class="task-modal-discrepancy-head">
                    ${severityBadgeHtml(d.severity || 'low')}
                    <span>Linked Discrepancy</span>
                </div>
                <p class="alert-card-message">${escapeHtml(d.message)}</p>
                <div class="discrepancy-row-resolve-form task-modal-resolve-form">
                    <label>What's correct / how was this resolved?</label>
                    <input type="text" class="text-input" id="taskModalResolveSource" placeholder="e.g. Confirmed via the lease document, section 12">
                    <label>Note</label>
                    <textarea class="text-input" id="taskModalResolveNote" rows="2" placeholder="Why?"></textarea>
                    <p class="discrepancy-row-error error-text" id="taskModalResolveError" style="display:none;"></p>
                    <button class="btn-primary" id="taskModalResolveBtn" type="button">Resolve Discrepancy &amp; Complete Task</button>
                </div>
            </div>
        `;
    },

    bindDiscrepancySection() {
        const btn = document.getElementById('taskModalResolveBtn');
        if (btn) btn.addEventListener('click', () => this.resolveDiscrepancyAndComplete());
    },

    async resolveDiscrepancyAndComplete() {
        const source = document.getElementById('taskModalResolveSource').value.trim();
        const note = document.getElementById('taskModalResolveNote').value.trim();
        const errorEl = document.getElementById('taskModalResolveError');
        errorEl.style.display = 'none';

        if (!source || !note) {
            errorEl.textContent = "What's correct and a note are both required.";
            errorEl.style.display = 'block';
            return;
        }

        const btn = document.getElementById('taskModalResolveBtn');
        btn.disabled = true;
        btn.textContent = 'Resolving...';

        try {
            // One atomic call -- POST /tasks/<id>/status resolves the
            // linked discrepancy (the same real resolve_discrepancy path
            // a direct resolve uses) and completes the task together,
            // instead of two separate requests that could partially fail.
            const updated = await Api.updateTaskStatus(this.task.id, 'done', { correctSource: source, note });
            showToast('Discrepancy resolved — task completed.', 'success');
            this.task = updated;
            this.render();
            if (this._onChange) this._onChange(this.task);
        } catch (err) {
            errorEl.textContent = err.message;
            errorEl.style.display = 'block';
            btn.disabled = false;
            btn.textContent = 'Resolve Discrepancy & Complete Task';
        }
    },

    // ---- Linked lease: view + edit extracted fields (requirements 1-3) ----

    renderFieldGroups() {
        const container = document.getElementById('taskModalFieldGroups');
        if (!container || !this.task.lease) return;
        const data = this.task.lease.extracted_fields;
        container.innerHTML = '';
        FIELD_GROUPS.forEach(group => {
            const present = group.fields.filter(key => data.hasOwnProperty(key));
            if (present.length === 0) return;
            const section = document.createElement('div');
            section.className = 'field-group';
            const heading = document.createElement('h4');
            heading.className = 'field-group-title';
            heading.textContent = group.name;
            section.appendChild(heading);
            const grid = document.createElement('div');
            grid.className = 'results-grid task-modal-results-grid';
            present.forEach(key => grid.appendChild(this.createFieldCard(key, data[key])));
            section.appendChild(grid);
            container.appendChild(section);
        });
    },

    // A smaller, task-scoped clone of LeaseDetail.createResultCard
    // (detail-view.js) rather than a shared function -- this card skips
    // the source-citation/validation-note detail the full lease page
    // shows, since the task view's job is quick correction, not a full
    // review surface (that's one click away via "Open full lease page").
    createFieldCard(fieldKey, fieldData) {
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

        if (fieldData.manually_verified) {
            const badge = document.createElement('span');
            badge.className = 'edited-badge';
            badge.textContent = found ? 'Manually Edited' : 'Manually Verified — Not Found';
            body.appendChild(badge);
        }

        card.appendChild(body);
        return card;
    },

    startInlineEdit(valueDiv, fieldKey, card) {
        if (valueDiv.querySelector('input')) return;
        const fieldData = this.task.lease.extracted_fields[fieldKey];
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
                card.replaceWith(this.createFieldCard(fieldKey, fieldData));
                return;
            }

            input.disabled = true;
            try {
                const saved = await saveLeaseFieldEdit(this.task.lease.id, fieldKey, newValue === '' ? null : newValue, { taskId: this.task.id });
                this.task.lease.extracted_fields[fieldKey] = saved;
                const newCard = this.createFieldCard(fieldKey, saved);
                card.replaceWith(newCard);
                this.flashSaved(newCard);
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

    // A brief highlight pulse on the just-saved card -- requirement 3's
    // "clear confirmation... when saved" on top of the toast, since a
    // toast alone is easy to miss when attention is already on the
    // field grid inside a modal.
    flashSaved(cardEl) {
        cardEl.classList.add('result-card-just-saved');
        setTimeout(() => cardEl.classList.remove('result-card-just-saved'), 1200);
    },
};
