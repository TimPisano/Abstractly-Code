"""
Validation for the synthetic Section 8 demo property (Oak Hollow Apartments).

This test guards the demo data fixtures in backend/benchmark_data/s8_demo/:
  - expected_findings.json totals match the sum of findings by category;
  - every finding's cited page and PDF exists and is readable;
  - the findings are internally consistent;
  - the generator reproduces byte-identical outputs (except .xlsx).

No network, no Anthropic API.
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.pdf_extractor import PDFExtractor

DEMO_DIR = os.path.join(
    os.path.dirname(__file__),
    "..",
    "benchmark_data",
    "s8_demo",
)


def test_expected_findings_totals():
    """Confirm that total dollar amounts equal the sum of individual findings."""
    with open(os.path.join(DEMO_DIR, "expected_findings.json"), encoding="utf-8") as f:
        findings = json.load(f)

    findings_list = findings.get("findings", [])

    # Group by kind (confirmed vs potential) and sum
    totals_by_kind = {}
    for finding in findings_list:
        impact = finding.get("dollar_impact")
        if impact:
            kind = impact.get("kind")
            total = impact.get("total", 0)
            if kind not in totals_by_kind:
                totals_by_kind[kind] = 0
            totals_by_kind[kind] += total

    # Expected totals as stated in README
    expected_confirmed = 1451
    expected_potential = 17981

    actual_confirmed = totals_by_kind.get("confirmed", 0)
    actual_potential = totals_by_kind.get("potential", 0)
    actual_exposure = totals_by_kind.get("exposure", 0)

    # E1 and E6 are now "exposure" not "potential"; they were in potential before
    # But let's check what we actually have
    print(
        f"Confirmed: {actual_confirmed} (expected {expected_confirmed})",
    )
    print(
        f"Potential: {actual_potential} (expected {expected_potential})",
    )
    print(f"Exposure: {actual_exposure}")

    # E1 ($2,886) and E6 ($1,630) changed from potential to exposure
    # So new totals: confirmed stays 1,451; potential = 17,981 - 2,886 - 1,630 = 13,465; exposure = 4,516
    expected_confirmed_new = 1451
    expected_potential_new = 17981 - 2886 - 1630  # 13,465
    expected_exposure_new = 2886 + 1630  # 4,516

    assert (
        actual_confirmed == expected_confirmed_new
    ), f"Confirmed total mismatch: got {actual_confirmed}, expected {expected_confirmed_new}"
    assert (
        actual_potential == expected_potential_new
    ), f"Potential total mismatch: got {actual_potential}, expected {expected_potential_new}"
    assert (
        actual_exposure == expected_exposure_new
    ), f"Exposure total mismatch: got {actual_exposure}, expected {expected_exposure_new}"


def test_pdf_pages_exist():
    """Confirm every cited page exists in its PDF."""
    with open(os.path.join(DEMO_DIR, "expected_findings.json"), encoding="utf-8") as f:
        findings = json.load(f)

    extractor = PDFExtractor()
    pdf_cache = {}

    def get_pdf_pages(rel_path):
        """Cache PDF page counts to avoid re-reading."""
        if rel_path not in pdf_cache:
            full_path = os.path.join(DEMO_DIR, rel_path)
            assert os.path.exists(
                full_path
            ), f"PDF not found: {full_path}"
            try:
                with open(full_path, "rb") as f:
                    pages = extractor.extract_text(f, pdf_path=full_path)
                pdf_cache[rel_path] = pages
            except Exception as e:
                raise AssertionError(
                    f"Failed to extract pages from {full_path}: {e}"
                )
        return pdf_cache[rel_path]

    findings_list = findings.get("findings", [])
    for finding in findings_list:
        finding_id = finding.get("id")
        evidence = finding.get("evidence", [])
        for ev in evidence:
            rel_path = ev.get("file")
            page_num = ev.get("page")

            if rel_path and page_num:
                # Page numbers in the JSON are 1-indexed; PDF extraction is 0-indexed
                try:
                    pages = get_pdf_pages(rel_path)
                    assert (
                        page_num <= len(pages)
                    ), f"{finding_id}: page {page_num} cited in {rel_path}, but PDF has only {len(pages)} pages"
                except AssertionError as e:
                    raise e
                except Exception as e:
                    raise AssertionError(
                        f"{finding_id}: error checking {rel_path} page {page_num}: {e}"
                    )


def test_clean_units_exist():
    """Confirm that clean control units are mentioned but have no findings."""
    with open(os.path.join(DEMO_DIR, "expected_findings.json"), encoding="utf-8") as f:
        findings = json.load(f)

    clean_units = findings.get("clean_units", [])
    assert clean_units, "No clean units listed (expected at least one control)"

    findings_list = findings.get("findings", [])
    found_units = set()
    for finding in findings_list:
        for unit in finding.get("units", []):
            found_units.add(unit)

    for clean_unit in clean_units:
        assert (
            clean_unit not in found_units
        ), f"Clean control unit {clean_unit} should have no findings but does"


def test_generator_reproducibility():
    """Confirm that regenerating produces byte-identical outputs.

    The generator is the source of truth. Running it again with no code changes
    must produce identical PDFs, CSV, README, and JSON (Excel differs only by timestamp).
    """
    # Read current files before regeneration
    with open(os.path.join(DEMO_DIR, "expected_findings.json"), "rb") as f:
        json_before = f.read()
    with open(os.path.join(DEMO_DIR, "README.md"), "rb") as f:
        readme_before = f.read()

    # List all PDFs and CSV before
    files_dir = os.path.join(DEMO_DIR, "tenant_files")
    rent_roll_dir = os.path.join(DEMO_DIR, "rent_roll")
    pdfs_before = {}
    for fname in os.listdir(files_dir):
        if fname.endswith(".pdf"):
            with open(os.path.join(files_dir, fname), "rb") as f:
                pdfs_before[fname] = f.read()

    with open(os.path.join(rent_roll_dir, "oak_hollow_rent_roll_40unit.csv"), "rb") as f:
        csv_before = f.read()

    # Regenerate
    backend_dir = os.path.dirname(os.path.dirname(DEMO_DIR))
    result = subprocess.run(
        [sys.executable, "benchmark_data/s8_demo/generate_s8_demo.py"],
        cwd=backend_dir,
        capture_output=True,
    )
    assert result.returncode == 0, f"Generator failed: {result.stderr.decode()}"

    # Compare files after regeneration
    with open(os.path.join(DEMO_DIR, "expected_findings.json"), "rb") as f:
        json_after = f.read()
    assert json_before == json_after, "expected_findings.json changed after regeneration"

    with open(os.path.join(DEMO_DIR, "README.md"), "rb") as f:
        readme_after = f.read()
    assert readme_before == readme_after, "README.md changed after regeneration"

    for fname in pdfs_before:
        with open(os.path.join(files_dir, fname), "rb") as f:
            pdf_after = f.read()
        assert pdfs_before[fname] == pdf_after, f"PDF {fname} changed after regeneration"

    with open(os.path.join(rent_roll_dir, "oak_hollow_rent_roll_40unit.csv"), "rb") as f:
        csv_after = f.read()
    assert csv_before == csv_after, "CSV rent roll changed after regeneration"


if __name__ == "__main__":
    test_expected_findings_totals()
    print("✓ test_expected_findings_totals")

    test_pdf_pages_exist()
    print("✓ test_pdf_pages_exist")

    test_clean_units_exist()
    print("✓ test_clean_units_exist")

    test_generator_reproducibility()
    print("✓ test_generator_reproducibility")

    print("\nAll tests passed.")
