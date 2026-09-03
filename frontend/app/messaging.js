/**
 * Team Messaging: a persistent floating panel (FAB + panel, markup at
 * the .app-shell level in index.html -- a sibling of <main>, so it
 * survives every section switch instead of being torn down and
 * rebuilt). Real backend (backend/app/messaging.py): direct + group
 * threads, strict participant-only access (a non-participant gets 404,
 * never 403 -- a thread's existence isn't confirmed to someone who
 * isn't in it).
 *
 * Three panes inside the one panel (conversation list / new-
 * conversation / thread), swapped by hiding/showing -- not separate
 * page navigations, so opening a thread and coming back to the list
 * feels instant, no full reload.
 *
 * Polling, not push (same precedent as startLiveActivityPolling() in
 * app.js): unread count every 20s always; while a thread is actually
 * open, that thread's own messages every 4s via `since=<last message
 * timestamp>` (cheap -- only new messages come back, not the whole
 * history each time).
 */
const Messaging = {
    isOpen: false,
    threads: [],
    activeThreadId: null,
    _unreadPollTimer: null,
    _threadPollTimer: null,
    _lastMessageTimestamp: null,

    toggle() {
        this.isOpen ? this.close() : this.openPanel();
    },

    openPanel() {
        this.isOpen = true;
        document.getElementById('messagingPanel').style.display = 'flex';
        document.getElementById('messagingFabBtn').setAttribute('aria-expanded', 'true');
        this.showListPane();
    },

    close() {
        this.isOpen = false;
        document.getElementById('messagingPanel').style.display = 'none';
        document.getElementById('messagingFabBtn').setAttribute('aria-expanded', 'false');
        this._stopThreadPolling();
    },

    _showPane(name) {
        ['List', 'New', 'Thread'].forEach(p => {
            document.getElementById(`messaging${p}Pane`).style.display = p === name ? 'flex' : 'none';
        });
    },

    async showListPane() {
        this._stopThreadPolling();
        this.activeThreadId = null;
        this._showPane('List');
        await this.loadConversationList();
    },

    async showNewPane() {
        this._showPane('New');
        const list = document.getElementById('messagingTeammateList');
        list.innerHTML = '<p class="loading-inline" role="status"><span class="spinner-small"></span> Loading...</p>';
        try {
            const members = await Api.listTeamMembers();
            const others = members.filter(m => !window.CURRENT_USER || m.id !== window.CURRENT_USER.id);
            if (others.length === 0) {
                list.innerHTML = '<p class="empty-inline">No other teammates yet.</p>';
                return;
            }
            list.innerHTML = others.map(u => `
                <button class="messaging-teammate-item" data-id="${u.id}" type="button">
                    ${avatarHtml(u.name, 'team-avatar-sm')}
                    <span>${escapeHtml(u.name)}</span>
                </button>
            `).join('');
            list.querySelectorAll('.messaging-teammate-item').forEach(btn => {
                btn.addEventListener('click', () => this.startDirectThread(parseInt(btn.dataset.id, 10)));
            });
        } catch (err) {
            list.innerHTML = `<p class="error-text">Failed to load teammates: ${escapeHtml(err.message)}</p>`;
        }
    },

    async startDirectThread(userId) {
        try {
            const thread = await Api.createThread('direct', [userId]);
            await this.openThread(thread.id);
        } catch (err) {
            showError(`Failed to start conversation: ${err.message}`);
        }
    },

    async loadConversationList() {
        const el = document.getElementById('messagingConversationList');
        el.innerHTML = '<p class="loading-inline" role="status"><span class="spinner-small"></span> Loading...</p>';
        try {
            this.threads = await Api.listThreads();
            if (this.threads.length === 0) {
                el.innerHTML = '<p class="empty-inline">No conversations yet — start one with the + above.</p>';
                return;
            }
            el.innerHTML = this.threads.map(t => this._conversationRowHtml(t)).join('');
            el.querySelectorAll('.messaging-conversation-item').forEach(row => {
                row.addEventListener('click', () => this.openThread(parseInt(row.dataset.threadId, 10)));
            });
        } catch (err) {
            el.innerHTML = `<p class="error-text">Failed to load conversations: ${escapeHtml(err.message)}</p>`;
        }
    },

    _conversationTitle(thread) {
        if (thread.thread_type === 'direct') {
            return thread.other_participant ? thread.other_participant.name : 'Conversation';
        }
        return thread.name || `Group (${thread.participants.length} people)`;
    },

    _conversationRowHtml(thread) {
        const title = this._conversationTitle(thread);
        const avatarName = thread.thread_type === 'direct' && thread.other_participant ? thread.other_participant.name : title;
        return `
            <button class="messaging-conversation-item ${thread.unread_count > 0 ? 'has-unread' : ''}" data-thread-id="${thread.id}" type="button">
                ${avatarHtml(avatarName, 'team-avatar-sm')}
                <span class="messaging-conversation-item-body">
                    <span class="messaging-conversation-item-title">${escapeHtml(title)}</span>
                </span>
                ${thread.unread_count > 0 ? `<span class="messaging-unread-badge">${thread.unread_count > 9 ? '9+' : thread.unread_count}</span>` : ''}
            </button>
        `;
    },

    async openThread(threadId) {
        this.activeThreadId = threadId;
        this._showPane('Thread');
        const thread = this.threads.find(t => t.id === threadId);
        document.getElementById('messagingThreadTitle').textContent = thread ? this._conversationTitle(thread) : 'Conversation';
        const container = document.getElementById('messagingThreadMessages');
        container.innerHTML = '<p class="loading-inline" role="status"><span class="spinner-small"></span> Loading...</p>';
        try {
            const messages = await Api.getThreadMessages(threadId);
            this._renderMessages(messages, true);
            await Api.markThreadRead(threadId);
            this._refreshUnreadBadge();
            this._startThreadPolling(threadId);
        } catch (err) {
            container.innerHTML = `<p class="error-text">Failed to load messages: ${escapeHtml(err.message)}</p>`;
        }
    },

    _renderMessages(messages, replace) {
        const container = document.getElementById('messagingThreadMessages');
        if (messages.length === 0 && replace) {
            container.innerHTML = '<p class="empty-inline">No messages yet — say hello.</p>';
            return;
        }
        const html = messages.map(m => {
            const mine = window.CURRENT_USER && m.sender_user_id === window.CURRENT_USER.id;
            return `
                <div class="messaging-message ${mine ? 'messaging-message-mine' : ''}">
                    ${!mine ? `<span class="messaging-message-sender">${escapeHtml(m.sender ? m.sender.name : 'Unknown')}</span>` : ''}
                    <span class="messaging-message-body">${escapeHtml(m.body)}</span>
                    <span class="messaging-message-time" title="${escapeHtml(formatDate(m.created_at))}">${timeAgo(m.created_at)}</span>
                </div>
            `;
        }).join('');
        if (replace) {
            container.innerHTML = html || '<p class="empty-inline">No messages yet — say hello.</p>';
        } else {
            container.insertAdjacentHTML('beforeend', html);
        }
        if (messages.length > 0) this._lastMessageTimestamp = messages[messages.length - 1].created_at;
        container.scrollTop = container.scrollHeight;
    },

    async sendMessage(text) {
        const trimmed = text.trim();
        if (!trimmed || !this.activeThreadId) return;
        try {
            const message = await Api.sendThreadMessage(this.activeThreadId, trimmed);
            this._renderMessages([message], false);
        } catch (err) {
            showError(`Failed to send message: ${err.message}`);
        }
    },

    _startThreadPolling(threadId) {
        this._stopThreadPolling();
        this._threadPollTimer = setInterval(async () => {
            if (!this.isOpen || this.activeThreadId !== threadId) return;
            try {
                const newMessages = await Api.getThreadMessages(threadId, this._lastMessageTimestamp);
                if (newMessages.length > 0) {
                    this._renderMessages(newMessages, false);
                    await Api.markThreadRead(threadId);
                    this._refreshUnreadBadge();
                }
            } catch (err) { /* best-effort */ }
        }, 4000);
    },

    _stopThreadPolling() {
        if (this._threadPollTimer) {
            clearInterval(this._threadPollTimer);
            this._threadPollTimer = null;
        }
    },

    startUnreadPolling() {
        if (this._unreadPollTimer) return;
        this._refreshUnreadBadge();
        this._unreadPollTimer = setInterval(() => this._refreshUnreadBadge(), 20000);
    },

    async _refreshUnreadBadge() {
        try {
            const result = await Api.unreadMessageCount();
            const badge = document.getElementById('messagingFabBadge');
            if (result.total_unread > 0) {
                badge.textContent = result.total_unread > 9 ? '9+' : String(result.total_unread);
                badge.style.display = '';
            } else {
                badge.style.display = 'none';
            }
            // If the panel's conversation list is currently showing, keep its own unread badges in sync too.
            if (this.isOpen && !this.activeThreadId) this.loadConversationList();
        } catch (err) { /* best-effort */ }
    },
};

function _initMessagingBindings() {
    document.getElementById('messagingFabBtn').addEventListener('click', () => Messaging.toggle());
    document.getElementById('messagingCloseBtn').addEventListener('click', () => Messaging.close());
    document.getElementById('messagingNewCloseBtn').addEventListener('click', () => Messaging.close());
    document.getElementById('messagingThreadCloseBtn').addEventListener('click', () => Messaging.close());
    document.getElementById('messagingNewBtn').addEventListener('click', () => Messaging.showNewPane());
    document.getElementById('messagingNewBackBtn').addEventListener('click', () => Messaging.showListPane());
    document.getElementById('messagingThreadBackBtn').addEventListener('click', () => Messaging.showListPane());
    document.getElementById('messagingThreadForm').addEventListener('submit', (e) => {
        e.preventDefault();
        const input = document.getElementById('messagingThreadInput');
        const text = input.value;
        input.value = '';
        Messaging.sendMessage(text);
    });
    Messaging.startUnreadPolling();
}
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _initMessagingBindings);
} else {
    _initMessagingBindings();
}
