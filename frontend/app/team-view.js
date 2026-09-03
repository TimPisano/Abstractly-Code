/**
 * Team View: real team member management (add/edit role/deactivate/
 * reset password) -- backed by the `users` table and /team/members*
 * routes (see backend/app/database.py and app/auth.py). This replaces
 * the "no real accounts" gap team-notes-view.js's own comment used to
 * describe; that gap is closed as of the collaboration-platform work
 * (see DECISIONS.md).
 *
 * Every /team/members* route is @require_role('admin')-gated on the
 * backend -- that's the real permission boundary. The admin-only
 * check here is purely UX: a non-admin sees one clear explanation
 * instead of an empty table or a wall of failed requests.
 */
const ROLE_LABELS = { admin: 'Admin', analyst: 'Analyst', viewer: 'Viewer' };

const TeamView = {
    members: [],

    async load() {
        const session = await Api.authSession();
        const isAdmin = session.authenticated && session.role === 'admin';
        document.getElementById('teamAdminOnlyNotice').style.display = isAdmin ? 'none' : '';
        document.getElementById('teamContent').style.display = isAdmin ? '' : 'none';
        if (!isAdmin) return;

        await this.refresh();
    },

    async refresh() {
        const container = document.getElementById('teamMembersTableContainer');
        container.innerHTML = '<p class="loading-inline"><span class="spinner-small"></span> Loading team members...</p>';
        try {
            this.members = await Api.listTeamMembers();
            this.render();
        } catch (err) {
            container.innerHTML = `<p class="error-text">Failed to load team members: ${escapeHtml(err.message)}</p>`;
        }
    },

    render() {
        const container = document.getElementById('teamMembersTableContainer');
        if (this.members.length === 0) {
            container.innerHTML = '<p class="admin-empty">No team members yet.</p>';
            return;
        }

        container.innerHTML = `
            <table class="team-members-table">
                <thead>
                    <tr><th>Name</th><th>Email</th><th>Role</th><th>Status</th><th></th></tr>
                </thead>
                <tbody>
                    ${this.members.map((m) => `
                        <tr data-member-id="${m.id}" class="${m.status === 'deactivated' ? 'status-pill-deactivated' : ''}">
                            <td>${escapeHtml(m.name)}</td>
                            <td>${escapeHtml(m.email)}</td>
                            <td>
                                <select class="team-role-select" data-member-id="${m.id}">
                                    ${Object.entries(ROLE_LABELS).map(([value, label]) =>
                                        `<option value="${value}" ${m.role === value ? 'selected' : ''}>${label}</option>`
                                    ).join('')}
                                </select>
                            </td>
                            <td>
                                <button type="button" class="btn-secondary team-status-toggle-btn" data-member-id="${m.id}" data-current-status="${m.status}">
                                    ${m.status === 'active' ? 'Deactivate' : 'Reactivate'}
                                </button>
                            </td>
                            <td>
                                <button type="button" class="btn-secondary team-reset-password-btn" data-member-id="${m.id}">Reset Password</button>
                            </td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        `;

        container.querySelectorAll('.team-role-select').forEach((select) => {
            select.addEventListener('change', () => this.updateRole(parseInt(select.dataset.memberId, 10), select.value));
        });
        container.querySelectorAll('.team-status-toggle-btn').forEach((btn) => {
            btn.addEventListener('click', () => this.toggleStatus(parseInt(btn.dataset.memberId, 10), btn.dataset.currentStatus));
        });
        container.querySelectorAll('.team-reset-password-btn').forEach((btn) => {
            btn.addEventListener('click', () => this.resetPassword(parseInt(btn.dataset.memberId, 10)));
        });
    },

    async updateRole(memberId, role) {
        try {
            await Api.updateTeamMember(memberId, { role });
            showToast('Role updated.', 'success');
            await this.refresh();
        } catch (err) {
            showError(`Failed to update role: ${err.message}`);
            await this.refresh(); // revert the select to the real value
        }
    },

    async toggleStatus(memberId, currentStatus) {
        const newStatus = currentStatus === 'active' ? 'deactivated' : 'active';
        if (newStatus === 'deactivated' && !(await confirmDialog({
            title: 'Deactivate team member?',
            message: 'They will no longer be able to sign in. You can reactivate them later.',
            confirmText: 'Deactivate',
            danger: true,
        }))) {
            return;
        }
        try {
            await Api.updateTeamMember(memberId, { status: newStatus });
            showToast(newStatus === 'active' ? 'Member reactivated.' : 'Member deactivated.', 'success');
            await this.refresh();
        } catch (err) {
            showError(`Failed to update status: ${err.message}`);
        }
    },

    async resetPassword(memberId) {
        const newPassword = prompt('New password for this team member (at least 8 characters):');
        if (!newPassword) return;
        if (newPassword.length < 8) {
            showError('Password must be at least 8 characters.');
            return;
        }
        try {
            await Api.resetTeamMemberPassword(memberId, newPassword);
            showToast('Password reset. Share the new password with them directly.', 'success');
        } catch (err) {
            showError(`Failed to reset password: ${err.message}`);
        }
    },

    async addMember(e) {
        e.preventDefault();
        const messageEl = document.getElementById('teamAddMessage');
        const submitBtn = document.getElementById('teamAddSubmitBtn');
        messageEl.textContent = '';
        messageEl.classList.remove('is-error');

        const name = document.getElementById('teamAddName').value.trim();
        const email = document.getElementById('teamAddEmail').value.trim();
        const role = document.getElementById('teamAddRole').value;
        const password = document.getElementById('teamAddPassword').value;

        submitBtn.disabled = true;
        submitBtn.textContent = 'Adding...';
        try {
            await Api.createTeamMember({ name, email, role, password });
            document.getElementById('teamAddMemberForm').reset();
            document.getElementById('teamAddRole').value = 'analyst';
            showToast(`${name} added to the team.`, 'success');
            await this.refresh();
        } catch (err) {
            messageEl.textContent = err.message;
            messageEl.classList.add('is-error');
        } finally {
            submitBtn.disabled = false;
            submitBtn.textContent = 'Add Member';
        }
    },
};

registerView('team', TeamView);

function _initTeamViewBindings() {
    document.getElementById('teamAddMemberForm').addEventListener('submit', (e) => TeamView.addMember(e));
}
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _initTeamViewBindings);
} else {
    _initTeamViewBindings();
}
