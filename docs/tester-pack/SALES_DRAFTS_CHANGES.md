# Sales drafts — what changed (2026-10-01)

The drafts live only on your machine, in
`~/dev/projects/lease-abstraction/drafts/sales/`. `drafts/` is gitignored,
because outreach drafts can name real companies. Originals are kept
beside each file as `*.bak-2026-10-01`. To see the changes:

```bash
diff -u ~/dev/projects/lease-abstraction/drafts/sales/one-pager.md.bak-2026-10-01 ~/dev/projects/lease-abstraction/drafts/sales/one-pager.md
```

## one-pager.md

- **Removed "concessions"** from the extracted terms. Abstractly doesn't
  extract concessions, and the concession check isn't built yet.
- Mismatch list now matches the report's real types. Added **expired
  lease still shown as occupied**.
- Added the **T-12 cross-check** (rent roll vs. actual collections).
- Added a **Pricing** section: flat monthly fee per team, with Starter
  $499 ($399 annual), Growth $1,250 ($999 annual), Enterprise custom.
  User counts, document allowances and features come from
  `frontend/pricing-config.js` on `feature/pricing-page`.
- Toned down "a workflow measured in minutes" to "an upload and a
  focused review". Extraction is seconds to a minute per lease, and
  uploads are limited to 10 per minute, so a 200-unit deal isn't literally minutes.
- Named the PMS systems that export spreadsheets well, consistent with the site FAQ.

## demo-script.md

- **Fixed the severity claim.** A $150/month gap is **Low** severity
  (thresholds are $250 and $1,000/month), not High as the script said.
- **Removed "a report with their name at the top".** The export has no
  custom name or branding option.
- Citations are by **page** (with quote), not "page and line".
- Upload steps now match the real screens: lease upload, then Import
  Rent Roll with the property address.
- **Setup:** use the fictional Maple Ridge deal
  (`backend/benchmark_data/demo_deal/`). The demo site's built-in seed is
  4 commercial-style leases (a coffee shop, "Suite 200"), which is the
  wrong look for a multifamily pitch.
- Added a pricing answer and an optional T-12 beat.

## discovery-questions.md

- Added **Collections (T-12)** questions.
- Added **Budget and fit** questions mapped to the plan limits (users,
  documents per month, flat fee per team).

## Still true and worth knowing before you send any of it

- The **live pricing page on `main` still shows the old placeholder
  prices**. The per-team pricing exists only on `feature/pricing-page`
  (not merged). Don't link prospects to /pricing until it's merged.
- Plan document allowances (50 / 250) **aren't enforced** by the
  product. The backend applies a flat 200 documents/month to every team
  (`usage_limits_config.py`).
