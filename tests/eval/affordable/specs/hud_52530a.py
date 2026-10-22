"""HUD-52530A PBV HAP contract, Part 1, new construction or rehabilitation (07/2019). AcroForm.

Fictional single-stage PBV project. The form has no unit or rent table (exhibits A-D are
separate attachments), so the PHA's contract number and project address are written in
the page 1 header margin, the way a PHA stamps them.
"""

PHA = "Riverbend Housing Authority"
OWNER = "Maple Ridge Commons II LLC"
PROJECT = "Maple Ridge Commons Phase II, 1520 Maple Ridge Drive, Riverbend, IN 46990"
CONTRACT_NO = "RHA-PBV-2027-011"

SPEC = {
    "id": "hud_52530a",
    "source": "hud_52530a.pdf",
    "form": "HUD-52530A PBV HAP Contract Part 1, New Construction or Rehabilitation (07/2019)",
    "program": "PBV",
    "doc_type": "hap_contract",
    "notes": ("Single-stage PBV new construction project, 20-year initial term, 12 units designated for "
              "elderly families. Multi-stage execution pages (10-13) left blank, as a single-stage contract would."),
    "placements": [
        {"page": 1, "at": (90, 50), "size": 8.5, "text": f"PHA Contract No.: {CONTRACT_NO}"},
        {"page": 1, "at": (90, 62), "size": 8.5, "text": f"Project: {PROJECT}"},
        {"acro": "Text1", "text": PHA},
        {"acro": "Text2", "text": OWNER},
        {"acro": "CheckBox4", "text": "X"},          # single-stage project
        {"acro": "Text3", "text": "July 1, 2027"},
        {"acro": "Text6", "text": "20 years"},
        {"acro": "Text14", "text": "0"},             # units that received HUD assistance
        {"acro": "Text20", "text": "0"},             # units under a federal rent restriction
        {"acro": "CheckBox21", "text": "X"},         # units designated for elderly families
        {"acro": "Text28", "text": "12"},
        # Execution, single-stage (page 9)
        {"acro": "Text30", "text": PHA},
        {"acro": "Text52", "text": "/s/ Delphine Arkwright"},
        {"acro": "Text31", "text": "Delphine Arkwright, Executive Director"},
        {"acro": "Text32", "text": "06/24/2027"},
        {"acro": "Text33", "text": OWNER},
        {"acro": "Text53", "text": "/s/ Imogen Fairbairn"},
        {"acro": "Text34", "text": "Imogen Fairbairn, Manager"},
        {"acro": "Text35", "text": "06/22/2027"},
    ],
    "lease_fields": {
        "tenant": None,
        "landlord": OWNER,
        "rent_amount": None,
        "lease_start_date": "July 1, 2027",
        "lease_end_date": None,
        "property_address": PROJECT,
        "security_deposit": None,
    },
    "program_fields": {
        "contract_number": {"value": CONTRACT_NO, "type": "text"},
        "project": {"value": PROJECT, "type": "text"},
        "pha_name": {"value": PHA, "type": "text"},
        "owner_name": {"value": OWNER, "type": "text"},
        "effective_date": {"value": "07/01/2027", "type": "date", "shown_as": "July 1, 2027"},
        "initial_term": {"value": "20 years", "type": "text"},
        "units_prior_hud_assistance": {"value": "0", "type": "int"},
        "units_federal_rent_restriction": {"value": "0", "type": "int"},
        "elderly_designated_units": {"value": "12", "type": "int"},
        "pha_signatory": {"value": "Delphine Arkwright, Executive Director", "type": "text"},
        "pha_signature_date": {"value": "06/24/2027", "type": "date"},
        "owner_signatory": {"value": "Imogen Fairbairn, Manager", "type": "text"},
        "owner_signature_date": {"value": "06/22/2027", "type": "date"},
        "project_type": {"value": "Single-stage", "type": "checkbox"},
    },
}
