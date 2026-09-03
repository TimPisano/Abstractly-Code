#!/usr/bin/env python3
"""
Simple run script for the Flask API server.

Usage:
    python run.py                  # debug mode off (default, safe)
    FLASK_DEBUG=1 python run.py    # debug mode on (local dev only —
                                    # enables Werkzeug's interactive
                                    # debugger; never do this anywhere
                                    # reachable by anyone else, since it
                                    # shows full tracebacks/source/file
                                    # paths for unhandled exceptions)
    PORT=8080 python run.py        # listen on a different port (many
                                    # hosting platforms assign one via
                                    # this exact env var and expect the
                                    # app to read it, rather than being
                                    # hardcoded)
"""

import logging
import os

# Importing app.api configures logging for the whole process
# (app/logging_config.py).
from app.api import app

logger = logging.getLogger("app.run")

if __name__ == '__main__':
    debug_mode = os.environ.get('FLASK_DEBUG', '').lower() in ('1', 'true', 'yes')
    port = int(os.environ.get('PORT', '5000'))

    logger.info("Starting Abstractly API on http://localhost:%s (debug=%s)", port, "ON — local dev only" if debug_mode else "off")
    app.run(debug=debug_mode, host='0.0.0.0', port=port)
