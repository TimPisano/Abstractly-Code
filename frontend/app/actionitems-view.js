/**
 * Action Items: the single prioritized, chronological list combining
 * this user's due/overdue tasks, portfolio-wide lease expirations, and
 * renewal-notice deadlines -- see backend/app/action_items.py's
 * compute_action_items for exactly how the merge and sort work. This
 * view renders that one list; it doesn't compute anything itself.
 *
 * Deliberately no severity-based reordering here (unlike Alerts) --
 * the whole point of this view is "what do I need to do so I never
 * miss a date," so it stays sorted by date, overdue-first, exactly as
 * the backend returns it.
 */
const ActionItems = {
    items: [],

    async load() {
        document.getElementById('actionItemsContent').innerHTML =
            '<p class="loading-inline" role="status"><span class="spinner-small"></span> Loading action items...</p>';
        try {
            await this.fetchAndRender();
        } catch (err) {
            document.getElementById('actionItemsContent').innerHTML =
                `<p class="error-text">Failed to load action items: ${escapeHtml(err.message)}</p>`;
        }
    },

    async refresh() {
        const btn = document.getElementById('actionItemsRefreshBtn');
        btn.disabled = true;
        btn.textContent = 'Refreshing...';
        try {
            await this.fetchAndRender();
            showToast('Action items refreshed.', 'success');
        } catch (err) {
            showError(`Failed to refresh: ${err.message}`);
        } finally {
            btn.disabled = false;
            btn.textContent = 'Refresh';
        }
    },

    async fetchAndRender() {
        const { items } = await Api.actionItems();
        this.items = items;
        applyActionItemsBadge(items);
        this.render(items);
    },

    render(items) {
        const el = document.getElementById('actionItemsContent');
        if (items.length === 0) {
            el.innerHTML = `
                <div class="attention-clear">
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                    <span>Nothing due — no overdue tasks, no expirations or renewal deadlines in the next 90 days.</span>
                </div>
            `;
            return;
        }

        el.innerHTML = `<div class="item-card-list">${items.map((item, i) => this._cardHtml(item, i)).join('')}</div>`;

        el.querySelectorAll('.item-card').forEach((card) => {
            const item = this.items[parseInt(card.dataset.index, 10)];
            const open = () => this._open(item);
            card.addEventListener('click', open);
            card.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); }
            });
        });
    },

    _open(item) {
        if (item.category === 'task') {
            TaskDetailModal.open(item.detail.id, { onChange: () => this.fetchAndRender() });
        } else if (item.lease_id != null) {
            showLeaseDetail(item.lease_id);
        }
    },

    _categoryMeta(category) {
        return {
            task: { label: 'Task', icon: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>' },
            lease_expiration: { label: 'Lease Expiration', icon: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"/>' },
            renewal_deadline: { label: 'Renewal Deadline', icon: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M14.857 17.082a23.848 23.848 0 005.454-1.31A8.967 8.967 0 0118 9.75V9A6 6 0 006 9v.75a8.967 8.967 0 01-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 01-5.714 0m5.714 0a3 3 0 11-5.714 0"/>' },
        }[category] || { label: category, icon: '' };
    },

    _dateLabel(item) {
        if (item.overdue) return `Overdue — ${formatDate(item.date)}`;
        const daysOut = Math.round((new Date(item.date) - new Date()) / 86400000);
        if (daysOut <= 0) return 'Due today';
        if (daysOut === 1) return 'Due tomorrow';
        return `In ${daysOut} days — ${formatDate(item.date)}`;
    },

    _cardHtml(item, index) {
        const meta = this._categoryMeta(item.category);
        const dateClass = item.overdue ? 'item-card-date-overdue' : 'item-card-date-upcoming';
        return `
            <div class="item-card" data-index="${index}" role="button" tabindex="0">
                <span class="item-card-icon item-card-icon-${item.category}">
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">${meta.icon}</svg>
                </span>
                <div class="item-card-body">
                    <div class="item-card-head">
                        <span class="item-card-category">${escapeHtml(meta.label)}</span>
                        ${item.priority === 'high' ? '<span class="severity-badge severity-high">High Priority</span>' : ''}
                    </div>
                    <div class="item-card-title">${escapeHtml(item.title)}</div>
                    ${item.tenant ? `<div class="item-card-subtitle">${escapeHtml(item.tenant)}</div>` : ''}
                </div>
                <div class="item-card-date ${dateClass}">${escapeHtml(this._dateLabel(item))}</div>
            </div>
        `;
    },
};

/**
 * Applies an already-fetched action-items list to the sidebar's Action
 * Items nav badge -- same split pattern as applyAlertsBadge (see
 * alerts-view.js) so a caller that already has the data doesn't need a
 * second round trip just to update the badge. The badge counts overdue
 * items only, not the whole list -- "how many things have already
 * slipped" is the number worth a glance from every other screen in
 * the app, not "how many things exist on my radar at all."
 */
function applyActionItemsBadge(items) {
    const badge = document.getElementById('actionItemsNavBadge');
    const navItem = document.querySelector('.nav-item-actionitems');
    const overdueCount = items.filter((i) => i.overdue).length;
    navItem.classList.toggle('has-alerts', overdueCount > 0);
    if (overdueCount > 0) {
        badge.textContent = overdueCount > 99 ? '99+' : String(overdueCount);
        badge.style.display = '';
    } else {
        badge.style.display = 'none';
    }
}

/** Boot-time badge refresh -- same convention as refreshAlertsBadge(). */
async function refreshActionItemsBadge() {
    try {
        const { items } = await Api.actionItems();
        applyActionItemsBadge(items);
    } catch (err) { /* best-effort */ }
}

registerView('actionitems', ActionItems);

function _initActionItemsViewBindings() {
    document.getElementById('actionItemsRefreshBtn').addEventListener('click', () => ActionItems.refresh());
}
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _initActionItemsViewBindings);
} else {
    _initActionItemsViewBindings();
}
