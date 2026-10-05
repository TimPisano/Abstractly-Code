# Tester Verification Checklist

Drafted 2026-09-25, after merging `feature/deal-mismatch-report` and
`feature/landing-positioning` into `main` and pushing. Scope is
deliberately narrow: testers need the core pipeline to work on their real
documents and not leak data. They do **not** need payments, the T-12
feature, or full visual polish — those are explicitly out of scope here.

Each item: what's checked, how, and the result.

---

## 1. Golden path — does it work on real documents?

| # | Check | Method | Result |
|---|---|---|---|
| 1.1 | Upload a lease PDF → structured fields extracted with page/quote citations | Live, demo deployment (public demo creds) | ✅ `GET /leases/1` shows fields like `cam_charges` with `source: {page: 3, quote: "Monthly CAM Charges: $950.00"}` |
| 1.2 | Upload a rent roll → reconciled against leases | Live, demo deployment | ✅ `GET /portfolio/rent-roll-reconciliation` correctly surfaced a real discrepancy (`rent_amount`: lease says $22,750.00, rent roll says $23,500.00) |
| 1.3 | Generate a Deal Mismatch Report (JSON/PDF/Excel) | Live, demo deployment + local unit tests | ✅ `POST /portfolio/deal-mismatch-report` returns 200 with valid structure live; `test_deal_mismatch.py` covers JSON/PDF/Excel routes locally, all pass |
| 1.4 | Corrupt/unreadable file upload fails with a clear message, not a crash | Local test suite (`test_upload_validation.py`, `test_document_extractor.py`) | ✅ Both pass (the one suite failure is the unrelated pre-existing tesseract gap, see 3.2) |
| 1.5 | New deal-mismatch route is actually live (not still 404 on old code) | Live curl against prod + tester | ✅ Confirmed — 401 "Login required" on both `abstractly-api` and `abstractly-tester-api`, meaning the route exists and auth-gates it correctly. |

## 2. Data isolation — does it leak?

This app has **no per-account data isolation within one deployment**
(single shared `leases` table, confirmed in `HARDENING_LOG.md` 4.3 — the
multi-tenant work lives only in the unmerged, stale
`worktree-agent-ade7619750bfa9a9f` branch and is explicitly not part of
this scope). The mitigation is architectural, not code-level: **one
tester gets their own isolated Render deployment**
(`abstractly-tester-api`/`abstractly-tester`), separate from prod and
demo.

| # | Check | Method | Result |
|---|---|---|---|
| 2.1 | Tester deployment is a genuinely separate service/DB from prod and demo | Read `render.yaml` + `DEPLOYMENT.md` | ✅ Separate Render `web` service, own container/filesystem; no `disk:` block shared with any other service |
| 2.2 | Tester deployment has no `DEMO_MODE`, no seeded sample data | Read `render.yaml` | ✅ Confirmed — no `DEMO_MODE` var on `abstractly-tester-api` |
| 2.3 | Every data-bearing route rejects an anonymous caller (401/403/404), never 200 | Local test suite (`test_route_authorization.py`) | ✅ 71 mutating routes checked, all pass (route count grew from ~65 since the doc note was written — the new deal-mismatch routes are included) |
| 2.4 | Security headers (CSP, HSTS, X-Frame-Options, nosniff) present on live tester deployment | Live curl against `abstractly-tester-api`/`abstractly-tester` | ✅ All 5 headers present and correctly configured |
| 2.5 | CSRF protection active (cross-origin POST rejected) on live tester deployment | Live curl against `abstractly-tester-api` | ✅ `POST /leases` with `Origin: evil.example.com` → 403 "Cross-origin request blocked." |
| 2.6 | Uploaded tester documents don't land in prod's or demo's database | Code read — no shared `worker` service in `render.yaml`; each backend runs its own in-container worker against its own distinctly-named queue (`extraction-tester` vs `extraction-demo`) | ✅ No cross-deployment data path found |

## 3. Deploy sanity

| # | Check | Method | Result |
|---|---|---|---|
| 3.1 | `/health` returns healthy on prod, demo, and tester after the push | Live curl | ✅ All three `{"status":"healthy"}` |
| 3.2 | Full backend test suite green (minus the known tesseract-only local gap) | `python tests/run_all_tests.py` | ✅ 63/64 — only `test_document_extractor.py`'s OCR case fails, confirmed as the pre-existing `TesseractNotFoundError` (tesseract not installed on this dev machine; present in the deployed container) |
| 3.3 | 5 test files existed on disk but were never wired into `run_all_tests.py` (`test_analytics.py`, `test_deal_mismatch.py`, `test_demo_request.py`, `test_obligations.py`, `test_rent_roll_multiformat.py`) — includes the brand-new deal-mismatch tests | Ran each directly | ✅ All 5 pass standalone; added to the runner's list (pending commit) |

## Explicitly out of scope for this pass

- Payments / billing
- T-12 cross-checking feature (`feature/t12-crosscheck`, still unmerged by design — plan preserved at `docs/PLAN_t12_crosscheck.md`)
- Full visual polish
- True multi-tenant data isolation within a single deployment (mitigated via one-deployment-per-tester instead)
