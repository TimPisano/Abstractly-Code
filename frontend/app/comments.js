/**
 * Team Notes: a small, reusable comment-thread widget shared by the
 * Lease Detail sidebar, the Discrepancy Resolution modal, and the Task
 * Detail modal -- same markup/behavior everywhere rather than three
 * separate implementations, backed by the real comments API (see
 * backend/app/database.py's comments table / GET+POST
 * /leases/<id>/comments, /discrepancies/<id>/comments, and
 * /tasks/<id>/comments).
 *
 * "Visible to the whole team" needs no client-side scoping either --
 * there's no per-account data isolation anywhere in this app yet (see
 * DECISIONS.md), so a plain GET already is everyone's view.
 *
 * No "your name" input -- real per-user login exists now (see
 * access-gate.js's window.CURRENT_USER), and every comment route
 * always sources the author from the session, ignoring anything a
 * request body claims (see backend/app/api.py's
 * _validate_comment_payload). An editable name field here would just
 * be misleading busywork that the backend silently discards.
 */
function renderCommentsThread(containerEl, comments, { onSubmit }) {
    containerEl.innerHTML = `
        <div class="comments-list">
            ${comments.length ? comments.map(c => `
                <div class="comment-item">
                    ${avatarHtml(c.author_name, 'team-avatar-sm')}
                    <div class="comment-item-body">
                        <div class="comment-item-head">
                            <span class="comment-author">${escapeHtml(c.author_name)}</span>
                            <span class="comment-time" title="${escapeHtml(formatDate(c.created_at))}">${timeAgo(c.created_at)}</span>
                        </div>
                        <div class="comment-body">${escapeHtml(c.body)}</div>
                    </div>
                </div>
            `).join('') : '<p class="empty-inline">No notes yet — be the first to leave one.</p>'}
        </div>
        <div class="comment-add-row">
            <textarea class="text-input comment-body-input" rows="2" placeholder="Add a note for the team..."></textarea>
            <div class="comment-add-actions">
                <button class="btn-secondary comment-submit-btn" type="button">Add Note</button>
            </div>
            <p class="comment-error-text error-text" style="display:none;"></p>
        </div>
    `;

    const submitBtn = containerEl.querySelector('.comment-submit-btn');
    const bodyInput = containerEl.querySelector('.comment-body-input');
    const errorEl = containerEl.querySelector('.comment-error-text');

    submitBtn.addEventListener('click', async () => {
        const body = bodyInput.value.trim();
        errorEl.style.display = 'none';
        if (!body) {
            errorEl.textContent = 'A note is required.';
            errorEl.style.display = 'block';
            return;
        }
        submitBtn.disabled = true;
        submitBtn.textContent = 'Posting...';
        try {
            const updated = await onSubmit(body);
            renderCommentsThread(containerEl, updated, { onSubmit });
        } catch (err) {
            errorEl.textContent = err.message;
            errorEl.style.display = 'block';
            submitBtn.disabled = false;
            submitBtn.textContent = 'Add Note';
        }
    });

    bodyInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); submitBtn.click(); }
    });
}
