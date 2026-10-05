# Plan: pricing page round 2 — flat per-team pricing + marketing refresh

> Written retroactively on 2026-10-04, after the branch was built. The
> reviewer correctly flagged the missing plan as a Definition-of-Done gap.
> This records the scope the branch actually delivers and the two
> corrections made to bring it back inside that scope — it is not a
> pre-approved design doc, and it should be read as documentation of what
> happened.

## Goal

Replace the earlier per-property pricing with **flat per-team pricing**
and refresh the marketing site around it: Starter $499/mo ($399 annual),
Growth $1,250 ($999), Enterprise custom. Visually, give the landing and
pricing pages a fluted-glass WebGL hero, a sticky header, smooth scrolling
(Lenis), and the new logo.

## Prior art

- Builds directly on `feature/pricing-page` **round 1** (merged `a794f0e`),
  which introduced the config-driven pricing page. This branch is round 2
  on top of that, not a parallel version.
- Pricing values live in `frontend/pricing-config.js`, the single source
  round 1 established; this branch edits that file rather than hardcoding
  prices into markup.
- Overlaps `feature/landing-positioning` round 2, which rewrites the same
  marketing files with its own competing fluted-glass hero. **Unresolved
  product decision — only one hero should ship** (TASKS.md "Waiting on
  you" #6). This branch does not attempt to reconcile the two.

## Approach (as built)

1. Flat per-team tiers in `pricing-config.js`, rendered by `pricing.js`
   into `pricing.html`.
2. Fluted-glass WebGL hero + scroll behaviour in `landing.js`, styling in
   `landing.css`; Lenis vendored locally at `frontend/vendor/lenis.min.js`
   with its MIT licence alongside.
3. Sticky header, new logo, updated `favicon.svg`.

## Corrections made on 2026-10-04 (post-review)

The reviewer returned **FIX FIRST** on three items. Two were scope
violations that have now been removed from the branch:

1. **Duplicate of already-merged work (rule 5).** Commit `4e5f213`
   re-implemented the tester→tester-API routing in `frontend/config.js`
   that `fix/tester-api-routing` had already merged as `b6a46e9`. The
   logic was byte-identical; only the comment differed. Resolved by taking
   **main's** `config.js` wholesale when merging main into this branch
   (`72bcef8`), so `config.js` is now identical to main and the branch no
   longer touches it.
2. **Render billing change that the user asked to hold.** The tip commit
   `0a0d7a2` declared persistent disks and flipped `abstractly-api` and
   `abstractly-tester-api` from `plan: free` to `plan: starter`. Reverted
   in `e06db8e`. That change belongs to `chore/render-persistent-disk`
   (`22db0ea`), which is held pending the user's Render plan upgrade; a
   CSS refresh must not carry a billing decision. `render.yaml` and
   `docs/DEPLOYMENT.md` are now byte-identical to main.
3. **This plan file** — the third item.

Net effect: the branch is now **frontend-only**, 9 files, all under
`frontend/`.

## Files to change

- `frontend/index.html`, `frontend/pricing.html`
- `frontend/landing.css`, `frontend/landing.js`, `frontend/pricing.js`
- `frontend/pricing-config.js`
- `frontend/favicon.svg`
- `frontend/vendor/lenis.min.js`, `frontend/vendor/LENIS_LICENSE` (new)

## Files not to touch

- `render.yaml`, `docs/DEPLOYMENT.md` — reverted; see correction 2.
- `frontend/config.js` — reverted to main's; see correction 1.
- All backend code, `frontend/app/`, `frontend/admin/`, `frontend/owner/`.

## Team isolation & roles

**Not applicable, verified not assumed.** The branch adds no routes and no
queries; the diff is nine static frontend assets. Confirmed independently
by the `security-auditor` run on 2026-10-04 (no findings at any severity).

## Feature flag

None. Marketing-page content, reversible in one commit, and the pricing
numbers are the ones the user set.

## Verification

- `python backend/tests/run_all_tests.py` — **79/79** expected; no backend
  change, so this is a pure regression check.
- Headless screenshots of `index.html` and `pricing.html` at
  **1440 / 768 / 375** and several scroll positions, opened and looked at.
  WebGL hero must actually render (the screenshot tool reports WebGL
  availability and console errors).
- `security-auditor`: clean, 2026-10-04.
- `reviewer`: FIX FIRST → all three items addressed above; re-review due.

## Out of scope

- Choosing between this hero and `feature/landing-positioning`'s.
- The Render persistent-disk / billing change (now reverted out).
- Any pricing *enforcement* in the backend — these are marketing numbers;
  quota logic lives in `usage_limits.py` and is untouched.

## Open questions

1. **Which fluted-glass hero ships?** Still open, and it blocks merging
   both this and `feature/landing-positioning`.
2. Enterprise tier is currently live only on this branch — confirm the
   copy before it reaches production.
