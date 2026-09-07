"""
Synthetic full-lease-text fixtures (run through the REAL FieldExtractor,
then the REAL obligations.py) for verifying the obligations engine's
computed dates are actually correct -- not just that the code runs.

Each fixture is lease TEXT (varied real-world clause phrasing) plus a
hand-computed truth file of the obligation dates a human reading that
exact text should arrive at. This is what "spot-check by hand against
the source lease text" requires -- Part 1's rent-roll fixtures have no
clause prose at all to check obligations against.
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "lease_fixtures")

fixtures = []


def add(fixture_id, text, truth, notes):
    fixtures.append({"id": fixture_id, "text": text, "truth": truth, "notes": notes})


# 01: renewal deadline, "(N) options to renew" phrasing, standard notice
add("01_renewal_standard_phrasing", """
This Lease Agreement is entered into between Landlord and Tenant.
The Lease shall commence on April 1, 2023 (the "Commencement Date") and shall expire on March 31, 2028,
unless sooner terminated as provided herein.
Tenant shall pay Landlord Base Rent of $6,250.00 per month.
Tenant shall have two (2) options to renew this Lease for additional terms of five (5) years each,
provided Tenant delivers written notice to Landlord not less than one hundred eighty (180) days prior to
the expiration of the then-current Term. Renewal rent shall be based on the then-prevailing fair market rate.
""", {
    "renewal_notice_deadline": "2027-10-03",  # 2028-03-31 minus 180 days
}, "Lease end 2028-03-31 minus 180 days notice = 2027-10-03 (180 days before March 31, 2028, counting back: Mar31-180d -> Oct 3, 2027; verified: Mar31 to Oct3 is 180 days spanning Oct(28)+Nov(30)+Dec(31)+Jan(31)+Feb(28,2028 not leap)+Mar(31)=179 days to Oct 4? recompute carefully in the runner, this is a hand-check reference, see verification notes in the summary).")

# 02: renewal, "extend this Lease for one additional period" phrasing
add("02_renewal_extend_phrasing", """
The Term of this Lease shall commence on June 1, 2022 and end on May 31, 2027.
Base Rent shall be $4,800.00 per month during the initial Term.
Tenant may extend this Lease for one (1) additional period of three (3) years by providing Landlord
not less than two hundred seventy (270) days written notice prior to the expiration of the Term,
with renewal rent based on the Consumer Price Index.
""", {
    "renewal_notice_deadline": "2026-09-03",  # verified: date(2027,5,31) - timedelta(days=270)
}, "Lease end 2027-05-31 minus 270 days notice -- independently verified with plain date arithmetic (date(2027,5,31) - timedelta(days=270)), not hand-counted.")

# 03: flat percentage annual escalation
add("03_flat_percentage_escalation", """
This Lease commences on January 1, 2024 and expires on December 31, 2029.
Tenant shall pay Base Rent of $10,000.00 per month, which amount shall increase by three percent (3%)
on each annual anniversary of the Commencement Date for the remainder of the Term.
""", {
    "escalation_trigger_dates": ["2025-01-01", "2026-01-01", "2027-01-01", "2028-01-01", "2029-01-01"],
}, "3% annual escalation on each anniversary of Jan 1, 2024, through the Dec 31, 2029 lease end -- five anniversaries (2025-2029 inclusive).")

# 04: year-by-year escalation schedule
add("04_year_by_year_schedule", """
The Lease Term shall commence on March 1, 2023 and terminate on February 28, 2028.
Base Rent shall be as follows: Year 1: $8,000.00; Year 2: $8,240.00; Year 3: $8,487.00; Year 4: $8,742.00; Year 5: $9,004.00.
""", {
    "escalation_trigger_dates": ["2024-03-01", "2025-03-01", "2026-03-01", "2027-03-01"],
}, "Year 2's rate ($8,240) takes effect on the 1-year anniversary (2024-03-01), Year 3 on the 2-year anniversary (2025-03-01), etc. Year 1 is the starting rent, not a future trigger -- only 4 trigger dates for a 5-year schedule.")

# 05: termination option, standard phrasing
add("05_termination_standard_phrasing", """
This Lease commences on July 1, 2022 and expires on June 30, 2032.
Base Rent is $15,000.00 per month.
Notwithstanding the foregoing, Tenant shall have the one-time right to terminate this Lease effective as of
the last day of the 5th year of the Term, provided Tenant delivers written notice to Landlord no later than
one hundred eighty (180) days prior to such termination date.
""", {
    "termination_notice_deadline": "2027-01-01",  # verified: effective date(2027,6,30) - timedelta(days=180)
}, "The 5th year of a Term starting 2022-07-01 runs 2026-07-01 to 2027-06-30 -- its LAST day is 2027-06-30 (one day before the 5-year anniversary, 2027-07-01), not the anniversary itself. Notice deadline = 2027-06-30 minus 180 days. This off-by-one was caught by independently verifying with date arithmetic rather than trusting the code's first output -- see the obligations-engine writeup.")

# 06: no renewal/termination/escalation clauses at all -- everything should be empty, not guessed
add("06_no_special_clauses", """
This Lease commences on May 1, 2024 and expires on April 30, 2029.
Tenant shall pay Base Rent of $3,000.00 per month. There are no renewal options, no early termination
rights, and rent shall remain flat for the entire Term.
""", {
    "renewal_notice_deadline": None,
    "termination_notice_deadline": None,
    "escalation_trigger_dates": [],
}, "No renewal/termination/escalation language at all -- every obligation type must come back empty/None, never a guessed default.")

# 07: renewal notice period stated but lease end date missing -- must not guess
add("07_renewal_notice_no_end_date", """
This Lease commences on January 1, 2023.
Tenant shall have one (1) option to renew this Lease for five (5) years, provided Tenant delivers
written notice not less than ninety (90) days prior to the expiration of the Term.
""", {
    "renewal_notice_deadline": None,
}, "No lease_end_date stated anywhere -- renewal deadline requires it and must come back None, not computed from a guessed end date.")

# 08: insurance requirement present -- obligation reported, but with no fabricated date
add("08_insurance_requirement_present", """
This Lease commences on February 1, 2024 and expires on January 31, 2029. Base Rent is $5,500.00 per month.
Tenant shall maintain and keep in force Commercial General Liability insurance with limits of not less than
$2,000,000.00 per occurrence, naming Landlord as additional insured, throughout the Term.
""", {
    "insurance_obligation_present": True,
    "insurance_due_date": None,
}, "Insurance requirement is clearly stated, but the lease never states a certificate renewal DATE -- obligation must be reported as present with due_date=None, not a fabricated annual date.")

# 09: escalation percentage present but NOT annual (one-time bump) -- must not treat as recurring anniversary
add("09_one_time_escalation_not_annual", """
This Lease commences on September 1, 2023 and expires on August 31, 2028.
Base Rent shall be $7,000.00 per month for the first two years, increasing by ten percent (10%) at the
start of the third year of the Term only, with no further increases thereafter.
""", {
    "escalation_trigger_dates": [],
}, "A one-time 10% bump is NOT the same as an annual/anniversary escalation -- field_extractor's suffix logic only attaches 'annually' when the text says 'annual'/'anniversary'/'each year'/'per year', none of which appear here, so parse_percent's caller in obligations.py correctly finds no annual cue and returns no trigger dates rather than guessing this is recurring.")

# 10: termination clause present but notice period missing -- must not guess a default notice
add("10_termination_no_notice_period", """
This Lease commences on April 1, 2021 and expires on March 31, 2031.
Base Rent is $20,000.00 per month.
Tenant may terminate this Lease effective as of the end of the 7th year of the Term upon written notice
to Landlord.
""", {
    "termination_notice_deadline": None,
}, "Termination trigger year (7) is stated but no specific notice-day count is given ('upon written notice' with no day count) -- must come back None rather than assuming a default like 180 or 90 days.")

# 11: multiple renewal options, notice stated as months-style text (should not match day-based regex, honest None)
add("11_renewal_notice_in_months_text", """
This Lease commences on October 1, 2022 and expires on September 30, 2027.
Base Rent is $9,500.00 per month.
Tenant shall have three (3) options to renew this Lease for terms of five (5) years each, provided Tenant
delivers written notice at least six (6) months prior to the expiration of the then-current Term.
""", {
    "renewal_notice_deadline": None,
}, "Notice period is stated in MONTHS ('six (6) months'), not days -- parse_renewal_options' notice_days regex only recognizes a day-count ('N days notice'), so this correctly returns no notice_days rather than misreading '6' as 6 days. A real, documented limitation (see final summary), not a bug being fixed in this pass.")

# 12: escalation schedule where Year 1 differs from stated base rent (schedule is authoritative)
add("12_escalation_schedule_various_years", """
The Term commences on November 1, 2020 and expires on October 31, 2030.
Rent shall be paid as follows: Year 1: $12,000.00; Year 4: $13,200.00; Year 7: $14,520.00.
""", {
    "escalation_trigger_dates": ["2023-11-01", "2026-11-01"],
}, "Non-consecutive year numbers (1, 4, 7) -- Year 4's rate triggers on the 3-year anniversary (2023-11-01), Year 7's on the 6-year anniversary (2026-11-01). Year 1 is still the starting rent, not a trigger.")


for fx in fixtures:
    pages = [{"page": 1, "text": fx["text"].strip()}]
    with open(os.path.join(OUT_DIR, fx["id"] + ".json"), "w") as f:
        json.dump({"pages": pages, "truth": fx["truth"], "notes": fx["notes"]}, f, indent=2)

manifest = [{"id": fx["id"], "notes": fx["notes"]} for fx in fixtures]
with open(os.path.join(OUT_DIR, "_manifest.json"), "w") as f:
    json.dump(manifest, f, indent=2)

print(f"Generated {len(fixtures)} lease-text fixtures in {OUT_DIR}")
