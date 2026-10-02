"""
Renders a credit memo to Word (.docx) using python-docx (already a
dependency at 1.2.0 -- no new package).

Word, not PDF, because a credit memo is a document a bank analyst EDITS.
They add the sponsor section, write the recommendation, adjust language
for their committee, and put it on their own letterhead. A PDF would make
this a dead end; the existing PDF/Excel exports in the app
(investment_memo.py, deal_mismatch_export.py) are for documents meant to
be read as-issued, which is a different job.

This module renders. It computes nothing, calls no model, and decides no
layout of its own -- the section order and headings come from
credit_memo_template.py, and every figure comes from the engine via
credit_memo.build_credit_memo_data. If a figure looks wrong in the .docx,
the bug is upstream of here.

Each template block in SECTIONS maps to one `_render_*` function below.
Adding a block to a lender's template means adding one function here;
an unknown block name renders a visible marker rather than failing
silently, so a template typo is obvious in the output instead of
producing a quietly short document.
"""
import io
from typing import Any, Dict, List, Optional

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, RGBColor

from .normalize import format_currency

# Muted grey for source citations and caveats -- present and readable,
# but visually subordinate to the figures themselves.
_MUTED = RGBColor(0x66, 0x66, 0x66)


def _money(value: Optional[float]) -> str:
    """Currency, or an explicit marker. Never a blank cell: a blank in a financial table reads as zero, and an unknown is not a zero."""
    return format_currency(value) if value is not None else "n/a"


def _pct(value: Optional[float], places: int = 2) -> str:
    return f"{value:.{places}f}%" if value is not None else "n/a"


def _ratio(value: Optional[float]) -> str:
    return f"{value:.2f}x" if value is not None else "n/a"


def _add_table(document: Document, rows: List[List[str]]) -> None:
    """
    A two-or-more-column table with the first row as a bold header.
    'Table Grid' is python-docx's only guaranteed-present bordered style;
    anything else risks a KeyError on a default template.
    """
    if not rows:
        return
    table = document.add_table(rows=len(rows), cols=len(rows[0]))
    table.style = "Table Grid"
    for row_index, row in enumerate(rows):
        for col_index, value in enumerate(row):
            cell = table.cell(row_index, col_index)
            cell.text = str(value)
            if row_index == 0:
                for paragraph in cell.paragraphs:
                    for run in paragraph.runs:
                        run.bold = True
    document.add_paragraph()


def _add_muted(document: Document, text: str) -> None:
    paragraph = document.add_paragraph()
    run = paragraph.add_run(text)
    run.font.size = Pt(8)
    run.font.color.rgb = _MUTED


def _source_label(source: Optional[Dict[str, Any]]) -> str:
    """
    A citation a reader can actually follow back to the document.

    A T-12 is a spreadsheet, so its citation is a ROW. A lease PDF's is a
    PAGE. This prints whichever the source actually has and never invents
    the other -- "every input number links to its source document and
    page where one exists" is satisfied by citing the real locator, not
    by printing "page 1" for a worksheet.
    """
    if not source:
        return ""
    parts = [source.get("file") or "source document"]
    if source.get("page") is not None:
        parts.append(f"p. {source['page']}")
    if source.get("row") is not None:
        parts.append(f"row {source['row']}")
    if source.get("quote"):
        parts.append(f'"{source["quote"]}"')
    return " - ".join(parts)


# ----------------------------------------------------------------------
# Block renderers -- one per block name in credit_memo_template.SECTIONS
# ----------------------------------------------------------------------

def _render_loan_terms_table(document: Document, memo: Dict[str, Any]) -> None:
    terms = memo["underwriting"]["loan_terms"]
    basis = memo["underwriting"]["value_basis"]
    rows = [
        ["Loan term", "Value"],
        ["Loan amount", _money(terms.get("loan_amount"))],
        ["Interest rate", _pct(terms.get("annual_rate_pct"))],
        ["Amortization", f"{terms.get('amortization_years')} years"],
        ["Term", f"{terms.get('term_years')} years" if terms.get("term_years") else "n/a"],
        ["Interest-only period", f"{terms.get('interest_only_months') or 0} months"],
        ["Purchase price", _money(terms.get("purchase_price"))],
        ["Appraised value", _money(terms.get("appraised_value"))],
        ["Value basis for LTV", f"{_money(basis.get('value_basis'))} ({basis.get('value_basis_source') or 'n/a'})"],
        ["Units", str(terms.get("unit_count") or "n/a")],
    ]
    _add_table(document, rows)
    _add_muted(
        document,
        "Loan terms are as entered by the analyst from the term sheet; this application has "
        "no source document for them and does not cite one.",
    )


def _render_headline_ratios_table(document: Document, memo: Dict[str, Any]) -> None:
    underwriting = memo["underwriting"]
    ratios = underwriting["ratios"]
    rows = [
        ["Metric", "Value", "Test"],
        ["Underwritten NOI", _money(underwriting["noi_build_up"]["underwritten_noi"]), "-"],
        ["DSCR (amortizing)", _ratio(ratios.get("dscr")),
         f"target {underwriting['constraints_used']['target_dscr']}x"],
        ["LTV", _pct(ratios.get("ltv_pct")),
         f"max {_pct(underwriting['constraints_used']['max_ltv_pct'])}"],
        ["Debt yield", _pct(ratios.get("debt_yield_pct")),
         f"min {_pct(underwriting['constraints_used']['min_debt_yield_pct'])}"],
        ["Breakeven occupancy", _pct(ratios.get("breakeven_occupancy_pct")), "-"],
    ]
    _add_table(document, rows)


def _render_binding_constraint_statement(document: Document, memo: Dict[str, Any]) -> None:
    sizing = memo["underwriting"]["sizing"]
    requested = memo["underwriting"]["loan_terms"].get("loan_amount")
    maximum = sizing.get("maximum_loan")

    paragraph = document.add_paragraph()
    paragraph.add_run("Binding constraint: ").bold = True
    paragraph.add_run(sizing.get("binding_constraint_label") or "not determinable")

    paragraph = document.add_paragraph()
    paragraph.add_run("Maximum supportable loan: ").bold = True
    paragraph.add_run(_money(maximum))
    if requested is not None and maximum is not None:
        difference = round(maximum - requested, 2)
        if difference < 0:
            paragraph.add_run(
                f" - {_money(abs(difference))} BELOW the {_money(requested)} requested."
            ).bold = True
        else:
            paragraph.add_run(f" - {_money(difference)} of headroom above the {_money(requested)} requested.")
    document.add_paragraph()


def _render_recommendation_placeholder(document: Document, memo: Dict[str, Any]) -> None:
    """
    The recommendation line. Always the placeholder, never a verdict --
    see credit_memo_template.RECOMMENDATION_PLACEHOLDER. Rendered bold so
    nobody circulates the memo without noticing it needs completing.
    """
    paragraph = document.add_paragraph()
    run = paragraph.add_run(memo["recommendation_placeholder"])
    run.bold = True
    document.add_paragraph()


def _render_property_table(document: Document, memo: Dict[str, Any]) -> None:
    underwriting = memo["underwriting"]
    snapshot = underwriting.get("t12_snapshot") or {}
    rows = [
        ["Item", "Value"],
        ["Property address", memo.get("property_address") or "n/a"],
        ["Deal name", memo.get("deal_name") or "n/a"],
        ["Units", str(underwriting["loan_terms"].get("unit_count") or "n/a")],
        ["Historical T-12 NOI", _money(underwriting.get("historical_noi"))],
        ["Underwritten NOI", _money(underwriting["noi_build_up"]["underwritten_noi"])],
        ["T-12 source file", snapshot.get("filename") or "n/a"],
    ]
    _add_table(document, rows)


def _render_sponsor_placeholder(document: Document, memo: Dict[str, Any]) -> None:
    paragraph = document.add_paragraph()
    run = paragraph.add_run(memo["sponsor_placeholder"])
    run.bold = True
    document.add_paragraph()


def _render_rent_roll_table(document: Document, memo: Dict[str, Any]) -> None:
    """
    The rent-roll-versus-lease findings from the app's Deal Mismatch
    engine, plus the T-12's billed-versus-collected gap.

    The empty case is handled explicitly and loudly. "No lease documents
    on file" is a DATA GAP, and printing "0 discrepancies" there would
    tell a credit officer the rent roll had been verified clean when
    nothing was verified at all.
    """
    underwriting = memo["underwriting"]
    analysis = underwriting.get("rent_roll_analysis") or {}
    snapshot = underwriting.get("t12_snapshot") or {}
    t12_inputs = snapshot.get("t12_inputs") or {}

    if not analysis.get("has_lease_data"):
        paragraph = document.add_paragraph()
        run = paragraph.add_run(
            "No lease documents are on file for this property in this application, so the "
            "rent roll has NOT been verified against signed leases. This is a data gap, not "
            "a clean result."
        )
        run.bold = True
        document.add_paragraph()
    else:
        _add_table(document, [
            ["Rent roll vs. lease check", "Value"],
            ["Units checked", str(analysis.get("total_units_checked"))],
            ["Discrepancies found", str(analysis.get("total_discrepancies"))],
            ["Annual income overstatement", _money(analysis.get("annual_income_overstatement"))],
        ])

        discrepancies = analysis.get("discrepancies") or []
        if discrepancies:
            detail = [["Unit", "Type", "Rent roll", "Lease", "Annual impact", "Source"]]
            for row in discrepancies[:40]:
                detail.append([
                    row.get("unit") or "n/a",
                    row.get("discrepancy_type") or "",
                    str(row.get("rent_roll_value") or "n/a"),
                    str(row.get("lease_value") or "n/a"),
                    _money(row.get("annual_dollar_impact")),
                    _source_label(row.get("source")) or "no lease on file",
                ])
            _add_table(document, detail)
            if len(discrepancies) > 40:
                _add_muted(document, f"Showing the first 40 of {len(discrepancies)} findings.")

    collected = t12_inputs.get("total_rent_collected")
    billed = t12_inputs.get("net_rental_income_billed")
    if collected is not None or billed is not None:
        _add_table(document, [
            ["T-12 collections", "Value"],
            ["Net rental income billed", _money(billed)],
            ["Total rent collected", _money(collected)],
            ["Shortfall",
             _money(round(billed - collected, 2)) if (billed is not None and collected is not None) else "n/a"],
        ])


def _render_noi_build_up_table(document: Document, memo: Dict[str, Any]) -> None:
    """
    The full NOI build-up, line by line, with each T-12-sourced figure's
    citation. This is the table that makes the memo auditable: a reviewer
    can take any line back to the exact row of the operating statement it
    came from.
    """
    build_up = memo["underwriting"]["noi_build_up"]
    sources = memo["underwriting"].get("sources") or {}

    def citation(key: str) -> str:
        return _source_label(sources.get(key))

    rows = [
        ["Line", "Amount", "Source"],
        ["Gross potential rent", _money(build_up["gross_potential_rent"]), citation("gross_potential_rent")],
        [f"Less: vacancy at {_pct(build_up['vacancy_pct'])}", f"({_money(build_up['vacancy_amount'])})",
         "underwriting assumption"],
        ["Less: loss to lease", f"({_money(build_up['loss_to_lease'])})", citation("loss_to_lease")],
        ["Less: concessions", f"({_money(build_up['concessions'])})", citation("concessions")],
        ["Less: bad debt / collection loss", f"({_money(build_up['bad_debt'])})", citation("bad_debt")],
        ["Effective rental income", _money(build_up["effective_rental_income"]), "computed"],
        ["Plus: other income", _money(build_up["other_income"]), citation("other_income")],
        ["Effective gross income", _money(build_up["effective_gross_income"]), "computed"],
        ["Less: operating expenses (ex. management fee)",
         f"({_money(build_up['operating_expenses_ex_management'])})",
         citation("operating_expenses_ex_management")],
        [f"Less: management fee at {_pct(build_up['management_fee_pct'])} of EGI",
         f"({_money(build_up['management_fee'])})", "underwriting assumption"],
        [f"Less: replacement reserves at {_money(build_up['replacement_reserves_per_unit'])}/unit",
         f"({_money(build_up['replacement_reserves'])})", "underwriting assumption"],
        ["UNDERWRITTEN NOI", _money(build_up["underwritten_noi"]), "computed"],
    ]
    _add_table(document, rows)

    snapshot = memo["underwriting"].get("t12_snapshot") or {}
    if snapshot.get("management_fee_removed") is not None:
        _add_muted(
            document,
            f"The T-12's own management fee of {_money(snapshot['management_fee_removed'])} was "
            "removed from the operating expense total before the underwritten management fee "
            "above was applied, so the fee is charged once rather than twice.",
        )
    _add_muted(
        document,
        "Replacement reserves are an underwriting addition, not a T-12 line item - an operating "
        "statement records what was spent, while a lender charges a forward-looking per-unit "
        "reserve. Underwritten NOI therefore sits below historical NOI even at identical vacancy.",
    )


def _render_historical_vs_underwritten_table(document: Document, memo: Dict[str, Any]) -> None:
    underwriting = memo["underwriting"]
    historical = underwriting.get("historical_noi")
    underwritten = underwriting["noi_build_up"]["underwritten_noi"]
    rows = [
        ["Measure", "Historical (T-12)", "Underwritten"],
        ["Net operating income", _money(historical), _money(underwritten)],
        ["Difference", "-",
         _money(round(underwritten - historical, 2)) if historical is not None else "n/a"],
    ]
    _add_table(document, rows)


def _render_t12_line_items_table(document: Document, memo: Dict[str, Any]) -> None:
    """Every line the T-12 parser read, with its row number -- the raw evidence behind the build-up above."""
    snapshot = memo["underwriting"].get("t12_snapshot") or {}
    line_items = snapshot.get("line_items") or []
    if not line_items:
        return
    rows = [["T-12 line item", "Annual amount", "Row"]]
    for item in line_items:
        rows.append([
            item.get("label", ""),
            _money(item.get("annual_amount")),
            str((item.get("source") or {}).get("row", "")),
        ])
    _add_table(document, rows)
    _add_muted(
        document,
        f"Read from {snapshot.get('filename') or 'the uploaded operating statement'}. "
        "Row numbers refer to that file; a spreadsheet has no page numbers.",
    )


def _render_ratios_table(document: Document, memo: Dict[str, Any]) -> None:
    underwriting = memo["underwriting"]
    ratios = underwriting["ratios"]
    debt_service = underwriting["debt_service"]
    rows = [
        ["Ratio", "Value", "Basis"],
        ["DSCR (fully amortizing)", _ratio(ratios.get("dscr")),
         f"NOI / {_money(debt_service.get('annual_debt_service_amortizing'))} annual debt service"],
        ["DSCR (year one as paid)", _ratio(ratios.get("dscr_year_one")),
         f"NOI / {_money(debt_service.get('annual_debt_service_year_one'))}"],
        ["DSCR (interest-only)", _ratio(ratios.get("dscr_interest_only")),
         f"NOI / {_money(debt_service.get('annual_debt_service_interest_only'))}"],
        ["LTV", _pct(ratios.get("ltv_pct")), f"against {ratios.get('ltv_basis') or 'n/a'}"],
        ["LTV vs. purchase price", _pct(ratios.get("ltv_vs_purchase_price_pct")), "-"],
        ["LTV vs. appraised value", _pct(ratios.get("ltv_vs_appraised_value_pct")), "-"],
        ["Debt yield", _pct(ratios.get("debt_yield_pct")), "NOI / loan amount"],
        ["Breakeven occupancy", _pct(ratios.get("breakeven_occupancy_pct")),
         "(operating expenses + debt service) / potential income"],
    ]
    _add_table(document, rows)
    _add_muted(
        document,
        "DSCR is quoted on fully amortizing debt service as the headline figure, because that is "
        "the payment the property must service once any interest-only period expires. "
        "Breakeven occupancy includes replacement reserves and holds operating expenses fixed.",
    )


def _render_max_loan_table(document: Document, memo: Dict[str, Any]) -> None:
    sizing = memo["underwriting"]["sizing"]
    constraints = memo["underwriting"]["constraints_used"]
    binding = sizing.get("binding_constraint")
    rows = [["Constraint", "Test", "Maximum loan", "Binds?"]]
    for key, label, test in [
        ("dscr", "Target DSCR", f"{constraints['target_dscr']}x"),
        ("ltv", "Maximum LTV", _pct(constraints["max_ltv_pct"])),
        ("debt_yield", "Minimum debt yield", _pct(constraints["min_debt_yield_pct"])),
    ]:
        rows.append([
            label, test, _money(sizing.get(f"max_loan_by_{key}")),
            "YES" if key == binding else "",
        ])
    _add_table(document, rows)


def _render_stress_table(document: Document, memo: Dict[str, Any]) -> None:
    rows = [["Stress case", "NOI", "DSCR", "Debt yield", "Breakeven occ.", "Max loan", "Binds"]]
    for case in memo["underwriting"].get("stress_tests", []):
        rows.append([
            case["label"],
            _money(case["underwritten_noi"]),
            _ratio(case["dscr"]),
            _pct(case["debt_yield_pct"]),
            _pct(case["breakeven_occupancy_pct"]),
            _money(case["maximum_loan"]),
            case.get("binding_constraint") or "",
        ])
    _add_table(document, rows)
    _add_muted(
        document,
        "Occupancy stresses are applied as additional vacancy on top of the underwriting "
        "assumption, so \"occupancy -10 points\" against a 5% vacancy assumption means 15% vacancy.",
    )


def _render_narrative(document: Document, memo: Dict[str, Any], section_key: str) -> None:
    prose = (memo.get("narratives") or {}).get(section_key)
    if not prose:
        return
    for block in [p.strip() for p in prose.split("\n\n") if p.strip()]:
        document.add_paragraph(block)
    document.add_paragraph()


def _render_assumptions_appendix(document: Document, memo: Dict[str, Any]) -> None:
    """
    Every assumption and constraint, with whether it's still the default.
    An appendix rather than a section because it's reference material --
    but it's in the document, because "every assumption is visible" has to
    survive the memo leaving the app.
    """
    rows = memo["underwriting"].get("assumption_rows") or []
    if not rows:
        return
    document.add_heading("Appendix A - Assumptions and Constraints Used", level=1)
    table_rows = [["Assumption", "Value", "Unit", "Type", "Default?"]]
    for row in rows:
        table_rows.append([
            row["label"], str(row["value"]), row["unit"], row["kind"],
            "default" if row["is_default"] else "EDITED",
        ])
    _add_table(document, table_rows)
    _add_muted(
        document,
        "These are analyst judgments, not figures read from a document, so they carry no source "
        "citation. Figures taken from a document cite it in the tables above.",
    )


def _render_sources_appendix(document: Document, memo: Dict[str, Any]) -> None:
    """Every input number and where it came from, in one place -- the audit trail for the whole memo."""
    rows = memo["underwriting"].get("input_rows") or []
    if not rows:
        return
    document.add_heading("Appendix B - Input Sources", level=1)
    table_rows = [["Input", "Value", "Origin", "Source"]]
    for row in rows:
        value = row.get("value")
        table_rows.append([
            row["label"],
            _money(value) if isinstance(value, (int, float)) else str(value if value is not None else "n/a"),
            "T-12 document" if row["origin"] == "t12_document" else "entered by analyst",
            _source_label(row.get("source")) or "no source document",
        ])
    _add_table(document, table_rows)


_BLOCK_RENDERERS = {
    "loan_terms_table": _render_loan_terms_table,
    "headline_ratios_table": _render_headline_ratios_table,
    "binding_constraint_statement": _render_binding_constraint_statement,
    "recommendation_placeholder": _render_recommendation_placeholder,
    "property_table": _render_property_table,
    "sponsor_placeholder": _render_sponsor_placeholder,
    "rent_roll_table": _render_rent_roll_table,
    "noi_build_up_table": _render_noi_build_up_table,
    "historical_vs_underwritten_table": _render_historical_vs_underwritten_table,
    "t12_line_items_table": _render_t12_line_items_table,
    "ratios_table": _render_ratios_table,
    "max_loan_table": _render_max_loan_table,
    "stress_table": _render_stress_table,
}


def generate_credit_memo_docx(memo: Dict[str, Any]) -> bytes:
    """
    Renders `credit_memo.build_credit_memo_data`'s output to .docx bytes.

    Walks credit_memo_template.SECTIONS in order and renders each block
    through _BLOCK_RENDERERS. An unrecognized block name emits a visible
    "[ unrecognized template block ]" marker rather than being skipped --
    a typo in a swapped-in lender template should be obvious in the
    output, not produce a quietly incomplete memo.
    """
    document = Document()

    document.add_heading(memo["title"], level=0)

    subtitle = document.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.LEFT
    label = memo.get("deal_name") or memo.get("property_address") or "Loan request"
    run = subtitle.add_run(f"{label}\nPrepared {memo['generated_date']}")
    run.bold = True

    _add_muted(document, memo["preamble"])

    if not memo.get("narratives_generated"):
        paragraph = document.add_paragraph()
        run = paragraph.add_run(
            f"NOTE: narrative sections were not generated ({memo.get('narratives_reason')}). "
            "All computed figures below are complete and unaffected."
        )
        run.bold = True

    for section in memo["sections"]:
        document.add_heading(section["heading"], level=1)
        for block in section["blocks"]:
            if block == "narrative":
                _render_narrative(document, memo, section["key"])
                continue
            renderer = _BLOCK_RENDERERS.get(block)
            if renderer is None:
                document.add_paragraph(f"[ unrecognized template block: {block} ]")
                continue
            renderer(document, memo)

    _render_assumptions_appendix(document, memo)
    _render_sources_appendix(document, memo)

    document.add_paragraph()
    _add_muted(document, memo["footer"])

    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()
