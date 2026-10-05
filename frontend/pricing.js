/**
 * Pricing page only: renders the tier cards from PRICING_CONFIG
 * (pricing-config.js, loaded just before this file) and wires the
 * Monthly / Annual toggle. Kept separate from landing.js (shared by
 * index.html and pricing.html) since this logic — and the config it
 * reads — has no reason to load on any other page.
 *
 * Pure DOM rendering, no framework, consistent with landing.js.
 */

const CAPITALIZE = (s) => s.charAt(0).toUpperCase() + s.slice(1);

function _formatMonthlyPrice(tier, annual) {
    const price = annual ? tier.annualPriceMonthly : tier.monthlyPrice;
    return `$${price.toLocaleString('en-US')}<span>/mo</span>`;
}

function _savingsPercent(tier) {
    return Math.round((1 - tier.annualPriceMonthly / tier.monthlyPrice) * 100);
}

function _tierCardHtml(tier, annual) {
    const featuredClass = tier.featured ? ' pricing-card-featured' : '';
    const badge = tier.featured ? '<span class="pricing-badge">Most Popular</span>' : '';

    let priceHtml;
    let annualNoteHtml = '';
    if (tier.custom) {
        priceHtml = '<div class="pricing-tier-price pricing-tier-price-custom">Contact us</div>';
    } else {
        priceHtml = `<div class="pricing-tier-price">${_formatMonthlyPrice(tier, annual)}</div>`;
        annualNoteHtml = annual
            ? `<p class="pricing-annual-note">billed annually &mdash; save ${_savingsPercent(tier)}%</p>`
            : '<p class="pricing-annual-note">billed monthly</p>';
    }

    const userLine = tier.maxUsersLabel
        ? tier.maxUsersLabel
        : `Up to ${tier.maxUsers} users`;

    const limitLine = tier.monthlyDocumentLimit
        ? `<li>Up to ${tier.monthlyDocumentLimit} documents/month</li>`
        : '';

    const includesLine = tier.includesPrevious
        ? `<li class="pricing-feature-includes">Everything in ${CAPITALIZE(tier.includesPrevious)}, plus:</li>`
        : '';

    const featureItems = tier.features.map((f) => `<li>${f}</li>`).join('');

    const ctaClass = tier.cta.style === 'primary' ? 'btn-primary' : 'btn-secondary';

    return `
        <div class="pricing-card${featuredClass}">
            ${badge}
            <h2 class="pricing-tier-name">${tier.name}</h2>
            <p class="pricing-tier-desc">${tier.description}</p>
            ${priceHtml}
            ${annualNoteHtml}
            <ul class="pricing-feature-list">
                <li>${userLine}</li>
                ${limitLine}
                ${includesLine}
                ${featureItems}
            </ul>
            <a href="index.html#book-demo" class="${ctaClass} pricing-cta">${tier.cta.label}</a>
        </div>
    `;
}

function renderPricingGrid(annual) {
    const grid = document.getElementById('pricingGrid');
    if (!grid) return;
    grid.innerHTML = PRICING_CONFIG.tiers.map((t) => _tierCardHtml(t, annual)).join('');
}

const toggleWrap = document.getElementById('pricingToggle');
if (toggleWrap) {
    const monthlyBtn = document.getElementById('pricingToggleMonthly');
    const annualBtn = document.getElementById('pricingToggleAnnual');

    const setAnnual = (annual) => {
        monthlyBtn.setAttribute('aria-pressed', String(!annual));
        annualBtn.setAttribute('aria-pressed', String(annual));
        renderPricingGrid(annual);
    };

    monthlyBtn.addEventListener('click', () => setAnnual(false));
    annualBtn.addEventListener('click', () => setAnnual(true));

    setAnnual(false);
} else {
    // Toggle markup missing for some reason -- still show monthly
    // pricing rather than leaving the grid empty.
    renderPricingGrid(false);
}
