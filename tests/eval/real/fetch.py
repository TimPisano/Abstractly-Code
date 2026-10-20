"""
Download the real-document eval set listed in manifest.json.

  python -I tests/eval/real/fetch.py                 # everything that needs no setup
  SEC_USER_AGENT="Your Name you@example.com" python -I tests/eval/real/fetch.py --only lease_edgar_nurix_woodlands

For each document: download the source into sources/ (once), check its
SHA-256 against the manifest, and write the page range the answer key
covers to docs/<id>.pdf. Neither folder is committed (.gitignore); the
manifest, SOURCES.md and the answer keys are.

SEC EDGAR refuses requests that don't carry a User-Agent naming a
contact (https://www.sec.gov/os/accessing-edgar-data), so those
documents are skipped unless SEC_USER_AGENT is set. EDGAR exhibits are
HTML or plain text; they are converted to a text PDF so the same
pipeline reads them.
"""

import argparse
import hashlib
import html
import io
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCES = HERE / "sources"
DOCS = HERE / "docs"
USER_AGENT = "Mozilla/5.0 (compatible; AbstractlyEvalFetcher/1.0; +https://getabstractly.com)"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def download(url: str, user_agent: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(req, timeout=180) as resp:
        return resp.read()


def cut_pages(data: bytes, first: int, last: int) -> bytes:
    from pypdf import PdfReader, PdfWriter
    reader = PdfReader(io.BytesIO(data))
    writer = PdfWriter()
    for i in range(first - 1, min(last, len(reader.pages))):
        writer.add_page(reader.pages[i])
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def text_to_pdf(text: str) -> bytes:
    """Plain text -> a text-layer PDF (Letter, Courier 9 pt), wrapping long lines."""
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    import textwrap
    out = io.BytesIO()
    c = canvas.Canvas(out, pagesize=letter)
    width, height = letter
    y = height - 54
    for raw in text.splitlines() or [""]:
        for line in textwrap.wrap(raw, 95) or [""]:
            if y < 54:
                c.showPage()
                y = height - 54
            c.setFont("Courier", 9)
            c.drawString(54, y, line)
            y -= 11
    c.save()
    return out.getvalue()


def html_to_text(data: bytes) -> str:
    s = data.decode("utf-8", errors="replace")
    s = re.sub(r"(?is)<(script|style).*?</\1>", " ", s)
    s = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|li|h\d|table)>", "\n", s)
    s = re.sub(r"(?s)<[^>]+>", " ", s)
    s = html.unescape(s)
    s = re.sub(r"[ \t\xa0]+", " ", s)
    return re.sub(r"\n\s*\n\s*\n+", "\n\n", s).strip()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--only", nargs="*", help="document ids to fetch")
    args = ap.parse_args(argv)

    manifest = json.loads((HERE / "manifest.json").read_text())
    SOURCES.mkdir(exist_ok=True)
    DOCS.mkdir(exist_ok=True)
    cache = {}
    failed = 0
    for doc in manifest["documents"]:
        if args.only and doc["id"] not in args.only:
            continue
        env = doc.get("requires_env")
        if env and not os.environ.get(env):
            print(f"skip  {doc['id']}: needs {env} (see SOURCES.md)")
            continue
        ua = os.environ[env] if env else USER_AGENT
        src = SOURCES / f"{sha256(doc['url'].encode())[:16]}.{doc['format']}"
        if doc["url"] in cache:
            data = cache[doc["url"]]
        elif src.exists():
            data = src.read_bytes()
        else:
            try:
                data = download(doc["url"], ua)
            except Exception as e:  # network or HTTP error: report and go on
                print(f"FAIL  {doc['id']}: {type(e).__name__}: {e}")
                failed += 1
                continue
            src.write_bytes(data)
        cache[doc["url"]] = data

        got = sha256(data)
        note = ""
        if doc.get("sha256") and got != doc["sha256"]:
            note = "  WARNING: source changed since the answer key was written; recheck it"
        elif not doc.get("sha256"):
            note = f"  (no recorded hash; record sha256 {got} in manifest.json)"

        if doc["format"] == "pdf":
            first, last = doc["pages"]
            out = cut_pages(data, first, last)
        else:
            text = data.decode("utf-8", errors="replace") if doc["format"] == "txt" else html_to_text(data)
            out = text_to_pdf(text)
        (DOCS / f"{doc['id']}.pdf").write_bytes(out)
        print(f"ok    {doc['id']}  ({len(data):,} bytes){note}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
