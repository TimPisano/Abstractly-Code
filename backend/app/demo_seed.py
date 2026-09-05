"""
Seed/reset logic for the standing demo account, used ONLY on the
separate demo deployment (DEMO_MODE=true) -- never touches the
production database, since it never runs unless that env var is set.
See DEPLOYMENT.md's "Demo deployment" section for how the two
deployments are kept apart.

Why a dedicated deployment instead of a demo user inside the real app:
this codebase has no per-account data isolation -- every user account
reads and writes the same shared `leases` table (see database.py's
schema). A demo login inside the production database would see every
real customer's leases, not a walled-off sandbox. Running this seed
module against a second, separate SQLite file (its own Render service,
its own DB_PATH) is what actually makes "walled off from real customer
data" true, by construction rather than by new per-row filtering logic.

`seed_demo_data()` is idempotent (no-op if the demo DB already has
leases) and is called once at startup when DEMO_MODE=true (see
api.py). `reset_demo_data()` wipes every content table in the CURRENT
database and reseeds -- safe here specifically because this module
only ever runs against the dedicated demo database, never production.
"""

import logging
import os
import tempfile

from app import auth, database

logger = logging.getLogger(__name__)

# Every login seeded on this deployment. All share the same sample
# leases/rent roll below (this app has no per-account isolation even
# within one database -- see the module docstring), so these are
# separate names for separate visitors to use, not separate sandboxes.
# All are "public" demo credentials, not secrets -- see DEPLOYMENT.md.
DEMO_ACCOUNTS = [
    {"email": "demo@abstractly.app", "name": "Demo Account", "password": "Demo2026!", "role": "analyst"},
    {"email": "holden@abstractly.demo", "name": "Holden", "password": "Holden12!", "role": "analyst"},
]

# Every content table a real user's activity can touch. Reset wipes
# all of them and nothing else -- `users`/`password_reset_tokens`
# stay untouched so the demo login itself (and the seeded admin/owner
# row from ADMIN_EMAIL/ADMIN_PASSWORD_HASH, if set on this deployment)
# survives a reset; `waitlist_signups` is the marketing landing page's
# own list, unrelated to any demo visitor's lease data.
_CONTENT_TABLES = [
    "activity_log",
    "lease_tags",
    "discrepancy_resolutions",
    "discrepancies",
    "alerts",
    "comments",
    "revenue_entries",
    "expense_entries",
    "assignments",
    "assistant_conversations",
    "message_thread_participants",
    "messages",
    "message_threads",
    "linked_email_accounts",
    "oauth_states",
    "tasks",
    "lease_field_edits",
    "ai_extraction_runs",
    "training_rounds",
    "leases",
]

_PROPERTY_A = "428 Harbor View Drive, Suite 200, Miami, FL 33131"
_PROPERTY_B = "1200 Innovation Parkway, Floor 4, Austin, TX 78701"


def _pdf_field(value, page, quote, confidence="high"):
    return {"value": value, "source": {"page": page, "quote": quote}, "confidence": confidence}


def _not_found():
    return {"value": None, "source": None, "confidence": None}


def _rent_roll_field(value, row, filename, quote):
    return {"value": value, "source": {"row": row, "file": filename, "quote": quote}, "confidence": "high"}


def _sample_pdf_leases():
    """Two abstracted leases, in the exact shape FieldExtractor.extract_fields() produces."""
    retail = {
        "tenant": _pdf_field("Coastal Brew Coffee Co.", 1, "Tenant: Coastal Brew Coffee Co., a Florida limited liability company"),
        "landlord": _pdf_field("Harborview Retail Partners LLC", 1, "Landlord: Harborview Retail Partners LLC"),
        "rent_amount": _pdf_field("$8,500.00", 2, "Monthly Rent: $8,500.00"),
        "lease_start_date": _pdf_field("03/01/2023", 1, "Commencement Date: March 1, 2023"),
        "lease_end_date": _pdf_field("02/28/2028", 1, "Expiration Date: February 28, 2028"),
        "property_address": _pdf_field(_PROPERTY_A, 1, _PROPERTY_A),
        "security_deposit": _pdf_field("$17,000.00", 2, "Security Deposit: $17,000.00"),
        "cam_charges": _pdf_field("$950.00", 3, "Monthly CAM Charges: $950.00"),
        "rent_escalation": _pdf_field(
            "3% annually on each anniversary of the Commencement Date", 3,
            "Base Rent shall increase by three percent (3%) annually on each anniversary of the Commencement Date",
        ),
        "renewal_options": _pdf_field(
            "One 5-year renewal option at 95% of then-current market rent", 4,
            "Tenant shall have one (1) option to renew for a period of five (5) years at ninety-five percent (95%) of then-current market rent",
        ),
        "permitted_use": _pdf_field("Retail coffee shop and cafe with incidental food service", 2, "Premises shall be used solely as a retail coffee shop and cafe"),
        "exclusivity_clause": _pdf_field(
            "Landlord shall not lease to another specialty coffee retailer within the shopping center", 5,
            "Landlord agrees not to lease space within the Shopping Center to another specialty coffee retailer", "medium",
        ),
        "insurance_requirements": _pdf_field("$2,000,000 general liability; Tenant named as additional insured", 4, "Commercial General Liability insurance with limits of not less than $2,000,000"),
        "default_cure_period": _pdf_field("10 days for monetary default, 30 days for non-monetary default", 6, "ten (10) days for monetary default and thirty (30) days for any non-monetary default"),
        "square_footage": _pdf_field("1,450 sq ft", 1, "consisting of approximately 1,450 square feet"),
    }

    office = {
        "tenant": _pdf_field("Northbridge Analytics Inc.", 1, "Tenant: Northbridge Analytics Inc., a Delaware corporation"),
        "landlord": _pdf_field("Innovation Parkway Holdings LLC", 1, "Landlord: Innovation Parkway Holdings LLC"),
        "rent_amount": _pdf_field("$22,750.00", 2, "Monthly Rent: $22,750.00"),
        "lease_start_date": _pdf_field("07/01/2022", 1, "Commencement Date: July 1, 2022"),
        "lease_end_date": _pdf_field("06/30/2027", 1, "Expiration Date: June 30, 2027"),
        "property_address": _pdf_field(_PROPERTY_B, 1, _PROPERTY_B),
        "security_deposit": _pdf_field("$45,500.00", 2, "Security Deposit: $45,500.00"),
        "cam_charges": _pdf_field("$3,200.00", 3, "Monthly CAM Charges: $3,200.00"),
        "rent_escalation": _pdf_field("2.5% annual increase", 3, "Base Rent shall increase by two and one-half percent (2.5%) annually"),
        "renewal_options": _pdf_field("Two consecutive 3-year renewal options", 4, "Tenant shall have two (2) consecutive options to renew, each for a period of three (3) years"),
        "permitted_use": _pdf_field("General office use", 2, "Premises shall be used for general office purposes"),
        "exclusivity_clause": _not_found(),
        "insurance_requirements": _pdf_field("$5,000,000 umbrella policy required", 4, "Tenant shall maintain a commercial umbrella policy with limits of not less than $5,000,000"),
        "default_cure_period": _pdf_field("15 days", 6, "fifteen (15) days after written notice"),
        "square_footage": _pdf_field("8,200 sq ft", 1, "consisting of approximately 8,200 square feet"),
    }

    return [
        {"filename": "coastal_brew_lease.pdf", "extracted_fields": retail, "display_name": "Coastal Brew Coffee Co. - " + _PROPERTY_A},
        {"filename": "northbridge_analytics_lease.pdf", "extracted_fields": office, "display_name": "Northbridge Analytics Inc. - " + _PROPERTY_B},
    ]


def _sample_rent_roll_leases():
    """
    Two rent-roll-derived leases, in the exact shape
    rent_roll_import.parse_rent_roll_rows() produces -- one row matches
    its PDF counterpart exactly (a clean validation), the other has a
    deliberately different rent amount so the reconciliation feature
    (see comparison.compute_rent_roll_reconciliation, exact-address
    matching) has something real to flag on first load.
    """
    filename = "q1_2026_rent_roll.csv"

    clean = {
        "tenant": _rent_roll_field("Coastal Brew Coffee Co.", 2, filename, "Coastal Brew Coffee Co."),
        "landlord": _not_found(),
        "rent_amount": _rent_roll_field("$8,500.00", 2, filename, "8500.00"),
        "lease_start_date": _not_found(),
        "lease_end_date": _not_found(),
        "property_address": _rent_roll_field(_PROPERTY_A, 2, filename, "Suite 200"),
        "security_deposit": _not_found(),
        "cam_charges": _not_found(),
        "rent_escalation": _not_found(),
        "renewal_options": _not_found(),
        "permitted_use": _not_found(),
        "exclusivity_clause": _not_found(),
        "insurance_requirements": _not_found(),
        "default_cure_period": _not_found(),
        "square_footage": _rent_roll_field("1,450 sq ft", 2, filename, "1450"),
    }

    mismatched = {
        "tenant": _rent_roll_field("Northbridge Analytics Inc.", 3, filename, "Northbridge Analytics Inc."),
        "landlord": _not_found(),
        "rent_amount": _rent_roll_field("$23,500.00", 3, filename, "23500.00"),  # deliberately != the $22,750.00 lease PDF value
        "lease_start_date": _not_found(),
        "lease_end_date": _not_found(),
        "property_address": _rent_roll_field(_PROPERTY_B, 3, filename, "Floor 4"),
        "security_deposit": _not_found(),
        "cam_charges": _not_found(),
        "rent_escalation": _not_found(),
        "renewal_options": _not_found(),
        "permitted_use": _not_found(),
        "exclusivity_clause": _not_found(),
        "insurance_requirements": _not_found(),
        "default_cure_period": _not_found(),
        "square_footage": _rent_roll_field("8,200 sq ft", 3, filename, "8200"),
    }

    return [
        {"filename": filename, "extracted_fields": clean, "display_name": "Coastal Brew Coffee Co. - " + _PROPERTY_A},
        {"filename": filename, "extracted_fields": mismatched, "display_name": "Northbridge Analytics Inc. - " + _PROPERTY_B},
    ]


_SEED_LOCK_PATH = os.path.join(tempfile.gettempdir(), "abstractly_demo_seed.lock")


def seed_demo_data() -> None:
    """
    Idempotent: no-op if the demo database already has any leases.

    Guarded by an exclusive-create lock file (same pattern as api.py's
    FLASK_SECRET_KEY fallback), not just the leases-empty check above --
    gunicorn runs multiple worker processes, each importing this module
    and calling this function independently at boot. Two workers can
    both see an empty leases table before either has committed its own
    inserts (a plain check-then-act race), each proceeding to seed --
    caught live on the real demo deployment as 8 leases instead of 4.
    Only the first process to win the exclusive-create actually seeds;
    reset_demo_data() removes the lock file first so a real reset can
    still reseed afterward.
    """
    try:
        fd = os.open(_SEED_LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
    except FileExistsError:
        logger.info("Demo data seed already claimed by another process -- skipping.")
        return

    existing = database.get_all_leases(document_type=None)
    if existing:
        logger.info("Demo data already present (%d lease(s)) -- skipping seed.", len(existing))
        return

    for account in DEMO_ACCOUNTS:
        user_result = database.create_user(
            account["email"], account["name"], auth.hash_password(account["password"]), role=account["role"],
        )
        if user_result["status"] == "created":
            logger.info("Seeded demo user %s", account["email"])

    for lease in _sample_pdf_leases():
        database.insert_lease(lease["filename"], lease["extracted_fields"], document_type="lease", display_name=lease["display_name"])

    for lease in _sample_rent_roll_leases():
        database.insert_lease(lease["filename"], lease["extracted_fields"], document_type="lease", display_name=lease["display_name"])

    database.insert_activity("demo_seeded", "Demo account seeded with sample leases and a sample rent roll")
    logger.info("Demo data seeded: 2 sample leases + 2 matching rent-roll rows.")


def reset_demo_data() -> None:
    """Wipes every content table (see _CONTENT_TABLES) and reseeds. Only ever call this against the dedicated demo database."""
    conn = database.get_connection()
    try:
        for table in _CONTENT_TABLES:
            conn.execute(f"DELETE FROM {table}")
        conn.commit()
    finally:
        conn.close()

    try:
        os.remove(_SEED_LOCK_PATH)
    except FileNotFoundError:
        pass
    logger.warning("Demo data reset: all content tables wiped.")
    seed_demo_data()
