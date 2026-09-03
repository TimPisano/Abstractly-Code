# Production image for the Abstractly backend (Flask API).
#
# Docker, not Render's native Python buildpack, specifically because
# this app needs two SYSTEM-LEVEL binaries beyond what pip can install:
#   - tesseract-ocr: OCR fallback for scanned/image leases
#     (app/pdf_extractor.py, via pytesseract)
#   - poppler-utils: rasterizes PDF pages to images for that OCR path
#     (app/pdf_extractor.py, via pdf2image)
# A buildpack has no reliable way to install OS packages; a Dockerfile
# does, via apt-get below, so both actually exist when the container
# runs -- not just the Python wheels that talk to them.

FROM python:3.11-slim

# --no-install-recommends keeps the image smaller; libglib2.0-0 is a
# real runtime dependency of Pillow's image codecs on a slim base,
# not decorative.
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    poppler-utils \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copied and installed before the rest of the source so Docker's layer
# cache only re-runs `pip install` when requirements.txt itself
# changes, not on every code edit -- meaningfully faster rebuilds.
COPY requirements.txt .
# Upgrade pip/setuptools first -- the base image's bundled versions lag
# and have had their own CVEs (setuptools CVE-2024-6345 / CVE-2022-40897).
RUN pip install --no-cache-dir --upgrade pip setuptools \
    && pip install --no-cache-dir -r requirements.txt

COPY . .

# Render sets $PORT itself and expects the app to bind to it; 5000 is
# just the local-dev fallback if this image is ever run somewhere that
# doesn't set it. --workers 2: this app's SQLite access already opens
# a fresh short-lived connection per call (see database.py's
# get_connection), so it tolerates multiple worker processes fine;
# kept modest since Render's cheaper tiers have limited RAM. --timeout
# 120: OCR fallback on a large scanned PDF can genuinely take a while;
# gunicorn's default 30s would kill that request mid-extraction.
CMD gunicorn app.api:app --bind 0.0.0.0:${PORT:-5000} --workers 2 --timeout 120
