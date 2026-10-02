/**
 * Help & Guides view: a searchable list of articles (help-content.js)
 * with a reader pane. Static content, no API calls -- it works the same
 * for every user and every role, and needs nothing from the backend.
 *
 * Articles can be opened directly with showView('help', {article: id}),
 * so any other view can link to the right explanation (e.g. the Deal
 * Mismatch Report could link to 'discrepancy-types').
 */
const HelpView = {
    _activeId: null,
    _query: '',

    load(params) {
        const articles = window.HELP_ARTICLES || [];
        const wanted = params && params.article;
        if (wanted && articles.some(a => a.id === wanted)) {
            this._activeId = wanted;
        } else if (!this._activeId && articles.length) {
            this._activeId = articles[0].id;
        }
        this.renderList();
        this.renderArticle();
    },

    _matches(article, q) {
        if (!q) return true;
        // Search the visible text, not the HTML tags.
        const text = (article.title + ' ' + article.summary + ' ' +
                      article.body.replace(/<[^>]+>/g, ' ')).toLowerCase();
        return q.toLowerCase().split(/\s+/).filter(Boolean).every(w => text.includes(w));
    },

    renderList() {
        const list = document.getElementById('helpArticleList');
        if (!list) return;
        const articles = (window.HELP_ARTICLES || []).filter(a => this._matches(a, this._query));
        if (!articles.length) {
            list.innerHTML = '<p class="help-no-results">No articles match that search. ' +
                'Try a simpler word like "upload", "export" or "rent".</p>';
            return;
        }
        const groups = [];
        articles.forEach(a => {
            let g = groups.find(x => x.name === a.category);
            if (!g) groups.push(g = { name: a.category, items: [] });
            g.items.push(a);
        });
        list.innerHTML = groups.map(g => `
            <div class="help-group">
                <div class="help-group-label">${escapeHtmlHelp(g.name)}</div>
                ${g.items.map(a => `
                    <button type="button" class="help-list-item${a.id === this._activeId ? ' active' : ''}" data-help-id="${a.id}">
                        <span class="help-list-title">${escapeHtmlHelp(a.title)}</span>
                        <span class="help-list-summary">${escapeHtmlHelp(a.summary)}</span>
                    </button>`).join('')}
            </div>`).join('');
    },

    renderArticle() {
        const pane = document.getElementById('helpArticle');
        if (!pane) return;
        const article = (window.HELP_ARTICLES || []).find(a => a.id === this._activeId);
        if (!article) {
            pane.innerHTML = '<p class="help-no-results">Pick an article on the left.</p>';
            return;
        }
        // Article bodies are static, trusted strings shipped in
        // help-content.js (never user input), so innerHTML is safe here.
        pane.innerHTML = `
            <div class="help-article-category">${escapeHtmlHelp(article.category)}</div>
            <h2 class="help-article-title">${escapeHtmlHelp(article.title)}</h2>
            <div class="help-article-body">${article.body}</div>`;
        // Label each cell with its column heading, so on phones (where
        // rows stack into cards, see styles.css) a cell like "None." still
        // says which column it belongs to.
        pane.querySelectorAll('.help-article-body table').forEach(table => {
            const heads = [...table.querySelectorAll('tr:first-child th')].map(th => th.textContent.trim());
            table.querySelectorAll('tr').forEach(tr => {
                [...tr.children].forEach((cell, i) => {
                    if (cell.tagName === 'TD' && heads[i]) cell.dataset.label = heads[i];
                });
            });
        });
        pane.scrollTop = 0;
    },

    open(id) {
        this._activeId = id;
        this.renderList();
        this.renderArticle();
        const pane = document.getElementById('helpArticle');
        // On narrow screens the reader sits below the list; bring it into view.
        if (pane && window.innerWidth < 900) pane.scrollIntoView({ behavior: 'smooth', block: 'start' });
    },
};

function escapeHtmlHelp(s) {
    return String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

registerView('help', HelpView);

function _initHelpViewBindings() {
    const list = document.getElementById('helpArticleList');
    if (list) {
        list.addEventListener('click', (e) => {
            const btn = e.target.closest('[data-help-id]');
            if (btn) HelpView.open(btn.dataset.helpId);
        });
    }
    // Links inside articles: <a data-help-link="article-id"> opens another
    // article; <a data-goto="view"> jumps to that part of the app.
    const pane = document.getElementById('helpArticle');
    if (pane) {
        pane.addEventListener('click', (e) => {
            const link = e.target.closest('[data-help-link]');
            if (link) {
                e.preventDefault();
                HelpView.open(link.dataset.helpLink);
                return;
            }
            const go = e.target.closest('[data-goto]');
            if (go) {
                e.preventDefault();
                showView(go.dataset.goto);
            }
        });
    }
    const search = document.getElementById('helpSearch');
    if (search) {
        search.addEventListener('input', () => {
            HelpView._query = search.value.trim();
            HelpView.renderList();
        });
    }
}
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _initHelpViewBindings);
} else {
    _initHelpViewBindings();
}
