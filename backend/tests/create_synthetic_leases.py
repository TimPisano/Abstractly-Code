"""
Generates 3 synthetic lease PDFs for robustness testing, each deliberately
structured/phrased/formatted differently from sample_lease.pdf and
sample_lease_commercial.pdf and from each other:

  - retail_lease.pdf:    numeric dates, annual-rent-with-monthly-
                          parenthetical, a full year-by-year escalation
                          table, alternate renewal/permitted-use phrasing,
                          "business days" cure period, label-style parties
                          with LP/Co. suffixes, no exclusivity clause.
  - office_lease.pdf:    heavy legal prose, lettered sections, defined-term
                          parties, legal-style "1st day of January, 2026"
                          dates, "...ending DATE" phrasing, CPI renewal
                          basis, "covenants" exclusivity wording, aggregate
                          insurance limit, no security deposit or CAM.
  - casual_sublease.pdf: informal letter-style short sublease. Missing
                          most commercial-specific clauses entirely (by
                          design, to test clean "Not Found" handling).

Each generator function returns the ground-truth values used by
test_synthetic_accuracy.py to score extraction accuracy.
"""

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
import os


def _write_pdf(filename, paragraphs, title=None):
    output_path = os.path.join(os.path.dirname(__file__), filename)
    c = canvas.Canvas(output_path, pagesize=letter, invariant=1)
    width, height = letter
    left_margin = 1 * inch
    right_margin = width - 1 * inch
    max_width = right_margin - left_margin

    y_position = height - 1 * inch

    if title:
        c.setFont("Helvetica-Bold", 15)
        c.drawString(left_margin, y_position, title)
        y_position -= 0.4 * inch

    c.setFont("Helvetica", 11)

    def wrap_text(text, font_name, font_size, max_w):
        words = text.split(" ")
        lines = []
        current = ""
        for word in words:
            candidate = (current + " " + word).strip()
            if c.stringWidth(candidate, font_name, font_size) <= max_w:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines

    line_height = 0.22 * inch

    for para in paragraphs:
        lines = wrap_text(para, "Helvetica", 11, max_width)
        for line in lines:
            if y_position < 1 * inch:
                c.showPage()
                c.setFont("Helvetica", 11)
                y_position = height - 1 * inch
            c.drawString(left_margin, y_position, line)
            y_position -= line_height
        y_position -= line_height * 0.6

    c.save()
    print(f"Created: {output_path}")


def create_retail_lease():
    paragraphs = [
        "LEASE SUMMARY",
        "LANDLORD: Harborview Retail Partners LP",
        "TENANT: Cascade Apparel Co.",
        "PREMISES ADDRESS: 8890 Riverside Plaza, Unit 12, Portland, Oregon 97201",
        "Lease Commencement Date: 04/01/2025",
        "Lease Expiration Date: 03/31/2035",
        "",
        "1. RENT. Base Rent for the Premises shall be $72,000.00 per annum "
        "($6,000.00 per month), payable in advance on the first day of each "
        "month.",
        "",
        "2. RENT ESCALATION. Base Rent shall increase according to the "
        "following schedule: Year 1: $6,000.00, Year 2: $6,180.00, Year 3: "
        "$6,365.00, with the same 3% increase applied in each subsequent "
        "year of the Term.",
        "",
        "3. SECURITY DEPOSIT. Tenant shall pay Landlord a security deposit "
        "of $6,000.00 upon signing this Lease.",
        "",
        "4. COMMON AREA MAINTENANCE. Tenant's monthly CAM contribution "
        "shall be $350.00, subject to annual adjustment based on actual "
        "shopping center operating costs.",
        "",
        "5. RENEWAL. Tenant may extend this Lease for one (1) additional "
        "period of three (3) years by providing Landlord ninety (90) days' "
        "written notice prior to expiration of the Term; renewal Base Rent "
        "shall equal the then-prevailing fair market rate.",
        "",
        "6. PERMITTED USE. Tenant shall use the Premises exclusively as a "
        "general retail store selling apparel and accessories, and shall "
        "not use the Premises for any other purpose.",
        "",
        "7. INSURANCE. Tenant's commercial general liability policy shall "
        "provide not less than One Million Dollars ($1,000,000) per "
        "occurrence coverage, naming Landlord as an additional insured.",
        "",
        "8. DEFAULT. In the event Tenant fails to cure a monetary default "
        "within five (5) business days following written notice from "
        "Landlord, Tenant shall be in default under this Lease.",
    ]
    _write_pdf("retail_lease.pdf", paragraphs, title="RETAIL LEASE AGREEMENT")

    return {
        "tenant": "Cascade Apparel Co.",
        "landlord": "Harborview Retail Partners LP",
        "rent_amount": "$6,000.00",
        "lease_start_date": "04/01/2025",
        "lease_end_date": "03/31/2035",
        "property_address": "8890 Riverside Plaza",
        "security_deposit": "$6,000.00",
        "cam_charges": "$350.00",
        "rent_escalation": "Year 1",
        "renewal_options": "1 option",
        "permitted_use": "retail store",
        "exclusivity_clause": None,
        "insurance_requirements": "$1,000,000",
        "default_cure_period": "5 days",
    }


def create_office_lease():
    paragraphs = [
        "OFFICE LEASE AGREEMENT",
        "This Office Lease Agreement is made by and between Blackstone "
        "Commercial Holdings, Inc. (\"Landlord\") and Vertex Analytics LLC "
        "(\"Tenant\").",
        "",
        "A. PREMISES. The premises are located at 2200 Wilshire Corporate "
        "Center, 14th Floor, Los Angeles, California 90025 (the "
        "\"Premises\").",
        "",
        "B. TERM. This Lease shall commence on the 1st day of January, "
        "2026, and shall continue for a period of ten (10) years, ending "
        "December 31, 2035.",
        "",
        "C. RENT. Tenant shall pay Base Rent in the amount of $9,500.00 "
        "per month, in advance, without any prior demand therefor.",
        "",
        "D. RENT ADJUSTMENT. Base Rent shall increase by four percent (4%) "
        "on each anniversary of the Commencement Date.",
        "",
        "E. RENEWAL. Tenant shall have one (1) option to renew this Lease "
        "for an additional term of five (5) years, provided written notice "
        "is delivered to Landlord not less than two hundred seventy (270) "
        "days prior to the Expiration Date. The renewal Base Rent shall be "
        "adjusted in accordance with the Consumer Price Index.",
        "",
        "F. USE. The Premises shall be used solely for general office "
        "purposes and for no other purpose without Landlord's prior "
        "written consent.",
        "",
        "G. EXCLUSIVITY. Landlord covenants that it shall not lease any "
        "other space in the building to a direct competitor of Tenant "
        "engaged in the business of data analytics software.",
        "",
        "H. INSURANCE. Tenant shall maintain commercial general liability "
        "insurance in an amount not less than $2,000,000.00 in the "
        "aggregate.",
        "",
        "I. DEFAULT. If Tenant fails to cure any monetary default within "
        "fifteen (15) days after receipt of written notice from Landlord, "
        "Tenant shall be deemed in default hereunder.",
    ]
    _write_pdf("office_lease.pdf", paragraphs)

    return {
        "tenant": "Vertex Analytics LLC",
        "landlord": "Blackstone Commercial Holdings, Inc.",
        "rent_amount": "$9,500.00",
        "lease_start_date": "1st day of January, 2026",
        "lease_end_date": "December 31, 2035",
        "property_address": "2200 Wilshire Corporate Center",
        "security_deposit": None,
        "cam_charges": None,
        "rent_escalation": "4%",
        "renewal_options": "1 option",
        "permitted_use": "general office purposes",
        "exclusivity_clause": "direct competitor",
        "insurance_requirements": "$2,000,000",
        "default_cure_period": "15 days",
    }


def create_casual_sublease():
    paragraphs = [
        "Hey! Here's the deal we talked about, in writing so we're both "
        "covered.",
        "",
        "Landlord is Jordan Blake and the tenant is Alex Chen.",
        "",
        "Rent will be $1,800 a month, starting September 1, 2025 and "
        "running through August 31, 2026.",
        "",
        "Security deposit is one month's rent ($1,800), due when you move "
        "in.",
        "",
        "That's basically it — pay on time, keep the place in one piece, "
        "and we're all good. Thanks!",
    ]
    _write_pdf("casual_sublease.pdf", paragraphs)

    return {
        "tenant": "Alex Chen",
        "landlord": "Jordan Blake",
        "rent_amount": "$1,800",
        "lease_start_date": "September 1, 2025",
        "lease_end_date": "August 31, 2026",
        "property_address": None,
        "security_deposit": "$1,800",
        "cam_charges": None,
        "rent_escalation": None,
        "renewal_options": None,
        "permitted_use": None,
        "exclusivity_clause": None,
        "insurance_requirements": None,
        "default_cure_period": None,
    }


if __name__ == "__main__":
    create_retail_lease()
    create_office_lease()
    create_casual_sublease()
