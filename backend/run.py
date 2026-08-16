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

import os

from app.api import app

if __name__ == '__main__':
    debug_mode = os.environ.get('FLASK_DEBUG', '').lower() in ('1', 'true', 'yes')
    port = int(os.environ.get('PORT', '5000'))

    print("Starting Lease Extraction API server...")
    print(f"Server running at http://localhost:{port}")
    print(f"Debug mode: {'ON (local dev only!)' if debug_mode else 'off'}")
    print("Press CTRL+C to stop")
    print()
    app.run(debug=debug_mode, host='0.0.0.0', port=port)
