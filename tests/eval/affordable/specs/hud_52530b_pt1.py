"""HUD-52530B PBV HAP contract, Part 1, existing housing (07/2019). AcroForm.

Fictional existing PBV project. The form has no unit or rent table (exhibits A-D are
separate attachments), so the PHA's contract number and project address are written in
the page 1 header margin, the way a PHA stamps them. The PBC-to-PBV addendum (pages 9-10)
and the MTW rider (page 11) are left blank: this is not a certificate conversion.
"""

PHA = "Riverbend Housing Authority"
OWNER = "Maple Ridge Commons Housing LLC"
PROJECT = "Maple Ridge Commons, 1500 Maple Ridge Drive, Riverbend, IN 46990"
CONTRACT_NO = "RHA-PBV-2027-004"

SPEC = {
    "id": "hud_52530b_pt1",
    "source": "hud_52530b_pt1.pdf",
    "form": "HUD-52530B PBV HAP Contract Part 1, Existing Housing (07/2019)",
    "program": "PBV",
    "doc_type": "hap_contract",
    "notes": "Existing-housing PBV contract, 15-year initial term, 8 units designated for elderly families.",
    "placements": [
        {"page": 1, "at": (90, 39), "size": 8.5, "text": f"PHA Contract No.: {CONTRACT_NO}"},
        {"page": 1, "at": (90, 51), "size": 8.5, "text": f"Project: {PROJECT}"},
        {"acro": "Text1", "text": PHA},
        {"acro": "Text2", "text": OWNER},
        {"acro": "Text3", "text": "03/01/2027"},
        {"acro": "Text4", "text": "Fifteen (15) years"},
        {"acro": "Text12", "text": "0"},             # units that received HUD assistance
        {"acro": "Text18", "text": "0"},             # units under a federal rent restriction
        {"acro": "CheckBox19", "text": "X"},         # units designated for elderly families
        {"acro": "Text21", "text": "8"},
        # Execution (page 8)
        {"acro": "Text23", "text": PHA},
        {"acro": "Text75", "text": "/s/ Delphine Arkwright"},
        {"acro": "Text24", "text": "Delphine Arkwright, Executive Director"},
        {"acro": "Text25", "text": "February 18, 2027"},
        {"acro": "Text26", "text": OWNER},
        {"acro": "Text76", "text": "/s/ Callum Northey"},
        {"acro": "Text27", "text": "Callum Northey, Managing Member"},
        {"acro": "Text28", "text": "February 16, 2027"},
    ],
    "lease_fields": {
        "tenant": None,
        "landlord": OWNER,
        "rent_amount": None,
        "lease_start_date": "03/01/2027",
        "lease_end_date": None,
        "property_address": PROJECT,
        "security_deposit": None,
    },
    "program_fields": {
        "contract_number": {"value": CONTRACT_NO, "type": "text"},
        "project": {"value": PROJECT, "type": "text"},
        "pha_name": {"value": PHA, "type": "text"},
        "owner_name": {"value": OWNER, "type": "text"},
        "effective_date": {"value": "03/01/2027", "type": "date"},
        "initial_term": {"value": "Fifteen (15) years", "type": "text"},
        "units_prior_hud_assistance": {"value": "0", "type": "int"},
        "units_federal_rent_restriction": {"value": "0", "type": "int"},
        "elderly_designated_units": {"value": "8", "type": "int"},
        "pha_signatory": {"value": "Delphine Arkwright, Executive Director", "type": "text"},
        "pha_signature_date": {"value": "02/18/2027", "type": "date", "shown_as": "February 18, 2027"},
        "owner_signatory": {"value": "Callum Northey, Managing Member", "type": "text"},
        "owner_signature_date": {"value": "02/16/2027", "type": "date", "shown_as": "February 16, 2027"},
    },
}
