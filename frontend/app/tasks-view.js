/**
 * Tasks View: title/description/due-date/assignee/status to-dos
 * (backend/app/tasks.py) -- distinct from Assignments ("who owns this
 * record"): a task is a concrete to-do that may or may not be about a
 * specific record. Supports creating a task directly from a
 * discrepancy or alert (see createFromDiscrepancy/createFromAlert,
 * wired into discrepancies-view.js's and alerts-view.js's card actions
 * respectively) via the real POST /tasks/from-discrepancy/<id> and
 * /tasks/from-alert/<id> routes, which carry the source's own
 * message/category/severity into the new task automatically.
 */
const Tasks = {
    all: [],
    teamMembers: [],
    filters: { showDone: false, assignedTo: '' },
    editingId: null,

    async load() {
        document.getElementById('tasksListContent').innerHTML = '<p class="loading-inline"><span class="spinner-small"></span> Loading...</p>';
        this.hideForm();
        try {
            this.teamMembers = await Api.listTeamMembers();
            this._populateAssigneeSelects();
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
    },

    async fetchAndRender() {
        const params = {};
        if (this.filters.assignedTo) params.assignedTo = parseInt(this.filters.assignedTo, 10);
        let tasks = await Api.listTasks(params);
        // No "not done" filter on the backend (status is a single exact
        // match) -- done/not-done is a client-side view toggle over the
        // same full list, same reasoning as every other showX-hidden-
        // by-default filter in this app (e.g. Alerts' showDismissed).
        if (!this.filters.showDone) tasks = tasks.filter(t => t.status !== 'done');
        tasks.sort((a, b) => {
            if (a.status === 'done' && b.status !== 'done') return 1;
            if (b.status === 'done' && a.status !== 'done') return -1;
            if (!a.due_date && !b.due_date) return 0;
            if (!a.due_date) return 1;
            if (!b.due_date) return -1;
            return a.due_date.localeCompare(b.due_date);
        });
        this.all = tasks;
        this.render(tasks);
    },

    render(tasks) {
        const el = document.getElementById('tasksListContent');
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
        return `
            <div class="task-item ${task.status === 'done' ? 'task-item-done' : ''}" data-id="${task.id}">
                <input type="checkbox" class="task-complete-check" data-id="${task.id}" ${task.status === 'done' ? 'checked' : ''} title="Mark complete">
                <div class="task-item-body">
                    <div class="task-item-title">${escapeHtml(task.title)}</div>
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
        if (!confirm('Delete this task?')) return;
        try {
            await Api.deleteTask(taskId);
            showToast('Task deleted.', 'success');
            await this.fetchAndRender();
        } catch (err) {
            showError(`Failed to delete task: ${err.message}`);
        }
    },

    showForm(prefill) {
        this.editingId = prefill && prefill.id ? prefill.id : null;
        document.getElementById('taskFormId').value = this.editingId || '';
        document.getElementById('taskFormTitle').value = (prefill && prefill.title) || '';
        document.getElementById('taskFormDescription').value = (prefill && prefill.description) || '';
        document.getElementById('taskFormDueDate').value = (prefill && prefill.due_date) || '';
        document.getElementById('taskFormAssignee').value = (prefill && prefill.assigned_to_user_id) || '';
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

        try {
            if (this.editingId) {
                await Api.updateTask(this.editingId, { title, description, due_date: dueDate });
                await Api.assignTask(this.editingId, assignedToUserId);
                showToast('Task updated.', 'success');
            } else {
                await Api.createTask({ title, description, dueDate, assignedToUserId });
                showToast('Task created.', 'success');
            }
            this.hideForm();
            await this.fetchAndRender();
        } catch (err) {
            showError(`Failed to save task: ${err.message}`);
        }
    },

    // Called from discrepancies-view.js / alerts-view.js card actions.
    async createFromDiscrepancy(discrepancyId) {
        try {
            await Api.createTaskFromDiscrepancy(discrepancyId, {});
            showToast('Task created from discrepancy.', 'success');
        } catch (err) {
            showError(`Failed to create task: ${err.message}`);
        }
    },

    async createFromAlert(alertId) {
        try {
            await Api.createTaskFromAlert(alertId, {});
            showToast('Task created from alert.', 'success');
        } catch (err) {
            showError(`Failed to create task: ${err.message}`);
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
}
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _initTasksViewBindings);
} else {
    _initTasksViewBindings();
}
