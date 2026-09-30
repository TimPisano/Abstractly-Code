# Plan: Marketing site redesign (institutional-fintech direction)

Scope check: this touches `frontend/index.html` (near-total rewrite of
the body sections), `frontend/pricing.html` (re-theme + announcement
bar, same data/logic), `frontend/landing.css` (large addition/rewrite —
new hero/nav/announcement-bar treatment, typography scale, hero-visual
component, pricing-preview component), and `frontend/landing.js` (adds
the count-up animation, `prefers-reduced-motion`-aware). It does **not**
touch `frontend/pricing-config.js` or `frontend/pricing.js` (same
tiers/toggle logic, just restyled), the backend, `/demo-request`, or
`frontend/design-system.css` — that file is shared with the app and
admin screens (loaded there via `app/styles.css`'s `@import` and
directly by `admin.css`), and this task is scoped to the marketing site
only. I'm being explicit about this because it matters: any new
palette/typography tokens go into `landing.css`'s own `:root` block
(only loaded by `index.html`/`pricing.html`), never into
`design-system.css`, so nothing here can visually change the app or
admin screens.

I'll say this plainly up front: this is a **big diff**, not an
incremental tweak — most of `index.html`'s body and most of
`landing.css` gets rewritten. I'm not going to pretend otherwise in the
interest of looking minimal.

I don't have `ornn.com` open and I'm not going to fetch it — going on
the brief itself (oversized headlines, restrained palette, data-forward
visuals, dark hero, institutional fintech) rather than that specific
site, so there's no risk of lifting its actual layout or copy.

---

## Design defaults (stating these so you can veto before I build)

**Palette: keep the existing brand tokens, don't introduce a new
accent.** The current `--lux-black` / `--lux-ivory` / `--lux-accent`
(warm brass, #b68a4e) palette in `design-system.css` was already built
around "one flat accent color, never a gradient... reads as considered
and editorial" (its own code comment). That's already the brief. I'll
reuse it rather than invent a second palette — restyling is about
typography scale, whitespace, and a dark hero treatment, not a color
change.

**Structure: dark hero + dark nav/announcement bar, light body
sections, dark closing CTA + footer.** This is the standard
institutional-fintech pattern (dark bookends, light content in between)
and it's what "lots of whitespace" in your brief points to — an
all-dark page fights that instruction. Nav and the announcement bar
stay dark on **both** pages (not just where there's a hero) for one
consistent header across the site; pricing.html's body stays light
throughout (it has no hero, just a header).

**Hero visual honesty:** your brief asks for a Deal Mismatch Report
card with a headline number that counts up to an "annual income
overstatement," with a few mismatch rows under it. The site already has
a real sample-report section lower down, built from **actual
reconciliation-engine output** on one real test lease (see the existing
code comment on that section) — genuine data, but only one lease with
one dollar-figure discrepancy, not a multi-unit rent roll. Forcing that
into a multi-row "several units, all overstated" hero visual would mean
either (a) fabricating additional dollar rows and presenting them
alongside real engine output as if they were also real, or (b) relabeling
real output as something it isn't. Neither is something I'll do
silently. My plan: label the hero card **"Illustrative example"** (not
"Sample — test data," which the lower section uses for the real thing),
use clearly hypothetical unit numbers and round dollar figures to
build the multi-row scenario your brief describes, and keep the real
engine-output section further down as the actual target of the hero's
"See a sample report ↓" button — so the hero is an honest illustration
of the *kind* of thing the product catches, and the real proof is one
scroll away, not conflated with it. Flagging this clearly since it's a
judgment call on a claim, not a pure style choice.

**"Data isolated per team" trust pillar — needs your confirmation
before I write it as fact.** I checked `database.py` when writing the
pricing FAQ last round: there's no per-tenant/org scoping column or
separate-database architecture in this codebase today (confirmed again
just now — nothing changed). This trust pillar is one of the three
things a visitor would see high on the homepage; if I write "your data
is isolated per team" as a flat claim and it isn't true yet, that's a
false trust signal on the exact kind of page where accuracy matters
most. I'll include it as requested, but marked with the same
`<!-- TODO: confirm/document the actual multi-tenant isolation model
-->` treatment the pricing-page FAQ already uses for this — **unless
you tell me the isolation model is already real** (e.g. a
per-customer deployment/database, which the demo-deployment split in
`DEPLOYMENT.md` suggests might be closer to true than I assumed), in
which case I'll write it as a confirmed fact instead. Tell me which.

---

## 1. Announcement bar (`index.html` + `pricing.html`)

Thin, dark, sits above the nav (not sticky/fixed — a fixed bar adds
scroll-jacking complexity your brief didn't ask for). Copy: **"Now
onboarding beta testers. Book a demo →"**, the "Book a demo" portion
linking to `#book-demo` (`index.html#book-demo` from the pricing page).
No dismiss button — kept simple, matches "thin."

---

## 2. Hero (`index.html` only)

- Dark near-black background reusing the existing `.hero-bg` layer
  (`.hero-glow` + `.hero-grid` — already exactly the "subtle grid /
  gradient background" your brief asks for, just needs the literal
  skyline `<svg>` removed since a city-skyline silhouette reads as
  generic-real-estate, not data-forward fintech).
- Two-column layout at desktop width: left = eyebrow, oversized `<h1>`
  (tight negative letter-spacing, bigger than today's hero type),
  one-line subhead, two buttons (**Book a Demo** primary, **See a
  sample report ↓** secondary, scrolling to the real sample section).
  Right = the new Deal Mismatch Report visual. Stacks to one column on
  mobile, visual under the copy.
- Headline: your exact line, **"Check the rent roll before you
  close."**, as the `<h1>` with the accent treatment the current hero
  already uses for a phrase.
- The Deal Mismatch Report card: "Illustrative example" tag (see above),
  a large count-up headline number (e.g. an annualized total built from
  2–3 clearly hypothetical per-unit rent gaps), those 2–3 mismatch rows
  underneath in a compact list. Pure HTML/CSS + one small JS function
  for the count — `IntersectionObserver`-triggered (counts once, when
  the card scrolls/loads into view), and skipped entirely (final number
  shown immediately) under `prefers-reduced-motion: reduce`, same
  guard `landing.js` already uses for `.reveal`.

---

## 3. Problem section (`index.html`)

This absorbs the site's existing **real** sample-report content (actual
reconciliation-engine output on one real test lease, already fact-checked
and already carrying its own honest "not live data" caveat) — reframed
as "here's a genuine example of what goes wrong," which is also the
scroll target for the hero's "See a sample report" button. This replaces
a separate abstract "the problem is X" section with something more
data-forward and concrete, in keeping with the brief's "data-forward
visuals" note, and avoids writing a second, softer version of a problem
statement that's already made concretely by real output. A short lead-in
sentence or two frames it before the real report card.

---

## 4. Three-step how it works (`index.html`)

Keeps the current three steps (upload leases + rent roll → see every
mismatch with dollar impact → export a report) — restyled to the new
oversized-number-per-step treatment, copy essentially unchanged since
it's already tight and accurate.

---

## 5. Built for multifamily (`index.html`)

Keeps the current three differentiator points (volume not negotiation,
constant turnover, closing-table timing vs. asset management) and folds
in a compact capability strip — a row of short chips/labels (OCR
extraction, Yardi/AppFolio/RealPage/MRI/Buildium import, T12
cross-check, citation-linked validation) instead of the current
three-column "Platform" section's long prose — same real facts,
condensed to fit a leaner institutional-site structure instead of a
sprawling feature-breakdown section.

---

## 6. Three trust pillars (`index.html`)

Exactly the three from your brief:
1. Data isolated per team — see the open question above on wording.
2. Every finding cites the source page and quote in the lease — real,
   already an established claim elsewhere on the site.
3. Documents are not used to train AI — **No**, with `<!-- TODO: verify
   -->`, same treatment as the pricing-page FAQ's identical question.

Compact 3-up grid, not the current longer 6-item Trust & Security list —
the fuller list (SOC 2 status, credential handling, deletion rights)
either gets trimmed into these three or moves into the FAQ rather than
staying as its own dense section, to match a leaner structure.

---

## 7. Pricing preview (`index.html`)

A compact 3-card teaser reusing `PRICING_CONFIG` (loads
`pricing-config.js` on `index.html` too — read-only, no duplicated
numbers to maintain in two places) showing each tier's name and
starting monthly-per-property price, with one "Compare all plans →"
button linking to `pricing.html`. No toggle here — that stays on the
real pricing page; this is a teaser, not a duplicate.

---

## 8. FAQ (`index.html`)

Keeps the current five questions (data handling, accuracy, formats/PMS
support, how this differs from outlier-flagging, does it replace an
analyst) — content already fact-checked in earlier rounds, just
restyled to match. Contract/pilot/cancellation questions stay on
`pricing.html` only, not duplicated here.

---

## 9. Final CTA (`index.html`)

Dark closing band (reuses the existing `.statement` pattern), bigger
oversized-headline treatment, single **Book a Demo** button.

---

## 10. Footer (`index.html` + `pricing.html`)

Restyled for the dark treatment, same content and links as today
(brand, Pricing / Book a Demo links, contact, copyright).

---

## `pricing.html` re-theme

Not restructured — same tiers/toggle/FAQ, same `pricing-config.js` /
`pricing.js` logic untouched. Gets: the new announcement bar, the dark
nav/footer treatment, the oversized-headline typography on its header,
and restyled cards/toggle/FAQ to match the new visual system. Body stays
light (no dark hero — there's no hero here, just a header).

---

## Tests

No backend changes, so no new backend tests. I'll run the existing
`backend/tests/` suite once as the same sanity check as the last two
rounds. The Book a Demo form's markup gets restyled but its fields, IDs,
and `landing.js` submit handler are untouched, so it keeps working
exactly as today — I'll verify it end-to-end in-browser (submit a real
test request against a local backend) before committing, not just
visually.

---

## What I'm explicitly *not* doing
- Not touching `design-system.css`, the backend, `pricing-config.js`'s
  data shape, or `pricing.js`'s render/toggle logic.
- Not introducing a new accent color or a second palette.
- Not using any stock photography, external images, fabricated
  testimonials, or customer logos — every visual is HTML/CSS/inline SVG,
  same as the current site.
- Not claiming the hero's illustrative card is real benchmark data, and
  not claiming per-team data isolation is live unless you confirm it is.

---

Waiting on your go-ahead, plus two calls:
1. Is per-team data isolation actually real today (e.g. a genuinely
   separate deployment/database per customer), or should that trust
   pillar ship with the `TODO: confirm` treatment like the AI-training
   claim?
2. OK with the hero's Deal Mismatch Report card being an explicitly
   labeled "Illustrative example" (hypothetical numbers) rather than
   trying to stretch the one real sample-report lease into a multi-unit
   scenario?
