# Plan: Multifamily positioning rewrite + Book a Demo

Scope check: this touches only `frontend/index.html`, `frontend/pricing.html`,
`frontend/landing.css`, `frontend/landing.js`, and adds one new backend
endpoint + supporting DB table + emails + tests. It does **not** touch
`app/auth.py`, `app/deal_mismatch.py`, rent roll parsing, lease extraction,
or any deployment config (`render.yaml`, `DEPLOYMENT.md`, etc.).

---

## Part 1 — Positioning rewrite

### Open question before I touch copy (needs your call)

The "Sample Report" section on `index.html` is real, captured output from
the reconciliation engine (see the code comment above it) — a commercial
retail unit ("2200 Larimer Street, Suite 140", tenant "Ridgeline Coffee
Roasters LLC"). I have no real multifamily engine output to swap in, and I'm
not going to fabricate a fake "real" sample.

Options:
1. **Keep this exact sample, add one caveat line** noting it's shown on a
   commercial unit but the reconciliation works the same way on a
   multifamily rent-roll line (unit/tenant/rent/dates). Fastest, least risk.
2. **Genericize the labels only** (e.g. swap "Suite 140" → "Unit 140",
   "Ridgeline Coffee Roasters LLC" → a placeholder residential-sounding
   name) while keeping the real dollar/date/discrepancy values, and add a
   note that it's illustrative formatting on real output values.
3. Leave the section out of the multifamily rewrite entirely for now (mark
   `TODO: replace with real multifamily sample once available`).

I'd default to **option 1** (least invasive, no risk of the copy looking
like fabricated data) unless you'd rather I do 2 or 3.

### Nav
- "Request Access" → **"Book a Demo"**, linking to a new `#book-demo`
  section (replaces the `#request-access` anchor on the hero).
- Everything else (How It Works, Sample Report, Platform, Trust & Security,
  FAQ, Pricing, Client Login) stays.
- `pricing.html`'s nav and all five `index.html#request-access` CTA links on
  that page get the same anchor/label swap.

### Hero
- Eyebrow: something like **"Built for multifamily syndicators"**.
- Headline: **"Catch rent roll errors before they cost you at closing."**
  (your exact line, as `<h1>`, with a styled accent word/phrase, matching
  the current two-line treatment).
- Subhead: rewritten around your framing — mid-size multifamily
  syndicators, rent roll checked against the actual leases before a deal
  closes, not "acquisitions analysts and asset managers" generically.
- CTA: the inline waitlist email-capture form is **replaced** with a single
  `Book a Demo` button that scrolls to the new `#book-demo` section. The
  existing `/waitlist` signup flow (backend route, admin approve/deny,
  `/app` access gate) is left completely alone — it just no longer has a
  visible entry point on the landing page. Nothing in `app/auth.py` or
  `access-gate.js` changes.
- "See a sample discrepancy report ↓" link stays.

### How It Works → your 3-step flow
1. Upload your leases and rent roll
2. See every mismatch, with dollar impact
3. Export a report for your lender or LP

(Rewritten from the current "Upload / We read & match / Discrepancy report"
copy to your wording, keeping the same 3-card layout.)

### New section: "Why multifamily is different"
A short section (3-4 short points or a 2-3 sentence block) making the case
your prompt asked for — e.g., hundreds of small, similar leases instead of
a handful of long, heavily negotiated commercial leases; rent roll accuracy
matters unit-by-unit at scale in a way a commercial tenant-by-tenant tool
isn't built for; renewals/turnover volume is constant, not occasional.
Placed after "How It Works", before or merged into "What It Catches".

### Sections that carry over with copy edits, not structural changes
- **What It Catches** — reframe examples toward rent-roll/unit language
  (already mostly generic: "rent that doesn't match," "stale expiration,"
  works for multifamily as-is with light wording tweaks).
- **Platform (Standardization / Validation / Analysis)** — mostly reusable.
  Two items are commercial-specific and I'd trim or reframe:
  - "WALT (weighted average lease term)" and "tenant concentration /
    Herfindahl-Hirschman" are office/retail concepts (a handful of anchor
    tenants) that don't really apply to a 200-unit apartment building.
    I'd either cut these two bullets or reframe them as roadmap items,
    rather than claim them as live multifamily features.
  - Everything else (OCR extraction, Excel/PDF import, Yardi/AppFolio/
    RealPage/MRI/Buildium import, citation-linked validation, T12
    cross-check, loss-to-lease) genuinely applies to multifamily and stays.
- **Trust & Security**, **FAQ** — copy edits only (swap "acquisitions
  analyst" language for "syndicator" framing), no structural change. FAQ
  gets no new questions unless you want one about multifamily specifically.
- **Dark statement section** — CTA becomes "Book a Demo" → `#book-demo`.

### New section: Book a Demo (`#book-demo`)
Replaces the removed hero form as the page's actual conversion point. Sits
near the bottom, above the footer (after FAQ / statement section). Contains
the form described in Part 2.

### Footer
- Contact email is already present (`timmypisano24@gmail.com`, plain text
  next to the phone number). I'll make it a proper `mailto:` link since
  right now it's unlinked plain text — that's the one footer change needed.
  Let me know if you want a different/dedicated address instead of your
  Gmail.

### `<title>` / meta description / OG tags
Rewritten to the new positioning (multifamily syndicators, rent roll vs.
lease reconciliation before closing) — same fields, new copy.

---

## Part 2 — Book a Demo form + backend endpoint

### Frontend (`index.html` + `landing.css` + `landing.js`)
Form fields: Name, Work Email, Company, Number of Units in Portfolio,
Message (optional) — plus a hidden honeypot field (visually hidden via
absolute positioning off-screen + `tabindex="-1"` + `autocomplete="off"`,
not `display:none`, so it still catches simple bots but isn't a screen-
reader trap).

- Client-side validation: required-field checks, email shape check, units
  must be a positive whole number, message length capped — mirroring the
  existing waitlist form's inline error pattern (`.waitlist-error` /
  `.waitlist-confirm` become a `.demo-form-error` / `.demo-form-confirm`
  pair, same visual language).
- On submit: `POST {API_BASE_URL}/demo-request` with JSON body, same
  try/catch-network-error handling as the existing waitlist submit
  handler, swap in the success state (clear confirmation message, form
  hidden) on 2xx.
- Styling: new `.demo-form` block in `landing.css`, built from the same
  design tokens (`--lux-accent`, `--radius-sm`, etc.) as the rest of the
  page — a card-style form, not a repaint of the waitlist single-input bar.

### Backend

**CSRF**: already handled. `app/security.py`'s `install_security()` runs a
global `before_request` Origin/Referer check on every state-changing
request except `/health` — the new `POST /demo-request` route is covered
automatically, no extra code needed.

**New DB table** (`app/database.py`, added to `init_db()` next to the
`waitlist_signups`/`pageviews` tables, and to `reset_db()`'s drop list):

```sql
CREATE TABLE IF NOT EXISTS demo_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    work_email TEXT NOT NULL,
    company TEXT NOT NULL,
    units INTEGER NOT NULL,
    message TEXT,
    created_at TEXT NOT NULL
)
```
Plus `insert_demo_request(...)` and `get_all_demo_requests()` (the latter
only so the data isn't write-only from day one — no new admin UI is in
scope, this is just a plain read function).

**New route** (`app/api.py`, placed near the waitlist section, reusing its
established shape):

```
POST /demo-request
Body: {name, work_email, company, units, message (optional), website (honeypot, must be empty)}
```
- Per-IP rate limit via the existing `security.RateLimiter` class (same one
  `/analytics/pageview` already uses) — e.g. 8 requests/minute/IP.
- Honeypot check first: if `website` is non-empty, return the *same* 201
  success response without touching the DB or sending any email — never
  signal to a bot that it was caught.
- Server-side validation: name/company non-empty and length-capped,
  work_email matches the existing `_EMAIL_RE`, units is a positive integer
  in a sane range (1–1,000,000), message length-capped and optional.
  Validation failures → 400 with a specific, safe message (e.g. "Please
  enter a valid email address") — never a stack trace or internal detail.
- On success: insert the row, then two best-effort emails via
  `email_service.py` (reusing `_send_email_best_effort`, same as waitlist):
  - `send_demo_request_notification(admin_email, request_data)` → to
    `ADMIN_EMAIL`, with the submitted details.
  - `send_demo_request_confirmation(work_email, name)` → short "we got
    your request, we'll follow up" email to the requester, same visual
    template as the existing confirmation emails in `email_service.py`.
  - Both follow the existing fail-open contract: an email failure never
    fails the request. The submission is already committed before either
    send is attempted.
- Response: `{"message": "..."}` on success (generic, no internal IDs
  leaked), matching the waitlist route's shape. All error paths return
  only generic, safe messages — nothing from an exception ever reaches the
  client (the existing global `@app.errorhandler(Exception)` in `api.py`
  already backstops anything unanticipated).

### Tests (new file: `backend/tests/test_demo_request.py`)
Modeled directly on `backend/tests/test_waitlist_email.py`'s pattern
(temp SQLite DB per test, mocked `smtplib.SMTP_SSL`, Flask test client):
- Valid submission succeeds, persists, and sends both emails.
- Missing/invalid required fields (name, work_email, company, units) each
  return 400 with a safe message and do **not** persist a row or send mail.
- Invalid email format rejected.
- Non-numeric / negative / zero / absurdly large `units` rejected.
- Honeypot field populated → 200 success response returned, but **no** row
  is inserted and **no** email is sent (spam case).
- Message field is optional — omitting it still succeeds.
- Overlong message/name/company values are rejected or truncated per the
  validation rule chosen above (test whichever behavior is implemented).
- Submission still succeeds (still persists) when SMTP raises or
  credentials are unset — mirrors the waitlist "email must never block
  signup" guarantee.
- Rate limit: N+1th request from the same IP within the window gets 429.
- CSRF: a state-changing request with a disallowed `Origin` header is
  rejected 403 by the existing global middleware (one test confirming the
  new route inherits this, not re-implementing it).

---

## What I'm explicitly *not* doing
- Not touching `app/auth.py`, `app/deal_mismatch.py`, rent roll
  parsing/extraction, or any file under deployment config.
- Not deleting or modifying the existing `/waitlist` backend flow, admin
  dashboard waitlist review, or `/app` access gate — only removing its
  visible entry point from the marketing page.
- Not adding an admin UI for reviewing demo requests — just the DB table
  and a plain read function, per your endpoint-only scope.
- Not touching `frontend/app/`, `frontend/admin/`, or `frontend/owner/`.

---

Waiting on your go-ahead, plus your call on the Sample Report question
above (defaulting to option 1 if you don't have a preference).
