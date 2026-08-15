"""
Google Sheets export for the lease portfolio, via a Google service
account — not per-user OAuth login, since this is a backend-triggered
export action, not a per-user auth flow. See backend/.env.example for
the full one-time Google Cloud setup this requires.

Every export creates a brand-new Sheet (never updates an existing one,
by explicit product decision) named "Lease Portfolio Export - <date>",
and shares it "anyone with the link can view" so the URL handed back to
the caller always opens — a service-account-created file isn't visible
to anyone else by default, and there's no single "current user" account
in this app to share it with individually instead. See .env.example for
the privacy tradeoff that implies (the same one the existing CSV/report
exports already have: link-reachable, not access-controlled).

Column formatting deliberately mirrors rent_roll_export.py's philosophy
rather than inventing a new one: most columns carry the extraction
engine's display strings verbatim, unmistakably-numeric currency/count
strings are retyped as real numbers (conservatively — only when the
string carries no qualifier a bare number would drop), a field that
wasn't found is a blank cell rather than the text "None" or "Not
Found", and Annual Rent / Rent per Square Foot are genuinely derived
(no such field is ever extracted) via the same app.normalize helpers
every other module uses, so they can't disagree with the dashboard.
"""

import logging
import os
import re
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .normalize import parse_currency, parse_square_footage, rent_per_sqft

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]

# (header label, extracted_fields key or None for a derived column)
COLUMNS: List[Tuple[str, Optional[str]]] = [
    ("Tenant Name", "tenant"),
    ("Landlord Name", "landlord"),
    ("Property Address", "property_address"),
    ("Monthly Rent", "rent_amount"),
    ("Annual Rent", None),
    ("Rent per Square Foot", None),
    ("Security Deposit", "security_deposit"),
    ("Rent Escalation", "rent_escalation"),
    ("Lease Start Date", "lease_start_date"),
    ("Lease End Date", "lease_end_date"),
    ("Renewal Options", "renewal_options"),
    ("Default/Cure Period", "default_cure_period"),
    ("Permitted Use", "permitted_use"),
    ("Exclusivity Clause", "exclusivity_clause"),
    ("Insurance Requirements", "insurance_requirements"),
    ("CAM Charges", "cam_charges"),
    ("Square Footage", "square_footage"),
]

# Same conservative-retyping philosophy as rent_roll_export.py's Excel
# export: a display string is only retyped as a real number when it
# carries no qualifier the bare number would silently drop.
_CURRENCY_COLUMNS = {"Monthly Rent", "Security Deposit", "CAM Charges"}
_PURE_CURRENCY = re.compile(r"^\s*\$\s?[\d,]+(?:\.\d+)?\s*$")


class SheetsExportError(Exception):
    """
    Raised for any failure exporting to Google Sheets. The message is
    always written to be safe to show directly to the person who
    clicked the button — no file paths, no raw exception text, no
    internal API error bodies. The real cause is always logged
    server-side first via logger.exception, same convention as this
    project's other external-service integration (email_service.py) and
    the hardening-pass error handlers in api.py.
    """


def _field_value(lease: Dict[str, Any], field_name: str) -> Optional[str]:
    fields = lease.get("extracted_fields") or {}
    entry = fields.get(field_name)
    if not isinstance(entry, dict):
        return None
    value = entry.get("value")
    return value if value not in (None, "") else None


def _numeric_or_text(value: str, column: str):
    """Retypes a pure currency/count string as a real number; otherwise returns the string as-is. See module docstring."""
    if column in _CURRENCY_COLUMNS and _PURE_CURRENCY.match(value):
        parsed = parse_currency(value)
        if parsed is not None:
            return parsed
    if column == "Square Footage":
        parsed = parse_square_footage(value)
        if parsed is not None:
            return parsed
    return value


def _lease_row(lease: Dict[str, Any]) -> List[Any]:
    rent_str = _field_value(lease, "rent_amount")
    sqft_str = _field_value(lease, "square_footage")

    monthly_rent = parse_currency(rent_str)
    annual_rent = round(monthly_rent * 12, 2) if monthly_rent is not None else None
    psf = rent_per_sqft(rent_str, sqft_str)
    psf = round(psf, 2) if psf is not None else None

    row: List[Any] = []
    for label, field_name in COLUMNS:
        if label == "Annual Rent":
            row.append(annual_rent if annual_rent is not None else "")
        elif label == "Rent per Square Foot":
            row.append(psf if psf is not None else "")
        else:
            value = _field_value(lease, field_name)
            row.append(_numeric_or_text(value, label) if value is not None else "")
    return row


def _load_credentials():
    creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not creds_path:
        raise SheetsExportError(
            "Google Sheets export isn't set up yet. An administrator needs to set "
            "GOOGLE_APPLICATION_CREDENTIALS in backend/.env — see backend/.env.example for the "
            "exact steps."
        )
    if not os.path.exists(creds_path):
        raise SheetsExportError(
            "Google Sheets export is misconfigured: no credentials file was found at the "
            "configured path. See backend/.env.example."
        )
    try:
        return service_account.Credentials.from_service_account_file(creds_path, scopes=SCOPES)
    except Exception:
        logger.exception("Failed to load Google service account credentials from %s", creds_path)
        raise SheetsExportError(
            "Google Sheets export is misconfigured: the credentials file isn't a valid service "
            "account key. See backend/.env.example."
        )


def export_to_google_sheets(leases: List[Dict[str, Any]]) -> Dict[str, str]:
    """
    Creates a brand-new Google Sheet, writes one header row plus one row
    per lease, shares it link-readable, and returns
    {"spreadsheet_id": ..., "url": ...}.

    Raises SheetsExportError on any failure — see that class's
    docstring for why every message it carries is safe to show directly
    to the user. Never returns a partially-written or broken sheet
    silently; if writing the data or setting sharing fails after the
    spreadsheet was already created, that failure still raises (the
    caller sees a clear error, even though an empty/orphaned sheet may
    be left behind in Google Drive — acceptable for a low-volume manual
    export action, not worth the complexity of transactional cleanup).
    """
    credentials = _load_credentials()

    try:
        sheets_service = build("sheets", "v4", credentials=credentials, cache_discovery=False)
        drive_service = build("drive", "v3", credentials=credentials, cache_discovery=False)

        title = f"Lease Portfolio Export - {date.today().isoformat()}"
        spreadsheet = sheets_service.spreadsheets().create(
            body={"properties": {"title": title}}
        ).execute()
        spreadsheet_id = spreadsheet["spreadsheetId"]

        header = [label for label, _ in COLUMNS]
        values = [header] + [_lease_row(lease) for lease in leases]

        sheets_service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range="A1",
            valueInputOption="RAW",
            body={"values": values},
        ).execute()

        drive_service.permissions().create(
            fileId=spreadsheet_id,
            body={"type": "anyone", "role": "reader"},
        ).execute()

        return {
            "spreadsheet_id": spreadsheet_id,
            "url": f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit",
        }

    except SheetsExportError:
        raise
    except HttpError as e:
        logger.exception("Google API error during Sheets export")
        status = getattr(e, "status_code", None) or getattr(getattr(e, "resp", None), "status", None)
        if status == 403:
            message = (
                "Google Sheets export failed: permission denied. Make sure both the Google "
                "Sheets API and Google Drive API are enabled for your Google Cloud project."
            )
        elif status == 401:
            message = (
                "Google Sheets export failed: Google rejected the credentials. Check that the "
                "service account key hasn't been revoked or deleted."
            )
        else:
            message = f"Google Sheets export failed: Google API returned an error (HTTP {status or 'unknown'})."
        raise SheetsExportError(message)
    except Exception:
        logger.exception("Unexpected error during Google Sheets export")
        raise SheetsExportError("Google Sheets export failed unexpectedly. Check the server logs for details.")
