# Abstractly

**AI-powered lease abstraction and rent roll validation for commercial real estate.**

Abstractly turns unstructured lease PDFs into clean, structured, source-cited data — then goes a step further by validating that data against rent rolls to catch the discrepancies that cost CRE teams time and money. What used to be hours of manual abstraction and line-by-line rent roll reconciliation becomes a workflow measured in minutes, with every extracted figure traceable back to the page and clause it came from.

## Key Features

- **AI-powered lease abstraction** — extracts tenant, rent, escalations, CAM charges, renewal options, and other key terms from lease PDFs, with a page-level source citation and confidence score on every field
- **Rent roll validation** — imports a rent roll and automatically reconciles it against abstracted lease data, flagging mismatches before they become costly errors
- **Portfolio dashboard** — aggregate metrics (total rent, CAM exposure, square footage), sortable/filterable lease list, and a portfolio health score at a glance
- **Automated risk detection** — flags below-market rent, missing standard clauses, notice-period outliers, and inconsistent terms
- **Grounded Q&A assistant** — ask plain-English questions about the portfolio and get answers backed by real citations, not guesses
- **Lease comparison & benchmarking** — compare leases side by side or against the portfolio average
- **Exports** — rent roll (CSV/Excel), investment memos, and printable portfolio summary reports
- **Multi-user access** — role-based accounts (owner/admin) with secure authentication

## Tech Stack

**Backend:** Python, Flask, SQLite — PDF/OCR parsing (pypdf, pdfplumber, Tesseract), Claude (Anthropic API) for AI-driven extraction and the Q&A assistant, bcrypt-based authentication

**Frontend:** Vanilla JavaScript, HTML5, CSS — no framework or build step

**Deployment:** Dockerized backend deployed on Render, static frontend served separately

## How It Works

1. **Upload** — drag in one or more lease PDFs, plus a rent roll if you have one
2. **Extract** — Abstractly reads each lease and pulls out the key terms, citing the exact page and quote behind every value
3. **Validate** — rent roll figures are automatically checked against the abstracted lease terms, and any discrepancies are surfaced immediately
4. **Analyze** — the portfolio dashboard rolls everything up into metrics, risk flags, and a health score
5. **Ask & export** — query the portfolio in plain English, or export a rent roll, investment memo, or summary report

## Demo

*Screenshots / live demo link coming soon.*

## Getting Started

```bash
# Backend
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python run.py            # runs on http://localhost:5000

# Frontend
cd frontend
python3 -m http.server 8080   # open http://localhost:8080
```

AI-powered extraction and the Q&A assistant require an `ANTHROPIC_API_KEY`; without one, the app runs on its built-in rule-based extraction engine.

---

*Abstractly is a portfolio project built to explore AI-assisted document intelligence for commercial real estate.*
