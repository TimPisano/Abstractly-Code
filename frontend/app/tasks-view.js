/**
 * Tasks View: title/description/due-date/assignee/status/priority
 * to-dos (backend/app/tasks.py) -- distinct from Assignments ("who
 * owns this record"): a task is a concrete to-do that may or may not
 * be about a specific record. Supports creating a task directly from
 * a discrepancy or alert (see createFromDiscrepancy/createFromAlert,
 * wired into discrepancies-view.js's and alerts-view.js's card actions
 * respectively) via the real POST /tasks/from-discrepancy/<id> and
 * /tasks/from-alert/<id> routes, which carry the source's own
 * message/category/severity into the new task automatically.
 *
 * Multi-select + bulk actions (Complete/Dismiss/Reassign) use the real
 * POST /tasks/bulk-status and /tasks/bulk-reassign routes -- server-
 * side loop-and-report, same pattern as /alerts/bulk-dismiss -- not a
 * client-side loop over the single-task endpoints. Bulk-completing a
 * task tied to a still-open discrepancy is impossible to confirm in a
 * batch (there's no per-task field for "which source was correct"), so
 * the backend SKIPS those rather than guessing; skipped ids are
 * reported back and surfaced so the user can resolve them individually
 * via the task modal.
 */
const Tasks = {
    all: [],
    teamMembers: [],
    filters: { showDone: false, assignedTo: '' },
    editingId: null,
    selected: new Set(),

    async load() {
        document.getElementById('tasksListContent').innerHTML = '<p class="loading-inline"><span class="spinner-small"></span> Loading...</p>';
        this.hideForm();
        this.selected.clear();

        // GET /team/members is admin-only (the full roster, including
        // emails, is sensitive) -- a non-admin (e.g. an analyst) still
        // needs to see and work every task, just without the "reassign
        // to" dropdown being populated. Caught separately from the task
        // fetch so a 403 here doesn't take down the whole page for the
        // exact role this Tasks view mainly exists for.
        try {
            this.teamMembers = await Api.listTeamMembers();
            this._populateAssigneeSelects();
        } catch (err) {
            this.teamMembers = [];
        }

        try {
            await this.fetchAndRender();
        } catch (err) {
            document.getElementById('tasksListContent').innerHTML = `<p class="error-text">Failed to load tasks: ${escapeHtml(err.message)}</p>`;
        }
    },

    _populateAssigneeSelects() {
        const options = this.teamMembers.map(u => `<option value="${u.id}">${escapeHtml(u.name)}</option>`).join('');
        const formSelect = document.getElementById('taskFormAssignee');
        const currentFormVal = formSelect.value;
        formSelect.innerHTML = `<option value="">Unassigned</option>${options}`;
        formSelect.value = currentFormVal;
        const filterSelect = document.getElementById('tasksAssigneeFilter');
        const currentFilterVal = filterSelect.value;
        filterSelect.innerHTML = `<option value="">Everyone</option>${options}`;
        filterSelect.value = currentFilterVal;
        const bulkSelect = document.getElementById('tasksBulkReassignSelect');
        const currentBulkVal = bulkSelect.value;
        bulkSelect.innerHTML = `<option value="">Reassign to...</option><option value="unassign">Unassign</option>${options}`;
        bulkSelect.value = currentBulkVal;
    },

    async fetchAndRender() {
        const params = {};
        if (this.filters.assignedTo) params.assignedTo = parseInt(this.filters.assignedTo, 10);
        let tasks = await Api.listTasks(params);
        // No "not done" filter on the backend (status is a single exact
        // match) -- done/dismissed vs. active is a client-side view
        // toggle over the same full list, same reasoning as every other
        // showX-hidden-by-default filter in this app (e.g. Alerts'
        // showDismissed).
        if (!this.filters.showDone) tasks = tasks.filter(t => t.status !== 'done' && t.status !== 'dismissed');
        // Backend already orders priority-first (see database.list_tasks),
        // but this client-side re-sort (done/dismissed always last) needs
        // to preserve that ordering within the active group, not just
        // fall back to due-date alone.
        tasks.sort((a, b) => {
            const aInactive = a.status === 'done' || a.status === 'dismissed';
            const bInactive = b.status === 'done' || b.status === 'dismissed';
            if (aInactive && !bInactive) return 1;
            if (bInactive && !aInactive) return -1;
            const aHigh = a.priority === 'high', bHigh = b.priority === 'high';
            if (aHigh && !bHigh) return -1;
            if (bHigh && !aHigh) return 1;
            if (!a.due_date && !b.due_date) return 0;
            if (!a.due_date) return 1;
            if (!b.due_date) return -1;
            return a.due_date.localeCompare(b.due_date);
        });
        this.all = tasks;
        // Dropping a selection whose task no longer appears (filtered
        // out, deleted, or already acted on) keeps the bulk bar's count
        // honest instead of silently counting a task that isn't even
        // on screen anymore.
        const visibleIds = new Set(tasks.map(t => t.id));
        for (const id of this.selected) if (!visibleIds.has(id)) this.selected.delete(id);
        this.render(tasks);
    },

    render(tasks) {
        const el = document.getElementById('tasksListContent');
        this._updateBulkBar();
        this._updateSelectAllCheckbox(tasks);
        if (tasks.length === 0) {
            el.innerHTML = `
                <div class="attention-clear">
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                    <span>${this.filters.showDone || this.filters.assignedTo ? 'No tasks match these filters.' : 'No open tasks — create one, or turn a discrepancy/alert into one from where it\'s shown.'}</span>
                </div>
            `;
            return;
        }
        el.innerHTML = `<div class="task-list">${tasks.map(t => this._taskHtml(t)).join('')}</div>`;

        el.querySelectorAll('.task-select-check').forEach(cb => {
            cb.addEventListener('change', () => this.toggleSelect(parseInt(cb.dataset.id, 10), cb.checked));
        });
        el.querySelectorAll('.task-complete-check').forEach(cb => {
            cb.addEventListener('change', () => this.toggleDone(parseInt(cb.dataset.id, 10), cb.checked));
        });
        el.querySelectorAll('.task-edit-btn').forEach(btn => {
            btn.addEventListener('click', () => this.startEdit(parseInt(btn.dataset.id, 10)));
        });
        el.querySelectorAll('.task-delete-btn').forEach(btn => {
            btn.addEventListener('click', () => this.deleteTask(parseInt(btn.dataset.id, 10)));
        });
        el.querySelectorAll('.task-source-link').forEach(link => {
            link.addEventListener('click', (e) => {
                e.stopPropagation();
                if (link.dataset.leaseId) showLeaseDetail(parseInt(link.dataset.leaseId, 10));
                else if (link.dataset.gotoDiscrepancies) showView('discrepancies');
            });
        });
        el.querySelectorAll('[data-task-open]').forEach(titleEl => {
            titleEl.addEventListener('click', () => {
                const taskId = parseInt(titleEl.dataset.taskOpen, 10);
                TaskDetailModal.open(taskId, { onChange: () => this.fetchAndRender() });
            });
        });
    },

    _dueDateClass(task) {
        if (!task.due_date || task.status === 'done') return '';
        const today = new Date().toISOString().slice(0, 10);
        if (task.due_date < today) return 'task-due-overdue';
        if (task.due_date === today) return 'task-due-today';
        return '';
    },

    _taskHtml(task) {
        const dueClass = this._dueDateClass(task);
        const dueLabel = task.due_date
            ? (dueClass === 'task-due-overdue' ? `Overdue — was due ${formatDate(task.due_date)}` : dueClass === 'task-due-today' ? 'Due today' : `Due ${formatDate(task.due_date)}`)
            : 'No due date';
        let sourceHtml = '';
        if (task.lease) {
            sourceHtml = `<button class="btn-text task-source-link" data-lease-id="${task.lease.id}" type="button">${escapeHtml(task.lease.display_name || 'View lease')} &rarr;</button>`;
        } else if (task.discrepancy) {
            sourceHtml = `<button class="btn-text task-source-link" data-goto-discrepancies="1" type="button">View discrepancy &rarr;</button>`;
        }
        const statusTag = task.status === 'dismissed' ? '<span class="task-status-tag task-status-tag-dismissed">Dismissed</span>' : '';
        return `
            <div class="task-item ${task.status === 'done' ? 'task-item-done' : ''} ${task.status === 'dismissed' ? 'task-item-dismissed' : ''}" data-id="${task.id}">
                <input type="checkbox" class="task-select-check" data-id="${task.id}" ${this.selected.has(task.id) ? 'checked' : ''} title="Select for bulk action">
                <input type="checkbox" class="task-complete-check" data-id="${task.id}" ${task.status === 'done' ? 'checked' : ''} title="Mark complete">
                <div class="task-item-body">
                    <div class="task-item-title-row">
                        ${task.priority === 'high' ? '<span class="task-priority-flag" title="High priority">&#9873; Urgent</span>' : ''}
                        <div class="task-item-title task-item-title-open" data-task-open="${task.id}" title="Open task">${escapeHtml(task.title)}</div>
                        ${statusTag}
                    </div>
                    ${task.description ? `<div class="task-item-description">${escapeHtml(task.description)}</div>` : ''}
                    <div class="task-item-meta">
                        <span class="${dueClass}">${dueLabel}</span>
                        ${task.assigned_to ? `<span class="task-item-assignee">${avatarHtml(task.assigned_to.name, 'team-avatar-sm')} ${escapeHtml(task.assigned_to.name)}</span>` : '<span class="muted">Unassigned</span>'}
                        ${sourceHtml}
                    </div>
                </div>
                <div class="task-item-actions">
                    <button class="btn-text task-edit-btn" data-id="${task.id}" type="button">Edit</button>
                    <button class="btn-text task-delete-btn" data-id="${task.id}" type="button">Delete</button>
                </div>
            </div>
        `;
    },

    async toggleDone(taskId, checked) {
        try {
            await Api.updateTaskStatus(taskId, checked ? 'done' : 'open');
            showToast(checked ? 'Task marked complete.' : 'Task reopened.', 'success');
            await this.fetchAndRender();
        } catch (err) {
            showError(`Failed to update task: ${err.message}`);
        }
    },

    async deleteTask(taskId) {
        if (!(await confirmDialog({ title: 'Delete this task?', confirmText: 'Delete', danger: true }))) return;
        try {
            await Api.deleteTask(taskId);
            showToast('Task deleted.', 'success');
            await this.fetchAndRender();
        } catch (err) {
            showError(`Failed to delete task: ${err.message}`);
        }
    },

    // ---- Bulk selection ----

    toggleSelect(taskId, checked) {
        if (checked) this.selected.add(taskId);
        else this.selected.delete(taskId);
        this._updateBulkBar();
        this._updateSelectAllCheckbox(this.all);
    },

    toggleSelectAll(checked) {
        if (checked) this.all.forEach(t => this.selected.add(t.id));
        else this.selected.clear();
        this.render(this.all);
    },

    clearSelection() {
        this.selected.clear();
        this.render(this.all);
    },

    _updateSelectAllCheckbox(tasks) {
        const cb = document.getElementById('tasksSelectAll');
        if (!cb) return;
        cb.checked = tasks.length > 0 && tasks.every(t => this.selected.has(t.id));
    },

    _updateBulkBar() {
        const bar = document.getElementById('tasksBulkBar');
        const count = this.selected.size;
        bar.style.display = count > 0 ? 'flex' : 'none';
        document.getElementById('tasksBulkCount').textContent = `${count} selected`;
    },

    async bulkComplete() {
        const ids = [...this.selected];
        if (ids.length === 0) return;
        try {
            const result = await Api.bulkUpdateTaskStatus(ids, 'done');
            this._reportBulkResult(result, 'completed');
            this.selected.clear();
            await this.fetchAndRender();
        } catch (err) {
            showError(`Failed to complete tasks: ${err.message}`);
        }
    },

    async bulkDismiss() {
        const ids = [...this.selected];
        if (ids.length === 0) return;
        if (!(await confirmDialog({
            title: `Dismiss ${ids.length} task${ids.length === 1 ? '' : 's'}?`,
            message: 'They’ll be hidden from the active list — still visible under "Show completed/dismissed".',
            confirmText: 'Dismiss',
        }))) return;
        try {
            const result = await Api.bulkUpdateTaskStatus(ids, 'dismissed');
            this._reportBulkResult(result, 'dismissed');
            this.selected.clear();
            await this.fetchAndRender();
        } catch (err) {
            showError(`Failed to dismiss tasks: ${err.message}`);
        }
    },

    async bulkReassign(value) {
        const ids = [...this.selected];
        if (ids.length === 0 || !value) return;
        const assignedToUserId = value === 'unassign' ? null : parseInt(value, 10);
        try {
            const result = await Api.bulkReassignTasks(ids, assignedToUserId);
            const name = value === 'unassign' ? 'Unassigned' : (this.teamMembers.find(u => u.id === assignedToUserId) || {}).name || 'selected member';
            showToast(`${result.updated.length} task${result.updated.length === 1 ? '' : 's'} reassigned to ${name}.`, 'success');
            this.selected.clear();
            document.getElementById('tasksBulkReassignSelect').value = '';
            await this.fetchAndRender();
        } catch (err) {
            showError(`Failed to reassign tasks: ${err.message}`);
        }
    },

    _reportBulkResult(result, verb) {
        const n = result.updated.length;
        let message = `${n} task${n === 1 ? '' : 's'} ${verb}.`;
        if (result.skipped_needs_discrepancy && result.skipped_needs_discrepancy.length > 0) {
            message += ` ${result.skipped_needs_discrepancy.length} skipped — tied to an open discrepancy that needs resolving first (open individually).`;
        }
        showToast(message, result.skipped_needs_discrepancy && result.skipped_needs_discrepancy.length > 0 ? 'info' : 'success');
    },

    showForm(prefill) {
        this.editingId = prefill && prefill.id ? prefill.id : null;
        document.getElementById('taskFormId').value = this.editingId || '';
        document.getElementById('taskFormTitle').value = (prefill && prefill.title) || '';
        document.getElementById('taskFormDescription').value = (prefill && prefill.description) || '';
        document.getElementById('taskFormDueDate').value = (prefill && prefill.due_date) || '';
        document.getElementById('taskFormAssignee').value = (prefill && prefill.assigned_to_user_id) || '';
        document.getElementById('taskFormPriority').checked = !!(prefill && prefill.priority === 'high');
        document.getElementById('taskFormSubmitBtn').textContent = this.editingId ? 'Save Changes' : 'Create Task';
        document.getElementById('taskFormPanel').style.display = 'block';
        document.getElementById('taskFormTitle').focus();
    },

    hideForm() {
        this.editingId = null;
        document.getElementById('taskFormPanel').style.display = 'none';
        document.getElementById('taskForm').reset();
    },

    startEdit(taskId) {
        const task = this.all.find(t => t.id === taskId);
        if (task) this.showForm(task);
    },

    async submitForm() {
        const title = document.getElementById('taskFormTitle').value.trim();
        if (!title) return;
        const description = document.getElementById('taskFormDescription').value.trim();
        const dueDate = document.getElementById('taskFormDueDate').value || null;
        const assigneeVal = document.getElementById('taskFormAssignee').value;
        const assignedToUserId = assigneeVal ? parseInt(assigneeVal, 10) : null;
        const priority = document.getElementById('taskFormPriority').checked ? 'high' : 'normal';

        try {
            if (this.editingId) {
                await Api.updateTask(this.editingId, { title, description, due_date: dueDate, priority });
                await Api.assignTask(this.editingId, assignedToUserId);
                showToast('Task updated.', 'success');
            } else {
                await Api.createTask({ title, description, dueDate, assignedToUserId, priority });
                showToast('Task created.', 'success');
            }
            this.hideForm();
            await this.fetchAndRender();
        } catch (err) {
            showError(`Failed to save task: ${err.message}`);
        }
    },

    // Called from discrepancies-view.js / alerts-view.js card actions.
    // `btn`, when given, is disabled for the duration of the call (a
    // fire-and-forget click with no disable-guard risks a double-click
    // creating two duplicate tasks from the same source -- every other
    // async action button in this app already guards against that) and
    // left in a persistent "✓ Task Created" state on success -- a
    // toast alone fades in a few seconds and is easy to miss on a
    // feed you're quickly triaging; a permanently-changed button can't
    // be missed and also prevents accidentally creating a second task
    // from the same alert/discrepancy with a stray extra click.
    async createFromDiscrepancy(discrepancyId, btn) {
        if (btn) { btn.disabled = true; btn.textContent = 'Creating...'; }
        try {
            await Api.createTaskFromDiscrepancy(discrepancyId, {});
            showToast('Task created from discrepancy.', 'success');
            if (btn) btn.textContent = '✓ Task Created';
        } catch (err) {
            showError(`Failed to create task: ${err.message}`);
            if (btn) { btn.disabled = false; btn.textContent = '+ Create Task'; }
        }
    },

    async createFromAlert(alertId, btn) {
        if (btn) { btn.disabled = true; btn.textContent = 'Creating...'; }
        try {
            await Api.createTaskFromAlert(alertId, {});
            showToast('Task created from alert.', 'success');
            if (btn) btn.textContent = '✓ Task Created';
        } catch (err) {
            showError(`Failed to create task: ${err.message}`);
            if (btn) { btn.disabled = false; btn.textContent = '+ Create Task'; }
        }
    },
};

registerView('tasks', Tasks);

function _initTasksViewBindings() {
    document.getElementById('newTaskBtn').addEventListener('click', () => Tasks.showForm());
    document.getElementById('taskFormCancelBtn').addEventListener('click', () => Tasks.hideForm());
    document.getElementById('taskForm').addEventListener('submit', (e) => {
        e.preventDefault();
        Tasks.submitForm();
    });
    document.getElementById('tasksShowDone').addEventListener('change', (e) => {
        Tasks.filters.showDone = e.target.checked;
        Tasks.fetchAndRender();
    });
    document.getElementById('tasksAssigneeFilter').addEventListener('change', (e) => {
        Tasks.filters.assignedTo = e.target.value;
        Tasks.fetchAndRender();
    });
    document.getElementById('tasksSelectAll').addEventListener('change', (e) => {
        Tasks.toggleSelectAll(e.target.checked);
    });
    document.getElementById('tasksBulkCompleteBtn').addEventListener('click', () => Tasks.bulkComplete());
    document.getElementById('tasksBulkDismissBtn').addEventListener('click', () => Tasks.bulkDismiss());
    document.getElementById('tasksBulkClearBtn').addEventListener('click', () => Tasks.clearSelection());
    document.getElementById('tasksBulkReassignSelect').addEventListener('change', (e) => Tasks.bulkReassign(e.target.value));
}
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _initTasksViewBindings);
} else {
    _initTasksViewBindings();
}
