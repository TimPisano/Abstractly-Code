"""
Script to create a realistic commercial lease PDF for testing.

Unlike the simple "Label: Value" residential sample, this document uses
narrative prose sentence structure typical of real commercial leases
(e.g. "Tenant shall pay ... the sum of $6,250.00 per month" instead of
"Monthly Rent: $6,250.00"). This is the primary fixture for the
commercial lease abstraction tool described in CLAUDE.md.
"""

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
import os


def create_commercial_lease():
    """Create a sample commercial lease PDF with prose-style clauses."""

    output_path = os.path.join(os.path.dirname(__file__), "sample_lease_commercial.pdf")

    c = canvas.Canvas(output_path, pagesize=letter)
    width, height = letter

    c.setFont("Helvetica-Bold", 16)
    c.drawString(1 * inch, height - 1 * inch, "COMMERCIAL LEASE AGREEMENT")

    c.setFont("Helvetica", 11)
    y_position = height - 1.6 * inch
    left_margin = 1 * inch
    right_margin = width - 1 * inch
    max_width = right_margin - left_margin
    line_height = 0.22 * inch

    paragraphs = [
        "This Commercial Lease Agreement (the \"Lease\") is made and entered into "
        "as of March 15, 2025, by and between Meridian Properties Group, LLC, a "
        "Texas limited liability company (\"Landlord\"), and Blue Sky Coffee "
        "Roasters, Inc., a Delaware corporation (\"Tenant\").",

        "1. PREMISES. Landlord leases to Tenant, and Tenant leases from Landlord, "
        "the premises located at 4200 Commerce Parkway, Suite 110, Austin, Texas "
        "78701 (the \"Premises\"), consisting of approximately 2,400 square feet.",

        "2. TERM. The term of this Lease shall commence on April 1, 2025 (the "
        "\"Commencement Date\") and shall expire on March 31, 2030 (the "
        "\"Expiration Date\"), unless sooner terminated as provided herein.",

        "3. BASE RENT. Tenant shall pay to Landlord as base rent for the "
        "Premises the sum of $6,250.00 per month, payable in advance on the "
        "first day of each calendar month during the Term, without demand, "
        "deduction, or offset.",

        "4. RENT ESCALATION. Commencing on the first anniversary of the "
        "Commencement Date, and on each anniversary thereafter, Base Rent shall "
        "increase by three percent (3%) over the Base Rent payable during the "
        "immediately preceding twelve-month period.",

        "5. SECURITY DEPOSIT. Upon execution of this Lease, Tenant shall deposit "
        "with Landlord the sum of $12,500.00 as a security deposit, to be held "
        "by Landlord as security for Tenant's faithful performance of its "
        "obligations hereunder.",

        "6. COMMON AREA MAINTENANCE. In addition to Base Rent, Tenant shall pay "
        "its proportionate share of Common Area Maintenance (CAM) charges, "
        "currently estimated at $875.00 per month, subject to annual "
        "reconciliation based on actual operating expenses.",

        "7. RENEWAL OPTION. Provided Tenant is not then in default, Tenant "
        "shall have two (2) options to renew this Lease for additional terms of "
        "five (5) years each, exercisable by written notice to Landlord not "
        "less than one hundred eighty (180) days prior to expiration of the "
        "then-current term. Rent during each renewal term shall be adjusted to "
        "the then-prevailing fair market rate.",

        "8. PERMITTED USE. The Premises shall be used solely for the operation "
        "of a retail coffee shop and roastery, and for no other purpose without "
        "the prior written consent of Landlord.",

        "9. EXCLUSIVITY. Landlord agrees that, during the Term, it shall not "
        "lease any other space within the shopping center to another tenant "
        "whose primary business is the retail sale of coffee, espresso, or tea "
        "beverages.",

        "10. INSURANCE. Tenant shall, at its own expense, maintain commercial "
        "general liability insurance with a minimum coverage of $2,000,000 per "
        "occurrence, naming Landlord as an additional insured.",

        "11. DEFAULT AND CURE. If Tenant fails to pay any installment of Base "
        "Rent when due, and such failure continues for ten (10) days after "
        "written notice from Landlord, Tenant shall be in default under this "
        "Lease and Landlord may pursue all remedies available at law.",
    ]

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

    for para in paragraphs:
        lines = wrap_text(para, "Helvetica", 11, max_width)
        for line in lines:
            if y_position < 1 * inch:
                c.showPage()
                c.setFont("Helvetica", 11)
                y_position = height - 1 * inch
            c.drawString(left_margin, y_position, line)
            y_position -= line_height
        y_position -= line_height * 0.6  # paragraph spacing

    if y_position < 2 * inch:
        c.showPage()
        c.setFont("Helvetica", 11)
        y_position = height - 1 * inch

    y_position -= 0.3 * inch
    c.drawString(left_margin, y_position, "SIGNATURES:")
    y_position -= 0.5 * inch
    c.drawString(left_margin, y_position, "Landlord: Meridian Properties Group, LLC   Date: ___________")
    y_position -= 0.5 * inch
    c.drawString(left_margin, y_position, "Tenant: Blue Sky Coffee Roasters, Inc.     Date: ___________")

    c.save()
    print(f"Sample commercial lease PDF created at: {output_path}")


if __name__ == "__main__":
    create_commercial_lease()
