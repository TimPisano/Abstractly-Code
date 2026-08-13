/**
 * Report View: previews the printable portfolio report (served by the
 * backend as self-contained HTML) in an iframe, with print and
 * download-as-HTML actions.
 */

const ReportView = {
    lastHtml: null,

    async load() {
        const frame = document.getElementById('reportFrame');
        frame.srcdoc = '<p style="font-family: sans-serif; padding: 2rem; color: #6b7280;">Loading report...</p>';
        try {
            this.lastHtml = await Api.portfolioReportHtml();
            frame.srcdoc = this.lastHtml;
        } catch (err) {
            frame.srcdoc = `<p style="font-family: sans-serif; padding: 2rem; color: #b3261e;">Failed to load report: ${escapeHtml(err.message)}</p>`;
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

document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('printReportBtn').addEventListener('click', () => ReportView.print());
    document.getElementById('downloadReportBtn').addEventListener('click', () => ReportView.download());
});
