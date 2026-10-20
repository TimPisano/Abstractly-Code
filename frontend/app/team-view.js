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
    invites: [],
    invitesEnabled: false,

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
        container.innerHTML = '<p class="loading-inline" role="status"><span class="spinner-small"></span> Loading team members...</p>';
        try {
            // Invites are optional (TEAM_INVITES_ENABLED); a failure there
            // must not hide the member list.
            const [members, invites] = await Promise.all([
                Api.listTeamMembers(),
                Api.listTeamInvites().catch(() => ({ enabled: false, invites: [] })),
            ]);
            this.members = members;
            this.invitesEnabled = Boolean(invites.enabled);
            this.invites = invites.invites || [];
            document.getElementById('teamInvitePanel').hidden = !this.invitesEnabled;
            document.getElementById('teamAddMemberPanel').hidden = this.invitesEnabled;
            this.render();
            this.renderInvites();
        } catch (err) {
            container.innerHTML = `<p class="error-text">Failed to load team members: ${escapeHtml(err.message)}</p>`;
        }
    },

    renderInvites() {
        const panel = document.getElementById('teamPendingInvitesPanel');
        const container = document.getElementById('teamPendingInvitesContainer');
        panel.hidden = !this.invitesEnabled || this.invites.length === 0;
        if (panel.hidden) {
            container.innerHTML = '';
            return;
        }
        container.innerHTML = `
            <table class="team-members-table">
                <thead>
                    <tr><th>Email</th><th>Role</th><th>Link</th><th></th></tr>
                </thead>
                <tbody>
                    ${this.invites.map((i) => `
                        <tr data-invite-id="${i.id}">
                            <td>${escapeHtml(i.email)}${i.name ? `<br><small>${escapeHtml(i.name)}</small>` : ''}</td>
                            <td>${escapeHtml(ROLE_LABELS[i.role] || i.role)}</td>
                            <td>${escapeHtml(this.inviteLinkLabel(i))}</td>
                            <td>
                                <button type="button" class="btn-secondary team-invite-resend-btn" data-invite-id="${i.id}">Resend</button>
                                <button type="button" class="btn-secondary team-invite-revoke-btn" data-invite-id="${i.id}" data-email="${escapeHtml(i.email)}">Revoke</button>
                            </td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        `;
        container.querySelectorAll('.team-invite-resend-btn').forEach((btn) => {
            btn.addEventListener('click', () => this.resendInvite(parseInt(btn.dataset.inviteId, 10), btn));
        });
        container.querySelectorAll('.team-invite-revoke-btn').forEach((btn) => {
            btn.addEventListener('click', () => this.revokeInvite(parseInt(btn.dataset.inviteId, 10), btn.dataset.email));
        });
    },

    inviteLinkLabel(invite) {
        if (invite.expired || !invite.expires_at) return 'Expired. Resend to send a new link.';
        const hours = Math.max(1, Math.round((new Date(invite.expires_at) - new Date()) / 3600000));
        return hours >= 24 ? `Expires in ${Math.round(hours / 24)} day${Math.round(hours / 24) === 1 ? '' : 's'}` : `Expires in ${hours} hour${hours === 1 ? '' : 's'}`;
    },

    /**
     * After an invite or resend: a toast if it was emailed; if email isn't
     * set up on this server, the link itself, to copy and send by hand.
     */
    showInviteResult(result, email) {
        const messageEl = document.getElementById('teamInviteMessage');
        messageEl.textContent = '';
        messageEl.classList.remove('is-error');
        if (result.emailed) {
            showToast(`Invite sent to ${email}.`, 'success');
            return;
        }
        messageEl.textContent = `Email isn't set up, so nothing was sent. Copy this link and send it to ${email} yourself (it works for 72 hours, once):`;
        const field = document.createElement('input');
        field.type = 'text';
        field.className = 'text-input';
        field.readOnly = true;
        field.value = result.invite_url || '';
        field.setAttribute('aria-label', 'Invite link');
        field.addEventListener('focus', () => field.select());
        messageEl.append(document.createElement('br'), field);
    },

    async sendInvite(e) {
        e.preventDefault();
        const messageEl = document.getElementById('teamInviteMessage');
        const submitBtn = document.getElementById('teamInviteSubmitBtn');
        if (submitBtn.disabled) return;
        messageEl.textContent = '';
        messageEl.classList.remove('is-error');

        const email = document.getElementById('teamInviteEmail').value.trim();
        const name = document.getElementById('teamInviteName').value.trim();
        const role = document.getElementById('teamInviteRole').value;

        submitBtn.disabled = true;
        submitBtn.textContent = 'Sending...';
        try {
            const result = await Api.createTeamInvite({ email, name, role });
            document.getElementById('teamInviteForm').reset();
            document.getElementById('teamInviteRole').value = 'analyst';
            await this.refresh();
            this.showInviteResult(result, email);
        } catch (err) {
            messageEl.textContent = err.message;
            messageEl.classList.add('is-error');
        } finally {
            submitBtn.disabled = false;
            submitBtn.textContent = 'Send Invite';
        }
    },

    async resendInvite(inviteId, button) {
        if (button.disabled) return;
        const invite = this.invites.find((i) => i.id === inviteId);
        button.disabled = true;
        button.textContent = 'Sending...';
        try {
            const result = await Api.resendTeamInvite(inviteId);
            await this.refresh();
            this.showInviteResult(result, invite ? invite.email : 'them');
        } catch (err) {
            showError(`Failed to resend invite: ${err.message}`);
            button.disabled = false;
            button.textContent = 'Resend';
        }
    },

    async revokeInvite(inviteId, email) {
        if (!(await confirmDialog({
            title: 'Revoke this invite?',
            message: `The link sent to ${email} will stop working. You can invite them again later.`,
            confirmText: 'Revoke',
            danger: true,
        }))) {
            return;
        }
        try {
            await Api.revokeTeamInvite(inviteId);
            showToast('Invite revoked.', 'success');
            await this.refresh();
        } catch (err) {
            showError(`Failed to revoke invite: ${err.message}`);
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
            message: "They'll be signed out right away, everywhere, and won't be able to sign in. You can reactivate them later.",
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
    document.getElementById('teamInviteForm').addEventListener('submit', (e) => TeamView.sendInvite(e));
}
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _initTeamViewBindings);
} else {
    _initTeamViewBindings();
}
