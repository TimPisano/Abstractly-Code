/**
 * Single source of truth for pricing-page content: every tier's price,
 * user limit, document limit, and feature list lives here, not in
 * pricing.html or pricing.js — change a number or a bullet by editing
 * this file only.
 *
 * Loaded before pricing.js (which reads this object and renders the
 * tier cards + wires the monthly/annual toggle), same
 * script-tag-shares-top-level-scope pattern config.js already uses for
 * API_BASE_URL.
 *
 * Pricing is flat per team/month (not per property) -- monthlyPrice and
 * annualPriceMonthly are both real dollar figures you gave directly,
 * not derived from a shared discount percentage (they don't reduce to
 * the exact same percentage off: Starter is ~20.0%, Growth ~20.1% --
 * close enough to both read as "~20% off," but storing the real number
 * per tier avoids rounding drift). pricing.js computes the displayed
 * savings percentage from these two numbers rather than from a second,
 * separately-maintained constant.
 */
const PRICING_CONFIG = {
    tiers: [
        {
            id: 'starter',
            name: 'Starter',
            description: 'For small syndicators doing a few deals a year.',
            monthlyPrice: 499,
            annualPriceMonthly: 399, // billed annually, shown as a monthly rate
            maxUsers: 3,
            // TODO: no usage-limits config exists anywhere in this
            // codebase yet -- confirmed via docs/OPERATIONS.md ("Plans
            // / usage limits: There are none... no plan tiers in the
            // schema or code") and docs/AI_PIPELINE_LOG.md. This number
            // is a placeholder, not derived from anything real -- set
            // the actual monthly document cap once a usage-limits
            // system exists to enforce it.
            monthlyDocumentLimit: 50,
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
            monthlyPrice: 1250,
            annualPriceMonthly: 999, // billed annually, shown as a monthly rate
            maxUsers: 10,
            // TODO: same caveat as Starter's monthlyDocumentLimit above
            // -- placeholder, not derived from a real usage-limits config.
            monthlyDocumentLimit: 250,
            includesPrevious: 'starter', // renders "Everything in Starter, plus:"
            features: [
                'T-12 cross-check',
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
            maxUsersLabel: 'Custom user count',
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
