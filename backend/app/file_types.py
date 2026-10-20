"""
Decides what an uploaded file really is from its CONTENT (magic bytes,
the inside of ZIP / OLE2 containers, a text heuristic), not from the name
the browser sent. Used by the large-file upload pipeline (app/upload_jobs.py)
before anything parses the file.

Why content and not extension: the filename is fully attacker- and
accident-controlled. Before this, a PNG named lease.pdf failed with
"this PDF may be corrupted", a Windows executable named tool.pdf got the
same message, and a PDF named lease.txt was decoded as text and saved as
a garbage lease (see docs/plans/large-files-repro.txt, scenario F).

The result's `extension` is a canonical one ("pdf", "docx", ...) that the
existing extractors dispatch on (document_extractor.extract_pages and
rent_roll_import.parse_rent_roll_file both choose a parser by extension),
so a mislabeled-but-valid file is processed as what it actually is.

Only the first few KB are read (plus the ZIP/OLE2 directory for Office
files), so this is cheap on a 150 MB upload.
"""
import os
import zipfile
import zlib
from typing import List, Optional

import olefile
from lxml import etree

_HEAD_BYTES = 64 * 1024

# Office files are ZIPs that their parsers inflate fully in memory. A real
# lease .docx or a 5,000-row rent-roll .xlsx inflates to a few MB; a
# "zip bomb" inflates a small upload to gigabytes and takes the server
# down with it. Checked from the ZIP alone, before any parser runs
# (security review of this branch).
MAX_ZIP_UNCOMPRESSED_BYTES = 64 * 1024 * 1024
MAX_ZIP_ENTRIES = 20_000
# The XML parts cost far more than their size once parsed (measured, see
# docs/plans/large-files-REPORT.md section 6): python-docx ~9 MB of RAM
# per MB of XML, openpyxl ~3 MB per MB of shared strings, on a server with
# 512 MB in all. Images and embedded files inside cost only their size.
# A real lease .docx has 1-5 MB of XML; a 5,000-row rent roll .xlsx ~2 MB.
MAX_ZIP_XML_BYTES = {"docx": 10 * 1024 * 1024, "xlsx": 40 * 1024 * 1024, "xlsm": 40 * 1024 * 1024}
# python-docx keeps a node per element (~200 bytes each), so dense XML
# costs more than its size says: 10 MB of empty paragraphs is 1.6 million
# elements and took 348 MB. 500,000 parses in ~100 MB; the blank Word
# template is ~19,000 and a long, heavily formatted lease ~150,000.
# (openpyxl streams sheets and shared strings, so .xlsx needs no count.)
MAX_DOCX_ELEMENTS = 500_000
# Parts starting like this can't be XML, so no parser builds a tree from
# them: images (PNG, JPEG, GIF, BMP, TIFF, WMF), embedded OLE/ZIP/PDF.
# EMF is checked by its signature at byte 40.
_BINARY_PART_MAGIC = (b"\x89PNG", b"\xff\xd8\xff", b"GIF8", b"BM", b"II*\x00", b"MM\x00*", b"\xd7\xcd\xc6\x9a",
                      b"\x01\x00\x09\x00", b"\x02\x00\x09\x00", b"\xd0\xcf\x11\xe0", b"PK\x03\x04", b"%PDF")
# BITMAPINFOHEADER sizes a real .bmp carries at byte 14 -- so a text file
# that merely starts with "BM" isn't mistaken for an image.
_BMP_DIB_HEADER_SIZES = {12, 40, 52, 56, 64, 108, 124}

# What each upload kind accepts, by canonical extension. Lease documents:
# the formats the product supports. Rent rolls additionally keep the
# image formats their importer already accepted (webp, bmp) and have no
# .doc reader (a table needs structure the legacy .doc heuristic can't
# recover).
LEASE_KINDS = {"pdf", "docx", "doc", "xlsx", "xlsm", "xls", "csv", "tsv", "txt", "jpg", "png", "heic", "tiff"}
RENT_ROLL_KINDS = (LEASE_KINDS - {"doc"}) | {"webp", "bmp"}
ACCEPTED_BY_UPLOAD_KIND = {"lease": LEASE_KINDS, "rent_roll": RENT_ROLL_KINDS}

ACCEPTED_LABEL = {
    "lease": "PDF, Word (.docx, .doc), Excel (.xlsx, .xls), CSV, TXT, or an image (JPG, PNG, HEIC, TIFF)",
    "rent_roll": "Excel (.xlsx, .xls), CSV, TXT, PDF, Word (.docx), or an image (JPG, PNG, HEIC, TIFF)",
}

# Every filename extension a user might pick, for the file picker's
# accept="" attribute (aliases included -- .jpeg, .tif, .heif).
PICKER_EXTENSIONS = {
    "lease": [".pdf", ".docx", ".doc", ".xlsx", ".xlsm", ".xls", ".csv", ".tsv", ".txt",
              ".jpg", ".jpeg", ".png", ".heic", ".heif", ".tif", ".tiff"],
    "rent_roll": [".xlsx", ".xlsm", ".xls", ".csv", ".tsv", ".txt", ".pdf", ".docx",
                  ".jpg", ".jpeg", ".png", ".heic", ".heif", ".tif", ".tiff", ".webp", ".bmp"],
}

_EXTENSION_ALIASES = {"jpeg": "jpg", "tif": "tiff", "heif": "heic"}

_LABELS = {
    "pdf": "PDF", "docx": "Word document", "doc": "Word 97-2003 document", "xlsx": "Excel workbook",
    "xlsm": "Excel workbook", "xls": "Excel 97-2003 workbook", "csv": "CSV file", "tsv": "tab-separated file",
    "txt": "text file", "jpg": "JPG image", "png": "PNG image", "heic": "HEIC photo", "tiff": "TIFF image",
    "webp": "WebP image", "bmp": "BMP image",
}

# HEIF brands that mean a still image Pillow can open through pillow-heif.
# "avif" deliberately absent: same container, different codec, no decoder here.
_HEIF_BRANDS = {b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"mif1", b"msf1"}


class UnsupportedFileType(Exception):
    """The file's content isn't a format this upload accepts. str(e) is a friendly, user-facing message."""


class DetectedType:
    def __init__(self, extension: str, original_extension: str):
        self.extension = extension
        self.label = _LABELS.get(extension, extension.upper())
        self.original_extension = original_extension

    @property
    def mismatched_name(self) -> bool:
        """True when the filename's extension disagrees with the content (e.g. a PNG named .pdf)."""
        original = _EXTENSION_ALIASES.get(self.original_extension, self.original_extension)
        if original == self.extension:
            return False
        # Text formats are all "text" by content; the name is what tells
        # them apart, so they never count as a mismatch with each other.
        return not (original in ("csv", "tsv", "txt") and self.extension in ("csv", "tsv", "txt"))

    def canonical_filename(self, filename: str) -> str:
        """`filename` with its extension replaced by the detected one when they disagree -- what the existing extension-dispatching parsers should be handed."""
        if not self.mismatched_name and self.original_extension:
            return filename
        stem = os.path.splitext(os.path.basename(filename or "upload"))[0] or "upload"
        return f"{stem}.{self.extension}"

    def __repr__(self):
        return f"DetectedType({self.extension!r})"


def _extension_of(filename: Optional[str]) -> str:
    name = os.path.basename(filename or "")
    return name.rsplit(".", 1)[1].lower() if "." in name else ""


def _rejection(upload_kind: str, what: str) -> UnsupportedFileType:
    return UnsupportedFileType(
        f"This file looks like {what}, which we can't read. "
        f"Please upload {ACCEPTED_LABEL[upload_kind]}."
    )


def xml_parts(archive: zipfile.ZipFile) -> List[zipfile.ZipInfo]:
    """
    The parts of an Office file a parser may build an XML tree from: every
    file in it except those whose first bytes say image or embedded binary.
    Decided by content, not by name or [Content_Types].xml, because a
    package can point its parser at any part under any name.
    """
    parts = []
    for info in archive.infolist():
        if info.is_dir():
            continue
        with archive.open(info) as part:
            head = part.read(44)
        if not (head.startswith(_BINARY_PART_MAGIC) or (head[:4] == b"\x01\x00\x00\x00" and head[40:44] == b" EMF")):
            parts.append(info)
    return parts


def _detect_zip(path: str, upload_kind: str, original_extension: str) -> str:
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_ZIP_ENTRIES or sum(e.file_size for e in entries) > MAX_ZIP_UNCOMPRESSED_BYTES:
                raise UnsupportedFileType(
                    "This file expands to far more data than a real document or spreadsheet, so it wasn't opened. "
                    "If it's genuine, export it again (or save it as PDF or CSV) and upload that."
                )
            extension = _office_type(entries, upload_kind, original_extension)
            parts = xml_parts(archive)
            xml_bytes = sum(e.file_size for e in parts)
            too_dense = (extension == "docx" and xml_bytes <= MAX_ZIP_XML_BYTES["docx"]
                         and _more_elements_than(archive, parts, MAX_DOCX_ELEMENTS))
    except (zipfile.BadZipFile, zlib.error, EOFError, RuntimeError, OSError):
        # RuntimeError: an encrypted entry; zlib/EOF: a damaged one.
        raise UnsupportedFileType(
            "This file appears to be a damaged Office document or ZIP archive. "
            "Open it, save a fresh copy, and upload that."
        )
    if xml_bytes > MAX_ZIP_XML_BYTES[extension]:
        mb, limit_mb = xml_bytes / (1024 * 1024), MAX_ZIP_XML_BYTES[extension] // (1024 * 1024)
        if extension == "docx":
            raise UnsupportedFileType(
                f"This Word document holds more text and formatting than we can open safely ({mb:.0f} MB of "
                f"document data; the limit is {limit_mb} MB). Save it as a PDF and upload that."
            )
        raise UnsupportedFileType(
            f"This workbook holds more data than we can open safely ({mb:.0f} MB of sheet data; the limit is "
            f"{limit_mb} MB). Split it into smaller workbooks (for example, one per property) and upload each one."
        )
    if too_dense:
        raise UnsupportedFileType(
            "This Word document holds more text and formatting than we can open safely. "
            "Save it as a PDF and upload that."
        )
    return extension


def _more_elements_than(archive: zipfile.ZipFile, parts: List[zipfile.ZipInfo], limit: int) -> bool:
    """Streams the parts' XML (memory stays flat) and stops as soon as `limit` is passed. Unparseable parts are skipped: the parser reports them."""
    count = 0
    for info in parts:
        with archive.open(info) as part:
            try:
                for _, element in etree.iterparse(part, events=("end",), resolve_entities=False, no_network=True,
                                                  load_dtd=False):
                    count += 1
                    if count > limit:
                        return True
                    element.clear()
                    while element.getprevious() is not None:
                        del element.getparent()[0]
            except etree.XMLSyntaxError:
                continue
    return False


def _office_type(entries: List[zipfile.ZipInfo], upload_kind: str, original_extension: str) -> str:
    names = {e.filename for e in entries}
    if "word/document.xml" in names:
        return "docx"
    if "xl/workbook.xml" in names:
        return "xlsm" if (original_extension == "xlsm" or "xl/vbaProject.bin" in names) else "xlsx"
    if any(n.startswith("ppt/") for n in names):
        raise _rejection(upload_kind, "a PowerPoint presentation")
    if "mimetype" in names or "content.xml" in names:
        raise _rejection(upload_kind, "an OpenDocument file (LibreOffice / OpenOffice). Save it as .docx or .xlsx")
    raise _rejection(upload_kind, "a ZIP archive. Unzip it and upload the documents inside one at a time")


def _detect_ole(path: str, upload_kind: str) -> str:
    try:
        with olefile.OleFileIO(path) as ole:
            streams = {"/".join(entry) for entry in ole.listdir()}
    except Exception:
        raise UnsupportedFileType(
            "This looks like an older Office file, but it appears to be damaged. "
            "Open it, save a fresh copy, and upload that."
        )
    if "EncryptedPackage" in streams or "EncryptionInfo" in streams:
        raise UnsupportedFileType(
            "This Office file is password-protected. Remove the password (or save an unprotected copy) "
            "and upload it again."
        )
    if "WordDocument" in streams:
        return "doc"
    if "Workbook" in streams or "Book" in streams:
        return "xls"
    if "PowerPoint Document" in streams:
        raise _rejection(upload_kind, "a PowerPoint presentation")
    raise _rejection(upload_kind, "an older Office file of a type we don't support")


def _looks_like_text(head: bytes) -> bool:
    if not head or b"\x00" in head:
        return False
    try:
        text = head.decode("utf-8")
    except UnicodeDecodeError as e:
        # The 64 KB cut can land mid-character; anything earlier must decode.
        if e.start < len(head) - 4:
            text = head.decode("latin-1")
        else:
            text = head[:e.start].decode("utf-8")
    printable = sum(1 for c in text if c.isprintable() or c in "\r\n\t")
    return printable / max(len(text), 1) >= 0.95


def _detect_text_flavor(head: bytes, original_extension: str) -> str:
    if original_extension in ("csv", "tsv", "txt"):
        return original_extension
    first_lines = head.decode("latin-1").splitlines()[:20]
    if first_lines and sum(1 for line in first_lines if "\t" in line) >= len(first_lines) * 0.8:
        return "tsv"
    if first_lines and sum(1 for line in first_lines if line.count(",") >= 2) >= len(first_lines) * 0.8:
        return "csv"
    return "txt"


def _is_bmp(head: bytes) -> bool:
    return head.startswith(b"BM") and len(head) >= 18 and int.from_bytes(head[14:18], "little") in _BMP_DIB_HEADER_SIZES


def _is_executable(head: bytes) -> bool:
    if head.startswith(b"\x7fELF") or head[:4] in (b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe"):
        return True
    if not head.startswith(b"MZ") or len(head) < 64:
        return False
    # A Windows program: the DOS header's e_lfanew (bytes 60-63) points at
    # "PE\0\0", or it has the classic DOS stub text. A text file that just
    # starts with "MZ" has neither.
    pe_offset = int.from_bytes(head[60:64], "little")
    return head[pe_offset:pe_offset + 4] == b"PE\x00\x00" or b"This program cannot be run" in head[:512]


def _is_pdf(path: str, head: bytes) -> bool:
    """%PDF- at the start, or (readers tolerate leading junk) within the first 1 KB of a file that also ends like a PDF."""
    if head.startswith(b"%PDF-"):
        return True
    if b"%PDF-" not in head[:1024]:
        return False
    with open(path, "rb") as f:
        f.seek(0, os.SEEK_END)
        f.seek(max(0, f.tell() - 2048))
        return b"%%EOF" in f.read()


def detect_file_type(path: str, filename: Optional[str], upload_kind: str = "lease") -> DetectedType:
    """
    Content-based type of the file at `path`. `filename` (the name the
    browser sent) is used only to tell CSV from TSV from TXT and to word
    error messages -- never to decide what parser runs.

    Raises UnsupportedFileType with a friendly message for empty files,
    content this `upload_kind` doesn't accept, and recognizably-wrong
    files (executables, archives, presentations, password-protected
    Office files).
    """
    if upload_kind not in ACCEPTED_BY_UPLOAD_KIND:
        raise ValueError(f"unknown upload kind {upload_kind!r}")
    original_extension = _extension_of(filename)

    with open(path, "rb") as f:
        head = f.read(_HEAD_BYTES)
    if not head:
        raise UnsupportedFileType("This file is empty. Check you picked the right file and upload it again.")

    if _is_pdf(path, head):
        extension = "pdf"
    elif head.startswith(b"PK\x03\x04"):
        extension = _detect_zip(path, upload_kind, original_extension)
    elif head.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        extension = _detect_ole(path, upload_kind)
    elif head.startswith(b"\xff\xd8\xff"):
        extension = "jpg"
    elif head.startswith(b"\x89PNG\r\n\x1a\n"):
        extension = "png"
    elif head[:4] in (b"II*\x00", b"MM\x00*"):
        extension = "tiff"
    elif head[4:8] == b"ftyp" and head[8:12] in _HEIF_BRANDS:
        extension = "heic"
    elif head[4:8] == b"ftyp" and head[8:12] in (b"avif", b"avis"):
        raise _rejection(upload_kind, "an AVIF image. Save it as JPG or PNG")
    elif head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        extension = "webp"
    elif _is_bmp(head):
        extension = "bmp"
    elif head[:6] in (b"GIF87a", b"GIF89a"):
        raise _rejection(upload_kind, "a GIF image. Save it as PNG or JPG")
    elif _is_executable(head):
        raise _rejection(upload_kind, "a program, not a document")
    elif head.startswith(b"{\\rtf"):
        raise _rejection(upload_kind, "a Rich Text (.rtf) document. Save it as .docx or PDF")
    elif head[:5].lower() == b"<?xml" or head.lstrip()[:15].lower().startswith((b"<!doctype html", b"<html")):
        raise _rejection(upload_kind, "a web page or XML file. Save it as PDF")
    elif head.startswith((b"\x1f\x8b", b"7z\xbc\xaf", b"Rar!")):
        raise _rejection(upload_kind, "a compressed archive. Extract it and upload the documents inside")
    elif _looks_like_text(head):
        extension = _detect_text_flavor(head, original_extension)
    else:
        raise UnsupportedFileType(
            "We couldn't recognize this file's format. "
            f"Please upload {ACCEPTED_LABEL[upload_kind]}."
        )

    if extension not in ACCEPTED_BY_UPLOAD_KIND[upload_kind]:
        if upload_kind == "rent_roll" and extension == "doc":
            raise UnsupportedFileType(
                "Rent rolls can't be read from Word 97-2003 (.doc) files. Save it as .docx, or export the "
                "rent roll to Excel or CSV, and upload that."
            )
        raise _rejection(upload_kind, f"a {_LABELS.get(extension, extension.upper())}")
    return DetectedType(extension, original_extension)
