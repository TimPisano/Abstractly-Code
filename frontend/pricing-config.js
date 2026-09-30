/**
 * Single source of truth for pricing-page content: every tier's price,
 * property limit, and feature list lives here, not in pricing.html or
 * pricing.js — change a number or a bullet by editing this file only.
 *
 * Loaded before pricing.js (which reads this object and renders the
 * tier cards + wires the monthly/annual toggle), same
 * script-tag-shares-top-level-scope pattern config.js already uses for
 * API_BASE_URL.
 *
 * Every dollar figure below is a PLACEHOLDER, not market-tested pricing
 * — see the TODO comments on each one and the on-page warning banner in
 * pricing.html that surfaces this to a real visitor too.
 */
const PRICING_CONFIG = {
    // TODO: placeholder discount — confirm the real annual discount
    // before launch (kept as a single percentage so every tier's
    // annual price derives from it consistently).
    annualDiscountPercent: 20,

    tiers: [
        {
            id: 'starter',
            name: 'Starter',
            description: 'For small syndicators doing a few deals a year.',
            monthlyPricePerProperty: 25, // TODO: placeholder price — not market-tested
            propertyLimit: 15,            // TODO: placeholder limit — confirm real cap
            features: [
                'Lease abstraction',
                'Rent roll validation',
                'Deal Mismatch Report — PDF & Excel export',
            ],
            cta: { label: 'Book a Demo', style: 'secondary' },
            featured: false,
        },
        {
            id: 'growth',
            name: 'Growth',
            description: 'For a growing team underwriting deals every week.',
            monthlyPricePerProperty: 20, // TODO: placeholder price — not market-tested
            propertyLimit: 75,            // TODO: placeholder limit — confirm real cap
            includesPrevious: 'starter',  // renders "Everything in Starter, plus:"
            features: [
                'T-12 cross-check',
                'Multiple team members with roles',
                'Priority support',
            ],
            cta: { label: 'Book a Demo', style: 'primary' },
            featured: true,
        },
        {
            id: 'enterprise',
            name: 'Enterprise',
            description: 'For firms who need us embedded in how they underwrite.',
            custom: true, // no price — renders "Contact us" instead
            propertyLimitLabel: 'Custom property count',
            includesPrevious: 'growth', // renders "Everything in Growth, plus:"
            features: [
                'Custom onboarding',
                'Dedicated support',
                'Security review',
            ],
            cta: { label: 'Contact Us', style: 'primary' },
            featured: false,
        },
    ],
};
