"""
Final-verification script: hits the ACTUAL RUNNING backend server (not a
direct function call) via HTTP for every test document, to catch any
server-layer issues (temp file handling, request parsing, JSON
serialization) that calling FieldExtractor directly wouldn't reveal.

Requires the backend to already be running at API_BASE_URL.
"""
import os
import sys
import json
import urllib.request

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from create_synthetic_leases import create_retail_lease, create_office_lease, create_casual_sublease

API_BASE_URL = "http://localhost:5000"

DOCS = [
    {"name": "sample_lease.pdf", "expected": {
        "tenant": "John Smith", "landlord": "Property Management LLC", "rent_amount": "$2,500",
        "lease_start_date": "January 15, 2024", "lease_end_date": "January 14, 2025",
        "property_address": "123 Main Street", "security_deposit": "$2,500",
        "cam_charges": None, "rent_escalation": None, "renewal_options": None,
        "permitted_use": None, "exclusivity_clause": None, "insurance_requirements": None,
        "default_cure_period": None,
    }},
    {"name": "sample_lease_commercial.pdf", "expected": {
        "tenant": "Blue Sky Coffee Roasters", "landlord": "Meridian Properties Group",
        "rent_amount": "$6,250.00", "lease_start_date": "April 1, 2025", "lease_end_date": "March 31, 2030",
        "property_address": "4200 Commerce Parkway", "security_deposit": "$12,500.00",
        "cam_charges": "$875.00", "rent_escalation": "3%", "renewal_options": "2 option",
        "permitted_use": "coffee shop", "exclusivity_clause": "coffee",
        "insurance_requirements": "$2,000,000", "default_cure_period": "10 days",
    }},
    {"name": "retail_lease.pdf", "expected": create_retail_lease()},
    {"name": "office_lease.pdf", "expected": create_office_lease()},
    {"name": "casual_sublease.pdf", "expected": create_casual_sublease()},
]


def call_api(pdf_path):
    boundary = "----LiveAPITestBoundary"
    with open(pdf_path, "rb") as f:
        file_data = f.read()

    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{os.path.basename(pdf_path)}"\r\n'
        f"Content-Type: application/pdf\r\n\r\n"
    ).encode() + file_data + f"\r\n--{boundary}--\r\n".encode()

    req = urllib.request.Request(
        f"{API_BASE_URL}/extract",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.loads(resp.read().decode())
        # /extract now returns {"leases": [...]} (a list, even for a
        # single-lease PDF) so multi-lease PDFs can return more than
        # one — every fixture here is a genuine single lease, so the
        # first (only) entry's fields is what this test's assertions
        # are written against.
        return body["leases"][0]["fields"]


def main():
    overall_pass = True
    for doc in DOCS:
        path = os.path.join(os.path.dirname(__file__), doc["name"])
        print("=" * 70)
        print(f"LIVE API TEST: {doc['name']}")
        print("=" * 70)

        result = call_api(path)

        for field, expected in doc["expected"].items():
            actual = result[field]["value"]
            if expected is None:
                ok = actual is None
            else:
                ok = bool(actual) and expected.lower() in str(actual).lower()
            mark = "PASS" if ok else "FAIL"
            if not ok:
                overall_pass = False
            print(f"{mark:5s} {field:24s} expected={expected!r:40s} actual={actual!r} conf={result[field].get('confidence')}")
        print()

    print("=" * 70)
    print("OVERALL:", "PASS" if overall_pass else "FAIL")
    print("=" * 70)
    return overall_pass


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
