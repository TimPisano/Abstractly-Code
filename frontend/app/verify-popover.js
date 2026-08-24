/**
 * Click-to-Verify Popover: a single reusable overlay for tracing any
 * number shown in the app back to its source. Two modes:
 *
 *  - showSource(): one field's citation ({page, quote} or {row, file,
 *    quote}) -- used wherever a number comes from exactly one lease's
 *    one field (rent roll rollup table, comparison table, T12 panel).
 *  - showAggregate(): a portfolio-level number (a total, an average, a
 *    WALT) that was rolled up from several leases -- lists the
 *    contributing leases with their own values, click one to open it
 *    and see ITS citation, since the aggregate itself isn't extracted
 *    from any single document/page.
 *
 * Deliberately does not replace the always-visible per-field citation
 * on the Lease Detail view (`.field-source` in detail-view.js) -- that
 * inline display already satisfies CLAUDE.md's "every extracted field
 * must show its source" bar, and hiding it behind a click would be a
 * regression, not an enhancement. This popover exists for every OTHER
 * place a number appears without any source shown today.
 */
const VerifyPopover = {
    _docClickHandler: null,
    _escHandler: null,

    ensureContainer() {
        let el = document.getElementById('verifyPopover');
        if (!el) {
            el = document.createElement('div');
            el.id = 'verifyPopover';
            el.className = 'verify-popover';
            el.style.display = 'none';
            document.body.appendChild(el);
        }
        return el;
    },

    close() {
        const el = document.getElementById('verifyPopover');
        if (el) el.style.display = 'none';
        if (this._docClickHandler) {
            document.removeEventListener('mousedown', this._docClickHandler, true);
            document.removeEventListener('keydown', this._escHandler, true);
            this._docClickHandler = null;
            this._escHandler = null;
        }
    },

    _position(el, triggerEl) {
        const rect = triggerEl.getBoundingClientRect();
        const popW = el.offsetWidth || 320;
        let left = rect.left;
        if (left + popW > window.innerWidth - 16) left = window.innerWidth - popW - 16;
        if (left < 16) left = 16;

        const popH = el.offsetHeight || 160;
        let top = rect.bottom + 8;
        if (top + popH > window.innerHeight - 16) {
            top = Math.max(16, rect.top - popH - 8);
        }
        el.style.left = `${left}px`;
        el.style.top = `${top}px`;
    },

    _open(triggerEl, innerHtml) {
        const el = this.ensureContainer();
        el.innerHTML = innerHtml;
        el.style.display = 'block';
        this._position(el, triggerEl);

        const onDocClick = (e) => {
            if (el.contains(e.target) || triggerEl.contains(e.target)) return;
            this.close();
        };
        const onEsc = (e) => { if (e.key === 'Escape') this.close(); };
        this._docClickHandler = onDocClick;
        this._escHandler = onEsc;
        // Deferred so the click that opened the popover doesn't also
        // register as the "click outside" that immediately closes it.
        setTimeout(() => {
            document.addEventListener('mousedown', onDocClick, true);
            document.addEventListener('keydown', onEsc, true);
        }, 0);

        const closeBtn = el.querySelector('.verify-popover-close');
        if (closeBtn) closeBtn.addEventListener('click', () => this.close());
    },

    /** One field's citation. `source` is {page, quote} or {row, file, quote}; null/undefined renders an honest empty state. */
    showSource(triggerEl, { title, source, confidence, unavailableReason }) {
        const header = `
            <div class="verify-popover-title">
                <span>${escapeHtml(title || 'Verified Source')}</span>
                <button type="button" class="verify-popover-close" aria-label="Close">&times;</button>
            </div>
        `;
        if (!source) {
            this._open(triggerEl, `
                ${header}
                <p class="verify-popover-empty">${escapeHtml(unavailableReason || 'No source on file for this value.')}</p>
            `);
            return;
        }
        const locationLabel = 'row' in source
            ? `Row ${source.row} of ${escapeHtml(source.file)}`
            : `Page ${source.page}`;
        this._open(triggerEl, `
            ${header}
            <div class="field-source verify-popover-source">
                <div class="source-page">${locationLabel}</div>
                <div class="source-quote">"${escapeHtml(source.quote)}"</div>
            </div>
            ${confidence ? `<div class="verify-popover-confidence">${confidenceBadgeHtml(confidence, true)}</div>` : ''}
        `);
    },

    /** A rolled-up portfolio number -- lists the leases behind it, each clickable to open and verify individually. */
    showAggregate(triggerEl, { title, leases }) {
        const rows = (leases || []).filter(l => l.value !== null && l.value !== undefined && l.value !== '');
        const header = `
            <div class="verify-popover-title">
                <span>${escapeHtml(title)}</span>
                <button type="button" class="verify-popover-close" aria-label="Close">&times;</button>
            </div>
        `;
        if (rows.length === 0) {
            this._open(triggerEl, `${header}<p class="verify-popover-empty">No contributing leases with a value for this metric.</p>`);
            return;
        }
        const body = `
            <p class="verify-popover-subtitle">Based on ${rows.length} lease${rows.length === 1 ? '' : 's'} — click one to open it and verify its source.</p>
            <div class="verify-popover-list">
                ${rows.map(l => `
                    <div class="verify-popover-row" data-lease-id="${l.id}">
                        <div class="verify-popover-row-title">${escapeHtml(l.name)}</div>
                        <div class="verify-popover-row-value">${escapeHtml(String(l.value))}</div>
                    </div>
                `).join('')}
            </div>
        `;
        this._open(triggerEl, header + body);
        document.querySelectorAll('#verifyPopover .verify-popover-row').forEach(row => {
            row.addEventListener('click', () => {
                this.close();
                showLeaseDetail(parseInt(row.dataset.leaseId, 10));
            });
        });
    },
};

/** Small inline trigger button used everywhere a number needs a "verify" affordance next to it. */
function verifyTriggerHtml(extraClass) {
    return `
        <button type="button" class="verify-trigger ${extraClass || ''}" title="Verify source" aria-label="Verify source">
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
        </button>
    `;
}

/**
 * Per-table-cell verify trigger: embeds the lease id + field key it
 * belongs to right on the button, so one delegated bindCellVerifyTriggers()
 * call can wire up every cell in a table (Rent Roll rollup, Comparison)
 * without each render function needing its own click-binding logic.
 * Returns '' for a field with no value -- nothing to verify.
 */
function cellVerifyTriggerHtml(lease, fieldKey) {
    const field = lease && lease.extracted_fields && lease.extracted_fields[fieldKey];
    if (!field || field.value === null || field.value === undefined) return '';
    return `
        <button type="button" class="verify-trigger cell-verify-trigger" data-lease-id="${lease.id}" data-field="${fieldKey}" title="Verify source" aria-label="Verify source">
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
        </button>
    `;
}

/** Wires every .cell-verify-trigger inside containerSelector to open VerifyPopover.showSource for its own lease+field, looking the lease up in AppState.leases (already loaded, full extracted_fields -- no extra fetch). */
function bindCellVerifyTriggers(containerSelector) {
    document.querySelectorAll(`${containerSelector} .cell-verify-trigger`).forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const leaseId = parseInt(btn.dataset.leaseId, 10);
            const fieldKey = btn.dataset.field;
            const lease = AppState.leases.find(l => l.id === leaseId);
            const field = lease && lease.extracted_fields && lease.extracted_fields[fieldKey];
            VerifyPopover.showSource(btn, {
                title: FIELD_LABELS[fieldKey] || fieldKey,
                source: field && field.source,
                confidence: field && field.confidence,
            });
        });
    });
}
