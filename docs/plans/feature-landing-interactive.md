# feature/landing-interactive

Make the marketing landing page (`frontend/index.html`) more interactive
without changing its design system or the sitewide cursor-follow light.
Frontend only; no backend, no routes, no new dependencies.

## Prior art

- `feature/pricing-page` (merged `c21ced5`) is the shipped design; this builds on it.
- `feature/landing-positioning` is superseded; not used.
- `feature/calendly-booking` (plan only) rewrites Book-a-Demo CTA hrefs in
  `index.html`. Overlap is small: one new "Book a call" link here uses the
  same `#book-demo` anchor, so whichever lands second updates one more href.
- The hero already has a static Maple Ridge card + $42,780 count-up; this
  replaces that card rather than adding a second one.

## Build

1. **Hero scan animation** replaces the static deal card. A compact table of
   10 rows from the fictional Maple Ridge 16-unit sample rent roll
   (`backend/benchmark_data/demo_deal/`), including the 6 findings the old
   card already summed to $42,780 (H104, C203 expired-but-occupied; G204,
   D203, J303, B104 rent above lease). A soft gold scan line steps down row
   by row; flagged rows highlight, a tag replaces the tenant/lease-end cells
   ("Lease expired, still occupied" / "Rent above lease by $N/mo"), the rent
   cell shows that row's annual impact, and the gold monospace ticker counts
   up cumulatively. Labeled "Sample deal" + "fictional demo deal". Replays
   when the card leaves the viewport and comes back.
2. **Marquee** below the hero: slow, continuous, text-only
   "Reads exports from AppFolio · Yardi · RealPage · MRI · Buildium · Excel · CSV".
   (Request named Entrata; nothing in the codebase has been tested on or
   claims Entrata, so it uses the list the FAQ already claims. One-word
   change if the user wants Entrata.)
3. **Exposure calculator** section (after "Built for multifamily"): sliders
   for units (20–1,000) and average monthly rent ($600–$3,500); shows an
   annual income-at-risk range = units × rent × 12 × 0.5%–2%. The assumption
   is stated on the page as an assumption, not a measured statistic.
   "Book a call" button under it → `#book-demo`; if the demo form's units
   field is empty, the click fills it with the slider's unit count.

## Rules

- No logos, testimonials, or anything presented as live data.
- `prefers-reduced-motion`: hero shows its final state (all rows flagged,
  total shown, no scan line); marquee is static and wraps; calculator
  updates instantly.
- Mobile: tenant column hidden under 480px; marquee and calculator readable at 375px.

## Verification

Headless screenshots (`.claude/tools/screenshots.mjs` / `ui-checker`) at
1440/768/375 and several scroll positions, plus mid-animation and
reduced-motion frames, opened and looked at. Full test suite.

## Out of scope

Cap-rate / purchase-price framing in the calculator; Calendly; any change to
pricing.html.
