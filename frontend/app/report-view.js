/**
 * Report View: previews the printable portfolio report (served by the
 * backend as self-contained HTML) in an iframe, with print and
 * download-as-HTML actions.
 */

const ReportView = {
    lastHtml: null,

    async load() {
        document.getElementById('exportCsvBtn').href = Api.rentRollCsvUrl();
        document.getElementById('exportStatus').innerHTML = '';

        const frame = document.getElementById('reportFrame');
        frame.srcdoc = '<p style="font-family: sans-serif; padding: 2rem; color: #8b8779;">Loading report...</p>';
        try {
            this.lastHtml = await Api.portfolioReportHtml();
            frame.srcdoc = this.lastHtml;
        } catch (err) {
            frame.srcdoc = `<p style="font-family: sans-serif; padding: 2rem; color: #9a3b3b;">Failed to load report: ${escapeHtml(err.message)}</p>`;
        }
    },

    async exportToGoogleSheets() {
        const btn = document.getElementById('exportSheetsBtn');
        const status = document.getElementById('exportStatus');
        btn.disabled = true;
        btn.textContent = 'Exporting...';
        status.innerHTML = '';

        try {
            const result = await Api.exportToGoogleSheets();
            status.innerHTML = `
                <div class="export-status export-status-success">
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                    <span>Exported to Google Sheets. <a href="${escapeHtml(result.url)}" target="_blank" rel="noopener noreferrer">Open the sheet &rarr;</a></span>
                </div>
            `;
        } catch (err) {
            status.innerHTML = `
                <div class="export-status export-status-error">
                    <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z"/></svg>
                    <span>${escapeHtml(err.message)}</span>
                </div>
            `;
        } finally {
            btn.disabled = false;
            btn.textContent = 'Export to Google Sheets';
        }
    },

    print() {
        const frame = document.getElementById('reportFrame');
        if (frame.contentWindow) {
            frame.contentWindow.focus();
            frame.contentWindow.print();
        }
    },

    download() {
        if (!this.lastHtml) return;
        const blob = new Blob([this.lastHtml], { type: 'text/html' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `portfolio_report_${Date.now()}.html`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
    },
};

registerView('report', ReportView);

// Loaded dynamically by access-gate.js after the gate passes, well after
// DOMContentLoaded already fired -- see the comment in app.js for why a
// readyState check is needed here instead of a plain addEventListener.
function _initReportViewBindings() {
    document.getElementById('printReportBtn').addEventListener('click', () => ReportView.print());
    document.getElementById('downloadReportBtn').addEventListener('click', () => ReportView.download());
    document.getElementById('exportSheetsBtn').addEventListener('click', () => ReportView.exportToGoogleSheets());
}
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _initReportViewBindings);
} else {
    _initReportViewBindings();
}
