# Tester emails

Three templates for you to send by hand (nothing here sends anything).

| File | When |
|---|---|
| `01-invite.md` | Day 0, when the tester's account exists |
| `02-day3-checkin.md` | Day 3 after their first login |
| `03-feedback-request.md` | Day 7–10, or after they've run one real deal |

## Fill-ins

Everything you must replace is written as **`[[FILL: …]]`** so it's
impossible to miss and easy to search for. Search each email for
`[[FILL` before sending; none should remain.

Common ones:

- `[[FILL: first name]]`
- `[[FILL: login email]]` / `[[FILL: temporary password]]` — create the
  user first (Team page, as an admin), then paste their login. Send the
  password in a separate message if you can. **Give testers the Analyst
  role**: Viewers can't open the Deal Mismatch Report or upload anything.
  They also need to be on a team, or uploads fail with "Your account
  isn't assigned to a team yet".
- `[[FILL: your calendar link]]`
- `[[FILL: questionnaire link]]` — wherever you host
  `docs/tester-pack/feedback-questionnaire.md` (Google Form, Typeform,
  or just paste the questions into the email).

## Two things to check before sending

1. **Uploaded files can disappear.** The tester deployment runs on
   Render's free tier with no persistent disk, so a deploy, restart, or
   15 minutes of inactivity can wipe uploaded leases. The invite tells
   testers to keep their source files and re-upload if needed. Remove
   that line once the tester API has a disk (TASKS.md → Blocked).
2. **AI extraction depends on API credits.** If the Anthropic account
   isn't funded when testers start, extraction falls back to the
   rule-based engine and will miss more fields. Fund it before sending
   invites, or expect worse first impressions.

The URL in the emails is the tester deployment:
`https://abstractly-tester.onrender.com/app/login.html`.
