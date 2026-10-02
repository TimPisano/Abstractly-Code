# Abstractly beta — tester questionnaire

Ten questions, about 5 minutes. They're built around two things we need
to know: **does Abstractly save you time**, and **does it catch real
errors**. Answer for the deal(s) you actually ran through it.

To use it: paste into a Google Form or Typeform (types are given for
each question), or send as plain text. Questions 3, 5 and 6 matter most;
keep them even if you shorten the form.

---

**1. How many deals did you run through Abstractly, and roughly how big were they?**
*Short answer*, e.g. "2 deals, 96 and 210 units".

**2. For a typical deal, how long does checking the rent roll against the leases take you (or your team) today, by hand?**
*Multiple choice:* Under 2 hours · 2–5 hours · 5–10 hours · 10–20 hours · More than 20 hours · We don't check it unit by unit today

**3. With Abstractly, how long did the same check take, including uploading, fixing anything it got wrong, and reviewing the report?**
*Multiple choice:* Under 30 minutes · 30–60 minutes · 1–2 hours · 2–5 hours · Longer than by hand
*Optional comment:* What took the most time?

**4. Did every lease and the rent roll upload and read correctly?**
*Multiple choice:* Yes, everything · Mostly, I fixed a few fields · Several problems · Couldn't get it to work
*If not:* Which file, and what happened? (file type, scanned or digital, what you saw)

**5. Did the Deal Mismatch Report catch a real discrepancy you did NOT already know about?**
*Multiple choice:* Yes, more than one · Yes, one · No, but it found the ones I already knew · No, and it missed ones I knew about
*If yes:* What was it, and roughly what was it worth per year?

**6. Did it flag anything that turned out NOT to be a real problem, or miss something that was?**
*Long answer:* Please name the unit and what the report said. This is the single most useful thing you can tell us.

**7. When you checked a flagged item against the lease, how useful was the page citation?**
*Scale 1–5:* 1 = I couldn't verify it · 3 = it helped, but I still had to dig · 5 = it took me straight to the right clause

**8. Were the dollar-impact numbers believable enough to put in front of an IC, lender, or LP?**
*Multiple choice:* Yes, as-is · Yes, after I checked them · Not yet, I'd redo them myself · I didn't look at the dollar figures
*Optional:* What would make you trust them more?

**9. If Abstractly were available today, would you use it on your next acquisition?**
*Multiple choice:* Definitely · Probably · Not sure · Probably not · Definitely not
*Optional:* What's the one thing that would change your answer?

**10. Anything else: something confusing, missing, or that you'd pay for if we added it?**
*Long answer*

---

*Thank you. A reply to any single question is still useful.*

## For you (not for testers): how to read the answers

- **Time saved:** compare Q2 with Q3 for each tester. Q3 "Longer than
  by hand" or Q4 "Several problems" means onboarding or extraction is
  failing, not the idea.
- **Real errors caught:** Q5 "Yes" plus a dollar figure is your best
  sales proof point. Ask permission to quote it.
- **Trust:** Q6 and Q7 low means accuracy or citation work comes before
  growth. Q6 entries become regression test cases (`qa-tester` agent).
- **Intent:** Q9 "Definitely" or "Probably" with no blocker in the
  comment marks a pricing-conversation candidate.
