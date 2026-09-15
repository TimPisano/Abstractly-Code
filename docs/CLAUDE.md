# Lease Abstraction Tool

## What this does
Ingests a commercial lease PDF and extracts structured data: tenant
name, rent amount, rent escalation schedule, lease start/end dates,
renewal options, CAM charges, security deposit, exclusivity clauses,
and any unusual/non-standard terms.

## Tech stack
- Python backend (PDF parsing + extraction)
- Simple web UI to upload a lease and view/edit extracted results
- Output as both a clean UI view and exportable JSON/CSV

## Quality bar
- Every extracted field must show its source (page number/quote) so
  a human can verify it, not just trust it blindly
- Ambiguous or missing fields should be flagged clearly as
  "not found" rather than guessed at silently
- Include a basic test suite as a foundation for future accuracy work

## Workflow rules
- Commit after each working milestone with a clear message
- Log architecture decisions in DECISIONS.md
- Write a PROGRESS.md summarizing what's built and what's next
- This project will be built incrementally over time — leave clean,
  well-documented stopping points
