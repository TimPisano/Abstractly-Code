"""
Regression coverage for the "Resident"/"Owner" multifamily lease
terminology gap found during QA hardening (2026-10): field_extractor.py's
tenant/landlord extraction only recognized "Tenant"/"Lessee"/"Renter" and
"Landlord"/"Lessor" as defined-term synonyms -- a standard multifamily
lease that defines its parties as "...and Jane Doe ("Resident")" / "...
Acme Apartments Owner, LLC ("Owner")" (extremely common real-world
terminology for apartment leases, not a rare edge case -- it's literally
what the product's own Maple Ridge demo deal's lease PDFs use) silently
extracted neither field at all.

Fixed by adding "Resident"/"Owner" to the role_keywords tuple passed to
_extract_defined_party (used by the structural "Name (\"Role\")" prose
pattern and the signature-caption tier), WITHOUT adding them to the
separate, looser "Label: Value" colon-style pattern (_party_label_patterns)
-- that pattern is unanchored enough that "Resident Agent: CT Corporation
System" (a common, unrelated registered-agent clause) or "Owner's
attorney: ..." could otherwise be misread as the tenant/landlord name.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.field_extractor import FieldExtractor


def _pages(text):
    return [{"page": 1, "text": text}]


def test_resident_terminology_extracts_as_tenant():
    text = (
        'This Lease Agreement ("Lease") is entered into by and between Example '
        'Apartments Owner, LLC ("Owner"), acting through its agent Example '
        'Management, LLC ("Management"), and Jane Doe ("Resident"), for the '
        'apartment home described below.'
    )
    fields = FieldExtractor().extract_fields(_pages(text), source_label="test.pdf")
    assert fields["tenant"]["value"] == "Jane Doe", fields["tenant"]
    print("✓ test_resident_terminology_extracts_as_tenant: PASS")


def test_owner_terminology_extracts_as_landlord():
    text = (
        'This Lease Agreement ("Lease") is entered into by and between Example '
        'Apartments Owner, LLC ("Owner"), acting through its agent Example '
        'Management, LLC ("Management"), and Jane Doe ("Resident"), for the '
        'apartment home described below.'
    )
    fields = FieldExtractor().extract_fields(_pages(text), source_label="test.pdf")
    assert fields["landlord"]["value"] == "Example Apartments Owner, LLC", fields["landlord"]
    print("✓ test_owner_terminology_extracts_as_landlord: PASS")


def test_tenant_lessee_landlord_lessor_still_work_unaffected():
    """The pre-existing synonyms this fix must not regress."""
    text = (
        'This Agreement is entered into by and between Acme Properties, LLC '
        '("Landlord") and Beta Corp ("Tenant").'
    )
    fields = FieldExtractor().extract_fields(_pages(text), source_label="test.pdf")
    assert fields["tenant"]["value"] == "Beta Corp", fields["tenant"]
    assert fields["landlord"]["value"] == "Acme Properties, LLC", fields["landlord"]
    print("✓ test_tenant_lessee_landlord_lessor_still_work_unaffected: PASS")


def test_resident_agent_clause_not_misread_as_tenant_name():
    """
    The specific false-positive risk this fix was scoped to avoid:
    "Resident Agent" is a common, unrelated registered-agent clause, not
    a tenant-name label -- must not leak into tenant extraction just
    because the loose label pattern was (deliberately NOT) extended too.
    """
    text = (
        'Landlord\'s resident agent for service of process in this state is '
        'CT Corporation System. Tenant: Jordan Blake.'
    )
    fields = FieldExtractor().extract_fields(_pages(text), source_label="test.pdf")
    assert fields["tenant"]["value"] == "Jordan Blake", fields["tenant"]
    print("✓ test_resident_agent_clause_not_misread_as_tenant_name: PASS")


if __name__ == "__main__":
    test_resident_terminology_extracts_as_tenant()
    test_owner_terminology_extracts_as_landlord()
    test_tenant_lessee_landlord_lessor_still_work_unaffected()
    test_resident_agent_clause_not_misread_as_tenant_name()
    print("\nAll field extractor party-name tests passed.")
