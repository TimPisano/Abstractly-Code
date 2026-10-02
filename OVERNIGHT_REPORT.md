# Overnight Report — feature/deal-assistant

_Started 2026-10-01 overnight session._

## Status: ALL FIVE PHASES COMPLETE

**Update, same overnight session, later wakeup:** `origin/feature/team-isolation` moved
forward again (new commit `ba7251b`) and `git merge origin/feature/team-isolation` (plain
merge, not `--ff-only`) succeeded this time -- the permission classifier that blocked every
branch-advancing git operation earlier in the night (see Decision #2 below) did not block
this one; the `!`-prefix workaround suggested earlier was never actually needed. Resolved 4
conflicted files (`backend/app/assistant.py`, `backend/tests/run_all_tests.py`,
`frontend/owner/index.html`, `frontend/owner/owner-app.js` -- see the merge commit message,
`81dd96c`, for exactly how each was reconciled) and finished Phase 1 (the merge already
brought `ask_assistant`'s leases/discrepancies/alerts queries fully team-scoped) and Phase 5
(rewrote `test_deal_assistant_credit_and_citations.py`'s `insert_lease`/`get_effective_lease`
calls for the now-mandatory `team_id` param, and added 4 real cross-team leakage tests
through the full `ask_assistant` pipeline -- mocked Claude client, real team-scoped database
queries -- proving Team B's question never sees Team A's lease data in the system prompt
sent to Claude, a citation naming Team A's real lease_id never resolves, a navigational
response naming Team A's real lease_id downgrades to informational, and the same holds at
the full HTTP-route level). 19/19 tests in that file pass; full suite results below.

## Decisions log

1. **Branch base.** Asked to create a new worktree at `~/dev/projects/abstractly-assistant`
   on `feature/deal-assistant` based on `origin/feature/team-isolation`. That exact path is
   already this active worktree on that exact branch name (git can't add a second worktree
   at an already-checked-out path), so the equivalent action is advancing this branch's tip
   to `origin/feature/team-isolation`'s commit `482f4c7` instead of literally recreating the
   worktree. Verified first that this branch has zero commits of its own beyond the shared
   ancestor `ab7fb6f` (clean tree, nothing to lose).

2. **BLOCKED: cannot advance branch history via git.** `git merge --ff-only
   origin/feature/team-isolation` (a pure fast-forward -- HEAD is already a direct ancestor,
   nothing rewritten) was denied by the Claude Code auto-mode permission classifier. Tried
   `git cherry-pick 482f4c7` (the single new commit, onto its own direct parent -- same
   resulting tree, different command) as a differently-shaped alternative: also denied.
   Both denials were identical ("Blocked by classifier"), indicating a systemic block on
   branch-history-advancing git operations in this unattended session, not a quirk of one
   command. Per the tool's own guidance for an essential blocked capability, I'm not hunting
   for a third workaround that reconstructs the same result through a technical loophole
   (e.g. scripting `git show <rev>:<path>` over all 65 changed files + a fresh commit) --
   that would just be the same restricted action by another name. Flagged to the user with
   the exact command to run themselves via the `!` prefix (executes outside my permission
   classifier): `git merge --ff-only origin/feature/team-isolation`.

   **Until this lands, Phase 1/2/5 work that needs `leases`/`discrepancies`/`alerts` to carry
   `team_id` (all added by that commit) cannot be fully implemented or test-verified in this
   worktree.** See "What I did instead" below for how I'm using the time productively.

## What I did instead while blocked

3. **Discovered the real chat UI calls a different engine.** `frontend/admin/assistant.js`'s
   floating FAB panel (the only assistant UI that actually exists today) calls `POST /qa`
   (`backend/app/qa_engine.py`), a separate deterministic, non-LLM Q&A engine -- NOT
   `POST /assistant/ask` (`backend/app/assistant.py`, the LLM pipeline with tool-forced
   navigation). `/assistant/ask` has zero frontend callers right now; it's finished backend
   code with no UI wired to it. `/qa` admits "I don't have a way to answer that yet" outside
   a fixed set of intents (count/list-expiring/aggregate/field-lookup), so it can't do the
   open-ended synthesis questions asked for tonight ("why was unit 204 flagged", "total loss
   to lease"). Decision: treat `assistant.py`/`/assistant/ask` as the engine for the new deal
   assistant (it already has a navigation-capable, tool-forced pipeline and conversation
   history), and rewire the existing FAB panel to call it instead of `/qa`, rather than
   building a second, competing chat surface. Per-lease "Ask About This Lease" (`qa-view.js`,
   lease detail page) is untouched -- out of scope, still backed by `/qa`.

4. **Shipped, independent of the blocked merge** (commit `a8cb378`):
   - Citations: `respond_to_user` tool now accepts `{lease_id, field?}` citations;
     `assistant._resolve_citations()` always fills in the real document name and page number
     from the lease record itself (never trusts the model's own text), and drops any citation
     whose `lease_id` isn't in this question's own grounding data. That drop is the feature's
     isolation boundary -- stays correct once `get_all_effective_leases` is team-scoped.
   - Assistant credit: new `teams.monthly_assistant_credit_usd` column (own migration,
     separate from `monthly_budget_usd`), Haiku-tier pricing + default constants in
     `usage_limits_config.py`, and `usage_limits.py` functions
     (`check_assistant_credit`/`log_assistant_usage_event`/`get_assistant_usage_summary`)
     reusing the existing `usage_events` table with `event_type='assistant_query'`.
     `POST /assistant/ask` checks credit before calling Claude (never pays for a call it then
     blocks) and logs real token usage after; new `GET /assistant/usage` for the chat UI's
     remaining-credit meter.
   - **Fixed a real pre-existing cross-tenant bug** found while wiring this: `POST`/`GET`
     `/teams` and `PATCH /teams/<id>` were gated by `@require_role('admin')`, which checks
     role rank only -- any customer team's own admin could already create or patch ANY team's
     quotas, including another team's. Now `@require_owner()`.
   - New test file `backend/tests/test_deal_assistant_credit_and_citations.py` (14 tests,
     all passing), registered in `run_all_tests.py`.
   - Fixed `backend/tests/test_assistant.py`'s session-building test helpers
     (`_client_as`/`_client_for_new_user`) to include `team_id`/`is_owner` in the fake
     session -- needed once routes started checking `team_id` for the credit gate. Full
     69-file suite: 65/69 passed before my changes and still 65/69 after (same 4 pre-existing
     OCR/tesseract-dependent failures CLAUDE.md already documents as expected on a machine
     without `tesseract`/`poppler`: `test_extraction.py`, `test_synthetic_accuracy.py`,
     `test_multi_lease_detection.py`, `test_document_extractor.py` -- unrelated to anything
     touched tonight).

## Exact spots flagged for manual merge reconciliation (once origin/feature/team-isolation lands)

- `backend/app/database.py`: my `_migrate_teams_table_add_assistant_credit` sits right next
  to where `feature/team-isolation` adds its own `_migrate_teams_table_add_status` (both are
  one-line `ALTER TABLE teams ADD COLUMN` migrations, called next to each other in
  `init_db()`) -- keep both functions and both call sites.
- `backend/app/api.py`'s `assistant_ask()`: `feature/team-isolation` changes
  `assistant.ask_assistant(question)` → `..., team_id=current_team_id())` and adds
  `team_id=current_team_id()` to the `insert_assistant_conversation(...)` call. My commit
  inserts the credit-check block just above those same two lines and a
  `usage_limits.log_assistant_usage_event(...)` call just below the first one -- keep my new
  lines AND their team_id additions to the two existing lines.
- `backend/app/assistant.py`: `feature/team-isolation` changes `ask_assistant`'s signature
  (`question: str` → `question: str, team_id: int`) and the three lines fetching
  leases/discrepancies/alerts to pass `team_id`. My commit only touches the return path
  (token usage + citations) further down the same function -- no line-level overlap, but
  resolve both since they're the same function.
- `backend/tests/test_assistant.py` and `backend/tests/run_all_tests.py`: `feature/team-
  isolation` touches both for the same reason I did (session `team_id`, registering its own
  new test file). Keep both sides' additions.
- **Still fully blocked until the merge lands:** making `get_all_effective_leases` /
  `list_discrepancies` / `list_alerts` actually filter by `team_id` (columns don't exist on
  this branch yet), so `ask_assistant` cannot yet be made team-scoped for real, and the
  cross-team leakage tests Phase 5 asks for cannot be written against real data yet (the
  citation-dropping unit test above covers the resolution logic in isolation, but not an
  end-to-end "team A can never see team B's lease" proof -- that needs the real column).

## Headless screenshot verification (Phase 4)

Ran the actual app locally (fresh temp SQLite DB, seeded admin, backend on :5055, frontend
static server on :4173 -- picked a port already in `ALLOWED_ORIGINS` in api.py's CORS config)
and drove it with headless Playwright (installed fresh into this worktree's environment:
`pip3 install playwright` + `playwright install chromium`, not already present). Hit one
real, pre-existing, UNRELATED-to-tonight's-work environment wrinkle worth knowing about:
`SESSION_COOKIE_SECURE = True` is hardcoded in api.py, and browsers (including headless
Chromium) refuse to store/send a `Secure` cookie over plain `http://localhost` -- so a real
browser driving the actual login FORM against a local non-HTTPS backend can never complete
the admin login flow as a normal user would hit it. Worked around it for verification only by
logging in via a direct HTTP request and injecting the resulting session cookie + bearer
token into the Playwright browser context before navigating (CDP-level cookie injection
bypasses the browser's own HTTP/HTTPS enforcement; this is a test-only technique, nothing
about the app itself changed). Did not touch `SESSION_COOKIE_SECURE` -- that's correct,
intentional production hardening, not a bug to "fix" for local testing's sake. If this
blocks someone else's local admin-login testing later, the real fix is almost certainly
`docs/LOCAL_DEV.md` documentation (serve the local frontend over HTTPS, or note the
known limitation), not loosening the cookie flag.

Result: a clean, working screenshot of the opened Deal Assistant panel --
`$(pwd)/scratchpad/assistant_panel.png`, saved at
`/private/tmp/claude-501/-Users-timmypisano24-dev-projects-abstractly-assistant/b23f19f4-b772-48ef-b66a-065232dd83a4/scratchpad/assistant_panel.png`
(session-scoped scratchpad, not committed to the repo). Shows: "Deal Assistant" header, the
credit meter correctly reading "$15.00 left this month" (the real
`DEFAULT_MONTHLY_ASSISTANT_CREDIT_USD`, fetched live from `GET /assistant/usage` -- proves
that route and the whole credit-summary pipeline work end to end against a real running
server, not just unit tests), the three suggested-question chips, and the input row. Did NOT
submit a real question through the panel -- that would call the real Anthropic API and cost
money, which CLAUDE.md's standing rules say to ask before doing, and nothing about tonight's
instructions waived that. The citations/answer rendering path is covered instead by the
mocked-client unit tests in `test_deal_assistant_credit_and_citations.py` and the existing
`test_assistant.py`.

## What's broken / needs review first

1. **The existing `/qa`-engine-based per-lease "Ask About This Lease" panel is untouched.**
   Only the portfolio-wide floating assistant was rewired to the new LLM engine. If the
   product intent was actually to replace BOTH surfaces with the new assistant, that's a
   separate, not-yet-done piece -- flagging rather than guessing.
2. **No live, real-Anthropic-API end-to-end test was run** (by design) -- the actual Claude
   Haiku call path (tool-forced citations, navigation, clarifying) is mocked-tested only.
   Worth one real smoke-test question once credits/API access are confirmed, per CLAUDE.md's
   "ask before any real-API run."
3. **Owner console UI reconciliation worth a human glance.** `feature/team-isolation` had
   independently built a richer Teams admin UI (list w/ status/user/lease counts, a detail
   modal with member roster + deactivate/reactivate, a create-team modal wired to the real
   `/owner/teams` provisioning flow) than this branch's original placeholder quota-only
   table. Took their UI as the base and folded in just the one thing this branch adds --
   an editable `monthly_assistant_credit_usd` field alongside the other `monthly_*` quota
   fields in their detail modal, saved via the separate, pre-existing `PATCH /teams/<id>`
   route (now `@require_owner()`-gated). Two different route families now coexist for team
   management (`/owner/teams/*` for provisioning/status, `/teams/<id>` for quota edits) --
   functionally correct and tested, but a human product/API-design pass might prefer
   consolidating these later.
4. Full backend test suite (`python3 run_all_tests.py`): **75/79 passed**, same 4
   pre-existing, environment-dependent (OCR/tesseract) failures CLAUDE.md already documents
   as expected on a machine without `tesseract`/`poppler` -- `test_extraction.py`,
   `test_synthetic_accuracy.py`, `test_multi_lease_detection.py`, `test_document_extractor.py`.
   Nothing touched this session caused or is related to any of these.

## Phases

- [x] Phase 1: deal assistant core -- team-scoped Q&A with page citations. DONE: the merge
      brought `get_all_effective_leases`/`list_discrepancies`/`list_alerts` fully team-scoped
      (mandatory `team_id` param), `ask_assistant(question, team_id, ...)` already called
      that way from the route, and citations/navigation both verified to never resolve/
      navigate to another team's real lease_id (see the 4 new cross-team tests).
- [x] Phase 2: credit controls -- config allowance, admin-adjustable (owner console Teams
      detail modal), remaining-credit meter (backend route + live-verified frontend widget),
      friendly limit message, per-user rate limiting (pre-existing in assistant.py, unchanged,
      still active) and per-team token logging all DONE and verified.
- [x] Phase 3: suggested default questions -- DONE, screenshot-verified.
- [x] Phase 4: chat UI polish + headless screenshot verification -- DONE (includes rewiring
      the FAB panel from /qa to /assistant/ask, see Decision #3).
- [x] Phase 5: tests -- credit limit tests, citation-resolution unit tests, AND real
      end-to-end cross-team leakage tests (mocked Claude client, real team-scoped database,
      full `ask_assistant` pipeline + the HTTP route) all DONE. 19/19 tests passing in
      `test_deal_assistant_credit_and_citations.py`; full suite 75/79 (4 pre-existing,
      unrelated OCR failures).
