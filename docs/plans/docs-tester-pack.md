# Plan: docs/tester-pack

Overnight-mode task (user said: work autonomously, no questions; never
merge/push main; never open a browser; commit + push after every phase;
finish with OVERNIGHT_REPORT.md). Plan written for the record, not for
an approval stop.

## Goal

Everything a beta tester needs: in-app Getting Started + help center,
tester emails, a feedback questionnaire, and sales drafts that match
what the product actually does today.

## Prior art

- `frontend/app/` has no help/guide view (grep "help" across app files).
- Marketing `frontend/index.html` has an FAQ section — stay consistent.
- `docs/TESTER_VERIFICATION_CHECKLIST.md` is an internal QA checklist,
  not tester-facing.
- `drafts/sales/` (local, gitignored, primary checkout): `one-pager.md`,
  `demo-script.md`, `discovery-questions.md`.
- Pricing: per-team plans live only on `feature/pricing-page`
  (Starter $499 / $399 annual, Growth $1,250 / $999, Enterprise custom);
  `main` still shows old placeholder prices. Sales drafts use the per-team
  pricing from CLAUDE.md and flag that the site doesn't show it yet.

## Approach

1. **Phase 1** — new app view `help` (`frontend/app/help-view.js` +
   `help-content.js`), sidebar entry "Help & Guides", searchable article
   list + reader. First article: Getting Started (upload leases + rent
   roll, read the Deal Mismatch Report, export, discrepancy types).
2. **Phase 2** — articles for every feature, plus upload troubleshooting,
   in the same content file. Facts sourced from the code (routes, error
   messages, limits), not guesses.
3. **Phase 3** — `docs/tester-pack/emails/` invite, day-3 check-in,
   feedback request.
4. **Phase 4** — `docs/tester-pack/feedback-questionnaire.md` (10 Qs).
5. **Phase 5** — update `drafts/sales/*` in place (local only; backups
   kept as `*.bak-2026-10-01`), summary of changes in the report.
6. `OVERNIGHT_REPORT.md` at repo root of the branch.

## Files to change

`frontend/app/index.html` (nav button + view section),
`frontend/app/access-gate.js` (script list), new `help-view.js`,
`help-content.js`, CSS appended to `styles.css`; new `docs/tester-pack/*`.

## Not touching

Backend, routes, DB, marketing site, pricing page, other branches,
the primary checkout (except `drafts/sales/` and a TASKS.md row).

## Team isolation & roles

No routes or queries touched. Help content is static and the same for
every user. n/a.

## Verification

- `python backend/tests/run_all_tests.py` (no backend change; must stay 77/77).
- `node --check` on new JS.
- Headless screenshots of the Help view at 1440/768/375, several scroll
  positions, against a local backend with a throwaway DB — every PNG opened.
- Facts in articles cross-checked against code (file:line in report).

## Out of scope

Contextual "?" tooltips across every view, video walkthroughs, a backend
help API, translating the marketing FAQ.
