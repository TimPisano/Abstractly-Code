# Plan: Calendly popup on every Book a Demo CTA

## Goal

Every "Book a Demo" button on the marketing site (`index.html`,
`pricing.html`) opens the user's Calendly booking popup in place, instead
of scrolling down to the on-page demo-request form. A visitor can pick a
time without leaving the page. If Calendly is unavailable or blocked, the
button still falls back to the existing form — no CTA ever becomes a
dead click.

## Prior art

**None found** — this is greenfield. Searches run from the primary
checkout:

- `grep -n -i 'calendly\|booking\|calendar' TASKS.md` → nothing
- `git log --all --oneline -i --grep='calendly'` → nothing
- `git log --all --oneline -i --grep='booking'` → nothing
- `git grep -n -i 'calendly' <every local branch> -- frontend backend` → nothing
- `git stash list` → 2 stashes, both unrelated (t12 test WIP, agent-ade76 tenancy WIP)

What *does* already exist, and which this builds on rather than replaces:

- **A working demo-request flow.** `index.html:310-352` is a real form
  (`#demoForm`), handled in `landing.js:54-134`, posting to
  `POST /demo-request` (`backend/app/api.py:3422`), with inline validation,
  a success confirmation (`demoFormConfirm`), and a `demo_requested`
  analytics event. Tests: `backend/tests/test_demo_request.py`.
- **9 CTAs** pointing at `#book-demo`: 5 in `index.html` (announcement bar
  :33, nav :50, hero :76, sample-report note :171, footer :376) and 4 in
  `pricing.html` (:33, :50, :141, :157).
- Nav and hero **already have** Book a Demo buttons, so the task's step 3
  ("add one if missing") is a no-op.
- No "Get started" or "Contact sales" text exists on either page, so that
  part of the task's step 2 is also a no-op.

## Approach

1. Add the Calendly `<link>` + `<script async>` to the `<head>` of
   `frontend/index.html` and `frontend/pricing.html`. There is **no base
   template** (vanilla HTML, no build step), so this is two files.
2. Extend the Content-Security-Policy for all three frontend services in
   `render.yaml` to permit Calendly. Without this the popup is blocked and
   silently never opens — see **Why the CSP change is required** below.
3. Repoint the 9 CTAs to open the popup, keeping `href="#book-demo"`
   intact as a fallback:
   ```html
   <a href="#book-demo"
      onclick="Calendly.initPopupWidget({url: 'https://calendly.com/timmypisano24/abstractly-intro-call'}); return false;">Book a Demo</a>
   ```
   `return false` suppresses the anchor jump when Calendly loaded; if the
   script was blocked or failed, `Calendly` is undefined, the onclick
   throws, and the browser follows the href to the existing form. Graceful
   degradation for free.
4. **Do not touch the form's own submit button** (`index.html:352`,
   `id="demoSubmitBtn"`). Its label is also "Book a Demo", so the task's
   literal wording would catch it, but repointing it would break form
   submission entirely.
5. Headless screenshots at 1440/768/375 on both pages to confirm styling
   is untouched, plus a scripted check that the popup opens.

### Why the CSP change is required

All three frontends currently send (`render.yaml:124-128, 213-217, 316-320`):

```
default-src 'self'; style-src 'self' 'unsafe-inline';
img-src 'self' data:; font-src 'self';
```

There is no `script-src`, so scripts fall back to `default-src 'self'`.
Five separate directives would block Calendly:

| What Calendly needs | Blocked by | Fix |
|---|---|---|
| `widget.js` from `assets.calendly.com` | `default-src 'self'` | add `script-src 'self' https://assets.calendly.com` |
| `widget.css` from `assets.calendly.com` | `style-src` has no external host | add `https://assets.calendly.com` |
| the popup's `calendly.com` iframe | no `frame-src` → `default-src 'self'` | add `frame-src https://calendly.com` |
| host/avatar images | `img-src 'self' data:` | add `https://*.calendly.com` |
| its webfonts | `font-src 'self'` | add `https://assets.calendly.com` |

This is the one place the plan goes beyond "don't change anything else":
it is deployment config, not page content, and the feature does not
function without it.

## Files to change

- `frontend/index.html` — head snippet; 5 CTA onclicks
- `frontend/pricing.html` — head snippet; 4 CTA onclicks
- `render.yaml` — CSP for the 3 frontend services
- `docs/plans/feature-calendly-booking.md` — this file

## Files not to touch

- `frontend/landing.js`, the `#book-demo` form markup, `/demo-request`,
  `test_demo_request.py` — the fallback flow stays exactly as it is.
- `frontend/app/`, `frontend/admin/`, `frontend/owner/` — the customer app
  and staff consoles get no booking popup.
- `frontend/landing.css` — no styling changes (task requirement).
- Any backend code.

## Team isolation & roles

**Not applicable, and verified rather than assumed:** this change adds no
routes and no queries. It touches two static HTML files and `render.yaml`.
The one endpoint in the vicinity, `POST /demo-request`, is unauthenticated
public marketing intake by design and is not modified.

## Feature flag

None. A booking link is not a gated feature, it is reversible in one
commit, and the fallback means the worst case is the previous behaviour.

## Verification

- `python backend/tests/run_all_tests.py` — expect **79/79** (baseline on
  `main` @ `7ac879b`, confirmed by me today). No backend change, so this
  is a regression check only.
- A CSP unit check asserting each of the 5 directives names the Calendly
  host it needs, for all 3 frontend services — mirroring the existing
  `render.yaml`↔`config.js` pairing test from `fix/tester-api-routing`, so
  a future CSP edit can't silently re-break the popup.
- Headless screenshots (`node .claude/tools/screenshots.mjs`) of
  `index.html` and `pricing.html` at **1440 / 768 / 375**, several scroll
  positions, opened and looked at — confirming no visual change.
- A headless click test: click the hero CTA, assert a Calendly iframe is
  inserted and no CSP violation appears in the console.

## Out of scope

- Removing or hiding the existing demo-request form (it stays as the
  fallback; deciding its long-term fate is a separate product call).
- Adding Calendly to the customer app, admin, or owner consoles.
- Replacing the `demo_requested` analytics event with a Calendly
  conversion event.
- Picking between the competing `feature/pricing-page` and
  `feature/landing-positioning` heroes.

## Open questions

1. **Does Calendly replace the form, or sit in front of it?** This plan
   keeps both: popup first, form as fallback. If you want the form gone,
   that is a follow-up (it also orphans `/demo-request` and its test).
2. **Merge-order collision.** `feature/pricing-page` and
   `feature/landing-positioning` both rewrite `index.html` and
   `pricing.html`, and the hero choice is still open. Whichever of the
   three merges last will have to re-apply the onclicks. Cheapest order is
   to land the hero decision first, then this; happy to do it either way.
3. **Confirm the booking URL** is exactly
   `https://calendly.com/timmypisano24/abstractly-intro-call` — I will not
   guess at a different event slug.
