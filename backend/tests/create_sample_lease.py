"""
Script to create a sample lease PDF for testing.

This creates a simple text-based PDF with typical lease fields
that can be extracted by our system.
"""

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.units import inch
import os


def create_sample_lease():
    """Create a sample lease PDF with extractable fields."""

    output_path = os.path.join(os.path.dirname(__file__), "sample_lease.pdf")

    # Create PDF
    c = canvas.Canvas(output_path, pagesize=letter, invariant=1)
    width, height = letter

    # Title
    c.setFont("Helvetica-Bold", 16)
    c.drawString(1*inch, height - 1*inch, "RESIDENTIAL LEASE AGREEMENT")

    # Body text with lease details
    c.setFont("Helvetica", 12)
    y_position = height - 2*inch

    content = [
        "",
        "This Lease Agreement is entered into on January 1, 2024.",
        "",
        "PARTIES:",
        "Landlord: Property Management LLC",
        "Tenant: John Smith",
        "",
        "PROPERTY:",
        "Address: 123 Main Street, Apt 4B, San Francisco, CA 94102",
        "",
        "LEASE TERMS:",
        "Lease Start Date: January 15, 2024",
        "Lease End Date: January 14, 2025",
        "Term: 12 months",
        "",
        "RENT:",
        "Monthly Rent: $2,500.00",
        "Payment Due: 1st of each month",
        "Late Fee: $50.00 if paid after the 5th",
        "",
        "DEPOSIT:",
        "Security Deposit: $2,500.00",
        "Pet Deposit: N/A",
        "",
        "UTILITIES:",
        "Tenant is responsible for electricity, gas, and internet.",
        "Landlord provides water, sewer, and trash services.",
        "",
        "ADDITIONAL TERMS:",
        "- No smoking on the premises",
        "- No pets allowed without written permission",
        "- Tenant must maintain renter's insurance",
        "",
    ]

    for line in content:
        c.drawString(1*inch, y_position, line)
        y_position -= 0.25*inch

    # Signature section
    y_position -= 0.5*inch
    c.drawString(1*inch, y_position, "SIGNATURES:")
    y_position -= 0.5*inch
    c.drawString(1*inch, y_position, "Landlord: _______________________  Date: ___________")
    y_position -= 0.5*inch
    c.drawString(1*inch, y_position, "Tenant: _________________________  Date: ___________")

    # Save PDF
    c.save()
    print(f"Sample lease PDF created at: {output_path}")


if __name__ == "__main__":
    create_sample_lease()
