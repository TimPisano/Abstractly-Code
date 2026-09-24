# Accuracy-benchmark corpus — provenance

**Created:** 2026-09-09
**What this is:** 12 real commercial lease agreements, each filed publicly
with the U.S. Securities and Exchange Commission as an exhibit to a
company filing (10-K, 8-K, S-1, etc.). Retrieved from EDGAR full-text
search. These are genuine executed leases (or, where noted, executed
leases filed as an exhibit), not templates and not machine-generated.

**Why EDGAR:** every document here is already public record, so no
anonymization is required for the benchmark. Name-swapped copies for the
customer demo recording are produced separately (see the demo task) and
are **not** used to compute any accuracy number.

**Selection criteria applied:**
- A complete, standalone lease — not an amendment, assignment, guaranty,
  sublease, estoppel, or SNDA, and **not** a lease with its amendments
  bundled into the same document (checked for "First/Second Amendment",
  "Lease Amendment Agreement", ordinal-word amendment sections, and
  addenda that rewrite core terms).
- Unredacted economic terms (rent, term, deposit). Modern filings
  increasingly redact these with "[***]"; the corpus skews 2001-2006 as
  a result, with 2014 and 2026 leases included for range.
- All 15 abstracted fields determinable by a human reader (a field the
  lease genuinely does not address is recorded as a null in
  `ground_truth.json` — that is the correct extraction result).
- Spread across property types and drafting styles.

## The 12 leases

| # | id | Tenant / Landlord | Type | Lease date | SEC filer (CIK) | Source document |
|---|----|-------------------|------|-----------|-----------------|-----------------|
| 01 | `01_ionetix_office_2026` | Ionetix Radioisotopes, Inc. / Sonya S. Rothstein Trust | Office / medical (triple-net, single-tenant) | 2026-07-31 | Ionetix Corp (0002108121) | EX-10.26, [link](https://www.sec.gov/Archives/edgar/data/2108121/000121390026086823/ea030070001ex10-26.htm) |
| 02 | `02_convera_office_2005` | Convera Corporation / Gateway 44, LLC | Office (multi-tenant) | 2005-06-10 | Convera Corp (0001125536) | EX-10.10, [link](https://www.sec.gov/Archives/edgar/data/1125536/000114036106004931/ex10_10.htm) |
| 05 | `05_conns_retail_2003` | C.A.I., L.P. ("Conn's") / Fiesta Mart, Inc. | Retail (big-box, shopping center) | 2003 | Conn's Inc (0001223389) | EX-10.5, [link](https://www.sec.gov/Archives/edgar/data/1223389/000119312503052980/dex105.txt) |
| 07 | `07_growlife_retail_2014` | GrowLife Hydroponics, Inc. / W-ADP Meadows VII, L.L.C. | Retail (in-line, shopping center) | 2014-01-23 | GrowLife, Inc. (0001161582) | EX-10.17, [link](https://www.sec.gov/Archives/edgar/data/1161582/000135448815004451/phot_ex1017.htm) |
| 10 | `10_dover_retail_2006` | Dover Saddlery Retail, Inc. / Sparks Lot Seven, LLC | Retail + office (single-tenant) | 2006-03-29 | Dover Saddlery Inc (0001071625) | EX-10.38, [link](https://www.sec.gov/Archives/edgar/data/1071625/000095013506003480/b60722dsexv10w38.txt) |
| 13 | `13_altiris_office_2001` | Altiris, Inc. / Canopy Properties, Inc. | Office (multi-tenant) | 2001-12-31 | Altiris Inc (0001139650) | EX-10.6, [link](https://www.sec.gov/Archives/edgar/data/1139650/000101287002000884/dex106.txt) |
| 14 | `14_bareescentuals_office_2006` | MD Beauty, Inc. (Bare Escentuals) / ECI Stevenson LLC | Office (high-rise, multi-suite) | 2005-02-23 | Bare Escentuals Inc (0001295557) | EX-10.37, [link](https://www.sec.gov/Archives/edgar/data/1295557/000104746906009112/a2171457zex-10_37.htm) |
| 15 | `15_formfactor_industrial_2002` | Form Factor, Inc. / Corbett-Rumberger-Duke (individuals) | Industrial (AIR single-tenant net) | 1998-03-12 | FormFactor Inc (0001039399) | EX-10.16, [link](https://www.sec.gov/Archives/edgar/data/1039399/000089161802001883/f80848orex10-16.txt) |
| 16 | `16_dialysis_medical_2001` | Dialysis Corporation of America / Commons Office Research, LLC | Medical / office (multi-tenant) | 2001-06-11 | Dialysis Corp of America (0000201653) | EX-10(i), [link](https://www.sec.gov/Archives/edgar/data/201653/000101905601500333/ex-10i.txt) |
| 17 | `17_familysteak_retail_2002` | Family Steak Houses of Florida, Inc. (Ryan's Grill) / E.D.I. II Investments, Inc. | Retail (build-to-suit restaurant pad) | 2002 | Family Steak Houses of Florida (0000784539) | EX-10.03, [link](https://www.sec.gov/Archives/edgar/data/784539/000101270902001175/ex1003-802.txt) |
| 18 | `18_cuyamacabank_retail_2002` | Cuyamaca Bank, NA / The Auerbach Realty Group, LLC | Retail (bank branch, shopping center) | 2002-12-23 | Community Bancorp Inc (0001089503) | EX-10.23, [link](https://www.sec.gov/Archives/edgar/data/1089503/000119312505050828/dex1023.htm) |
| 19 | `19_saflink_office_2003` | Saflink Corporation / VA Branches, LLC | Office (multi-tenant "deed of lease") | 2003-11-10 | Saflink Corp (0000847555) | EX-10.8, [link](https://www.sec.gov/Archives/edgar/data/847555/000119312504054097/dex108.htm) |

Type mix: 5 office, 1 office/medical, 1 medical, 4 retail, 1 industrial.
Vintages: 1998-2026 (lease dates). Rent structures represented: flat,
stepped, CPI-indexed, percentage rent, triple-net.

## Files

- `leases/*.pdf` — the source documents, converted from the EDGAR HTML/text
  to PDF (headless Chrome print-to-PDF) so they run through the upload
  pipeline the same way a customer PDF would.
- `leases_txt/*.txt` — plain-text extraction of each, for reference while
  building/checking ground truth.
- `raw/*` — the original EDGAR bytes and the intermediate render HTML.
- `ground_truth.json` / `ground_truth.csv` — the 15-field answer key,
  recorded by hand from the source documents. See that file's `_meta`.

## Numbered gaps (03, 04, 06, 08, 09, 11, 12)

Those ids were earlier candidates dropped during ground-truth review for
bundling amendments or internal contradictions (Credence, Velodyne,
McCormick, Ukrop's, PTEK, Saxon, Imperium). They were replaced by 13-19.
The gaps in the numbering are deliberate — kept so the ids are stable.
