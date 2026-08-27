/**
 * AI Assistant: a persistent floating chat (FAB + panel, see the shell-
 * level markup in dashboard.html) answering two different kinds of
 * questions two different ways:
 *
 *  - Informational lease-data questions ("what's the average rent?",
 *    "which leases expire in 90 days?") go to the real POST /qa engine
 *    (backend/app/qa_engine.py) -- the exact same deterministic,
 *    grounded-with-citations engine "Ask About This Lease" already
 *    uses, called portfolio-wide (no lease_id) instead of scoped to one
 *    lease. Deterministic, not an LLM -- a question outside its known
 *    intents (count/list-expiring/aggregate/field-lookup) honestly
 *    returns "I don't have a way to answer that yet" rather than
 *    guessing. See DECISIONS.md.
 *
 *  - Navigational questions ("show me the discrepancies", "open the
 *    lease for Acme Corp") never touch /qa at all -- they're matched
 *    client-side and handled with a real showView()/showLeaseDetail()
 *    call. This isn't a shortcut around a smarter backend: /qa's answer
 *    engine only ever knows about LEASE FIELDS (tenant, rent, dates,
 *    etc.), so a question mentioning Alerts, Discrepancies, Trends,
 *    Reports, Team, Activity, Settings, Upload, or Access Requests
 *    genuinely has no informational answer available regardless of
 *    phrasing -- navigating there IS the correct response, not a
 *    workaround for a gap.
 *
 * Chat history is an in-memory array, cleared on page reload -- this
 * app has no concept of a persisted conversation/thread, and inventing
 * one (a new table, a new endpoint) is out of scope for a "does this
 * feel like a daily workspace" pass.
 */

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
            const result = await Api.askQuestion(question);
            thinking.remove();
            this.addMessage('bot', this._answerHtml(result), result.confidence === 'unsupported');
        } catch (err) {
            thinking.remove();
            this.addMessage('bot', `<p>${escapeHtml(err.message)}</p>`, true);
        }
    },

    _answerHtml(result) {
        let html = `<p>${escapeHtml(result.answer).replace(/\n/g, '<br>')}</p>`;
        if (result.citations && result.citations.length > 0) {
            html += '<div class="assistant-message-citations">';
            result.citations.slice(0, 3).forEach(c => {
                html += `<div>&#128196; ${escapeHtml(c.filename)}, page ${c.page}: &ldquo;${escapeHtml(c.quote)}&rdquo;</div>`;
            });
            if (result.citations.length > 3) {
                html += `<div>+ ${result.citations.length - 3} more</div>`;
            }
            html += '</div>';
        }
        return html;
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
