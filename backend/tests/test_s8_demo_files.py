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
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.pdf_extractor import PDFExtractor

DEMO_DIR = os.path.join(
    os.path.dirname(__file__),
    "..",
    "benchmark_data",
    "s8_demo",
)


def test_expected_findings_totals():
    """Each finding's total is monthly x months, and the README's headline
    totals equal the sum of the findings of each kind."""
    with open(os.path.join(DEMO_DIR, "expected_findings.json"), encoding="utf-8") as f:
        findings = json.load(f)["findings"]
    with open(os.path.join(DEMO_DIR, "README.md"), encoding="utf-8") as f:
        readme = f.read()

    sums = {}
    for finding in findings:
        impact = finding.get("dollar_impact")
        if not impact:
            continue
        assert impact["total"] == impact["monthly"] * impact["months"], finding["id"]
        sums[impact["kind"]] = sums.get(impact["kind"], 0) + impact["total"]

    assert set(sums) <= {"confirmed", "potential", "exposure"}, sums
    for kind, total in sums.items():
        assert f"**${total:,} {kind}**" in readme, f"README headline doesn't state ${total:,} {kind}"


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
    """The generator is the source of truth: regenerating (into a temp dir,
    never over the committed files) must reproduce README.md,
    expected_findings.json, the CSV rent roll and every PDF byte-for-byte.
    The .xlsx is skipped -- openpyxl stamps it with the current time."""
    with tempfile.TemporaryDirectory() as out:
        result = subprocess.run(
            [sys.executable, os.path.join(DEMO_DIR, "generate_s8_demo.py")],
            env={**os.environ, "S8_DEMO_OUT_DIR": out},
            capture_output=True,
        )
        assert result.returncode == 0, f"Generator failed: {result.stderr.decode()}"

        compared = 0
        for root, _dirs, files in os.walk(out):
            for fname in files:
                if fname.endswith(".xlsx"):
                    continue
                rel = os.path.relpath(os.path.join(root, fname), out)
                with open(os.path.join(out, rel), "rb") as f:
                    fresh = f.read()
                with open(os.path.join(DEMO_DIR, rel), "rb") as f:
                    committed = f.read()
                assert fresh == committed, f"{rel} differs from a fresh generator run"
                compared += 1
        # 10 tenant PDFs + CSV + README + JSON at minimum.
        assert compared >= 13, compared


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
