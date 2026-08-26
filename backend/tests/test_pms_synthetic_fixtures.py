"""
Tests the rent roll importer against SYNTHETIC PMS-style fixture files,
all in this directory: synthetic_yardi_rent_roll.csv/.xlsx,
synthetic_appfolio_rent_roll.csv, synthetic_realpage_rent_roll.csv,
synthetic_mri_rent_roll.csv, synthetic_buildium_rent_roll.csv.

IMPORTANT: These are fabricated test fixtures, clearly labeled as such
inside each file's own first row, NOT real vendor exports -- no real
sample files were available at the time this was built (see
DECISIONS.md's "PMS-specific rent roll import" entries). They were built
to match each platform's real, publicly-documented rent roll report
structure as closely as reasonably possible (decorative title/date rows
before the real header, each platform's own column terminology, a
Market/Actual-Rent-alongside-each-other column where realistic, a
multi-property portfolio-wide export for AppFolio and Buildium)
specifically so the header-row auto-detection, PMS terminology aliases,
per-row Property column, and market-rent denylist added for this
feature all get exercised against something more realistic than a
hand-written unit test fixture, not just unit-tested in isolation.

Swap in real vendor export files here (same filenames, or point these
tests at new ones) the moment real samples are available -- everything
below is written against each file's actual structure and known
content, not against any platform-specific assumption baked into the
test itself, so real files should need no test changes beyond updating
the expected values to match.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.rent_roll_import import parse_csv_rent_roll, parse_xlsx_rent_roll

FIXTURES_DIR = os.path.dirname(__file__)


def _read(filename):
    with open(os.path.join(FIXTURES_DIR, filename), "rb") as f:
        return f.read()


def test_synthetic_yardi_csv_imports_correctly():
    """
    Full end-to-end check against the synthetic Yardi CSV fixture: skips
    the 5-row decorative title/date block, uses "Rent Charge" (actual)
    not "Market Rent" (theoretical) for rent_amount, correctly skips the
    VACANT unit and the trailing Total row, and gets exact values for
    all 3 real tenants.
    """
    result = parse_csv_rent_roll(
        _read("synthetic_yardi_rent_roll.csv"),
        "synthetic_yardi_rent_roll.csv",
        base_property_address="Riverside Commons Shopping Center",
    )
    assert result["column_mapping"] == {
        "unit": 0, "tenant": 2, "square_footage": 3,
        "lease_start_date": 4, "lease_end_date": 5, "rent_amount": 7,
    }, result["column_mapping"]
    assert len(result["leases"]) == 3, result["leases"]
    assert len(result["skipped_rows"]) == 2  # VACANT unit + trailing Total row

    by_tenant = {l["extracted_fields"]["tenant"]["value"]: l["extracted_fields"] for l in result["leases"]}

    coffee = by_tenant["Riverside Coffee Roasters LLC"]
    assert coffee["rent_amount"]["value"] == "$3,200.00"  # Rent Charge, NOT Market Rent's $3,600.00
    assert coffee["property_address"]["value"] == "Riverside Commons Shopping Center, Suite 101"
    assert coffee["square_footage"]["value"] == "1,200 sq ft"
    assert coffee["lease_start_date"]["value"] == "03/01/2022"
    assert coffee["lease_end_date"]["value"] == "02/28/2027"

    dental = by_tenant["Bright Path Dental Group"]
    assert dental["rent_amount"]["value"] == "$4,950.00"  # not Market Rent's $5,400.00

    fitness = by_tenant["Meridian Fitness Studio"]
    assert fitness["rent_amount"]["value"] == "$6,800.00"  # not Market Rent's $7,200.00

    print("✓ test_synthetic_yardi_csv_imports_correctly: PASS")


def test_synthetic_yardi_xlsx_imports_correctly():
    """Same fixture, native .xlsx with real Excel date/numeric cell types (not CSV strings) -- confirms the xlsx path handles PMS-shaped data too, not just CSV."""
    result = parse_xlsx_rent_roll(
        _read("synthetic_yardi_rent_roll.xlsx"),
        "synthetic_yardi_rent_roll.xlsx",
        base_property_address="Meridian Business Park",
    )
    assert len(result["leases"]) == 2, result["leases"]
    assert len(result["skipped_rows"]) == 2  # VACANT unit + trailing Total row

    by_tenant = {l["extracted_fields"]["tenant"]["value"]: l["extracted_fields"] for l in result["leases"]}
    law = by_tenant["Summit Law Partners"]
    assert law["rent_amount"]["value"] == "$6,100.00"  # not Market Rent's $6,600.00
    assert law["property_address"]["value"] == "Meridian Business Park, Suite 201"
    # openpyxl hands back real date objects for a native Excel date cell --
    # confirms _cell_to_str's datetime handling round-trips correctly for
    # PMS-shaped data, not just the generic xlsx happy-path test's dates.
    assert law["lease_start_date"]["value"] == "May 01, 2023"
    assert law["lease_end_date"]["value"] == "April 30, 2028"

    print("✓ test_synthetic_yardi_xlsx_imports_correctly: PASS")


def test_synthetic_appfolio_csv_multi_property_imports_correctly():
    """
    Full end-to-end check against the synthetic AppFolio CSV fixture: a
    portfolio-wide export spanning TWO different properties in one file,
    deliberately imported with NO base_property_address at all (the
    realistic case for a multi-property pull -- there isn't one single
    address that would even be correct to type) to confirm the per-row
    Property column alone is sufficient. Also confirms "Unit 12" (a
    Unit cell that already spells out its own designator) isn't double-
    prefixed, alongside "Suite A" needing the prefix added.
    """
    result = parse_csv_rent_roll(
        _read("synthetic_appfolio_rent_roll.csv"),
        "synthetic_appfolio_rent_roll.csv",
    )
    assert len(result["leases"]) == 3, result["leases"]
    assert len(result["skipped_rows"]) == 1  # the Vacant unit

    by_tenant = {l["extracted_fields"]["tenant"]["value"]: l["extracted_fields"] for l in result["leases"]}

    legal = by_tenant["Lighthouse Legal Group"]
    assert legal["property_address"]["value"] == "425 Harbor View Plaza, Suite A"
    assert legal["rent_amount"]["value"] == "$4,100.00"

    imports = by_tenant["Golden Gate Imports"]
    assert imports["property_address"]["value"] == "910 Commerce Park Dr, Unit 12"  # not "Suite Unit 12"

    consulting = by_tenant["Blue Ridge Consulting"]
    assert consulting["property_address"]["value"] == "910 Commerce Park Dr, Unit 14"

    # The two different properties must genuinely be different buildings
    # for downstream building-level grouping (loss-to-lease, T12
    # reconciliation) -- not accidentally collapsed into one.
    assert legal["property_address"]["value"] != imports["property_address"]["value"]

    print("✓ test_synthetic_appfolio_csv_multi_property_imports_correctly: PASS")


def test_synthetic_realpage_csv_imports_correctly():
    """RealPage rent roll: "Actual Rent" must win over the adjacent "Market Rent" column, same principle as Yardi's Rent Charge, different platform's own terminology."""
    result = parse_csv_rent_roll(
        _read("synthetic_realpage_rent_roll.csv"),
        "synthetic_realpage_rent_roll.csv",
        base_property_address="Foothill Corporate Center",
    )
    assert len(result["leases"]) == 3, result["leases"]
    assert len(result["skipped_rows"]) == 2  # VACANT unit + trailing Total row

    by_tenant = {l["extracted_fields"]["tenant"]["value"]: l["extracted_fields"] for l in result["leases"]}
    alpine = by_tenant["Alpine Consulting Group"]
    assert alpine["rent_amount"]["value"] == "$4,400.00"  # Actual Rent, NOT Market Rent's $4,800.00
    assert alpine["property_address"]["value"] == "Foothill Corporate Center, Suite 100"

    cedar = by_tenant["Cedar Ridge Insurance"]
    assert cedar["rent_amount"]["value"] == "$5,900.00"  # not Market Rent's $6,300.00

    print("✓ test_synthetic_realpage_csv_imports_correctly: PASS")


def test_synthetic_mri_csv_imports_correctly():
    """MRI rent roll: "Occupant" for tenant, bare "Commence"/"Expire" (no "date" suffix) for lease dates -- MRI-specific terminology, not just Yardi/AppFolio's."""
    result = parse_csv_rent_roll(
        _read("synthetic_mri_rent_roll.csv"),
        "synthetic_mri_rent_roll.csv",
        base_property_address="Foothill Corporate Center",
    )
    assert len(result["leases"]) == 3, result["leases"]
    assert len(result["skipped_rows"]) == 2  # VACANT unit + trailing Total row

    by_tenant = {l["extracted_fields"]["tenant"]["value"]: l["extracted_fields"] for l in result["leases"]}
    harborview = by_tenant["Harborview Logistics"]
    assert harborview["rent_amount"]["value"] == "$7,150.00"
    assert harborview["property_address"]["value"] == "Foothill Corporate Center, Suite 200"
    assert harborview["lease_start_date"]["value"] == "03/01/2021"
    assert harborview["lease_end_date"]["value"] == "02/28/2027"

    print("✓ test_synthetic_mri_csv_imports_correctly: PASS")


def test_synthetic_buildium_csv_multi_property_imports_correctly():
    """Buildium: simpler terminology, but ALSO a genuine multi-property export (common for a Buildium-managed portfolio of scattered small properties) -- same per-row Property column mechanism as the AppFolio fixture, different platform."""
    result = parse_csv_rent_roll(_read("synthetic_buildium_rent_roll.csv"), "synthetic_buildium_rent_roll.csv")
    assert len(result["leases"]) == 3, result["leases"]
    assert result["skipped_rows"] == []

    by_tenant = {l["extracted_fields"]["tenant"]["value"]: l["extracted_fields"] for l in result["leases"]}
    dana = by_tenant["Dana Whitfield"]
    assert dana["property_address"]["value"] == "14 Chestnut St, Unit 1"
    marcus = by_tenant["Marcus Ibe"]
    assert marcus["property_address"]["value"] == "14 Chestnut St, Unit 2"
    dentistry = by_tenant["Redwood Family Dentistry"]
    assert dentistry["property_address"]["value"] == "508 Poplar Ave, Suite B"

    # Two genuinely different buildings, not merged.
    assert dana["property_address"]["value"] != dentistry["property_address"]["value"]

    print("✓ test_synthetic_buildium_csv_multi_property_imports_correctly: PASS")


def test_synthetic_fixtures_round_trip_through_the_real_import_route():
    """
    Same fixtures, but through the real Flask route (POST /leases/
    import-rent-roll) via test_client(), not a direct function call --
    confirms the multipart upload + property_address form field + JSON
    response shape all work end to end for PMS-shaped files specifically,
    the same way test_rent_roll_import_api.py already does for the
    generic broker-CSV case.
    """
    from app.api import app

    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["email"] = "test-analyst@example.com"
        sess["name"] = "Test Analyst"
        sess["role"] = "analyst"
    created_ids = []
    try:
        for filename, property_address, expected_count in [
            ("synthetic_yardi_rent_roll.csv", "Riverside Commons Shopping Center", 3),
            ("synthetic_appfolio_rent_roll.csv", None, 3),
            ("synthetic_realpage_rent_roll.csv", "Foothill Corporate Center", 3),
            ("synthetic_mri_rent_roll.csv", "Foothill Corporate Center", 3),
            ("synthetic_buildium_rent_roll.csv", None, 3),
        ]:
            data = {"file": (open(os.path.join(FIXTURES_DIR, filename), "rb"), filename)}
            if property_address:
                data["property_address"] = property_address
            resp = client.post("/leases/import-rent-roll", data=data, content_type="multipart/form-data")
            assert resp.status_code == 201, (filename, resp.get_json())
            body = resp.get_json()
            assert body["imported_count"] == expected_count, (filename, body)
            created_ids.extend(l["id"] for l in body["leases"])
    finally:
        for lease_id in created_ids:
            client.delete(f"/leases/{lease_id}")

    print("✓ test_synthetic_fixtures_round_trip_through_the_real_import_route: PASS")


if __name__ == "__main__":
    test_synthetic_yardi_csv_imports_correctly()
    test_synthetic_yardi_xlsx_imports_correctly()
    test_synthetic_appfolio_csv_multi_property_imports_correctly()
    test_synthetic_realpage_csv_imports_correctly()
    test_synthetic_mri_csv_imports_correctly()
    test_synthetic_buildium_csv_multi_property_imports_correctly()
    test_synthetic_fixtures_round_trip_through_the_real_import_route()
    print("\nAll PMS synthetic fixture tests passed.")
