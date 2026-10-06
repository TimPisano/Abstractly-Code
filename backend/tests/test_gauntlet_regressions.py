"""
Regression tests for bugs found by the overnight reliability gauntlet
(backend/tools/gauntlet/, branch qa/overnight-gauntlet). One test (or a
small group) per fix; each was confirmed failing before its fix landed.

Pure-function tests where possible (the detectors in deal_mismatch.py take
plain lease dicts), so these run in milliseconds and need no fixtures.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.portfolio import FIELD_NAMES, _normalize_address, _normalize_building_address
from app import deal_mismatch as dm
from datetime import date

TODAY = date(2026, 10, 5)


def _fields(**overrides):
    out = {}
    for name in FIELD_NAMES:
        v = overrides.get(name)
        out[name] = ({"value": v, "source": {"page": 1, "quote": str(v)}, "confidence": "high"} if v is not None
                     else {"value": None, "source": None, "confidence": None})
    return out


_ids = iter(range(1, 10_000))


def _rr(**f):
    return {"id": next(_ids), "filename": "rent_roll.csv", "extracted_fields": _fields(**f)}


def _doc(**f):
    return {"id": next(_ids), "filename": "lease.pdf", "extracted_fields": _fields(**f)}


def _client_with_fresh_db(team_id=1):
    """Fresh temp DB + an analyst session on a real team (real routes, real scoping)."""
    import tempfile
    from app.api import app
    from app import database, usage_limits
    from _session_users import sync_session_user
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    database.configure(tmp.name)
    database.init_db()
    usage_limits._reset_extraction_rate_limit_for_tests()
    client = app.test_client()
    with client.session_transaction() as s:
        s["user_id"] = 7
        s["team_id"] = team_id
        s["email"] = "gauntlet-test@abstractly.test"
        s["name"] = "Gauntlet Test"
        s["role"] = "analyst"
        sync_session_user(s)
    return client, tmp.name


def _post(client, url, filename, data, form=None):
    import io
    payload = dict(form or {})
    payload["file"] = (io.BytesIO(data), filename)
    return client.post(url, data=payload, content_type="multipart/form-data")


def _types(rows):
    return sorted(r["discrepancy_type"] for r in rows)


# ---------------------------------------------------------------- unit matching
def test_same_unit_matches_across_designator_wording():
    """
    The rent-roll importer turns a bare "101" into "<typed address>, Suite 101";
    a multifamily lease says "Apt 101" (or "Unit 101", "#101") with the city
    after it. Same unit -- before the fix every such pair was reported as a
    false unit_no_lease + lease_no_unit and every real check on it was lost.
    """
    rr = "1450 Cedar Bend Dr, Austin, TX 78745, Suite 101"
    for lease in ("1450 Cedar Bend Dr, Apt 101, Austin, TX 78745",
                  "1450 Cedar Bend Dr, Unit 101, Austin, TX 78745",
                  "1450 Cedar Bend Dr #101, Austin, TX 78745",
                  "1450 Cedar Bend Dr, Apartment No. 101, Austin, TX 78745",
                  "1450 Cedar Bend Dr, Apt #101, Austin, TX 78745",
                  "1450 Cedar Bend Drive, Austin, TX 78745, Suite 101",
                  "1450 Cedar Bend Dr, Austin, TX 78745, Suite 0101"):
        assert _normalize_address(rr) == _normalize_address(lease), (lease, _normalize_address(rr), _normalize_address(lease))
    print("✓ test_same_unit_matches_across_designator_wording: PASS")


def test_different_units_and_buildings_still_do_not_match():
    a = "1450 Cedar Bend Dr, Austin, TX 78745, Suite 101"
    for other in ("1450 Cedar Bend Dr, Austin, TX 78745, Suite 102",
                  "1450 Cedar Bend Dr, Austin, TX 78745, Suite 1010",
                  "1452 Cedar Bend Dr, Austin, TX 78745, Suite 101",
                  "1450 Cedar Bend Dr, Austin, TX 78745",
                  "1450 Cedar Bend Ct, Austin, TX 78745, Suite 101"):
        assert _normalize_address(a) != _normalize_address(other), other
    # "Unity" is a street name, not "Unit y".
    assert _normalize_building_address("12 Unity Ave, Suite 3") == _normalize_building_address("12 Unity Ave, Suite 4")
    assert _normalize_building_address("12 Unity Ave") != _normalize_building_address("12 Ave")
    print("✓ test_different_units_and_buildings_still_do_not_match: PASS")


def test_report_pairs_apt_lease_with_suite_rent_roll_row():
    rr = _rr(tenant="Greta Fairbanks", rent_amount="$1,600.00", property_address="1450 Cedar Bend Dr, Austin, TX 78745, Suite 101",
             lease_start_date="04/01/2026", lease_end_date="03/31/2027")
    doc = _doc(tenant="Greta Fairbanks", rent_amount="$1,450.00", property_address="1450 Cedar Bend Dr, Apt 101, Austin, TX 78745",
               lease_start_date="April 1, 2026", lease_end_date="March 31, 2027")
    rows = []
    for det in dm._DETECTORS:
        rows += det([rr, doc], TODAY) if det in dm._DATE_AWARE_DETECTORS else det([rr, doc])
    assert _types(rows) == ["rent_mismatch"], _types(rows)
    print("✓ test_report_pairs_apt_lease_with_suite_rent_roll_row: PASS")


def test_typed_long_street_suffix_matches_abbreviated_lease_building():
    """Uploader typed "Drive", the leases say "Dr": same building for report scoping."""
    assert _normalize_building_address("1450 Cedar Bend Drive, Austin, TX 78745") == \
        _normalize_building_address("1450 Cedar Bend Dr., Apt 101, Austin, TX 78745")
    print("✓ test_typed_long_street_suffix_matches_abbreviated_lease_building: PASS")


# ---------------------------------------------------------------- tenant names
def test_tenant_name_order_and_co_residents_are_not_a_mismatch():
    """
    Yardi/AppFolio export "SORENSEN, CELESTE"; the lease says "Celeste
    Sorensen". A rent roll lists "A & B" where the lease names "A and B" (or
    only one of them). None of these is a different tenant -- before the fix
    each was a high-severity tenant_mismatch.
    """
    same = [("SORENSEN, CELESTE", "Celeste Sorensen"),
            ("Noor Bellweather & Lucia Xenakis", "Noor Bellweather and Lucia Xenakis"),
            ("Noor Bellweather & Lucia Xenakis", "Lucia Xenakis"),
            ("Smith, John Q.", "John Q. Smith"),
            ("John Smith", "John Q. Smith")]
    for rr_name, lease_name in same:
        rr = _rr(tenant=rr_name, rent_amount="$1,000.00", property_address="1 A St, Suite 1")
        doc = _doc(tenant=lease_name, rent_amount="$1,000.00", property_address="1 A St, Apt 1")
        assert dm.detect_tenant_mismatch([rr, doc]) == [], (rr_name, lease_name)
    different = [("Mateo Nakamura", "Malik Nakamura"), ("NAKAMURA, MATEO", "Mateo Ingram"),
                 ("Avery Fairbanks", "Greta Okafor"), ("Jordan Lee & Sam Lee", "Pat Lee")]
    for rr_name, lease_name in different:
        rr = _rr(tenant=rr_name, rent_amount="$1,000.00", property_address="1 A St, Suite 1")
        doc = _doc(tenant=lease_name, rent_amount="$1,000.00", property_address="1 A St, Apt 1")
        assert _types(dm.detect_tenant_mismatch([rr, doc])) == ["tenant_mismatch"], (rr_name, lease_name)
    print("✓ test_tenant_name_order_and_co_residents_are_not_a_mismatch: PASS")


# ---------------------------------------------------------------- CSV decoding
def test_csv_rent_roll_decoding_cp1252_utf16_and_binary():
    """
    Excel on Windows saves CSV as Windows-1252 ("José Peña" became
    "Jos\ufffd Pe\ufffda" and then a false tenant_mismatch); Excel's
    "Unicode Text" is UTF-16 with a BOM; and a PNG renamed .csv crashed the
    import route with a 500 (_csv.Error: line contains NUL).
    """
    from app.rent_roll_import import parse_rent_roll_file, RentRollImportError
    rows = "Unit,Tenant,Rent\r\n101,José Peña,\"$1,200.00\"\r\n102,Zoë Lefèvre,1300\r\n"
    got = parse_rent_roll_file(rows.encode("cp1252"), "rr.csv", "1 A St")
    assert [l["extracted_fields"]["tenant"]["value"] for l in got["leases"]] == ["José Peña", "Zoë Lefèvre"], got["leases"]
    got = parse_rent_roll_file(rows.encode("utf-8"), "rr.csv", "1 A St")
    assert [l["extracted_fields"]["tenant"]["value"] for l in got["leases"]] == ["José Peña", "Zoë Lefèvre"]
    got = parse_rent_roll_file(rows.encode("utf-16"), "rr.csv", "1 A St")
    assert len(got["leases"]) == 2 and got["leases"][0]["extracted_fields"]["tenant"]["value"] == "José Peña"
    png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00(\x00\x00\x00(\x08\x02\x00\x00\x00"
    try:
        parse_rent_roll_file(png, "rr.csv", "1 A St")
        raise AssertionError("binary file accepted")
    except RentRollImportError as e:
        assert "text" in str(e).lower(), str(e)
    print("✓ test_csv_rent_roll_decoding_cp1252_utf16_and_binary: PASS")


# ---------------------------------------------------------------- rent-roll rows vs lease documents
def test_rent_roll_rows_are_rent_roll_rows_whatever_the_file_format():
    """
    Whether a record is a rent-roll row or a lease document was decided by
    the file EXTENSION (only .csv/.xlsx counted as rent rolls). A rent roll
    imported from .tsv/.txt/.xls/.docx/.pdf was therefore treated as a pile
    of LEASES by the Deal Mismatch Report: every unit came back as
    lease_no_unit and nothing was compared. The importer now marks its rows.
    """
    from app.portfolio import _is_rent_roll_import
    client, db = _client_with_fresh_db()
    try:
        tsv = "Unit\tTenant\tRent\n101\tAvery Ashgrove\t1200\n102\tJordan Bellweather\t1300\n".encode()
        r = _post(client, "/leases/import-rent-roll", "rent_roll.tsv", tsv, {"property_address": "9 Elm St, Austin, TX 78701"})
        assert r.status_code == 201, r.get_json()
        r = client.post("/portfolio/deal-mismatch-report", data={"property_address": "9 Elm St, Austin, TX 78701"},
                        content_type="multipart/form-data")
        types = sorted(row["discrepancy_type"] for row in r.get_json()["discrepancies"])
        assert types == ["unit_no_lease", "unit_no_lease"], types
    finally:
        os.unlink(db)
    assert _is_rent_roll_import({"filename": "rent_roll.pdf", "source_kind": "rent_roll"})
    assert not _is_rent_roll_import({"filename": "lease_abstract.xlsx", "source_kind": "document"})
    assert _is_rent_roll_import({"filename": "legacy_rent_roll.csv"})  # rows from before the marker existed
    print("✓ test_rent_roll_rows_are_rent_roll_rows_whatever_the_file_format: PASS")


def test_excel_unicode_text_txt_rent_roll_imports():
    """Excel's "Unicode Text" save: .txt, UTF-16, TAB-delimited. The route refused .txt outright."""
    client, db = _client_with_fresh_db()
    try:
        txt = "Unit\tTenant\tRent\r\n101\tAvery Ashgrove\t1,200.00\r\n102\tJosé Peña\t1,300.00\r\n".encode("utf-16")
        r = _post(client, "/leases/import-rent-roll", "rent_roll.txt", txt, {"property_address": "9 Elm St"})
        assert r.status_code == 201, r.get_json()
        body = r.get_json()
        assert body["imported_count"] == 2, body
        names = sorted(l.get("display_name", "") for l in body["leases"])
        assert any("José Peña" in n for n in names), names
    finally:
        os.unlink(db)
    print("✓ test_excel_unicode_text_txt_rent_roll_imports: PASS")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("\nAll gauntlet regression tests passed.")
