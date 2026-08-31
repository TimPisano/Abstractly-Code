/**
 * One-Click Discrepancy Resolution: opened from a rent-roll-vs-lease
 * mismatch row (Dashboard's "Portfolio Composition & Risk" panel) or a
 * rent-roll-vs-T12 mismatch (Upload view's T12 cross-check result).
 * Shows both conflicting values side by side, each with its own real
 * citation (pulled from AppState.leases for rent-roll-vs-lease -- already
 * loaded, full extracted_fields with sources, no extra fetch needed --
 * or from t12_source for the T12 side), lets the user pick which one is
 * correct, and attach a short note.
 *
 * Backed by the real discrepancy-persistence API (see
 * backend/app/discrepancies.py and the /discrepancies/<id>/resolve
 * route) -- every mismatch object returned by
 * /portfolio/rent-roll-reconciliation and /portfolio/t12-reconciliation
 * already carries discrepancy_id/resolution_status/resolution inline
 * (see sync_rent_roll_reconciliation / sync_t12_reconciliation), so
 * this modal just acts on that id. There's no real per-user login in
 * this app yet, so "resolved by" is a free-text name the resolver
 * types in -- same self-reported-identity convention the access gate
 * already uses -- cached in localStorage only so it's pre-filled next
 * time, not as the source of truth (the server's own resolved_by field
 * is that).
 */
const DiscrepancyModal = {
    current: null,

    _resolverName() {
        return getUserIdentity().name || '';
    },

    ensureContainer() {
        let el = document.getElementById('discrepancyModalContainer');
        if (!el) {
            el = document.createElement('div');
            el.id = 'discrepancyModalContainer';
            document.body.appendChild(el);
        }
        return el;
    },

    close() {
        const el = document.getElementById('discrepancyModalContainer');
        if (el) el.innerHTML = '';
        document.removeEventListener('keydown', this._escHandler, true);
        this.current = null;
    },

    /**
     * `spec`: { title, subtitle, discrepancyId, resolutionStatus,
     * resolution, sides: [{key, label, displayValue, source}, {...}] }.
     * `onResolved(updatedDiscrepancy)` fires after a successful
     * resolve/reopen so the caller can refresh its own list.
     */
    open(spec, { onResolved } = {}) {
        this.current = spec;
        this._onResolved = onResolved;

        const existing = spec.resolutionStatus === 'resolved' ? spec.resolution : null;
        const container = this.ensureContainer();
        container.innerHTML = `
            <div class="discrepancy-modal-backdrop" id="discrepancyBackdrop">
                <div class="discrepancy-modal" role="dialog" aria-modal="true" aria-label="Resolve discrepancy">
                    <div class="discrepancy-modal-header">
                        <div>
                            <h2>Resolve Discrepancy</h2>
                            <p class="discrepancy-modal-subtitle">${escapeHtml(spec.subtitle || '')}</p>
                        </div>
                        <button type="button" class="verify-popover-close discrepancy-modal-close" aria-label="Close">&times;</button>
                    </div>

                    ${existing ? `
                        <div class="discrepancy-resolved-banner">
                            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                            <span><strong>${escapeHtml(existing.correct_source)}</strong> marked correct by ${escapeHtml(existing.resolved_by)} on ${formatDate(existing.created_at)}${existing.note ? ` &mdash; "${escapeHtml(existing.note)}"` : ''}</span>
                        </div>
                    ` : ''}

                    <div class="discrepancy-compare">
                        ${spec.sides.map(s => this._sideHtml(s, existing)).join('')}
                    </div>

                    ${spec.discrepancyId == null ? `
                        <p class="discrepancy-local-warning">
                            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z"/></svg>
                            <span>This discrepancy hasn't been recorded yet — reload the page that showed it, then try again.</span>
                        </p>
                    ` : `
                        <div class="discrepancy-note-row">
                            <label for="discrepancyResolverName">Your name</label>
                            <input type="text" id="discrepancyResolverName" class="text-input" placeholder="e.g. J. Alvarez" value="${escapeHtml(this._resolverName())}">
                            <label for="discrepancyNoteInput">Note</label>
                            <textarea id="discrepancyNoteInput" class="text-input" rows="2" placeholder="e.g. Confirmed via the 2nd amendment — rent roll export is stale.">${escapeHtml((existing && existing.note) || '')}</textarea>
                        </div>
                    `}

                    <div class="discrepancy-modal-actions">
                        <button class="btn-secondary" id="discrepancyCancelBtn" type="button">${existing ? 'Close' : 'Cancel'}</button>
                        ${existing ? `<button class="btn-danger" id="discrepancyReopenBtn" type="button">Reopen</button>` : ''}
                    </div>
                    <div id="discrepancyModalStatus"></div>

                    ${spec.discrepancyId != null ? `
                        <div class="discrepancy-discussion">
                            <h3>Discussion</h3>
                            <div id="discrepancyComments"><p class="loading-inline"><span class="spinner-small"></span> Loading notes...</p></div>
                        </div>
                    ` : ''}
                </div>
            </div>
        `;

        container.querySelector('.discrepancy-modal-close').addEventListener('click', () => this.close());
        container.querySelector('#discrepancyCancelBtn').addEventListener('click', () => this.close());
        container.querySelector('#discrepancyBackdrop').addEventListener('click', (e) => {
            if (e.target.id === 'discrepancyBackdrop') this.close();
        });
        const reopenBtn = container.querySelector('#discrepancyReopenBtn');
        if (reopenBtn) reopenBtn.addEventListener('click', () => this._reopen());

        container.querySelectorAll('.discrepancy-pick-btn').forEach(btn => {
            btn.addEventListener('click', () => this._confirmSide(btn.dataset.sideKey, btn.dataset.sideLabel));
        });

        this._escHandler = (e) => { if (e.key === 'Escape') this.close(); };
        document.addEventListener('keydown', this._escHandler, true);

        if (spec.discrepancyId != null) this._loadComments(spec.discrepancyId);
    },

    async _loadComments(discrepancyId) {
        const el = document.getElementById('discrepancyComments');
        if (!el) return;
        try {
            const comments = await Api.listDiscrepancyComments(discrepancyId);
            if (!document.getElementById('discrepancyComments')) return; // modal closed while loading
            renderCommentsThread(el, comments, {
                onSubmit: (body) => Api.addDiscrepancyComment(discrepancyId, body),
            });
        } catch (err) {
            if (el) el.innerHTML = `<p class="error-text">Failed to load notes: ${escapeHtml(err.message)}</p>`;
        }
    },

    _sideHtml(side, existing) {
        const isChosen = existing && existing.correct_source === side.label;
        const source = side.source;
        return `
            <div class="discrepancy-side ${isChosen ? 'discrepancy-side-chosen' : ''}">
                <div class="discrepancy-side-label">${escapeHtml(side.label)}${isChosen ? ' <span class="severity-badge severity-low">Chosen</span>' : ''}</div>
                <div class="discrepancy-side-value">${escapeHtml(side.displayValue) || '<span class="muted">—</span>'}</div>
                ${source ? `
                    <div class="field-source">
                        <div class="source-page">${'row' in source ? `Row ${source.row} of ${escapeHtml(source.file)}` : `Page ${source.page}`}</div>
                        <div class="source-quote">"${escapeHtml(source.quote)}"</div>
                    </div>
                ` : side.sourceNote ? `<p class="verify-popover-subtitle">${escapeHtml(side.sourceNote)}</p>` : `<p class="verify-popover-empty">No source on file for this value.</p>`}
                ${this.current.discrepancyId != null ? `<button class="btn-primary btn-block discrepancy-pick-btn" type="button" data-side-key="${escapeHtml(side.key)}" data-side-label="${escapeHtml(side.label)}">Mark ${escapeHtml(side.label)} Correct</button>` : ''}
            </div>
        `;
    },

    async _confirmSide(sideKey, sideLabel) {
        const spec = this.current;
        if (!spec || spec.discrepancyId == null) return;
        const nameInput = document.getElementById('discrepancyResolverName');
        const noteInput = document.getElementById('discrepancyNoteInput');
        const resolverName = (nameInput.value || '').trim();
        const note = (noteInput.value || '').trim();
        const statusEl = document.getElementById('discrepancyModalStatus');

        if (!resolverName) {
            statusEl.innerHTML = `<p class="error-text">Your name is required so the team knows who resolved this.</p>`;
            return;
        }
        if (!note) {
            statusEl.innerHTML = `<p class="error-text">A short note is required — why is ${escapeHtml(sideLabel)} correct?</p>`;
            return;
        }

        const btn = document.querySelector(`.discrepancy-pick-btn[data-side-key="${sideKey}"]`);
        btn.disabled = true;
        btn.textContent = 'Saving...';
        statusEl.innerHTML = '';

        setUserIdentity(resolverName);

        try {
            const result = await Api.resolveDiscrepancy(spec.discrepancyId, {
                correctSource: sideLabel,
                note,
                resolvedBy: resolverName,
            });
            showToast(`Discrepancy resolved — ${sideLabel} marked correct.`, 'success');
            this.close();
            if (this._onResolved) this._onResolved(result);
        } catch (err) {
            statusEl.innerHTML = `<p class="error-text">${escapeHtml(err.message)}</p>`;
            btn.disabled = false;
            btn.textContent = `Mark ${sideLabel} Correct`;
        }
    },

    async _reopen() {
        const spec = this.current;
        if (!spec || spec.discrepancyId == null) return;
        const resolverName = (this._resolverName() || prompt('Your name (for the record):') || '').trim();
        if (!resolverName) return;
        const note = (prompt('Why are you reopening this?') || '').trim();
        if (!note) return;

        try {
            const result = await Api.reopenDiscrepancy(spec.discrepancyId, { note, resolvedBy: resolverName });
            setUserIdentity(resolverName);
            showToast('Discrepancy reopened.', 'info');
            this.close();
            if (this._onResolved) this._onResolved(result);
        } catch (err) {
            showError(`Failed to reopen: ${err.message}`);
        }
    },
};
