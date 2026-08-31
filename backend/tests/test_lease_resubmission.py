"""
Tests for the "resubmit lease" workflow (Canvas-style: replace, don't
duplicate): database.py's supersede_lease/get_lease_version_chain/
repoint_lease_references/get_stale_open_discrepancies_for_lease, and
POST /leases/<id>/resubmit, GET /leases/<id>/versions, plus the
possible-resubmission hint on POST /leases.

Uses real generated PDFs (reportlab) run through the actual extraction
pipeline via the real HTTP routes -- not synthetic discrepancy rows --
so this exercises the same code path a real resubmission would, same
convention as test_multipage_field.py / create_red_flag_leases.py.
"""

import os
import sys
import tempfile
import io

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch

from app.api import app
from app import database

FIXTURES_DIR = os.path.dirname(__file__)


def _fresh_temp_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    database.configure(tmp.name)
    database.init_db()
    return tmp.name


def _authed_client():
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["email"] = "test-analyst@example.com"
        sess["name"] = "Test Analyst"
        sess["role"] = "analyst"
    return client


def _viewer_client():
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = 2
        sess["email"] = "viewer@example.com"
        sess["name"] = "Test Viewer"
        sess["role"] = "viewer"
    return client


# ------------------------------------------------------------------
# PDF fixture builder -- based verbatim on create_commercial_lease.py's
# proven-working clause wording, with the insurance / default-and-cure
# / security-deposit clauses individually toggleable, everything else
# (tenant, landlord, property, dates, rent) held fixed across versions
# so a "resubmission" is recognized as a correction of the SAME lease.
# ------------------------------------------------------------------

def _build_lease_pdf(path, include_insurance, include_cure, include_deposit):
    c = canvas.Canvas(path, pagesize=letter, invariant=1)
    width, height = letter
    left_margin = 1 * inch
    right_margin = width - 1 * inch
    max_width = right_margin - left_margin
    line_height = 0.22 * inch

    c.setFont("Helvetica-Bold", 16)
    c.drawString(left_margin, height - 1 * inch, "COMMERCIAL LEASE AGREEMENT")
    c.setFont("Helvetica", 11)

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
    ]

    if include_deposit:
        paragraphs.append(
            "5. SECURITY DEPOSIT. Upon execution of this Lease, Tenant shall deposit "
            "with Landlord the sum of $12,500.00 as a security deposit, to be held "
            "by Landlord as security for Tenant's faithful performance of its "
            "obligations hereunder."
        )

    paragraphs.append(
        "6. COMMON AREA MAINTENANCE. In addition to Base Rent, Tenant shall pay "
        "its proportionate share of Common Area Maintenance (CAM) charges, "
        "currently estimated at $875.00 per month, subject to annual "
        "reconciliation based on actual operating expenses."
    )
    paragraphs.append(
        "7. RENEWAL OPTION. Provided Tenant is not then in default, Tenant "
        "shall have two (2) options to renew this Lease for additional terms of "
        "five (5) years each, exercisable by written notice to Landlord not "
        "less than one hundred eighty (180) days prior to expiration of the "
        "then-current term. Rent during each renewal term shall be adjusted to "
        "the then-prevailing fair market rate."
    )
    paragraphs.append(
        "8. PERMITTED USE. The Premises shall be used solely for the operation "
        "of a retail coffee shop and roastery, and for no other purpose without "
        "the prior written consent of Landlord."
    )

    if include_insurance:
        paragraphs.append(
            "10. INSURANCE. Tenant shall, at its own expense, maintain commercial "
            "general liability insurance with a minimum coverage of $2,000,000 per "
            "occurrence, naming Landlord as an additional insured."
        )
    if include_cure:
        paragraphs.append(
            "11. DEFAULT AND CURE. If Tenant fails to pay any installment of Base "
            "Rent when due, and such failure continues for ten (10) days after "
            "written notice from Landlord, Tenant shall be in default under this "
            "Lease and Landlord may pursue all remedies available at law."
        )

    def wrap_text(text, font_name, font_size, max_w):
        words = text.split(" ")
        lines, current = [], ""
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

    y = height - 1.6 * inch
    for para in paragraphs:
        for line in wrap_text(para, "Helvetica", 11, max_width):
            if y < 1 * inch:
                c.showPage()
                c.setFont("Helvetica", 11)
                y = height - 1 * inch
            c.drawString(left_margin, y, line)
            y -= line_height
        y -= line_height * 0.6
    c.save()


def _v1_bytes():
    """Missing insurance AND default/cure clauses; has the security deposit clause."""
    path = os.path.join(FIXTURES_DIR, "_resubmit_test_v1.pdf")
    _build_lease_pdf(path, include_insurance=False, include_cure=False, include_deposit=True)
    with open(path, "rb") as f:
        return f.read()


def _v2_bytes():
    """Corrected: insurance clause added (fixes one issue), default/cure still missing (stays open), security deposit REMOVED (a genuinely new issue)."""
    path = os.path.join(FIXTURES_DIR, "_resubmit_test_v2.pdf")
    _build_lease_pdf(path, include_insurance=True, include_cure=False, include_deposit=False)
    with open(path, "rb") as f:
        return f.read()


def _upload(client, content, filename="lease.pdf"):
    return client.post("/leases", data={"file": (io.BytesIO(content), filename)}, content_type="multipart/form-data")


def _resubmit(client, lease_id, content, filename="lease_corrected.pdf"):
    return client.post(f"/leases/{lease_id}/resubmit", data={"file": (io.BytesIO(content), filename)}, content_type="multipart/form-data")


# ------------------------------------------------------------------
# Core end-to-end scenario
# ------------------------------------------------------------------

def test_resubmit_replaces_lease_archives_old_and_reconciles_discrepancies():
    db_path = _fresh_temp_db()
    try:
        client = _authed_client()

        # Upload v1 -- missing insurance + default/cure clauses.
        resp = _upload(client, _v1_bytes(), "original.pdf")
        assert resp.status_code == 201, resp.get_json()
        old_lease = resp.get_json()["leases"][0]
        old_id = old_lease["id"]
        assert old_lease["status"] == "active"
        assert old_lease["version_number"] == 1

        # Real risk analysis must have flagged both missing clauses as open discrepancies.
        resp = client.get(f"/leases/{old_id}/risks")
        assert resp.status_code == 200
        categories = [f["category"] for f in resp.get_json()]
        assert categories.count("missing_clause") == 2, f"expected 2 missing_clause flags, got {categories}"

        open_discs_before = client.get(f"/discrepancies?lease_id={old_id}&status=open").get_json()
        fields_flagged_before = {d["field"] for d in open_discs_before}
        assert fields_flagged_before == {"insurance_requirements", "default_cure_period"}

        # Tag and comment the old lease -- must carry forward to the new version.
        client.post(f"/leases/{old_id}/tags", json={"tag": "needs-review"})
        client.post(f"/leases/{old_id}/comments", json={"body": "Flagged for legal review."})

        # Resubmit a corrected version: insurance fixed, cure period still
        # missing, security deposit clause removed (a genuinely new issue).
        resp = _resubmit(client, old_id, _v2_bytes())
        assert resp.status_code == 201, resp.get_json()
        result = resp.get_json()
        new_id = result["lease"]["id"]
        assert new_id != old_id
        assert result["previous_lease_id"] == old_id
        assert result["version_number"] == 2
        assert result["discrepancies_auto_resolved"] == 1, result

        # --- Requirement 3/4: old archived, new is current everywhere ---
        assert result["lease"]["status"] == "active"
        assert result["lease"]["version_number"] == 2
        assert result["lease"]["supersedes_lease_id"] == old_id

        old_after = client.get(f"/leases/{old_id}").get_json()
        assert old_after["status"] == "superseded", "old version must be archived, not deleted"
        assert database.get_lease(old_id) is not None, "old version must still exist in the DB"

        active_list = client.get("/leases").get_json()
        active_ids = {l["id"] for l in active_list}
        assert new_id in active_ids, "new version must appear in the default active lease list"
        assert old_id not in active_ids, "old version must NOT appear in the default active lease list"

        # --- Requirement 2: discrepancies reconciled against new data ---
        new_open = {d["field"]: d for d in client.get(f"/discrepancies?lease_id={new_id}&status=open").get_json()}
        assert "insurance_requirements" not in new_open, "fixed issue must not still be open"
        assert "default_cure_period" in new_open, "still-present issue must remain open"
        assert "security_deposit" in new_open, "a genuinely new issue must create a new discrepancy"

        new_resolved = {d["field"]: d for d in client.get(f"/discrepancies?lease_id={new_id}&status=resolved").get_json()}
        assert "insurance_requirements" in new_resolved, "fixed issue must be auto-resolved"
        insurance_disc = new_resolved["insurance_requirements"]
        assert insurance_disc["lease_id"] == new_id, "resolved discrepancy must be repointed to the new lease id"

        resolutions = database.get_discrepancy_resolutions(insurance_disc["id"])
        assert resolutions[-1]["resolved_by"] == "System"
        assert "resubmit" in resolutions[-1]["note"].lower()

        # The still-open discrepancy must have been refreshed onto the new lease id too.
        cure_disc = new_open["default_cure_period"]
        assert cure_disc["lease_id"] == new_id

        # --- Requirement 5: activity feed ---
        activity = client.get("/activity?limit=10").get_json()
        resubmit_entries = [a for a in activity if a["action_type"] == "lease_resubmitted"]
        assert len(resubmit_entries) == 1
        assert "Test Analyst" in resubmit_entries[0]["description"]
        assert "v2" in resubmit_entries[0]["description"]
        assert resubmit_entries[0]["lease_id"] == new_id

        # --- Tags/comments carried forward ---
        new_tags = client.get(f"/leases/{new_id}").get_json()["tags"]
        assert "needs-review" in new_tags
        new_comments = client.get(f"/leases/{new_id}/comments").get_json()
        assert any("legal review" in c["body"] for c in new_comments)

        # --- Version history walkable from either id ---
        for probe_id in (old_id, new_id):
            versions = client.get(f"/leases/{probe_id}/versions").get_json()["versions"]
            assert [v["version_number"] for v in versions] == [1, 2]
            assert versions[0]["id"] == old_id and versions[0]["is_current"] is False
            assert versions[1]["id"] == new_id and versions[1]["is_current"] is True
    finally:
        os.unlink(db_path)
        for f in ("_resubmit_test_v1.pdf", "_resubmit_test_v2.pdf"):
            p = os.path.join(FIXTURES_DIR, f)
            if os.path.exists(p):
                os.remove(p)
    print("✓ test_resubmit_replaces_lease_archives_old_and_reconciles_discrepancies: PASS")


def test_resubmitted_lease_excluded_from_portfolio_wide_views():
    db_path = _fresh_temp_db()
    try:
        client = _authed_client()
        old_id = _upload(client, _v1_bytes(), "a.pdf").get_json()["leases"][0]["id"]

        summary_before = client.get("/portfolio/summary").get_json()
        assert summary_before["lease_count"] == 1

        _resubmit(client, old_id, _v2_bytes())

        summary_after = client.get("/portfolio/summary").get_json()
        assert summary_after["lease_count"] == 1, "resubmission must not double-count the lease portfolio-wide"
    finally:
        os.unlink(db_path)
        for f in ("_resubmit_test_v1.pdf", "_resubmit_test_v2.pdf"):
            p = os.path.join(FIXTURES_DIR, f)
            if os.path.exists(p):
                os.remove(p)
    print("✓ test_resubmitted_lease_excluded_from_portfolio_wide_views: PASS")


# ------------------------------------------------------------------
# Validation / edge cases
# ------------------------------------------------------------------

def test_resubmit_route_404_for_nonexistent_lease():
    db_path = _fresh_temp_db()
    try:
        client = _authed_client()
        resp = _resubmit(client, 999999, _v2_bytes())
        assert resp.status_code == 404
    finally:
        os.unlink(db_path)
        p = os.path.join(FIXTURES_DIR, "_resubmit_test_v2.pdf")
        if os.path.exists(p):
            os.remove(p)
    print("✓ test_resubmit_route_404_for_nonexistent_lease: PASS")


def test_resubmit_route_409_for_already_superseded_lease():
    db_path = _fresh_temp_db()
    try:
        client = _authed_client()
        old_id = _upload(client, _v1_bytes(), "a.pdf").get_json()["leases"][0]["id"]
        first = _resubmit(client, old_id, _v2_bytes())
        assert first.status_code == 201
        new_id = first.get_json()["lease"]["id"]

        # Resubmitting the now-archived original again must be rejected,
        # and must tell the caller which id IS current.
        second = _resubmit(client, old_id, _v2_bytes())
        assert second.status_code == 409
        assert second.get_json()["current_lease_id"] == new_id
    finally:
        os.unlink(db_path)
        for f in ("_resubmit_test_v1.pdf", "_resubmit_test_v2.pdf"):
            p = os.path.join(FIXTURES_DIR, f)
            if os.path.exists(p):
                os.remove(p)
    print("✓ test_resubmit_route_409_for_already_superseded_lease: PASS")


def test_resubmit_route_requires_login_and_analyst_role():
    db_path = _fresh_temp_db()
    try:
        analyst = _authed_client()
        old_id = _upload(analyst, _v1_bytes(), "a.pdf").get_json()["leases"][0]["id"]

        anon = app.test_client()
        resp = anon.post(f"/leases/{old_id}/resubmit", data={"file": (io.BytesIO(_v2_bytes()), "x.pdf")}, content_type="multipart/form-data")
        assert resp.status_code == 401

        viewer = _viewer_client()
        resp = viewer.post(f"/leases/{old_id}/resubmit", data={"file": (io.BytesIO(_v2_bytes()), "x.pdf")}, content_type="multipart/form-data")
        assert resp.status_code == 403
    finally:
        os.unlink(db_path)
        for f in ("_resubmit_test_v1.pdf", "_resubmit_test_v2.pdf"):
            p = os.path.join(FIXTURES_DIR, f)
            if os.path.exists(p):
                os.remove(p)
    print("✓ test_resubmit_route_requires_login_and_analyst_role: PASS")


def test_resubmit_route_rejects_missing_file():
    db_path = _fresh_temp_db()
    try:
        client = _authed_client()
        old_id = _upload(client, _v1_bytes(), "a.pdf").get_json()["leases"][0]["id"]
        resp = client.post(f"/leases/{old_id}/resubmit", data={}, content_type="multipart/form-data")
        assert resp.status_code == 400
    finally:
        os.unlink(db_path)
        p = os.path.join(FIXTURES_DIR, "_resubmit_test_v1.pdf")
        if os.path.exists(p):
            os.remove(p)
    print("✓ test_resubmit_route_rejects_missing_file: PASS")


def test_resubmit_route_rejects_amendment_document_type():
    db_path = _fresh_temp_db()
    try:
        client = _authed_client()
        old_id = _upload(client, _v1_bytes(), "a.pdf").get_json()["leases"][0]["id"]
        amendment_id = database.insert_lease("amend.pdf", {}, document_type="amendment", base_lease_id=old_id)
        resp = _resubmit(client, amendment_id, _v2_bytes())
        assert resp.status_code == 400
    finally:
        os.unlink(db_path)
        for f in ("_resubmit_test_v1.pdf", "_resubmit_test_v2.pdf"):
            p = os.path.join(FIXTURES_DIR, f)
            if os.path.exists(p):
                os.remove(p)
    print("✓ test_resubmit_route_rejects_amendment_document_type: PASS")


# ------------------------------------------------------------------
# database.py unit-level checks
# ------------------------------------------------------------------

def test_get_lease_version_chain_single_version():
    db_path = _fresh_temp_db()
    try:
        lease_id = database.insert_lease("a.pdf", {})
        chain = database.get_lease_version_chain(lease_id)
        assert len(chain) == 1
        assert chain[0]["id"] == lease_id
        assert chain[0]["status"] == "active"
        assert chain[0]["version_number"] == 1
    finally:
        os.unlink(db_path)
    print("✓ test_get_lease_version_chain_single_version: PASS")


def test_repoint_lease_references_moves_everything():
    db_path = _fresh_temp_db()
    try:
        old_id = database.insert_lease("a.pdf", {})
        new_id = database.insert_lease("b.pdf", {}, status="active", supersedes_lease_id=old_id, version_number=2)

        natural_key = f"lease_risk:{old_id}:missing_clause:insurance_requirements:0"
        disc_id = database.upsert_discrepancy("lease_risk_flag", natural_key, "missing_clause", "msg", {}, lease_id=old_id)
        database.add_lease_tag(old_id, "important")
        database.add_comment("Analyst", "note here", lease_id=old_id)

        database.repoint_lease_references(old_id, new_id)

        updated = database.get_discrepancy(disc_id)
        assert updated["lease_id"] == new_id
        assert updated["natural_key"] == f"lease_risk:{new_id}:missing_clause:insurance_requirements:0", \
            "natural_key text itself must be repointed too, not just the lease_id column"
        assert database.get_lease_tags(new_id) == ["important"]
        assert database.get_lease_tags(old_id) == []
        assert any(c["body"] == "note here" for c in database.get_lease_comments(new_id))
        assert database.get_lease_comments(old_id) == []
    finally:
        os.unlink(db_path)
    print("✓ test_repoint_lease_references_moves_everything: PASS")


def test_resubmit_does_not_let_a_carried_forward_amendment_override_the_correction():
    """
    The real bug this guards against: repoint_lease_references used to
    carry amendments forward onto the new resubmitted lease id. Since
    get_effective_fields' "latest non-null amendment wins" rule means
    an amendment always beats the base row for any field it sets, a
    carried-forward amendment would keep silently overriding the very
    field the resubmission corrected -- found live via the export ->
    edit -> resubmit round trip, where a corrected rent amount kept
    reverting on every read after resubmitting.
    """
    db_path = _fresh_temp_db()
    try:
        client = _authed_client()

        # v1: missing insurance + cure clauses, has a security deposit clause.
        old_id = _upload(client, _v1_bytes(), "original.pdf").get_json()["leases"][0]["id"]

        # An amendment overrides rent_amount on the OLD lease.
        amendment_id = database.insert_lease(
            "amend.pdf",
            {**database.get_lease(old_id)["extracted_fields"], "rent_amount": {"value": "$9,999.00", "source": {"page": 1, "quote": "amended rent"}, "confidence": "high"}},
            document_type="amendment", base_lease_id=old_id,
        )
        effective_before = database.get_effective_fields(old_id)
        assert effective_before["rent_amount"]["value"] == "$9,999.00", "amendment must genuinely govern this field before resubmitting"

        # Resubmit a corrected document -- its own rent_amount is $6,250.00 (see _build_lease_pdf).
        resp = _resubmit(client, old_id, _v2_bytes())
        assert resp.status_code == 201, resp.get_json()
        new_id = resp.get_json()["lease"]["id"]

        effective_after = database.get_effective_fields(new_id)
        assert effective_after["rent_amount"]["value"] == "$6,250.00", \
            "the resubmitted document's own value must win -- a carried-forward old amendment must not silently override it"

        # The amendment itself is untouched, permanent history -- still
        # attached to the archived OLD lease, not deleted.
        assert database.get_lease(amendment_id)["base_lease_id"] == old_id
        old_effective = database.get_effective_fields(old_id)
        assert old_effective["rent_amount"]["value"] == "$9,999.00", "the archived old version's own history is unaffected"
    finally:
        os.unlink(db_path)
        for f in ("_resubmit_test_v1.pdf", "_resubmit_test_v2.pdf"):
            p = os.path.join(FIXTURES_DIR, f)
            if os.path.exists(p):
                os.remove(p)
    print("✓ test_resubmit_does_not_let_a_carried_forward_amendment_override_the_correction: PASS")


def test_get_stale_open_discrepancies_excludes_untouched_types():
    """A rent_roll_reconciliation discrepancy must never be treated as 'stale' by this check -- it's never touched by the lease-risk sync pass in the first place, so absence from that pass proves nothing about it."""
    db_path = _fresh_temp_db()
    try:
        lease_id = database.insert_lease("a.pdf", {})
        risk_id = database.upsert_discrepancy("lease_risk_flag", "nk1", "missing_clause", "msg", {}, lease_id=lease_id)
        recon_id = database.upsert_discrepancy("rent_roll_reconciliation", "nk2", "rent_roll_reconciliation", "msg", {}, lease_id=lease_id)

        stale = database.get_stale_open_discrepancies_for_lease(lease_id, ["lease_risk_flag", "cross_lease_mismatch"], keep_ids=[])
        stale_ids = {d["id"] for d in stale}
        assert risk_id in stale_ids
        assert recon_id not in stale_ids
    finally:
        os.unlink(db_path)
    print("✓ test_get_stale_open_discrepancies_excludes_untouched_types: PASS")


# ------------------------------------------------------------------
# Duplicate/resubmission-hint detection on normal upload
# ------------------------------------------------------------------

def test_upload_route_surfaces_possible_resubmission_hint():
    db_path = _fresh_temp_db()
    try:
        client = _authed_client()
        first = _upload(client, _v1_bytes(), "a.pdf").get_json()["leases"][0]
        assert first["possible_resubmission_of"] is None, "nothing existed yet to match against"

        second = _upload(client, _v2_bytes(), "b.pdf").get_json()["leases"][0]
        hint = second["possible_resubmission_of"]
        assert hint is not None, "same tenant + property address as an existing active lease should be flagged"
        assert hint["lease_id"] == first["id"]
    finally:
        os.unlink(db_path)
        for f in ("_resubmit_test_v1.pdf", "_resubmit_test_v2.pdf"):
            p = os.path.join(FIXTURES_DIR, f)
            if os.path.exists(p):
                os.remove(p)
    print("✓ test_upload_route_surfaces_possible_resubmission_hint: PASS")


if __name__ == "__main__":
    test_resubmit_replaces_lease_archives_old_and_reconciles_discrepancies()
    test_resubmitted_lease_excluded_from_portfolio_wide_views()
    test_resubmit_route_404_for_nonexistent_lease()
    test_resubmit_route_409_for_already_superseded_lease()
    test_resubmit_route_requires_login_and_analyst_role()
    test_resubmit_route_rejects_missing_file()
    test_resubmit_route_rejects_amendment_document_type()
    test_get_lease_version_chain_single_version()
    test_repoint_lease_references_moves_everything()
    test_resubmit_does_not_let_a_carried_forward_amendment_override_the_correction()
    test_get_stale_open_discrepancies_excludes_untouched_types()
    test_upload_route_surfaces_possible_resubmission_hint()
    print("\nAll lease resubmission tests passed.")
