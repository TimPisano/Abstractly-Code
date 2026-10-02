/**
 * Deal Assistant: a persistent floating chat (FAB + panel, see the
 * shell-level markup in dashboard.html), LLM-backed by POST
 * /assistant/ask (backend/app/assistant.py) -- team-scoped, cites a
 * real document and page for every claim grounded in a specific lease
 * (see assistant.py's _resolve_citations), and can hand back a
 * navigational response ({response_type: "navigational", route,
 * lease_id}) when the user wants to be taken somewhere instead of told
 * something.
 *
 * This is NOT the same engine as /qa (backend/app/qa_engine.py, the
 * deterministic, non-LLM engine the per-lease "Ask About This Lease"
 * panel uses, see qa-view.js) -- that one is unchanged and out of
 * scope here. This panel used to call /qa too; it was switched to
 * /assistant/ask because /qa's fixed intent set (count/list-expiring/
 * aggregate/field-lookup) can't answer open-ended synthesis questions
 * like "why was unit 204 flagged" or "what's my total loss to lease",
 * which need the LLM pipeline's access to discrepancies/alerts, not
 * just lease fields.
 *
 * Section/lease navigation is still matched client-side FIRST (zero
 * latency, zero API cost) for the common cases; anything that doesn't
 * match falls through to the real assistant call, which has its own
 * (slower, API-cost) navigational detection as a backstop for phrasing
 * the client-side regexes don't catch.
 *
 * Chat history is an in-memory array, cleared on page reload -- this
 * app has no concept of a persisted conversation/thread in the UI (the
 * backend does persist each Q&A to GET /assistant/conversations, but
 * nothing here re-hydrates from it on open yet).
 */

// Shown as clickable chips under the welcome message and after every
// answer (Phase 3: "good default questions"). Deliberately generic
// enough to make sense for any portfolio, not tied to one demo deal.
const ASSISTANT_SUGGESTED_QUESTIONS = [
    "Which leases expire in the next 6 months?",
    "Why was a unit flagged as a discrepancy?",
    "What's my total loss to lease?",
];

// Checked in order, most specific first, so a generic word late in the
// list (e.g. "note") can't steal a match a more specific one further up
// deserves ("discrepancy note" should still go to Discrepancies, not
// Team Notes -- discrepancies is checked first).
const ASSISTANT_SECTION_NAV = [
    { view: 'discrepancies', label: 'Discrepancies', match: /discrepanc/ },
    { view: 'alerts', label: 'Alerts', match: /\balerts?\b/ },
    { view: 'trends', label: 'Portfolio Trends', match: /\btrends?\b|\brollover\b/ },
    { view: 'report', label: 'Reports & Exports', match: /\breports?\b|\bexports?\b/ },
    { view: 'settings', label: 'Settings', match: /\bsettings?\b|change (my )?password/ },
    { view: 'access', label: 'Access Requests', match: /access request/ },
    { view: 'upload', label: 'Upload', match: /\bupload\b/ },
    { view: 'activity', label: 'Activity', match: /\bactivity\b/ },
    { view: 'teamnotes', label: 'Team', match: /\bteam\b|\bnotes?\b/ },
    { view: 'dashboard', label: 'Leases & Rent Rolls', match: /lease library|rent roll|lease (table|list)/ },
    { view: 'overview', label: 'Dashboard', match: /\b(dashboard|home ?page|overview)\b/ },
];

const Assistant = {
    isOpen: false,

    toggle() {
        this.isOpen ? this.close() : this.openPanel();
    },

    openPanel() {
        this.isOpen = true;
        document.getElementById('assistantPanel').style.display = 'flex';
        document.getElementById('assistantFabBtn').setAttribute('aria-expanded', 'true');
        document.getElementById('assistantInput').focus();
        if (!this._suggestedQuestionsRendered) this._renderSuggestedQuestions();
        this._refreshCreditMeter();
    },

    close() {
        this.isOpen = false;
        document.getElementById('assistantPanel').style.display = 'none';
        document.getElementById('assistantFabBtn').setAttribute('aria-expanded', 'false');
    },

    addMessage(role, html, isError = false) {
        const container = document.getElementById('assistantMessages');
        const el = document.createElement('div');
        el.className = `assistant-message assistant-message-${role}${isError ? ' is-error' : ''}`;
        el.innerHTML = html;
        container.appendChild(el);
        container.scrollTop = container.scrollHeight;
        return el;
    },

    async ask(rawQuestion) {
        const question = rawQuestion.trim();
        if (!question) return;
        this.addMessage('user', `<p>${escapeHtml(question)}</p>`);

        const section = this._matchSection(question);
        if (section) {
            this.addMessage('bot', `<p>Taking you to ${escapeHtml(section.label)}&hellip;</p>`);
            showView(section.view);
            return;
        }

        const leaseQuery = this._extractLeaseNavQuery(question);
        if (leaseQuery) {
            const thinking = this.addMessage('bot', '<p><span class="spinner-small"></span> Looking that up&hellip;</p>');
            const lease = await this._findLease(leaseQuery);
            thinking.remove();
            if (lease) {
                this.addMessage('bot', `<p>Opening ${escapeHtml(lease.display_name || lease.filename)}&hellip;</p>`);
                showLeaseDetail(lease.id);
            } else {
                this.addMessage('bot', `<p>I couldn't find a lease matching "${escapeHtml(leaseQuery)}" — try the tenant name or property address.</p>`, true);
            }
            return;
        }

        const thinking = this.addMessage('bot', '<p><span class="spinner-small"></span> Thinking&hellip;</p>');
        try {
            const result = await Api.askAssistant(question);
            thinking.remove();
            if (result.assistant_usage) this._renderCreditMeter(result.assistant_usage);

            if (result.response_type === 'navigational') {
                this.addMessage('bot', `<p>${escapeHtml(result.answer)}</p>`);
                if (result.route === 'detail' && result.lease_id != null) {
                    showLeaseDetail(result.lease_id);
                } else if (result.route) {
                    showView(result.route);
                }
            } else {
                // Both "informational" and "clarifying" render the same
                // way -- a clarifying question IS the answer in that
                // case, just one that asks something back instead of
                // stating a fact.
                this.addMessage('bot', this._answerHtml(result));
            }
            this._renderSuggestedQuestions();
        } catch (err) {
            thinking.remove();
            // Every error message this route can produce (team quota,
            // rate limit, credit limit, "temporarily unavailable") is
            // already written as a plain-English, user-facing sentence
            // server-side -- shown as a normal bot message, not the
            // harsher red is-error treatment, since none of these are
            // the user's fault or something retrying differently fixes.
            this.addMessage('bot', `<p>${escapeHtml(err.message)}</p>`);
        }
    },

    _answerHtml(result) {
        let html = `<p>${escapeHtml(result.answer).replace(/\n/g, '<br>')}</p>`;
        if (result.citations && result.citations.length > 0) {
            html += '<div class="assistant-message-citations">';
            result.citations.forEach(c => {
                const pageText = c.page != null ? `, page ${c.page}` : '';
                html += `<div>&#128196; ${escapeHtml(c.document)}${pageText}</div>`;
            });
            html += '</div>';
        }
        return html;
    },

    async _refreshCreditMeter() {
        try {
            this._renderCreditMeter(await Api.assistantUsage());
        } catch (err) {
            // Non-critical -- the meter just stays blank if this fails
            // (e.g. a brand-new session with no team yet); the chat
            // itself still works and will surface a clearer error if
            // the team really has no credit.
        }
    },

    _renderCreditMeter(summary) {
        const el = document.getElementById('assistantCreditMeter');
        if (!el || !summary) return;
        const pct = summary.limit_usd > 0 ? Math.min(100, (summary.used_usd / summary.limit_usd) * 100) : 100;
        const low = summary.remaining_usd <= 0;
        el.innerHTML = `
            <div class="assistant-credit-meter-label">${low ? 'No assistant credit left this month' : `$${summary.remaining_usd.toFixed(2)} left this month`}</div>
            <div class="assistant-credit-meter-bar"><div class="assistant-credit-meter-fill${low ? ' is-empty' : ''}" style="width:${pct}%"></div></div>
        `;
    },

    _renderSuggestedQuestions() {
        const el = document.getElementById('assistantSuggestedQuestions');
        if (!el) return;
        this._suggestedQuestionsRendered = true;
        el.innerHTML = ASSISTANT_SUGGESTED_QUESTIONS.map(q =>
            `<button type="button" class="assistant-suggested-chip">${escapeHtml(q)}</button>`
        ).join('');
        el.querySelectorAll('.assistant-suggested-chip').forEach((chip, i) => {
            chip.addEventListener('click', () => this.ask(ASSISTANT_SUGGESTED_QUESTIONS[i]));
        });
    },

    _matchSection(question) {
        const q = question.toLowerCase();
        return ASSISTANT_SECTION_NAV.find(entry => entry.match.test(q)) || null;
    },

    // Only treats the question as lease-navigation if it opens with an
    // actual navigation verb -- otherwise a genuinely informational
    // question that happens to mention a tenant name (e.g. "what's Acme
    // Corp's rent?") would wrongly get swallowed here instead of going
    // to /qa, which CAN answer that one for real.
    _extractLeaseNavQuery(question) {
        const m = question.match(/^\s*(?:take me to|go to|open|navigate to|pull up|show me)\s+(?:the\s+)?(?:lease\s+(?:for|of)\s+)?(.+?)\s*[?.!]*\s*$/i);
        if (!m) return null;
        const rest = m[1].trim();
        return rest.length >= 2 ? rest : null;
    },

    async _findLease(query) {
        const q = query.toLowerCase();
        let leases;
        try {
            leases = await Api.listLeases();
        } catch (err) {
            return null;
        }
        return leases.find(l => {
            const name = (l.display_name || '').toLowerCase();
            const tenant = (fieldValue(l, 'tenant') || '').toLowerCase();
            const address = (fieldValue(l, 'property_address') || '').toLowerCase();
            const filename = (l.filename || '').toLowerCase();
            return (name && name.includes(q)) || (tenant && tenant.includes(q)) || (address && address.includes(q)) || (filename && filename.includes(q));
        }) || null;
    },
};

function _initAssistantBindings() {
    document.getElementById('assistantFabBtn').addEventListener('click', () => Assistant.toggle());
    document.getElementById('assistantCloseBtn').addEventListener('click', () => Assistant.close());
    // The Today dashboard's "Ask a Question" quick action -- opens the
    // same persistent panel rather than being a second, separate
    // entry point into some other Q&A surface.
    const askBtn = document.getElementById('overviewAskAssistantBtn');
    if (askBtn) askBtn.addEventListener('click', () => Assistant.openPanel());
    document.getElementById('assistantForm').addEventListener('submit', (e) => {
        e.preventDefault();
        const input = document.getElementById('assistantInput');
        const question = input.value;
        input.value = '';
        Assistant.ask(question);
    });
}
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _initAssistantBindings);
} else {
    _initAssistantBindings();
}
