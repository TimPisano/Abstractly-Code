/**
 * Portfolio Trends View: visual, over-time reads on the portfolio.
 *
 * Rollover risk (forward-looking) comes from the real /portfolio/rollover
 * endpoint for the whole portfolio, or is recomputed client-side (see
 * computeRolloverBuckets) for a single selected property, since that
 * endpoint has no per-property filter.
 *
 * Rent growth, tenant turnover, and historical rollover pattern all come
 * from the real GET /portfolio/property-trends?property_address=X
 * endpoint (see backend/app/portfolio_history.py) -- built on the fact
 * that every lease/rent-roll upload has always been a permanent,
 * append-only record, so re-importing a rent roll or re-uploading a
 * lease over time already IS a real historical timeline, just not
 * previously queryable as one. That endpoint is scoped to one building
 * at a time; for "All Properties" this view fetches it once per
 * distinct building in the portfolio and merges the results client-side
 * (see _mergePropertyTrends) -- there's no portfolio-wide version of
 * this endpoint. One real limitation, inherited from the backend and
 * not worked around here: a deleted lease's history goes with it (a
 * hard delete), and a property with only ever ONE upload has nothing to
 * trend yet -- both produce an honest empty state below, not a guess.
 *
 * Charts are hand-rolled inline SVG (renderBarChart below), matching
 * this app's existing zero-JS-dependency approach rather than
 * introducing the project's first chart library.
 */

const Trends = {
    allLeases: [],
    portfolioRollover: null,
    propertyGroups: new Map(), // normalized building address -> raw address string
    selectedProperty: '', // '' = all properties

    async load() {
        document.getElementById('trendsRolloverChart').innerHTML = '<p class="loading-inline"><span class="spinner-small"></span> Loading...</p>';
        document.getElementById('trendsTurnoverChart').innerHTML = '';
        document.getElementById('trendsRentGrowthContent').innerHTML = '';
        try {
            const [leases, rollover] = await Promise.all([
                Api.listLeases(),
                Api.portfolioRollover(),
            ]);
            this.allLeases = leases;
            AppState.leases = leases;
            this.portfolioRollover = rollover;
            this.renderPropertyFilter();
            this.renderAll();
        } catch (err) {
            showError(`Failed to load portfolio trends: ${err.message}`);
            document.getElementById('trendsRolloverChart').innerHTML = `<p class="error-text">Failed to load: ${escapeHtml(err.message)}</p>`;
        }
    },

    renderPropertyFilter() {
        const select = document.getElementById('trendsPropertyFilter');
        const groups = new Map(); // normalized address -> display label
        this.allLeases.forEach(l => {
            const addr = fieldValue(l, 'property_address');
            const norm = normalizeBuildingAddress(addr);
            if (!norm || groups.has(norm)) return;
            groups.set(norm, addr);
        });
        this.propertyGroups = groups;
        const options = Array.from(groups.entries()).sort((a, b) => a[1].localeCompare(b[1]));
        select.innerHTML = `<option value="">All Properties (${this.allLeases.length} lease${this.allLeases.length === 1 ? '' : 's'})</option>` +
            options.map(([norm, label]) => `<option value="${escapeHtml(norm)}">${escapeHtml(label)}</option>`).join('');
        select.value = this.selectedProperty;
    },

    _filteredLeases() {
        if (!this.selectedProperty) return this.allLeases;
        return this.allLeases.filter(l => normalizeBuildingAddress(fieldValue(l, 'property_address')) === this.selectedProperty);
    },

    onPropertyChange(value) {
        this.selectedProperty = value;
        this.renderAll();
    },

    renderAll() {
        this.renderRollover();
        this._loadPropertyTrends()
            .then(trends => {
                this.renderRentGrowth(trends);
                this.renderTurnover(trends);
            })
            .catch(err => {
                document.getElementById('trendsRentGrowthContent').innerHTML = `<p class="error-text">Failed to load: ${escapeHtml(err.message)}</p>`;
                document.getElementById('trendsTurnoverChart').innerHTML = `<p class="error-text">Failed to load: ${escapeHtml(err.message)}</p>`;
            });
    },

    async _loadPropertyTrends() {
        if (this.selectedProperty) {
            const addr = this.propertyGroups.get(this.selectedProperty);
            if (!addr) return null;
            return Api.portfolioPropertyTrends(addr);
        }
        const addrs = Array.from(this.propertyGroups.values());
        if (addrs.length === 0) return null;
        const results = await Promise.all(addrs.map(a => Api.portfolioPropertyTrends(a).catch(() => null)));
        return this._mergePropertyTrends(results.filter(Boolean));
    },

    // No portfolio-wide equivalent of GET /portfolio/property-trends
    // exists on the backend (it's scoped to one building), so "All
    // Properties" combines one response per distinct building here --
    // straightforward concatenation/summation since each building's
    // trends are already independent of every other's.
    _mergePropertyTrends(results) {
        const units = [];
        let unitsWithGrowthData = 0;
        const events = [];
        let turnoverCount = 0, unitsTracked = 0;
        const byMonth = {};
        for (let m = 1; m <= 12; m++) byMonth[String(m).padStart(2, '0')] = 0;
        const byYear = {};
        let totalExpirationsTracked = 0;
        let recordCount = 0;

        results.forEach(r => {
            units.push(...r.rent_growth.units);
            unitsWithGrowthData += r.rent_growth.units_with_growth_data;
            events.push(...r.tenant_turnover.events);
            turnoverCount += r.tenant_turnover.turnover_count;
            unitsTracked += r.tenant_turnover.units_tracked;
            Object.entries(r.rollover_pattern.by_month).forEach(([k, v]) => { byMonth[k] += v; });
            Object.entries(r.rollover_pattern.by_year).forEach(([k, v]) => { byYear[k] = (byYear[k] || 0) + v; });
            totalExpirationsTracked += r.rollover_pattern.total_expirations_tracked;
            recordCount += r.record_count;
        });

        return {
            record_count: recordCount,
            rent_growth: { units, units_with_growth_data: unitsWithGrowthData },
            tenant_turnover: { events, turnover_count: turnoverCount, units_tracked: unitsTracked },
            rollover_pattern: { by_month: byMonth, by_year: byYear, total_expirations_tracked: totalExpirationsTracked },
        };
    },

    renderRentGrowth(trends) {
        const el = document.getElementById('trendsRentGrowthContent');
        const allTransitions = [];
        (trends ? trends.rent_growth.units : []).forEach(u => {
            u.transitions.forEach(t => allTransitions.push({ ...t, unit_address: u.unit_address }));
        });

        if (allTransitions.length === 0) {
            el.innerHTML = `<p class="attention-empty-note">Not enough history yet for this selection — needs at least two uploads for the same unit (e.g. two rent-roll snapshots, or a lease re-upload) to compare rent across time.</p>`;
            return;
        }

        allTransitions.sort((a, b) => (b.to_uploaded_at || '').localeCompare(a.to_uploaded_at || ''));
        const avgChange = allTransitions.reduce((s, t) => s + t.pct_change, 0) / allTransitions.length;

        el.innerHTML = `
            <p class="attention-summary-line">
                <strong>${avgChange >= 0 ? '+' : ''}${avgChange.toFixed(1)}%</strong> average change across ${allTransitions.length} tracked transition${allTransitions.length === 1 ? '' : 's'}
                (${trends.rent_growth.units_with_growth_data} unit${trends.rent_growth.units_with_growth_data === 1 ? '' : 's'} with enough history to trend)
            </p>
            <div class="rent-growth-list">
                ${allTransitions.slice(0, 10).map(t => `
                    <div class="rent-growth-item">
                        <div class="rent-growth-item-main">
                            <span class="rent-growth-item-address">${escapeHtml(t.unit_address || 'Unknown unit')}</span>
                            <span class="rent-growth-item-values">${escapeHtml(t.from_rent)} &rarr; ${escapeHtml(t.to_rent)}</span>
                            <span class="rent-growth-pct ${t.pct_change >= 0 ? 'rent-growth-up' : 'rent-growth-down'}">${t.pct_change >= 0 ? '+' : ''}${t.pct_change}%</span>
                            ${t.tenant_changed ? '<span class="severity-badge severity-medium">Tenant Turnover</span>' : ''}
                        </div>
                        <div class="rent-growth-item-date">${formatDate(t.to_uploaded_at)}</div>
                    </div>
                `).join('')}
            </div>
            ${allTransitions.length > 10 ? `<p class="attention-more">+${allTransitions.length - 10} more transition(s)</p>` : ''}
        `;
    },

    renderRollover() {
        const filtered = this._filteredLeases();
        // /portfolio/rollover is portfolio-wide only (no per-property
        // filter param exists on the backend) -- for "All Properties"
        // this uses that real, authoritative response. For a specific
        // property, the exact same bucketing rules are recomputed
        // client-side against just that property's leases (see
        // computeRolloverBuckets below, deliberately mirroring
        // portfolio.py's compute_rollover_schedule bucket-by-bucket).
        const usePortfolioWide = !this.selectedProperty;
        const schedule = usePortfolioWide ? this.portfolioRollover.rollover_schedule : computeRolloverBuckets(filtered).schedule;
        const walt = usePortfolioWide ? this.portfolioRollover.walt : computeRolloverBuckets(filtered).walt;

        const chartEl = document.getElementById('trendsRolloverChart');
        const summaryEl = document.getElementById('trendsRolloverSummary');

        if (!schedule || !schedule.buckets) {
            chartEl.innerHTML = '<p class="attention-empty-note">Not enough data yet for this selection — needs at least one lease with both a rent amount and an end date.</p>';
            summaryEl.innerHTML = '';
            return;
        }

        const bucketLabels = { year_1: 'Yr 1', year_2: 'Yr 2', year_3: 'Yr 3', year_4: 'Yr 4', year_5: 'Yr 5', year_6_plus: 'Yr 6+' };
        const bars = Object.keys(bucketLabels).map(key => ({
            label: bucketLabels[key],
            value: schedule.buckets[key].rent,
            sublabel: `${schedule.buckets[key].pct_of_total_rent.toFixed(0)}%`,
            colorOverride: key === 'year_1' ? riskColorVar(schedule.rollover_risk_level) : null,
        }));
        renderBarChart(chartEl, { bars, valueFormatter: fmtMoneyShort });

        summaryEl.innerHTML = `
            <div class="health-metric">
                <div class="health-metric-value">${walt && walt.walt_years != null ? `${walt.walt_years.toFixed(1)} yrs` : '—'}</div>
                <div class="health-metric-label">WALT (rent-weighted)</div>
            </div>
            <div class="health-metric">
                <div class="health-metric-value">${schedule.buckets.year_1.pct_of_total_rent.toFixed(1)}%</div>
                <div class="health-metric-label">Rent Rolling Over, Year 1</div>
            </div>
            <div class="health-metric">
                <div class="health-metric-value">${riskLevelBadgeHtml(schedule.rollover_risk_level)}</div>
                <div class="health-metric-label">Rollover Risk Level</div>
            </div>
            <div class="health-metric">
                <div class="health-metric-value">${schedule.already_expired ? schedule.already_expired.lease_count : 0}</div>
                <div class="health-metric-label">Already Expired, On File</div>
            </div>
        `;
    },

    // Historical expiration distribution -- real data from every
    // lease/rent-roll upload ever made at this property (see
    // compute_rollover_pattern), not just currently-on-file leases. A
    // year bucket includes every upload whose lease_end_date fell in
    // that year, so a unit re-uploaded multiple times over the years
    // contributes one data point per upload, same append-only-history
    // logic the rent growth panel above reads from.
    renderTurnover(trends) {
        const chartEl = document.getElementById('trendsTurnoverChart');
        const summaryEl = document.getElementById('trendsTurnoverSummary');
        const currentYear = new Date().getFullYear();

        if (!trends || trends.rollover_pattern.total_expirations_tracked === 0) {
            chartEl.innerHTML = '<p class="attention-empty-note">Not enough data yet for this selection — needs at least one upload with a parseable end date.</p>';
            summaryEl.innerHTML = '';
            return;
        }

        const byYear = trends.rollover_pattern.by_year;
        const years = Object.keys(byYear).sort();
        const bars = years.map(y => ({
            label: y,
            value: byYear[y],
            colorOverride: Number(y) < currentYear ? 'var(--slate-400)' : (Number(y) === currentYear ? 'var(--warning-color)' : 'var(--lux-accent)'),
        }));
        renderBarChart(chartEl, { bars, valueFormatter: v => String(v) });

        const recentEvents = trends.tenant_turnover.events.slice(-3).reverse();
        summaryEl.innerHTML = `
            <strong>${trends.tenant_turnover.turnover_count}</strong> tenant turnover event${trends.tenant_turnover.turnover_count === 1 ? '' : 's'} detected across ${trends.tenant_turnover.units_tracked} tracked unit${trends.tenant_turnover.units_tracked === 1 ? '' : 's'}
            ${recentEvents.length ? '— most recent: ' + recentEvents.map(e => `${escapeHtml(e.from_tenant)} &rarr; ${escapeHtml(e.to_tenant)}`).join(', ') : ''}
        `;
    },
};

/**
 * Client-side mirror of portfolio.py's compute_rollover_schedule /
 * compute_walt, used only when a specific property is selected (the
 * real backend endpoint is portfolio-wide only). Deliberately follows
 * the exact same bucket boundaries and risk thresholds documented
 * there so a property-filtered chart can't silently disagree with the
 * portfolio-wide one's own math.
 */
function computeRolloverBuckets(leases, referenceDate) {
    const ref = referenceDate || new Date();
    const bucketNames = ['year_1', 'year_2', 'year_3', 'year_4', 'year_5', 'year_6_plus'];
    const buckets = {};
    bucketNames.forEach(n => { buckets[n] = { rent: 0, lease_count: 0 }; });
    let alreadyExpiredRent = 0, alreadyExpiredCount = 0;
    let totalRent = 0, leaseCount = 0;
    let weightedYearsSum = 0, waltRentSum = 0, waltCount = 0;

    leases.forEach(l => {
        const endTs = parseLeaseDate(fieldValue(l, 'lease_end_date'));
        const rent = parseMoney(fieldValue(l, 'rent_amount'));
        if (endTs === null || !rent || rent <= 0) return;

        const daysRemaining = (endTs - ref.getTime()) / (1000 * 60 * 60 * 24);
        if (daysRemaining < 0) {
            alreadyExpiredRent += rent;
            alreadyExpiredCount += 1;
            return;
        }
        const yearsRemaining = daysRemaining / 365.25;
        weightedYearsSum += yearsRemaining * rent;
        waltRentSum += rent;
        waltCount += 1;

        const idx = Math.min(Math.floor(yearsRemaining), 5);
        const name = bucketNames[idx];
        buckets[name].rent += rent;
        buckets[name].lease_count += 1;
        totalRent += rent;
        leaseCount += 1;
    });

    const walt = { walt_years: waltCount > 0 && waltRentSum > 0 ? weightedYearsSum / waltRentSum : null };

    if (leaseCount === 0 && alreadyExpiredCount === 0) {
        return { schedule: { buckets: null, already_expired: null, total_rent: null, lease_count: 0, rollover_risk_level: null }, walt };
    }
    if (leaseCount === 0) {
        const bucketResults = {};
        bucketNames.forEach(n => { bucketResults[n] = { rent: 0, pct_of_total_rent: 0, lease_count: 0 }; });
        return {
            schedule: {
                buckets: bucketResults,
                already_expired: { rent: alreadyExpiredRent, lease_count: alreadyExpiredCount },
                total_rent: 0, lease_count: 0, rollover_risk_level: 'high',
            },
            walt,
        };
    }

    const bucketResults = {};
    bucketNames.forEach(n => {
        bucketResults[n] = {
            rent: buckets[n].rent,
            pct_of_total_rent: totalRent > 0 ? (buckets[n].rent / totalRent * 100) : 0,
            lease_count: buckets[n].lease_count,
        };
    });
    const year1Pct = bucketResults.year_1.pct_of_total_rent;
    const riskLevel = year1Pct >= 25 ? 'high' : year1Pct >= 15 ? 'moderate' : 'low';

    return {
        schedule: {
            buckets: bucketResults,
            already_expired: { rent: alreadyExpiredRent, lease_count: alreadyExpiredCount },
            total_rent: totalRent, lease_count: leaseCount, rollover_risk_level: riskLevel,
        },
        walt,
    };
}

/**
 * Approximate building-level grouping for the property filter dropdown
 * only -- strips a trailing suite/unit/# segment so multiple units at
 * one building collapse into one dropdown entry. Not the same rigor as
 * the backend's own _normalize_building_address (used for real
 * financial matching in the T12/loss-to-lease endpoints); good enough
 * for a client-side convenience filter, not a source of truth.
 */
function normalizeBuildingAddress(addr) {
    if (!addr) return null;
    let s = addr.toLowerCase().trim();
    s = s.replace(/,?\s*(suite|ste|unit|apt|#)\s*[\w-]*\s*$/i, '');
    s = s.replace(/\s+/g, ' ').trim();
    return s || null;
}

function riskColorVar(level) {
    if (level === 'high') return 'var(--severity-high)';
    if (level === 'moderate') return 'var(--severity-medium)';
    return 'var(--lux-accent)';
}

function fmtMoneyShort(value) {
    if (value === null || value === undefined) return '—';
    if (Math.abs(value) >= 1000) return `$${(value / 1000).toFixed(1)}K`;
    return `$${value.toFixed(0)}`;
}

/**
 * Hand-rolled inline-SVG bar chart -- this app has no charting library
 * (a deliberate choice, see the module docstring above), so this is
 * the one shared primitive both charts in this view build on. A fixed
 * 800x260 viewBox (rather than one sized to bars.length) keeps text
 * sizing predictable regardless of how many bars are drawn -- see the
 * comment in the design discussion this was built from for why a
 * per-bar-count viewBox made font sizing swing wildly at different
 * panel widths.
 */
function renderBarChart(containerEl, { bars, valueFormatter, barColor }) {
    const W = 800, H = 260, padBottom = 44, padTop = 30;
    const maxVal = Math.max(1, ...bars.map(b => b.value));
    const n = bars.length;
    const gap = 14;
    const barW = Math.min(84, (W - gap * (n + 1)) / n);
    const totalBarsW = barW * n + gap * (n - 1);
    const startX = (W - totalBarsW) / 2;
    const usableH = H - padBottom - padTop;

    let svg = `<svg viewBox="0 0 ${W} ${H}" class="trend-chart-svg" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Bar chart">`;
    svg += `<line x1="${startX - 4}" y1="${H - padBottom}" x2="${startX + totalBarsW + 4}" y2="${H - padBottom}" class="trend-chart-baseline" />`;
    bars.forEach((b, i) => {
        const x = startX + i * (barW + gap);
        const barH = Math.max(2, (b.value / maxVal) * usableH);
        const y = H - padBottom - barH;
        const fill = b.colorOverride || barColor || 'var(--lux-accent)';
        const valueLabel = valueFormatter ? valueFormatter(b.value) : String(b.value);
        svg += `
            <g>
                <title>${escapeHtml(b.label)}: ${escapeHtml(valueLabel)}</title>
                <rect x="${x}" y="${y}" width="${barW}" height="${barH}" rx="4" fill="${fill}"></rect>
                <text x="${x + barW / 2}" y="${y - 8}" text-anchor="middle" class="trend-chart-value-label">${escapeHtml(valueLabel)}</text>
                <text x="${x + barW / 2}" y="${H - padBottom + 20}" text-anchor="middle" class="trend-chart-axis-label">${escapeHtml(b.label)}</text>
                ${b.sublabel ? `<text x="${x + barW / 2}" y="${H - padBottom + 35}" text-anchor="middle" class="trend-chart-sublabel">${escapeHtml(b.sublabel)}</text>` : ''}
            </g>
        `;
    });
    svg += `</svg>`;
    containerEl.innerHTML = svg;
}

registerView('trends', Trends);

function _initTrendsViewBindings() {
    document.getElementById('trendsPropertyFilter').addEventListener('change', (e) => Trends.onPropertyChange(e.target.value));
}
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _initTrendsViewBindings);
} else {
    _initTrendsViewBindings();
}
