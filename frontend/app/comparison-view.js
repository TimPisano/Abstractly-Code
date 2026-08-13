/**
 * Comparison View: pick 2+ leases and see their terms side by side, with
 * each numeric term benchmarked against the portfolio average.
 */

const Comparison = {
    selected: new Set(),

    async load(params = {}) {
        try {
            AppState.leases = AppState.leases.length ? AppState.leases : await Api.listLeases();
        } catch (err) {
            showError(`Failed to load leases: ${err.message}`);
            return;
        }

        if (params.preselect && params.preselect.length) {
            this.selected = new Set(params.preselect);
        }

        this.renderPicker();
        document.getElementById('comparisonResults').innerHTML = '';

        if (this.selected.size >= 2) {
            this.runComparison();
        }
    },

    renderPicker() {
        const picker = document.getElementById('comparisonPicker');
        picker.innerHTML = AppState.leases.map(lease => `
            <label class="comparison-picker-item">
                <input type="checkbox" value="${lease.id}" ${this.selected.has(lease.id) ? 'checked' : ''}>
                ${escapeHtml(fieldValue(lease, 'tenant') || lease_filename(lease))}
            </label>
        `).join('');

        picker.querySelectorAll('input[type="checkbox"]').forEach(cb => {
            cb.addEventListener('change', () => {
                const id = parseInt(cb.value, 10);
                if (cb.checked) this.selected.add(id);
                else this.selected.delete(id);
            });
        });
    },

    async runComparison() {
        const ids = Array.from(this.selected);
        if (ids.length < 2) {
            showError('Select at least 2 leases to compare.');
            return;
        }

        const resultsEl = document.getElementById('comparisonResults');
        resultsEl.innerHTML = '<p class="loading-inline"><span class="spinner-small"></span> Comparing...</p>';

        try {
            const [comparison, benchmarks] = await Promise.all([
                Api.compareLeases(ids),
                Promise.all(ids.map(id => Api.leaseBenchmark(id).catch(() => null))),
            ]);
            this.render(comparison, ids, benchmarks);
        } catch (err) {
            resultsEl.innerHTML = `<p class="error-text">Comparison failed: ${escapeHtml(err.message)}</p>`;
        }
    },

    render(comparison, ids, benchmarks) {
        const rows = FIELD_GROUPS.flatMap(g => g.fields);
        const benchmarkableFields = { rent_amount: 'rent_amount', cam_charges: 'cam_charges', security_deposit: 'security_deposit' };

        let html = `<div class="panel"><div class="table-scroll"><table class="data-table comparison-table">`;
        html += `<thead><tr><th>Field</th>${comparison.filenames.map(f => `<th>${escapeHtml(f)}</th>`).join('')}</tr></thead><tbody>`;

        rows.forEach(field => {
            const values = comparison.fields[field] || [];
            html += `<tr><td class="field-name-cell">${FIELD_LABELS[field] || field}</td>`;
            values.forEach((value, i) => {
                const benchmark = benchmarks[i] && benchmarkableFields[field] ? benchmarks[i][benchmarkableFields[field]] : null;
                html += `<td>${escapeHtml(value) || '<span class="muted">Not found</span>'}${benchmarkBadge(benchmark)}</td>`;
            });
            html += `</tr>`;
        });

        html += `</tbody></table></div></div>`;
        document.getElementById('comparisonResults').innerHTML = html;
    },
};

function benchmarkBadge(benchmark) {
    if (!benchmark || benchmark.assessment === 'unknown') return '';
    const labels = { above_average: 'Above avg', below_average: 'Below avg', in_line: 'In line' };
    const sign = benchmark.diff_pct > 0 ? '+' : '';
    return ` <span class="benchmark-badge benchmark-${benchmark.assessment}">${labels[benchmark.assessment]} (${sign}${benchmark.diff_pct}%)</span>`;
}

registerView('comparison', Comparison);

document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('runComparisonBtn').addEventListener('click', () => Comparison.runComparison());
});
