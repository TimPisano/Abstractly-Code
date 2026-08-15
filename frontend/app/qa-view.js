/**
 * Q&A View: portfolio-wide natural-language question interface. Every
 * answer comes from /qa (no lease_id, so it's scoped to the whole
 * portfolio) and is rendered with its citations — see qaAnswerHtml in
 * detail-view.js, reused here for a consistent answer format.
 */

const QaView = {
    load() {
        // Nothing to prefetch — the history persists across visits within
        // the session so a user can navigate away and back mid-conversation.
    },

    async ask(question) {
        const history = document.getElementById('qaHistory');
        document.getElementById('qaExamples').style.display = 'none';

        const pendingId = `qa-portfolio-pending-${Date.now()}`;
        history.insertAdjacentHTML('beforeend', `
            <div class="qa-exchange">
                <div class="qa-question">${escapeHtml(question)}</div>
                <div class="qa-answer" id="${pendingId}"><span class="spinner-small"></span> Thinking...</div>
            </div>
        `);
        history.scrollTop = history.scrollHeight;

        try {
            const result = await Api.askQuestion(question);
            document.getElementById(pendingId).outerHTML = qaAnswerHtml(result);
        } catch (err) {
            document.getElementById(pendingId).outerHTML = `<div class="qa-answer qa-answer-error">Error: ${escapeHtml(err.message)}</div>`;
        }
        history.scrollTop = history.scrollHeight;
    },
};

registerView('qa', QaView);

// Loaded dynamically by access-gate.js after the gate passes, well after
// DOMContentLoaded already fired -- see the comment in app.js for why a
// readyState check is needed here instead of a plain addEventListener.
function _initQaViewBindings() {
    const askBtn = document.getElementById('qaBtn');
    const qaInput = document.getElementById('qaInput');
    const ask = () => {
        const question = qaInput.value.trim();
        if (!question) return;
        QaView.ask(question);
        qaInput.value = '';
    };
    askBtn.addEventListener('click', ask);
    qaInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') ask(); });

    document.querySelectorAll('.qa-example-chip').forEach(chip => {
        chip.addEventListener('click', () => {
            qaInput.value = chip.textContent;
            ask();
        });
    });
}
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _initQaViewBindings);
} else {
    _initQaViewBindings();
}
