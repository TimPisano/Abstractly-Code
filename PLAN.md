# Plan: Pricing page rewrite (Starter / Growth / Enterprise)

Scope check: this touches only `frontend/pricing.html`, a new
`frontend/pricing-config.js` (data) + a new `frontend/pricing.js`
(renderer), `frontend/landing.css` (styles that serve the pricing page,
the nav, and the footer only), and the `<nav>` / `<footer>` blocks of
`frontend/index.html`. It does **not** touch the backend, `frontend/app/`,
`frontend/admin/`, `frontend/owner/`, or any other section of
`index.html` (hero, how-it-works, platform, trust, FAQ, sample report,
etc.).

No backend change is needed — confirmed there's no Stripe/billing
integration anywhere in this codebase (`frontend/owner/index.html` says so
directly: "Manual entries — no billing integration is connected yet.").
Every CTA is a link to `index.html#book-demo`, exactly like the existing
pricing page already does — no checkout, no plan-selection state to
persist anywhere.

---

## 1. Config file — `frontend/pricing-config.js`

One plain global `const PRICING_CONFIG` object (same style as
`config.js`'s `API_BASE_URL` — no build step, no modules, loaded as a
`<script>` tag). Holds every price, property limit, and feature list, so
none of that data lives in HTML or in the renderer script:

```js
const PRICING_CONFIG = {
  // TODO: confirm the real annual discount before launch.
  annualDiscountPercent: 20,
  tiers: [
    {
      id: 'starter',
      name: 'Starter',
      description: 'For small syndicators doing a few deals a year.',
      monthlyPricePerProperty: 25, // TODO: placeholder — set real price
      propertyLimit: 15,           // TODO: placeholder — set real limit
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
      monthlyPricePerProperty: 20, // TODO: placeholder — set real price
      propertyLimit: 75,           // TODO: placeholder — set real limit
      includesPrevious: 'starter', // renders "Everything in Starter, plus:"
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
      custom: true,               // renders "Contact us" instead of a price
      propertyLimitLabel: 'Custom property count',
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
```

`propertyLimit` (a number) renders as "Up to N properties" as the first
feature-list line; `propertyLimitLabel` (a string) is used verbatim
instead, for Enterprise's "Custom property count." Every dollar figure
gets a `<!-- TODO: placeholder price, not market-tested -->` treatment —
see the existing `.pricing-placeholder-note` banner below, which stays
and gets its copy adjusted to name Starter/Growth explicitly (Enterprise
has no number to caveat).

**Open question:** should Enterprise's feature list say "Everything in
Growth, plus:" the way Growth says "Everything in Starter, plus:"? Your
prompt only listed 4 items for Enterprise (custom property count, custom
onboarding, dedicated support, security review) without that "plus"
framing, unlike Growth's explicit "everything in Starter plus." I'd
default to **adding "Everything in Growth, plus:"** since it'd be a
strange regression for the top tier to not include T-12 cross-check /
multi-seat / priority support — but I want your call before I write copy
that expands scope beyond what you listed.

---

## 2. Renderer — `frontend/pricing.js` (new, pricing.html only)

Reads `PRICING_CONFIG` and:
- Renders the three tier cards into a `<div id="pricingGrid">` container
  (markup generated from config, not hand-duplicated per tier — this is
  what makes "change the config, not the page" actually true).
- Wires a **Monthly / Annual** segmented toggle (two buttons,
  `aria-pressed` state, same interaction pattern as a tab control — no
  existing toggle/switch component in this codebase to match, so this
  introduces one new small pattern using existing tokens: `--lux-accent`,
  `--radius-full`, `--border-color`, `--shadow-sm`).
  - Monthly: `monthlyPricePerProperty` shown as `$X/property/mo`.
  - Annual: `monthlyPricePerProperty * (1 - annualDiscountPercent/100)`,
    shown the same way with a "billed annually" note — mirrors the old
    page's existing "or $X/yr — N months free" pattern, adapted to
    per-property pricing.
  - Enterprise ignores the toggle (always "Contact us").
- Pure DOM rendering, no framework — consistent with `landing.js`.

---

## 3. `frontend/pricing.html` rewrite

- Swap the 4-tier Starter/Team/Business/Concierge grid (flat monthly-only
  pricing, priced per document-volume) for the new 3-tier
  Starter/Growth/Enterprise grid, priced per property, rendered by
  `pricing.js` from config into `#pricingGrid` (replaces the current
  hand-written `.pricing-grid` markup).
- Add the Monthly/Annual toggle above the grid.
- Keep `.pricing-card`, `.pricing-tier-name`, `.pricing-feature-list`,
  etc. — same visual language, just populated dynamically. Grid CSS goes
  from `repeat(4, 1fr)` to `repeat(3, 1fr)` (and the `860px` breakpoint's
  2-column override no longer applies at 3 tiers — becomes 1 column
  below `860px`, matching the existing `560px` single-column rule already
  in place for smaller screens).
- Every CTA button links to `index.html#book-demo` (existing pattern —
  the demo form already lives there, not duplicated here).
- New **FAQ section** below the pricing grid, reusing the exact
  `.faq` / `.faq-list` / `.faq-item` (`<details>`/`<summary>`) component
  already on `index.html` — no new CSS needed. Six questions:

  1. **How do contracts work?** — factual, derivable from your prompt:
     annual or monthly, per-property pricing, toggle to compare. Safe to
     write directly.
  2. **Is there a pilot?** — not stated in your prompt and not a policy I
     can find anywhere in this codebase (no existing pilot/trial
     mentions). I'll write a non-committal answer ("ask during your demo
     about starting with a subset of your portfolio") and mark it
     `<!-- TODO: confirm real pilot policy/terms -->` rather than invent
     specific terms.
  3. **How accurate is the extraction?** — reuses (lightly adapted) the
     existing, already-honest answer from `index.html`'s FAQ: no
     fabricated accuracy percentage, every value shows confidence + a
     source citation.
  4. **How is customer data secured and isolated?** — reuses real facts
     from `index.html`'s Trust & Security section (never shared/resold,
     deletable anytime, no secrets in source control, access by request
     only). On "isolated" specifically: I checked `database.py` and
     there's no per-customer/tenant scoping column or separate-database
     architecture in this codebase today — so I will **not** claim a
     specific isolation architecture (e.g. "separate database per
     customer") I can't back up. I'll phrase this narrowly around what's
     actually true (your data is under your account, never shared) and
     add `<!-- TODO: confirm/document the actual multi-tenant isolation
     model before making a stronger isolation claim -->`.
  5. **Do you use our documents to train AI?** — **No**, per your
     instruction, with `<!-- TODO: verify -->` as you specified.
  6. **How do I cancel?** — not stated in your prompt. Same treatment as
     the pilot question: a generic, honest answer ("contact us, we'll
     process it at the end of your current billing period") marked
     `<!-- TODO: confirm exact cancellation process/notice period -->`
     rather than invented specifics.

---

## 4. Nav + footer link

- **Nav**: already links to `pricing.html` on both `index.html` and the
  current `pricing.html` (`<a href="pricing.html">Pricing</a>` /
  `class="nav-current"`) — no change needed here.
- **Footer**: currently has no links at all (just the brand mark and
  contact line) — there's an unused `.footer-links` CSS class already
  defined in `landing.css` (flex row, hover state) with no matching HTML
  anywhere. I'll add a `<div class="footer-links">` with **Pricing** and
  **Book a Demo** links into the `footer-top` row of both `index.html`
  and `pricing.html`, using that existing-but-dormant style rather than
  inventing new footer CSS.

---

## 5. Tests

No backend code changes, so no new backend tests are needed. I'll run
the existing backend suite (`backend/tests/`) once as a sanity check that
nothing was inadvertently touched, same as the last change on this repo.
There's no frontend test runner in this project (no `package.json`
anywhere) — verification here is a manual pass in-browser (toggle
behavior, all CTA links, FAQ expand/collapse, responsive breakpoints) via
the `run` skill before commit, not an automated frontend test suite.

---

## What I'm explicitly *not* doing
- Not touching the backend, `/demo-request` endpoint, or any DB schema —
  pricing is fully static/config-driven, no checkout or plan-selection
  state to persist.
- Not touching `frontend/app/`, `frontend/admin/`, `frontend/owner/`.
- Not touching any section of `index.html` besides `<nav>` and
  `<footer>`.
- Not inventing specific pilot terms, cancellation notice periods, or a
  multi-tenant isolation architecture that doesn't exist in this
  codebase yet — those get honest, general answers plus a `TODO` instead.

---

Waiting on your go-ahead, plus your call on the Enterprise "Everything in
Growth, plus:" framing question above (defaulting to **yes, include it**
if you don't have a preference).
