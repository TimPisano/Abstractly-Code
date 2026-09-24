"""
Hand-authored realistic commercial lease sample set for the homepage
accuracy/speed benchmark and the customer demo.

Ten fictional commercial leases (no real tenant/landlord names or real
addresses), deliberately varied in the ways real leases vary:

  - retail / office / restaurant / industrial / medical / salon /
    flex-space / fitness use types
  - label-style parties ("LANDLORD: ...") vs defined-term recitals
  - monthly rent vs annual-with-monthly-parenthetical vs percentage rent
  - escalation stated as a %, as a year-by-year schedule, as CPI, or
    absent (flat) or genuinely unstated
  - several clauses deliberately absent so "not found" is exercised
  - 5 date formats
  - 2 to 5 pages each

Each lease has an explicit ground_truth dict for the 15 fields the
Abstractly pipeline extracts. `null` means "the document does not state
this -> the correct answer is 'not found'".

Run:  venv/bin/python benchmark_data/build_sample_leases.py
Writes: benchmark_data/leases/*.pdf, ground_truth.json, ground_truth.csv
"""

import csv
import json
import os

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
LEASE_DIR = os.path.join(OUT_DIR, "leases")

FIELDS = [
    "tenant", "landlord", "rent_amount", "lease_start_date", "lease_end_date",
    "property_address", "security_deposit", "cam_charges", "rent_escalation",
    "renewal_options", "permitted_use", "exclusivity_clause",
    "insurance_requirements", "default_cure_period", "square_footage",
]


# ----------------------------------------------------------------------
# The ten leases
# ----------------------------------------------------------------------

LEASES = [
    {
        "id": "L01_riverbend_retail_coffee",
        "paragraphs": [
            "SHOPPING CENTER LEASE AGREEMENT",
            "",
            "LANDLORD: Riverbend Marketplace Holdings, LLC",
            "TENANT: Wren & Kettle Coffee, LLC",
            "",
            "1. PREMISES. Landlord hereby leases to Tenant, and Tenant leases from Landlord, "
            "that certain retail space known as Suite 140, Riverbend Marketplace, located at "
            "2200 Copperfield Road, Suite 140, Maple Grove, Minnesota 55311 (the \"Premises\"), "
            "consisting of approximately 1,650 rentable square feet.",
            "",
            "2. TERM. The term of this Lease shall be five (5) years, commencing on March 1, 2024 "
            "(the \"Commencement Date\") and expiring on February 28, 2029, unless sooner terminated "
            "in accordance with the terms hereof.",
            "",
            "3. BASE RENT. Tenant shall pay to Landlord base rent in the amount of $4,675.00 per "
            "month, payable in advance on the first day of each calendar month without demand, "
            "setoff, or deduction.",
            "",
            "4. RENT ADJUSTMENT. On each anniversary of the Commencement Date, the monthly base "
            "rent shall increase by three percent (3%) over the base rent payable for the "
            "immediately preceding twelve-month period.",
            "",
            "5. ADDITIONAL RENT; CAM. Tenant shall pay, as additional rent, its proportionate "
            "share of Common Area Maintenance charges, estimated at $3.25 per rentable square foot "
            "per annum, payable in equal monthly installments and reconciled annually.",
            "",
            "6. SECURITY DEPOSIT. Concurrently with its execution of this Lease, Tenant shall "
            "deposit with Landlord the sum of $9,350.00, to be held as security for Tenant's full "
            "and faithful performance of its obligations under this Lease.",
            "",
            "7. PERMITTED USE. The Premises shall be used and occupied solely for the operation of "
            "a specialty coffee shop and cafe, including the retail sale of coffee, tea, baked "
            "goods, and related merchandise, and for no other purpose without Landlord's prior "
            "written consent.",
            "",
            "8. EXCLUSIVE. So long as Tenant is operating under its permitted use and is not in "
            "default, Landlord shall not lease any other premises within the Shopping Center to "
            "any business whose primary use is the sale of specialty coffee beverages. This "
            "exclusive shall not apply to any tenant occupying more than 15,000 square feet.",
            "",
            "9. RENEWAL OPTION. Provided Tenant is not in default, Tenant shall have two (2) "
            "consecutive options to extend the term, each for a period of five (5) years, by "
            "delivering written notice to Landlord not less than nine (9) months prior to the "
            "expiration of the then-current term. Base rent for each renewal term shall be "
            "ninety-five percent (95%) of the then-prevailing fair market rent.",
            "",
            "10. INSURANCE. Tenant shall maintain commercial general liability insurance with "
            "limits of not less than $2,000,000 per occurrence and $3,000,000 in the aggregate, "
            "naming Landlord as an additional insured.",
            "",
            "11. DEFAULT. The occurrence of any of the following shall constitute an Event of "
            "Default: (a) Tenant fails to pay any installment of rent within five (5) days after "
            "written notice that the same is due; or (b) Tenant fails to perform any other "
            "obligation under this Lease and such failure continues for thirty (30) days after "
            "written notice from Landlord.",
        ],
        "ground_truth": {
            "tenant": "Wren & Kettle Coffee, LLC",
            "landlord": "Riverbend Marketplace Holdings, LLC",
            "rent_amount": "$4,675.00",
            "lease_start_date": "March 1, 2024",
            "lease_end_date": "February 28, 2029",
            "property_address": "2200 Copperfield Road, Suite 140, Maple Grove, Minnesota 55311",
            "security_deposit": "$9,350.00",
            "cam_charges": "$3.25 per rentable square foot per annum",
            "rent_escalation": "3% annually on each anniversary of the Commencement Date",
            "renewal_options": "Two 5-year options; 9 months' prior written notice; renewal rent at 95% of fair market rent",
            "permitted_use": "A specialty coffee shop and cafe (retail sale of coffee, tea, baked goods, and related merchandise)",
            "exclusivity_clause": "Landlord will not lease other center space to a business whose primary use is sale of specialty coffee beverages; does not apply to tenants over 15,000 sq ft",
            "insurance_requirements": "$2,000,000 per occurrence / $3,000,000 aggregate commercial general liability; Landlord as additional insured",
            "default_cure_period": "30 days after written notice for non-monetary default (5 days for monetary)",
            "square_footage": "1,650 sq ft",
        },
    },
    {
        "id": "L02_summit_tower_office",
        "paragraphs": [
            "OFFICE LEASE",
            "",
            "THIS OFFICE LEASE (this \"Lease\") is entered into as of the 15th day of June, 2023, "
            "by and between SUMMIT TOWER OWNER LP, a Delaware limited partnership (\"Landlord\"), "
            "and NORTHLIGHT DATA SYSTEMS, INC., a Delaware corporation (\"Tenant\").",
            "",
            "RECITALS. Landlord owns the office building commonly known as Summit Tower and "
            "located at 815 Franklin Avenue, Denver, Colorado 80202. Tenant desires to lease a "
            "portion of the building on the terms set forth herein.",
            "",
            "ARTICLE 1 - PREMISES. Landlord leases to Tenant Suite 1900, comprising approximately "
            "9,400 rentable square feet on the nineteenth (19th) floor of the Building "
            "(the \"Premises\").",
            "",
            "ARTICLE 2 - TERM. The term of this Lease shall commence on August 1, 2023 and, unless "
            "sooner terminated as provided herein, shall continue for a period of eighty-four (84) "
            "months, expiring on July 31, 2030.",
            "",
            "ARTICLE 3 - BASE RENT. Tenant shall pay annual base rent of $394,800.00, payable in "
            "equal monthly installments of $32,900.00, in advance, on the first day of each month "
            "of the term.",
            "",
            "ARTICLE 4 - RENT ESCALATION. Commencing on the first (1st) anniversary of the "
            "Commencement Date and on each anniversary thereafter, annual base rent shall increase "
            "by two and one-half percent (2.5%) over the annual base rent in effect for the "
            "preceding year.",
            "",
            "ARTICLE 5 - OPERATING EXPENSES. Tenant shall pay its pro rata share (4.7%) of "
            "increases in Building operating expenses and real estate taxes over the amounts "
            "incurred in the Base Year (calendar year 2023).",
            "",
            "ARTICLE 6 - SECURITY. Tenant shall provide Landlord, upon execution, a security "
            "deposit in the amount of $65,800.00.",
            "",
            "ARTICLE 7 - USE. Tenant shall use the Premises for general business and administrative "
            "office purposes consistent with a first-class office building, and for no other use.",
            "",
            "ARTICLE 8 - RENEWAL. Tenant shall have one (1) option to renew the term for an "
            "additional five (5) years, exercisable by written notice given no earlier than "
            "eighteen (18) months and no later than twelve (12) months prior to expiration of the "
            "initial term, at the then-fair market rental rate for comparable space in the Building.",
            "",
            "ARTICLE 9 - INSURANCE. Tenant shall carry commercial general liability insurance of "
            "not less than $3,000,000 combined single limit per occurrence, and property insurance "
            "covering Tenant's personal property and improvements.",
            "",
            "ARTICLE 10 - DEFAULT AND CURE. If Tenant fails to pay rent when due and such failure "
            "continues for five (5) business days after notice, or fails to observe any other "
            "covenant and such failure continues for fifteen (15) days after written notice "
            "(or such longer period as is reasonably required to cure if Tenant commences cure "
            "within such period), Tenant shall be in default.",
            "",
            "ARTICLE 11 - PARKING. Landlord shall make available to Tenant, at prevailing monthly "
            "rates, up to twenty (20) unreserved parking permits in the Building garage.",
        ],
        "ground_truth": {
            "tenant": "Northlight Data Systems, Inc.",
            "landlord": "Summit Tower Owner LP",
            "rent_amount": "$32,900.00",
            "lease_start_date": "August 1, 2023",
            "lease_end_date": "July 31, 2030",
            "property_address": "815 Franklin Avenue, Suite 1900, Denver, Colorado 80202",
            "security_deposit": "$65,800.00",
            "cam_charges": "Pro rata share 4.7% of increases in operating expenses and real estate taxes over 2023 base year",
            "rent_escalation": "2.5% annually on each anniversary of the Commencement Date",
            "renewal_options": "One 5-year option at fair market rental; notice no earlier than 18 months and no later than 12 months before expiration",
            "permitted_use": "General business and administrative office purposes",
            "exclusivity_clause": None,
            "insurance_requirements": "$3,000,000 combined single limit per occurrence commercial general liability",
            "default_cure_period": "15 days after written notice for non-monetary default (5 business days for monetary)",
            "square_footage": "9,400 sq ft",
        },
    },
    {
        "id": "L03_harbor_street_restaurant",
        "paragraphs": [
            "LEASE AGREEMENT (RESTAURANT)",
            "",
            "This Lease Agreement is made and entered into on the 3rd day of October, 2022, "
            "between Harbor Street Partners, a California general partnership (\"Landlord\"), and "
            "Marisol Hospitality Group, LLC, doing business as \"Costa Verde\" (\"Tenant\").",
            "",
            "PREMISES. The leased premises consist of the ground-floor restaurant space and "
            "outdoor patio located at 47 Harbor Street, Ground Floor, Santa Cruz, California 95060, "
            "containing approximately 3,900 square feet of interior space plus approximately 600 "
            "square feet of exclusive patio area.",
            "",
            "TERM. The initial term shall be ten (10) years, beginning on the Rent Commencement "
            "Date and ending on the last day of the one hundred twentieth (120th) full calendar "
            "month thereafter. The Rent Commencement Date is January 1, 2023.",
            "",
            "MINIMUM RENT. From the Rent Commencement Date, Tenant shall pay minimum monthly rent "
            "as follows: Months 1-24: $12,000.00 per month; Months 25-60: $13,500.00 per month; "
            "Months 61-96: $15,200.00 per month; Months 97-120: $17,100.00 per month.",
            "",
            "PERCENTAGE RENT. In addition to minimum rent, Tenant shall pay percentage rent equal "
            "to six percent (6%) of annual gross sales in excess of $2,400,000, payable quarterly.",
            "",
            "TRIPLE NET CHARGES. This is a triple net lease. Tenant shall pay all real property "
            "taxes, insurance premiums, and common area maintenance costs attributable to the "
            "Premises. CAM is currently estimated at $2,850.00 per month.",
            "",
            "SECURITY DEPOSIT. Tenant has deposited with Landlord the sum of $36,000.00 as a "
            "security deposit, plus an additional $10,000.00 as a fixturing and restoration "
            "deposit.",
            "",
            "USE. Tenant shall operate the Premises continuously as a full-service, sit-down "
            "restaurant serving lunch and dinner, with a full bar, under the trade name "
            "\"Costa Verde\" or such other name as Landlord approves in writing.",
            "",
            "RENEWAL. Tenant shall have one (1) option to extend for an additional term of five "
            "(5) years upon not less than two hundred seventy (270) days' prior written notice, "
            "at a minimum rent equal to the minimum rent in effect during the final year of the "
            "initial term, increased by ten percent (10%).",
            "",
            "INSURANCE. Tenant shall maintain: (i) commercial general liability insurance, "
            "including liquor liability, of not less than $5,000,000 per occurrence; and "
            "(ii) property insurance on all improvements and trade fixtures at full replacement "
            "cost.",
            "",
            "DEFAULT. If Tenant fails to pay rent or other charges within three (3) days after "
            "written notice, or fails to cure any non-monetary default within twenty (20) days "
            "after written notice, Landlord may exercise all remedies available at law or in "
            "equity.",
            "",
            "GREASE AND VENTILATION. Tenant shall, at its sole expense, maintain the grease "
            "interceptor and kitchen exhaust system and shall have the hood cleaned by a "
            "licensed contractor not less than quarterly.",
        ],
        "ground_truth": {
            "tenant": "Marisol Hospitality Group, LLC",
            "landlord": "Harbor Street Partners",
            "rent_amount": "$12,000.00",
            "lease_start_date": "January 1, 2023",
            "lease_end_date": "December 31, 2032",
            "property_address": "47 Harbor Street, Ground Floor, Santa Cruz, California 95060",
            "security_deposit": "$36,000.00",
            "cam_charges": "$2,850.00 per month (triple net; tenant also pays taxes and insurance)",
            "rent_escalation": "Stepped: $12,000/mo (mo 1-24); $13,500 (25-60); $15,200 (61-96); $17,100 (97-120)",
            "renewal_options": "One 5-year option; 270 days' prior written notice; rent = final-year minimum rent plus 10%",
            "permitted_use": "Full-service sit-down restaurant serving lunch and dinner with a full bar",
            "exclusivity_clause": None,
            "insurance_requirements": "$5,000,000 per occurrence commercial general liability including liquor liability",
            "default_cure_period": "20 days after written notice for non-monetary default (3 days for monetary)",
            "square_footage": "3,900 sq ft interior (plus ~600 sq ft patio)",
        },
    },
    {
        "id": "L04_gateway_industrial_nnn",
        "paragraphs": [
            "INDUSTRIAL BUILDING LEASE",
            "",
            "LANDLORD: Gateway Logistics Investors II, LLC",
            "TENANT: Ardent Fulfillment Co.",
            "",
            "1. PREMISES. Landlord leases to Tenant the entire industrial building located at "
            "9401 Distribution Way, Building C, Grove City, Ohio 43123, containing approximately "
            "84,000 square feet of warehouse and 6,000 square feet of office (90,000 square feet "
            "total).",
            "",
            "2. TERM. This Lease shall be for a term of seven (7) years and three (3) months, "
            "commencing 05/01/2024 and expiring 07/31/2031. The first three (3) months shall be "
            "an abated-rent fixturing period.",
            "",
            "3. BASE RENT. Beginning 08/01/2024, Tenant shall pay base rent at the initial rate of "
            "$0.62 per square foot per month ($55,800.00 per month) NNN.",
            "",
            "4. RENT INCREASES. Base rent shall increase annually by the greater of (a) three "
            "percent (3%), or (b) the percentage increase in the Consumer Price Index for All "
            "Urban Consumers (CPI-U, U.S. City Average) over the preceding twelve months, "
            "provided that no annual increase shall exceed five percent (5%).",
            "",
            "5. NET LEASE. This is an absolute triple net lease. Tenant is responsible for all "
            "taxes, insurance, utilities, and maintenance, including roof and structure. There "
            "are no common area maintenance charges as the Premises is a single-tenant building.",
            "",
            "6. SECURITY DEPOSIT. Tenant shall deposit $111,600.00 with Landlord upon execution, "
            "which Landlord shall reduce to $55,800.00 after the thirty-sixth (36th) month if "
            "Tenant has not been in monetary default.",
            "",
            "7. USE. The Premises shall be used for warehousing, distribution, light assembly, "
            "e-commerce order fulfillment, and related office use, and for no other purpose.",
            "",
            "8. RENEWAL. Tenant shall have two (2) options to renew, each of five (5) years, on "
            "twelve (12) months' notice, at the then-current fair market rent as determined by "
            "the parties or, failing agreement, by appraisal.",
            "",
            "9. INSURANCE. Tenant shall maintain commercial general liability coverage of at "
            "least $4,000,000 per occurrence, and \"all risk\" property insurance on the building "
            "at full replacement value with Landlord and Landlord's lender as loss payees.",
            "",
            "10. DEFAULT. A failure to pay any monetary obligation that continues for ten (10) "
            "days after written notice, or a failure to perform any other obligation that "
            "continues for thirty (30) days after written notice, constitutes an event of default.",
        ],
        "ground_truth": {
            "tenant": "Ardent Fulfillment Co.",
            "landlord": "Gateway Logistics Investors II, LLC",
            "rent_amount": "$55,800.00",
            "lease_start_date": "May 1, 2024",
            "lease_end_date": "July 31, 2031",
            "property_address": "9401 Distribution Way, Building C, Grove City, Ohio 43123",
            "security_deposit": "$111,600.00",
            "cam_charges": None,
            "rent_escalation": "Annually by greater of 3% or CPI-U, capped at 5%",
            "renewal_options": "Two 5-year options; 12 months' notice; fair market rent by agreement or appraisal",
            "permitted_use": "Warehousing, distribution, light assembly, e-commerce order fulfillment, and related office use",
            "exclusivity_clause": None,
            "insurance_requirements": "$4,000,000 per occurrence commercial general liability plus all-risk property insurance at full replacement value",
            "default_cure_period": "30 days after written notice for non-monetary default (10 days for monetary)",
            "square_footage": "90,000 sq ft (84,000 warehouse + 6,000 office)",
        },
    },
    {
        "id": "L05_cedar_medical_office",
        "paragraphs": [
            "MEDICAL OFFICE LEASE AGREEMENT",
            "",
            "This Medical Office Lease Agreement (\"Lease\") is dated for reference purposes as of "
            "February 9, 2024, and is made between Cedar Hollow Medical Plaza, LLC (\"Landlord\") "
            "and Willowmere Pediatric Associates, PLLC (\"Tenant\").",
            "",
            "1. PREMISES. The Premises is Suite 220 of the Cedar Hollow Medical Plaza, located at "
            "1330 Wellspring Drive, Suite 220, Cary, North Carolina 27518, consisting of "
            "approximately 4,250 usable square feet (4,675 rentable square feet after application "
            "of the Building's 10% common area load factor).",
            "",
            "2. TERM. The term is one hundred twenty-six (126) months, consisting of a six (6) "
            "month rent-abated build-out period followed by a one hundred twenty (120) month "
            "paying term. The Commencement Date is April 1, 2024. The Expiration Date is "
            "September 30, 2034.",
            "",
            "3. BASE RENT. Following the abatement period, Tenant shall pay base rent calculated "
            "at $31.00 per rentable square foot per year, i.e., $12,077.08 per month, subject to "
            "adjustment under Section 4.",
            "",
            "4. ANNUAL ADJUSTMENT. On each October 1 during the term, base rent per rentable "
            "square foot shall increase by $0.90.",
            "",
            "5. OPERATING COSTS. Tenant shall pay its proportionate share of Building operating "
            "costs, currently estimated at $9.75 per rentable square foot per year, in monthly "
            "installments.",
            "",
            "6. SECURITY DEPOSIT. Upon execution, Tenant shall deliver to Landlord a security "
            "deposit equal to two (2) months of initial base rent, being $24,154.16.",
            "",
            "7. PERMITTED USE. The Premises shall be used solely for the practice of pediatric "
            "medicine and directly related administrative functions, including a vaccine "
            "refrigeration room and a minor-procedure room, in compliance with all applicable "
            "healthcare regulations.",
            "",
            "8. EXCLUSIVE USE. During the term, Landlord shall not lease any other space in the "
            "Building to a medical practice whose primary specialty is pediatrics or pediatric "
            "urgent care. This restriction does not limit family-medicine or general-practice "
            "tenants.",
            "",
            "9. RENEWAL. Tenant has two (2) renewal options of five (5) years each. Tenant must "
            "give written notice between fifteen (15) and nine (9) months before the end of the "
            "then-current term. Renewal base rent shall be one hundred percent (100%) of fair "
            "market rent for comparable medical office space in the submarket.",
            "",
            "10. INSURANCE. Tenant shall maintain commercial general liability insurance of "
            "$1,000,000 per occurrence and $3,000,000 aggregate, and professional liability "
            "(malpractice) insurance of not less than $1,000,000 per claim.",
            "",
            "11. DEFAULT. If any payment of rent is not made within five (5) days after it is "
            "due, or if Tenant breaches any non-monetary obligation and does not cure within "
            "twenty-five (25) days after written notice, an event of default shall be deemed to "
            "have occurred.",
        ],
        "ground_truth": {
            "tenant": "Willowmere Pediatric Associates, PLLC",
            "landlord": "Cedar Hollow Medical Plaza, LLC",
            "rent_amount": "$12,077.08",
            "lease_start_date": "April 1, 2024",
            "lease_end_date": "September 30, 2034",
            "property_address": "1330 Wellspring Drive, Suite 220, Cary, North Carolina 27518",
            "security_deposit": "$24,154.16",
            "cam_charges": "$9.75 per rentable square foot per year (proportionate share of operating costs)",
            "rent_escalation": "$0.90 per rentable square foot increase on each October 1",
            "renewal_options": "Two 5-year options; notice between 15 and 9 months before term end; renewal rent at 100% of fair market rent",
            "permitted_use": "The practice of pediatric medicine and directly related administrative functions",
            "exclusivity_clause": "Landlord will not lease other Building space to a medical practice whose primary specialty is pediatrics or pediatric urgent care; does not limit family-medicine or general-practice tenants",
            "insurance_requirements": "$1,000,000 per occurrence / $3,000,000 aggregate commercial general liability; $1,000,000 per claim professional liability",
            "default_cure_period": "25 days after written notice for non-monetary default (5 days for monetary)",
            "square_footage": "4,675 rentable sq ft (4,250 usable)",
        },
    },
    {
        "id": "L06_lakeshore_single_tenant_retail",
        "paragraphs": [
            "GROUND LEASE / SINGLE-TENANT RETAIL",
            "",
            "LANDLORD: Lakeshore & Vine Family Trust",
            "TENANT: Brightleaf Pharmacy Partners, LLC",
            "",
            "SECTION 1. DEMISED PREMISES. Landlord leases to Tenant the land and the "
            "approximately 13,500 square foot single-tenant retail building located at "
            "600 Lakeshore Boulevard, Evanston, Illinois 60201.",
            "",
            "SECTION 2. TERM. The primary term of this Lease is fifteen (15) years, commencing "
            "on the 1st day of December, 2021, and continuing through the 30th day of November, "
            "2036.",
            "",
            "SECTION 3. RENT. The annual fixed rent during the primary term shall be "
            "$270,000.00, payable in monthly installments of $22,500.00 each. Fixed rent during "
            "the primary term shall not change.",
            "",
            "SECTION 4. NET LEASE. This Lease is completely net to Landlord. Tenant pays all "
            "taxes, assessments, insurance, utilities, and all maintenance and repairs of every "
            "kind. Because the Premises is free-standing and single-tenant, there is no common "
            "area and no CAM charge.",
            "",
            "SECTION 5. SECURITY. No security deposit is required under this Lease.",
            "",
            "SECTION 6. USE. The Premises may be used for the operation of a retail pharmacy and "
            "drug store, together with any lawful ancillary retail use, or for any other lawful "
            "retail purpose.",
            "",
            "SECTION 7. OPTIONS TO EXTEND. Tenant shall have four (4) separate options to extend "
            "the term, each for an additional period of five (5) years, upon six (6) months' "
            "written notice prior to the expiration of the then-current term. Annual fixed rent "
            "during the first extension option shall be $310,500.00, and shall increase by ten "
            "percent (10%) at the start of each subsequent extension option.",
            "",
            "SECTION 8. INSURANCE. Tenant shall keep in force commercial general liability "
            "insurance of not less than $3,000,000 per occurrence and shall insure the building "
            "for its full replacement cost.",
            "",
            "SECTION 9. DEFAULT. Should Tenant fail to pay rent within ten (10) days of written "
            "notice of nonpayment, or fail to perform any other term of this Lease within thirty "
            "(30) days of written notice, Tenant shall be in default.",
        ],
        "ground_truth": {
            "tenant": "Brightleaf Pharmacy Partners, LLC",
            "landlord": "Lakeshore & Vine Family Trust",
            "rent_amount": "$22,500.00",
            "lease_start_date": "December 1, 2021",
            "lease_end_date": "November 30, 2036",
            "property_address": "600 Lakeshore Boulevard, Evanston, Illinois 60201",
            "security_deposit": None,
            "cam_charges": None,
            "rent_escalation": "None during the primary term (fixed rent does not change)",
            "renewal_options": "Four 5-year options; 6 months' written notice; rent $310,500/yr in first option then +10% each subsequent option",
            "permitted_use": "A retail pharmacy and drug store plus lawful ancillary retail use, or any other lawful retail purpose",
            "exclusivity_clause": None,
            "insurance_requirements": "$3,000,000 per occurrence commercial general liability plus full-replacement-cost building insurance",
            "default_cure_period": "30 days after written notice for non-monetary default (10 days for monetary)",
            "square_footage": "13,500 sq ft",
        },
    },
    {
        "id": "L07_maple_court_shortform_shop",
        "paragraphs": [
            "SHORT FORM COMMERCIAL LEASE",
            "",
            "Landlord: Maple Court Rentals LLC. Tenant: The Tinsmith's Daughter LLC.",
            "",
            "Premises: 18 Maple Court, Unit B, Burlington, Vermont 05401.",
            "",
            "Term: Month-to-month, beginning 9/1/2024, terminable by either party on 60 days' "
            "written notice.",
            "",
            "Rent: $2,150 per month, due on the 1st.",
            "",
            "Deposit: $2,150.",
            "",
            "Use: Retail sale of handmade goods and gifts.",
            "",
            "Tenant pays its own electric and internet. Landlord pays heat and water. Tenant "
            "keeps the interior in good order and returns it broom-clean.",
            "",
            "Either party may terminate as stated above. If rent is more than 10 days late the "
            "Landlord may terminate on written notice.",
        ],
        "ground_truth": {
            "tenant": "The Tinsmith's Daughter LLC",
            "landlord": "Maple Court Rentals LLC",
            "rent_amount": "$2,150.00",
            "lease_start_date": "September 1, 2024",
            "lease_end_date": None,
            "property_address": "18 Maple Court, Unit B, Burlington, Vermont 05401",
            "security_deposit": "$2,150.00",
            "cam_charges": None,
            "rent_escalation": None,
            "renewal_options": None,
            "permitted_use": "Retail sale of handmade goods and gifts",
            "exclusivity_clause": None,
            "insurance_requirements": None,
            "default_cure_period": "10 days (rent more than 10 days late; landlord may terminate on written notice)",
            "square_footage": None,
        },
    },
    {
        "id": "L08_park_row_salon_gross",
        "paragraphs": [
            "COMMERCIAL LEASE (GROSS)",
            "",
            "This Lease is entered into between PARK ROW PROPERTIES, INC. (\"Lessor\") and "
            "GILDED THISTLE SALON & SPA, LLC (\"Lessee\") on May 20, 2023.",
            "",
            "1. LEASED PREMISES. Lessor leases to Lessee approximately 2,100 square feet of "
            "ground-floor commercial space commonly known as 92 Park Row, Suite 1, Providence, "
            "Rhode Island 02903.",
            "",
            "2. LENGTH OF LEASE. The term is three (3) years. It begins on July 1, 2023 and ends "
            "on June 30, 2026.",
            "",
            "3. RENT. The total monthly rent is $5,400.00, due on or before the first day of each "
            "month. This is a full-service gross lease; Lessor pays property taxes, building "
            "insurance, water, and common area upkeep. Lessee pays for its own electricity, gas, "
            "telephone, and janitorial service.",
            "",
            "4. RENT INCREASES. Rent shall increase on each July 1 by four percent (4%).",
            "",
            "5. SECURITY DEPOSIT. Lessee shall pay a security deposit of $10,800.00, equal to two "
            "months' rent, on signing.",
            "",
            "6. PERMITTED USE. The premises shall be used only as a hair salon and day spa "
            "offering hair, nail, skincare, and massage services.",
            "",
            "7. EXCLUSIVITY. Lessor agrees that it will not lease any other unit in the 92 Park "
            "Row building to another full-service hair salon or day spa during the term of this "
            "Lease or any renewal.",
            "",
            "8. OPTION TO RENEW. Lessee may renew this Lease for one (1) additional three-year "
            "term by giving Lessor written notice at least one hundred twenty (120) days before "
            "this Lease ends. Rent in the renewal term will continue to increase by four percent "
            "(4%) each July 1.",
            "",
            "9. INSURANCE. Lessee shall carry liability insurance of at least $1,000,000 per "
            "occurrence and shall name Lessor as an additional insured.",
            "",
            "10. DEFAULT. If Lessee does not pay rent within seven (7) days after written notice, "
            "or does not fix any other violation of this Lease within fourteen (14) days after "
            "written notice, Lessee is in default and Lessor may pursue any legal remedy.",
        ],
        "ground_truth": {
            "tenant": "Gilded Thistle Salon & Spa, LLC",
            "landlord": "Park Row Properties, Inc.",
            "rent_amount": "$5,400.00",
            "lease_start_date": "July 1, 2023",
            "lease_end_date": "June 30, 2026",
            "property_address": "92 Park Row, Suite 1, Providence, Rhode Island 02903",
            "security_deposit": "$10,800.00",
            "cam_charges": None,
            "rent_escalation": "4% on each July 1",
            "renewal_options": "One 3-year option; at least 120 days' written notice; 4% annual July 1 increases continue",
            "permitted_use": "A hair salon and day spa offering hair, nail, skincare, and massage services",
            "exclusivity_clause": "Lessor will not lease another unit in the 92 Park Row building to another full-service hair salon or day spa during the term or any renewal",
            "insurance_requirements": "$1,000,000 per occurrence liability insurance; Lessor named as additional insured",
            "default_cure_period": "14 days after written notice for non-monetary default (7 days for monetary)",
            "square_footage": "2,100 sq ft",
        },
    },
    {
        "id": "L09_foundry_flex_space",
        "paragraphs": [
            "FLEX / CREATIVE SPACE LEASE",
            "",
            "LANDLORD: Foundry Block Ventures LLC",
            "TENANT: Halcyon Instruments LLC",
            "",
            "1. THE SPACE. Landlord leases to Tenant Studio 4 at The Foundry, 355 Ironworks "
            "Avenue, Studio 4, Pittsburgh, Pennsylvania 15201, being approximately 2,800 square "
            "feet of combined workshop and office space.",
            "",
            "2. TERM. Twenty-four (24) months, from 2024-03-15 through 2026-03-14. After the "
            "initial term this Lease continues month-to-month until either party gives thirty "
            "(30) days' notice.",
            "",
            "3. RENT. Monthly rent is $4,900.00 for the first twelve (12) months and $5,145.00 "
            "for the second twelve (12) months. Month-to-month holdover rent is 125% of the last "
            "month's rent.",
            "",
            "4. SERVICES INCLUDED. Rent includes electricity, heat, high-speed internet, shared "
            "conference rooms, and use of the loading dock. There is no separate CAM charge; "
            "building services are bundled into rent.",
            "",
            "5. DEPOSIT. A refundable deposit of $4,900.00 is due on signing.",
            "",
            "6. USE. Tenant shall use the Space for light manufacturing and assembly of "
            "electronic measurement instruments, product design, and general office work. No "
            "processes involving open flame or hazardous chemicals are permitted.",
            "",
            "7. RENEWAL. This Lease does not grant a fixed renewal option; continued occupancy "
            "after the initial term is month-to-month as described in Section 2.",
            "",
            "8. INSURANCE. Tenant shall maintain general liability insurance with a limit of at "
            "least $1,000,000 each occurrence.",
            "",
            "9. DEFAULT. Nonpayment of rent not cured within five (5) days of written notice, or "
            "any other default not cured within twenty (20) days of written notice, entitles "
            "Landlord to terminate this Lease.",
        ],
        "ground_truth": {
            "tenant": "Halcyon Instruments LLC",
            "landlord": "Foundry Block Ventures LLC",
            "rent_amount": "$4,900.00",
            "lease_start_date": "March 15, 2024",
            "lease_end_date": "March 14, 2026",
            "property_address": "355 Ironworks Avenue, Studio 4, Pittsburgh, Pennsylvania 15201",
            "security_deposit": "$4,900.00",
            "cam_charges": None,
            "rent_escalation": "$4,900/mo for months 1-12, then $5,145/mo for months 13-24",
            "renewal_options": None,
            "permitted_use": "Light manufacturing and assembly of electronic measurement instruments, product design, and general office work",
            "exclusivity_clause": None,
            "insurance_requirements": "$1,000,000 each occurrence general liability insurance",
            "default_cure_period": "20 days after written notice for non-monetary default (5 days for monetary)",
            "square_footage": "2,800 sq ft",
        },
    },
    {
        "id": "L10_greenline_fitness_percentage",
        "paragraphs": [
            "RETAIL LEASE - FITNESS USE",
            "",
            "THIS RETAIL LEASE is entered into as of the 1st day of August, 2023 between "
            "GREENLINE STATION RETAIL LLC (\"Landlord\") and PACELINE STUDIOS INC. (\"Tenant\").",
            "",
            "1. PREMISES. The Premises is retail unit 210-215 at Greenline Station, 4120 Transit "
            "Parkway, Suite 210, Somerville, Massachusetts 02143, containing approximately 5,600 "
            "rentable square feet.",
            "",
            "2. TERM. The Lease term is eight (8) years. The Commencement Date is November 1, "
            "2023 and the Expiration Date is October 31, 2031.",
            "",
            "3. BASE RENT. Tenant shall pay base rent of $45.00 per rentable square foot per "
            "annum for the first Lease Year ($21,000.00 per month), increasing by three percent "
            "(3%) on each Lease Year anniversary.",
            "",
            "4. PERCENTAGE RENT. Tenant shall also pay percentage rent equal to seven percent "
            "(7%) of the amount by which Gross Sales in any Lease Year exceed the Breakpoint of "
            "$3,600,000.",
            "",
            "5. CAM, TAXES, INSURANCE. Tenant shall pay its pro rata share of common area "
            "maintenance, real estate taxes, and insurance, initially estimated at $11.50 per "
            "rentable square foot per annum.",
            "",
            "6. SECURITY DEPOSIT. Tenant shall deliver a letter of credit or cash security "
            "deposit in the amount of $84,000.00.",
            "",
            "7. USE. The Premises shall be used solely as a boutique indoor cycling and group "
            "fitness studio and the incidental retail sale of fitness apparel and accessories.",
            "",
            "8. EXCLUSIVE USE. Landlord covenants not to lease any other premises at Greenline "
            "Station to a business whose primary use is indoor cycling or spin classes. This "
            "exclusive does not restrict a full-service health club of more than 20,000 square "
            "feet, or a yoga or Pilates studio.",
            "",
            "9. RADIUS RESTRICTION. During the term, neither Tenant nor any affiliate shall "
            "operate another indoor cycling studio within a radius of two (2) miles of the "
            "Premises.",
            "",
            "10. RENEWAL. Tenant shall have one (1) option to renew for five (5) years, on notice "
            "given not less than twelve (12) months prior to expiration, with base rent for the "
            "renewal term at the greater of (a) fair market rent, or (b) the base rent in effect "
            "in the last year of the initial term.",
            "",
            "11. INSURANCE. Tenant shall carry commercial general liability insurance of not less "
            "than $3,000,000 per occurrence, including coverage for participant/athletic injury.",
            "",
            "12. DEFAULT. If Tenant fails to pay rent within five (5) days after written notice, "
            "or fails to cure a non-monetary default within thirty (30) days after written notice "
            "(subject to extension for cures that cannot reasonably be completed in thirty days), "
            "an Event of Default exists.",
        ],
        "ground_truth": {
            "tenant": "Paceline Studios Inc.",
            "landlord": "Greenline Station Retail LLC",
            "rent_amount": "$21,000.00",
            "lease_start_date": "November 1, 2023",
            "lease_end_date": "October 31, 2031",
            "property_address": "4120 Transit Parkway, Suite 210, Somerville, Massachusetts 02143",
            "security_deposit": "$84,000.00",
            "cam_charges": "$11.50 per rentable square foot per annum (pro rata share of CAM, taxes, insurance)",
            "rent_escalation": "3% on each Lease Year anniversary",
            "renewal_options": "One 5-year option; at least 12 months' notice; renewal rent at greater of fair market rent or last-year base rent",
            "permitted_use": "A boutique indoor cycling and group fitness studio plus incidental retail sale of fitness apparel and accessories",
            "exclusivity_clause": "Landlord will not lease other Greenline Station space to a business whose primary use is indoor cycling or spin; carve-outs for a >20,000 sq ft health club and for yoga/Pilates studios",
            "insurance_requirements": "$3,000,000 per occurrence commercial general liability including participant/athletic injury coverage",
            "default_cure_period": "30 days after written notice for non-monetary default (5 days for monetary)",
            "square_footage": "5,600 sq ft",
        },
    },
]


# ----------------------------------------------------------------------
# Rent rolls — three vendor styles covering the ten leases, with a few
# deliberate lease-vs-rent-roll disagreements for the reconciliation demo.
# `_gt` records the planted disagreements so the demo/E2E check can
# confirm the reconciliation engine flags them.
# ----------------------------------------------------------------------

RENT_ROLLS = [
    {
        "name": "rent_roll_broker_q1",
        "headers": ["Property", "Tenant Name", "SF", "Lease Start", "Lease End", "Monthly Rent", "Security Dep"],
        "title_rows": [
            ["Sample Portfolio — Broker Rent Roll (FABRICATED DEMO DATA)"],
            ["As of March 31, 2024"],
            [],
        ],
        "rows": [
            # matches L01 exactly (clean)
            ["2200 Copperfield Road, Suite 140, Maple Grove, Minnesota 55311", "Wren & Kettle Coffee, LLC", "1650", "03/01/2024", "02/28/2029", "$4,675.00", "$9,350.00"],
            # L02 — planted: rent roll rent ($30,200) disagrees with lease base rent ($32,900)
            ["815 Franklin Avenue, Suite 1900, Denver, Colorado 80202", "Northlight Data Systems, Inc.", "9400", "08/01/2023", "07/31/2030", "$30,200.00", "$65,800.00"],
            # L03 — clean
            ["47 Harbor Street, Ground Floor, Santa Cruz, California 95060", "Marisol Hospitality Group, LLC", "3900", "01/01/2023", "12/31/2032", "$12,000.00", "$36,000.00"],
            # L05 — planted: stale expiration (rent roll shows a year earlier)
            ["1330 Wellspring Drive, Suite 220, Cary, North Carolina 27518", "Willowmere Pediatric Associates, PLLC", "4675", "04/01/2024", "09/30/2033", "$12,077.08", "$24,154.16"],
            # L07 — clean (month-to-month; no end date)
            ["18 Maple Court, Unit B, Burlington, Vermont 05401", "The Tinsmith's Daughter LLC", "", "09/01/2024", "", "$2,150.00", "$2,150.00"],
        ],
        "_gt": [
            {"address": "815 Franklin Avenue, Suite 1900, Denver, Colorado 80202", "field": "rent_amount",
             "note": "rent roll $30,200 vs lease base $32,900 — planted rent understatement"},
            {"address": "1330 Wellspring Drive, Suite 220, Cary, North Carolina 27518", "field": "lease_end_date",
             "note": "rent roll 09/30/2033 vs lease September 30, 2034 — planted stale expiration"},
        ],
    },
    {
        "name": "rent_roll_yardi_style",
        "headers": ["Property", "Resident", "Sq Ft", "Move In", "Lease To", "Market Rent", "Rent Charge", "Deposit"],
        "title_rows": [
            ["YARDI VOYAGER — RENT ROLL WITH LEASE CHARGES (FABRICATED DEMO DATA)"],
            [],
        ],
        "rows": [
            # L04 — clean
            ["9401 Distribution Way, Building C, Grove City, Ohio 43123", "Ardent Fulfillment Co.", "90000", "05/01/2024", "07/31/2031", "58000", "55800", "111600"],
            # L06 — clean
            ["600 Lakeshore Boulevard, Evanston, Illinois 60201", "Brightleaf Pharmacy Partners, LLC", "13500", "12/01/2021", "11/30/2036", "24000", "22500", ""],
            # L08 — planted: tenant name form (trade name vs legal entity)
            ["92 Park Row, Suite 1, Providence, Rhode Island 02903", "Gilded Thistle Salon", "2100", "07/01/2023", "06/30/2026", "5600", "5400", "10800"],
            # L10 — planted: rent roll rent is high vs lease base rent
            ["4120 Transit Parkway, Suite 210, Somerville, Massachusetts 02143", "Paceline Studios Inc.", "5600", "11/01/2023", "10/31/2031", "22000", "23100", "84000"],
        ],
        "_gt": [
            {"address": "92 Park Row, Suite 1, Providence, Rhode Island 02903", "field": "tenant",
             "note": "'Gilded Thistle Salon' vs lease 'Gilded Thistle Salon & Spa, LLC' — planted name-form difference"},
            {"address": "4120 Transit Parkway, Suite 210, Somerville, Massachusetts 02143", "field": "rent_amount",
             "note": "rent roll $23,100 vs lease base $21,000 — planted rent overstatement"},
        ],
    },
    {
        "name": "rent_roll_appfolio_style",
        "headers": ["Property", "Tenant", "Sqft", "Start", "End", "Rent", "Deposit Held"],
        "title_rows": [],
        "rows": [
            # L09 — clean
            ["355 Ironworks Avenue, Studio 4, Pittsburgh, Pennsylvania 15201", "Halcyon Instruments LLC", "2800", "03/15/2024", "03/14/2026", "4900", "4900"],
            # L01 again (a second roll covering the same unit) — clean, same figures
            ["2200 Copperfield Road, Suite 140, Maple Grove, Minnesota 55311", "Wren & Kettle Coffee, LLC", "1650", "03/01/2024", "02/28/2029", "4675", "9350"],
            # phantom / vacant unit with no lease on file
            ["2200 Copperfield Road, Suite 155, Maple Grove, Minnesota 55311", "VACANT", "1100", "", "", "", ""],
        ],
        "_gt": [],
    },
]


def build_rent_rolls():
    manifest = []
    for rr in RENT_ROLLS:
        path = os.path.join(OUT_DIR, "rent_rolls", f"{rr['name']}.csv")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            for tr in rr["title_rows"]:
                w.writerow(tr)
            w.writerow(rr["headers"])
            for row in rr["rows"]:
                w.writerow(row)
        manifest.append({"name": rr["name"], "file": f"rent_rolls/{rr['name']}.csv",
                         "planted_disagreements": rr["_gt"]})
    return manifest


def _wrap(c, text, font, size, max_w):
    words, lines, cur = text.split(" "), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if c.stringWidth(trial, font, size) <= max_w:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def render_pdf(path, paragraphs):
    c = canvas.Canvas(path, pagesize=letter)
    width, height = letter
    left, right = 1 * inch, width - 1 * inch
    max_w = right - left
    y = height - 1 * inch
    for para in paragraphs:
        if para == "":
            y -= 0.16 * inch
            continue
        bold = para.isupper() and len(para) < 70
        font = "Helvetica-Bold" if bold else "Helvetica"
        for line in _wrap(c, para, font, 11, max_w):
            if y < 1 * inch:
                c.showPage()
                y = height - 1 * inch
            c.setFont(font, 11)
            c.drawString(left, y, line)
            y -= 0.22 * inch
        y -= 0.08 * inch
    c.save()


def main():
    os.makedirs(LEASE_DIR, exist_ok=True)
    manifest = []
    for lease in LEASES:
        pdf_path = os.path.join(LEASE_DIR, f"{lease['id']}.pdf")
        render_pdf(pdf_path, lease["paragraphs"])
        gt = lease["ground_truth"]
        assert set(gt) == set(FIELDS), f"{lease['id']}: field mismatch {set(gt) ^ set(FIELDS)}"
        manifest.append({"id": lease["id"], "file": f"{lease['id']}.pdf", "ground_truth": gt})

    rr_manifest = build_rent_rolls()

    with open(os.path.join(OUT_DIR, "ground_truth.json"), "w") as f:
        json.dump({"leases": manifest, "rent_rolls": rr_manifest}, f, indent=2)

    with open(os.path.join(OUT_DIR, "ground_truth.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["lease_id", "field", "ground_truth_value"])
        for entry in manifest:
            for field in FIELDS:
                val = entry["ground_truth"][field]
                w.writerow([entry["id"], field, "" if val is None else val])

    print(f"Wrote {len(manifest)} lease PDFs to {LEASE_DIR}")
    print(f"Ground truth: {os.path.join(OUT_DIR, 'ground_truth.json')} and ground_truth.csv")


if __name__ == "__main__":
    main()
