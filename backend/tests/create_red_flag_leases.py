"""
Generates 5 synthetic lease PDFs with deliberate red-flag-worthy issues,
each targeting specific risk_analysis.py checks so the risk engine has
real things to catch during portfolio verification:

  - underpriced_downtown.pdf:      rent well below market (below_market_rent)
  - missing_clauses_office.pdf:    no insurance/default-cure/deposit clauses (missing_clause x3)
  - tenant_friendly_terms.pdf:     10-year term with no escalation clause,
                                    a 45-day cure period, and a 15-day
                                    renewal notice (one_sided_terms x2,
                                    notice_period_outlier short)
  - inconsistent_escalation.pdf:   two different stated commencement
                                    dates, and a year-by-year escalation
                                    table with wildly inconsistent rates
                                    (date_inconsistency, escalation_inconsistency)
  - reversed_dates.pdf:            end date stated before the start date,
                                    plus a 330-day renewal notice period
                                    (date_inconsistency, notice_period_outlier long)

Each is otherwise a normal, internally-varied commercial lease (different
tenant/landlord/city/dates/rent) so the portfolio dashboard, timeline, and
comparison views have realistic diverse data to work with too — expiration
dates deliberately span every timeline bucket (already-expired through
8+ years out) in combination with the 5 fixtures from the prior session.

Each generator function returns a dict of expected ground-truth EXTRACTED
field values (for accuracy verification, same convention as
create_synthetic_leases.py) plus an "expected_risk_categories" list (for
verifying risk_analysis.py actually catches what it's supposed to).
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


def create_underpriced_downtown():
    """Below-market rent: $1.50/sqft vs. a portfolio average well above that."""
    paragraphs = [
        "This Commercial Lease Agreement is made by and between Presidio "
        "Commercial Properties (\"Landlord\") and Golden Gate Bakery LLC "
        "(\"Tenant\").",
        "",
        "1. PREMISES. The premises are located at 455 Market Street, Suite "
        "200, San Francisco, California 94105 (the \"Premises\"), "
        "consisting of approximately 1,500 square feet.",
        "",
        "2. TERM. This Lease shall commence on June 1, 2024, and shall "
        "expire on February 28, 2027.",
        "",
        "3. RENT. Tenant shall pay Base Rent in the amount of $2,250.00 "
        "per month, payable in advance on the first day of each month.",
        "",
        "4. RENT ESCALATION. Base Rent shall increase by two percent (2%) "
        "on each anniversary of the Commencement Date.",
        "",
        "5. SECURITY DEPOSIT. Tenant shall deposit with Landlord the sum "
        "of $2,250.00 as a security deposit.",
        "",
        "6. COMMON AREA MAINTENANCE. Tenant shall pay its proportionate "
        "share of Common Area Maintenance charges, currently estimated "
        "at $200.00 per month.",
        "",
        "7. RENEWAL. Tenant shall have one (1) option to renew this Lease "
        "for an additional term of five (5) years, provided written "
        "notice is delivered to Landlord not less than ninety (90) days "
        "prior to the Expiration Date. Renewal rent shall be at the "
        "then-prevailing fair market rate.",
        "",
        "8. PERMITTED USE. The Premises shall be used solely for the "
        "operation of a retail bakery, and for no other purpose without "
        "Landlord's prior written consent.",
        "",
        "9. INSURANCE. Tenant shall maintain commercial general liability "
        "insurance with a minimum coverage of $1,000,000 per occurrence.",
        "",
        "10. DEFAULT. If Tenant fails to cure a monetary default within "
        "ten (10) days after written notice from Landlord, Tenant shall "
        "be in default under this Lease.",
    ]
    _write_pdf("underpriced_downtown.pdf", paragraphs, title="COMMERCIAL LEASE AGREEMENT")

    return {
        "expected_fields": {
            "tenant": "Golden Gate Bakery LLC",
            "landlord": "Presidio Commercial Properties",
            "rent_amount": "$2,250.00",
            "lease_start_date": "June 1, 2024",
            "lease_end_date": "February 28, 2027",
            "property_address": "455 Market Street",
            "security_deposit": "$2,250.00",
            "cam_charges": "$200.00",
            "rent_escalation": "2%",
            "renewal_options": "1 option",
            "permitted_use": "bakery",
            "exclusivity_clause": None,
            "insurance_requirements": "$1,000,000",
            "default_cure_period": "10 days",
            "square_footage": "1,500",
        },
        "expected_risk_categories": ["below_market_rent"],
    }


def create_missing_clauses_office():
    """No security deposit, no insurance clause, no default/cure clause."""
    paragraphs = [
        "This Office Lease Agreement is made by and between Beacon Hill "
        "Properties LP (\"Landlord\") and Nimbus Software Solutions, Inc. "
        "(\"Tenant\").",
        "",
        "1. PREMISES. The premises are located at 88 Federal Street, 5th "
        "Floor, Boston, Massachusetts 02110 (the \"Premises\"), "
        "consisting of approximately 4,500 square feet.",
        "",
        "2. TERM. This Lease shall commence on March 1, 2025, and shall "
        "expire on February 28, 2028.",
        "",
        "3. RENT. Tenant shall pay Base Rent in the amount of $11,250.00 "
        "per month, payable in advance on the first day of each month.",
        "",
        "4. RENT ESCALATION. Base Rent shall increase by three percent "
        "(3%) on each anniversary of the Commencement Date.",
        "",
        "5. COMMON AREA MAINTENANCE. Tenant shall pay its proportionate "
        "share of Common Area Maintenance charges, currently estimated "
        "at $600.00 per month.",
        "",
        "6. RENEWAL. Tenant shall have one (1) option to renew this Lease "
        "for an additional term of three (3) years, provided written "
        "notice is delivered to Landlord not less than one hundred "
        "twenty (120) days prior to the Expiration Date. Renewal rent "
        "shall be adjusted in accordance with the Consumer Price Index.",
        "",
        "7. PERMITTED USE. The Premises shall be used solely for general "
        "office purposes and for no other purpose without Landlord's "
        "prior written consent.",
    ]
    _write_pdf("missing_clauses_office.pdf", paragraphs, title="OFFICE LEASE AGREEMENT")

    return {
        "expected_fields": {
            "tenant": "Nimbus Software Solutions, Inc.",
            "landlord": "Beacon Hill Properties LP",
            "rent_amount": "$11,250.00",
            "lease_start_date": "March 1, 2025",
            "lease_end_date": "February 28, 2028",
            "property_address": "88 Federal Street",
            "security_deposit": None,
            "cam_charges": "$600.00",
            "rent_escalation": "3%",
            "renewal_options": "1 option",
            "permitted_use": "general office",
            "exclusivity_clause": None,
            "insurance_requirements": None,
            "default_cure_period": None,
            "square_footage": "4,500",
        },
        "expected_risk_categories": ["missing_clause", "missing_clause", "missing_clause"],
    }


def create_tenant_friendly_terms():
    """10-year term with no escalation, a 45-day cure period, and a 15-day renewal notice."""
    paragraphs = [
        "This Commercial Lease Agreement is made by and between Oakwood "
        "Realty Trust (\"Landlord\") and Riverside Fitness Studio LLC "
        "(\"Tenant\").",
        "",
        "1. PREMISES. The premises are located at 1200 Riverside Drive, "
        "Austin, Texas 78701 (the \"Premises\"), consisting of "
        "approximately 3,200 square feet.",
        "",
        "2. TERM. This Lease shall commence on January 1, 2025, and shall "
        "expire on December 31, 2034.",
        "",
        "3. RENT. Tenant shall pay Base Rent in the amount of $8,000.00 "
        "per month, payable in advance on the first day of each month, "
        "with no scheduled increase during the Term.",
        "",
        "4. SECURITY DEPOSIT. Tenant shall deposit with Landlord the sum "
        "of $8,000.00 as a security deposit.",
        "",
        "5. COMMON AREA MAINTENANCE. Tenant shall pay its proportionate "
        "share of Common Area Maintenance charges, currently estimated "
        "at $400.00 per month.",
        "",
        "6. RENEWAL. Tenant shall have one (1) option to renew this Lease "
        "for an additional term of five (5) years, provided written "
        "notice is delivered to Landlord not less than fifteen (15) days "
        "prior to the Expiration Date. Renewal rent shall be at the "
        "then-prevailing fair market rate.",
        "",
        "7. PERMITTED USE. The Premises shall be used solely for the "
        "operation of a fitness studio, and for no other purpose without "
        "Landlord's prior written consent.",
        "",
        "8. INSURANCE. Tenant shall maintain commercial general liability "
        "insurance with a minimum coverage of $1,000,000 per occurrence.",
        "",
        "9. DEFAULT. If Tenant fails to cure a monetary default within "
        "forty-five (45) days after written notice from Landlord, Tenant "
        "shall be in default under this Lease.",
    ]
    _write_pdf("tenant_friendly_terms.pdf", paragraphs, title="COMMERCIAL LEASE AGREEMENT")

    return {
        "expected_fields": {
            "tenant": "Riverside Fitness Studio LLC",
            "landlord": "Oakwood Realty Trust",
            "rent_amount": "$8,000.00",
            "lease_start_date": "January 1, 2025",
            "lease_end_date": "December 31, 2034",
            "property_address": "1200 Riverside Drive",
            "security_deposit": "$8,000.00",
            "cam_charges": "$400.00",
            "rent_escalation": None,
            "renewal_options": "1 option",
            "permitted_use": "fitness studio",
            "exclusivity_clause": None,
            "insurance_requirements": "$1,000,000",
            "default_cure_period": "45 days",
            "square_footage": "3,200",
        },
        "expected_risk_categories": ["one_sided_terms", "one_sided_terms", "notice_period_outlier"],
    }


def create_inconsistent_escalation():
    """
    Two different stated commencement dates (Lease Summary block vs. Term
    section), and a year-by-year escalation table with wildly inconsistent
    rates (12.5% then 0.9%).
    """
    paragraphs = [
        "LEASE SUMMARY",
        "LANDLORD: Westfield Commercial Holdings",
        "TENANT: Pinnacle Consulting Group",
        "PROPERTY ADDRESS: 900 Century Plaza, Suite 310, Denver, Colorado 80202",
        "Square Footage: 2,800",
        "Commencement Date: June 1, 2025",
        "",
        "1. TERM. Notwithstanding anything to the contrary elsewhere in "
        "this Lease Summary, this Lease shall commence on July 1, 2025, "
        "and shall expire on May 31, 2030.",
        "",
        "2. RENT. Tenant shall pay Base Rent in the amount of $6,800.00 "
        "per month, payable in advance on the first day of each month.",
        "",
        "3. RENT ESCALATION. Base Rent shall increase according to the "
        "following schedule: Year 1: $6,800.00, Year 2: $7,650.00, Year "
        "3: $7,720.00, with Base Rent remaining fixed thereafter for the "
        "balance of the Term.",
        "",
        "4. SECURITY DEPOSIT. Tenant shall deposit with Landlord the sum "
        "of $6,800.00 as a security deposit.",
        "",
        "5. COMMON AREA MAINTENANCE. Tenant shall pay its proportionate "
        "share of Common Area Maintenance charges, currently estimated "
        "at $350.00 per month.",
        "",
        "6. RENEWAL. Tenant shall have one (1) option to renew this Lease "
        "for an additional term of five (5) years, provided written "
        "notice is delivered to Landlord not less than one hundred fifty "
        "(150) days prior to the Expiration Date. Renewal rent shall be "
        "at the then-prevailing fair market rate.",
        "",
        "7. PERMITTED USE. The Premises shall be used solely for general "
        "professional consulting office purposes and for no other "
        "purpose without Landlord's prior written consent.",
        "",
        "8. INSURANCE. Tenant shall maintain commercial general liability "
        "insurance with a minimum coverage of $2,000,000 per occurrence.",
        "",
        "9. DEFAULT. If Tenant fails to cure a monetary default within "
        "fourteen (14) days after written notice from Landlord, Tenant "
        "shall be in default under this Lease.",
    ]
    _write_pdf("inconsistent_escalation.pdf", paragraphs)

    return {
        "expected_fields": {
            "tenant": "Pinnacle Consulting Group",
            "landlord": "Westfield Commercial Holdings",
            "rent_amount": "$6,800.00",
            # The extractor's single-best-match will find whichever date
            # pattern it prioritizes first (label-style "Commencement
            # Date:" is tried before the prose "shall commence on" style),
            # so the primary extracted value is the summary block's date —
            # the SECOND, conflicting date is what find_all_date_candidates
            # (used by risk_analysis) is expected to also surface.
            "lease_start_date": "June 1, 2025",
            "lease_end_date": "May 31, 2030",
            "property_address": "900 Century Plaza",
            "security_deposit": "$6,800.00",
            "cam_charges": "$350.00",
            "rent_escalation": "Year 1",
            "renewal_options": "1 option",
            "permitted_use": "consulting office",
            "exclusivity_clause": None,
            "insurance_requirements": "$2,000,000",
            "default_cure_period": "14 days",
            "square_footage": "2,800",
        },
        "expected_risk_categories": ["date_inconsistency", "escalation_inconsistency"],
    }


def create_reversed_dates():
    """End date stated before the start date, plus a 330-day renewal notice period."""
    paragraphs = [
        "This Commercial Lease Agreement is made by and between Harbor "
        "Point Industrial Partners (\"Landlord\") and Coastal Marine "
        "Supply Co. (\"Tenant\").",
        "",
        "1. PREMISES. The premises are located at 77 Dockside Way, "
        "Norfolk, Virginia 23510 (the \"Premises\"), consisting of "
        "approximately 5,000 square feet.",
        "",
        "2. TERM. This Lease shall commence on January 1, 2026, and shall "
        "expire on January 1, 2024.",
        "",
        "3. RENT. Tenant shall pay Base Rent in the amount of $9,500.00 "
        "per month, payable in advance on the first day of each month.",
        "",
        "4. RENT ESCALATION. Base Rent shall increase by four percent "
        "(4%) on each anniversary of the Commencement Date.",
        "",
        "5. SECURITY DEPOSIT. Tenant shall deposit with Landlord the sum "
        "of $9,500.00 as a security deposit.",
        "",
        "6. COMMON AREA MAINTENANCE. Tenant shall pay its proportionate "
        "share of Common Area Maintenance charges, currently estimated "
        "at $700.00 per month.",
        "",
        "7. RENEWAL. Tenant shall have one (1) option to renew this Lease "
        "for an additional term of five (5) years, provided written "
        "notice is delivered to Landlord not less than three hundred "
        "thirty (330) days prior to the Expiration Date. Renewal rent "
        "shall be at the then-prevailing fair market rate.",
        "",
        "8. PERMITTED USE. The Premises shall be used solely for the "
        "operation of a marine equipment warehouse and distribution "
        "facility, and for no other purpose without Landlord's prior "
        "written consent.",
        "",
        "9. INSURANCE. Tenant shall maintain commercial general liability "
        "insurance with a minimum coverage of $1,500,000 per occurrence.",
        "",
        "10. DEFAULT. If Tenant fails to cure a monetary default within "
        "ten (10) days after written notice from Landlord, Tenant shall "
        "be in default under this Lease.",
    ]
    _write_pdf("reversed_dates.pdf", paragraphs, title="COMMERCIAL LEASE AGREEMENT")

    return {
        "expected_fields": {
            "tenant": "Coastal Marine Supply Co.",
            "landlord": "Harbor Point Industrial Partners",
            "rent_amount": "$9,500.00",
            "lease_start_date": "January 1, 2026",
            "lease_end_date": "January 1, 2024",
            "property_address": "77 Dockside Way",
            "security_deposit": "$9,500.00",
            "cam_charges": "$700.00",
            "rent_escalation": "4%",
            "renewal_options": "1 option",
            "permitted_use": "marine equipment warehouse",
            "exclusivity_clause": None,
            "insurance_requirements": "$1,500,000",
            "default_cure_period": "10 days",
            "square_footage": "5,000",
        },
        "expected_risk_categories": ["date_inconsistency", "notice_period_outlier"],
    }


if __name__ == "__main__":
    create_underpriced_downtown()
    create_missing_clauses_office()
    create_tenant_friendly_terms()
    create_inconsistent_escalation()
    create_reversed_dates()
