"""Local dev API for E2E auth testing. Emails are written to OUTBOX as JSON instead of sent
(unless REAL_EMAIL=1). Optional SMTP_DELAY simulates slow mail. Local testing only; never deployed."""
import json, os, sys, time, itertools
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "backend"))
from app import email_service
from app.api import app
OUT = os.environ["OUTBOX"]
counter = itertools.count(1)
_real_send = email_service._send
if True:
    def _capture(to_email, subject, text_body, html_body, reply_to=None):
        if os.environ.get("REAL_EMAIL") == "1":
            ok = _real_send(to_email, subject, text_body, html_body, reply_to)
            print("REAL SEND", subject, "->", "ok" if ok else "FAILED", flush=True)
        delay = float(os.environ.get("SMTP_DELAY", "0"))
        if delay: time.sleep(delay)
        n = next(counter)
        with open(os.path.join(OUT, f"{int(time.time()*1000)}-{n:03d}.json"), "w") as f:
            json.dump({"to": to_email, "subject": subject, "text": text_body, "html": html_body}, f)
        return True
    email_service._send = _capture
app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5731")), threaded=True)
