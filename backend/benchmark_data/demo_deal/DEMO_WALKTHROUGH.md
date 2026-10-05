# Maple Ridge Apartments — demo walkthrough (one page)

A sales script for live-demoing the Deal Mismatch Report against the
**fully fictional** Maple Ridge Apartments package (`README.md` in this
folder has the full technical detail; this is the talk track).

## Before the call

1. Reset the demo environment (`/demo/reset` or a fresh deployment) so
   nothing from a prior demo is still in the portfolio.
2. Have ready, in one folder: all 15 files in `leases/`, and
   `rent_roll/maple_ridge_rent_roll_demo_subset_16unit.xlsx`.
3. **Known quirk, say this out loud if it comes up, don't get caught off
   guard by it:** the fixture's dates are anchored to an "as of"
   snapshot of **08/31/2026**. Once real today's date is past that, a
   few more units than the headline "2 expired leases" will show up as
   expired-but-occupied — that's not a bug, it's the fixture's leases
   genuinely running out past their original term. If asked, say
   exactly that: "the other few are from this sample package's dates
   aging past its own snapshot — in your real portfolio that's a stale
   rent roll, which is exactly the kind of thing this catches."

## The walkthrough

**1. Open with the rent roll (30 seconds).** Upload
`maple_ridge_rent_roll_demo_subset_16unit.xlsx`, property address
`4500 Maple Ridge Trail, Dallas, TX 75248`. Let it render — point out
it looks exactly like what they already get from their PMS: header
block, As Of / Generated dates, frozen header, occupancy/loss-to-lease
summary at the bottom. **This is their own file type, not a tool they
have to learn.**

**2. Upload the 15 leases (1 minute).** Drag the whole `leases/` folder
in at once. While they process: "Every one of these is read page by
page — nothing here is OCR guesswork, every field has a citation back
to the exact page and sentence it came from."

**3. Run the Deal Mismatch Report — this is the moment (2 minutes).**
Click through and let the cover page load. **Pause on the headline
dollar figure.** Say the number out loud before they read it:
*"On a 16-unit sample, the signed leases say this rent roll is
overstating annual income by roughly $40,000 to $90,000 a year,
depending on exactly which units you count as expired today — on a
120-unit property, that's the kind of number that changes a purchase
price."*

**4. Walk the findings table (2 minutes).** It's sorted by dollar
impact, biggest first — that's deliberate, so the first thing they see
is the finding that matters most. Click into one or two detail pages:

- A **Rent Mismatch** (e.g. unit G204): "The rent roll says $1,955.
  The signed lease, page 1, says $1,695. That's a $260/month gap the
  seller's own rent roll doesn't catch — $3,120 a year, on one unit."
- An **Expired but Occupied** (e.g. unit C203 or H104): "This lease
  ended months ago. The rent roll still counts this tenant's rent as
  current income. There's no renewal on file — this income may not
  exist anymore."
- The **Unit on Rent Roll, No Lease** finding (F203): "The rent roll
  says this unit is occupied and paying $1,710/month. We have no lease
  for it at all. We're not saying that's wrong — we're saying nobody
  can currently prove it's right, and that's exactly the gap you'd
  otherwise discover during a 30-day diligence window, not before."

**5. Be honest about one gap (30 seconds).** If they ask about
concessions: "Three of these units have a lease concession — one free
month, a renewal discount — that the rent roll doesn't note anywhere.
We've already built the data model for that and it's on our near-term
roadmap; it's not live-detected in the report yet today. We'd rather
tell you that now than have you find out in a POC."

**6. Close on the T-12 (1 minute, optional — use if they're
underwriting-focused).** Show the T-12's Annual Summary panel:
"Separately, the trailing financials show about 6% of billed rent
historically never converts to cash — bad debt and collection loss.
That's invisible if you're underwriting off the rent roll's in-place
rent alone, which is exactly what the findings above already told you
not to trust at face value."

## The one-sentence pitch, if you only get one sentence

*"We read the leases behind the rent roll and tell you, unit by unit
with a dollar figure and a page citation, everywhere the seller's rent
roll and the signed leases disagree — before you close, not after."*
