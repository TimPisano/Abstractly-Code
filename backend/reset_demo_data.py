#!/usr/bin/env python3
"""
Wipes the demo deployment's database back to its clean seeded state
(2 sample leases + a matching sample rent roll, demo login intact) --
see app/demo_seed.py for exactly what gets cleared and reseeded.

Refuses to run unless DEMO_MODE=true is set in the environment, so
running this locally with your production .env loaded by mistake
can't wipe real customer data -- this script only ever touches
whatever database DB_PATH (or the default) points at in the current
environment.

Usage (run on the demo deployment, e.g. via Render's shell):
    DEMO_MODE=true venv/bin/python3 reset_demo_data.py

The same reset is also available over HTTP with no shell access
needed -- see DEPLOYMENT.md's "Demo deployment" section for the
curl command against POST /demo/reset.
"""

import os
import sys

if os.environ.get('DEMO_MODE', '').strip().lower() != 'true':
    print(
        "Refusing to run: DEMO_MODE is not set to 'true' in this environment.\n"
        "This script deletes ALL lease/discrepancy/task/etc. data in "
        "whatever database is currently configured -- only ever run it "
        "against the demo deployment, never production."
    )
    sys.exit(1)

from app.demo_seed import reset_demo_data  # noqa: E402 -- import after the guard above, deliberately

if __name__ == '__main__':
    reset_demo_data()
    print("Demo data reset complete: sample leases and rent roll restored, demo login unchanged.")
