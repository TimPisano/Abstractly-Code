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

function _formatPricePerProperty(monthlyPrice, annual) {
    const price = annual
        ? monthlyPrice * (1 - PRICING_CONFIG.annualDiscountPercent / 100)
        : monthlyPrice;
    // Prices are whole dollars today (see pricing-config.js) but the
    // discount math can produce cents -- show them only when present,
    // rather than always forcing "$20.00".
    const formatted = Number.isInteger(price) ? price : price.toFixed(2);
    return `$${formatted}<span>/property/mo</span>`;
}

function _tierCardHtml(tier, annual) {
    const featuredClass = tier.featured ? ' pricing-card-featured' : '';
    const badge = tier.featured ? '<span class="pricing-badge">Most Popular</span>' : '';

    let priceHtml;
    let annualNoteHtml = '';
    if (tier.custom) {
        priceHtml = '<div class="pricing-tier-price pricing-tier-price-custom">Contact us</div>';
    } else {
        priceHtml = `<div class="pricing-tier-price">${_formatPricePerProperty(tier.monthlyPricePerProperty, annual)}</div>`;
        annualNoteHtml = annual
            ? `<p class="pricing-annual-note">billed annually &mdash; save ${PRICING_CONFIG.annualDiscountPercent}%</p>`
            : '<p class="pricing-annual-note">billed monthly</p>';
    }

    const limitLine = tier.propertyLimitLabel
        ? tier.propertyLimitLabel
        : `Up to ${tier.propertyLimit} properties`;

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
                <li>${limitLine}</li>
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
