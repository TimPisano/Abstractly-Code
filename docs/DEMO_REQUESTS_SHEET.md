# Demo requests → Google Sheet

Every Book a Demo submission is saved in the app's database. You can see
all of them in the **owner console → Demo Requests** tab, which also
has an Export CSV button. This page covers the optional extra: having
each **new** submission appended to a Google Sheet as it arrives.

How it works: the backend POSTs each new request to a small Google Apps
Script attached to your sheet. The script checks a shared secret, then
adds a row. The send happens in the background and is best-effort, so
if Google is down the form still works. The request is still in the
owner console; it just won't be in the sheet. Only requests that arrive
*after* you set this up are forwarded. Use Export CSV to backfill older
ones.

## 1. Make a secret

In a terminal:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Copy the output. You'll paste it in two places: the script (step 2) and
Render (step 4).

## 2. Add the script to your sheet

1. Open (or create) the Google Sheet you want the requests in. Keep it
   private: it will hold prospects' names and emails.
2. Click **Extensions → Apps Script**. A code editor opens in a new tab.
3. Delete everything in `Code.gs` and paste this:

```javascript
// Abstractly: append each Book a Demo request to this spreadsheet.
// Setup guide: docs/DEMO_REQUESTS_SHEET.md in the Abstractly repo.

const SECRET = 'CHANGE-ME';           // same value as DEMO_REQUEST_SHEET_SECRET on Render
const SHEET_NAME = 'Demo Requests';   // tab to write to; created if missing
const HEADERS = ['Received (UTC)', 'Name', 'Email', 'Company', 'Units', 'Message', 'Request ID'];

function doPost(e) {
  let data;
  try {
    data = JSON.parse(e.postData.contents);
  } catch (err) {
    return reply_({ ok: false, error: 'bad request' });
  }
  if (!SECRET || SECRET === 'CHANGE-ME' || data.secret !== SECRET) {
    return reply_({ ok: false, error: 'unauthorized' });
  }

  const lock = LockService.getScriptLock();   // two requests at once must not collide
  lock.waitLock(10000);
  try {
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const sheet = ss.getSheetByName(SHEET_NAME) || ss.insertSheet(SHEET_NAME);
    if (sheet.getLastRow() === 0) {
      sheet.appendRow(HEADERS);
      sheet.setFrozenRows(1);
    }
    sheet.appendRow([
      data.created_at, data.name, data.work_email, data.company,
      data.units, data.message, data.id,
    ].map(plainText_));
  } finally {
    lock.releaseLock();
  }
  return reply_({ ok: true });
}

// These values come from a public web form. A value starting with = + - @
// would otherwise be run by Sheets as a formula; a leading ' keeps it text.
function plainText_(value) {
  if (value === null || value === undefined) return '';
  if (typeof value === 'string' && /^[=+\-@\t\r]/.test(value)) return "'" + value;
  return value;
}

function reply_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
```

4. Replace `CHANGE-ME` with the secret from step 1. Keep the quotes.
5. Click the **Save** icon (or ⌘S). Name the project anything, e.g.
   "Abstractly demo requests".

## 3. Deploy it as a web app

1. Click **Deploy → New deployment** (top right).
2. Click the gear icon next to "Select type" and choose **Web app**.
3. Fill in:
   - **Description:** `Abstractly demo requests`
   - **Execute as:** **Me** (your account, which owns the sheet)
   - **Who has access:** **Anyone**. This is required: the backend
     calls it without a Google login. The secret is what stops anyone
     else from writing to the sheet.
4. Click **Deploy**.
5. Google asks you to **Authorize access**. Pick your account. If you
   see "Google hasn't verified this app", click **Advanced → Go to
   (project name) (unsafe)**. It's your own script asking for access
   to your own sheet. Then click **Allow**.
6. Copy the **Web app URL**. It looks like
   `https://script.google.com/macros/s/AKfy…/exec`. It must end in
   `/exec`; the backend refuses anything else.

## 4. Turn it on in Render

1. Open the Render dashboard → **abstractly-api** (production, the
   service the marketing site's form posts to) → **Environment**.
2. Add two variables:
   - `DEMO_REQUEST_SHEET_WEBHOOK_URL` = the `/exec` URL from step 3
   - `DEMO_REQUEST_SHEET_SECRET` = the secret from step 1
3. **Save Changes**. Render redeploys the service, which takes a few
   minutes.

For local dev, put the same two lines in `backend/.env` instead.

## 5. Test it

Submit the Book a Demo form on the live site with your own details.
Within a few seconds a **Demo Requests** tab should appear in the sheet
with a header row and your request.

You can also test the script directly, without the site:

```bash
curl -L -X POST 'PASTE-THE-EXEC-URL' \
  -H 'Content-Type: application/json' \
  -d '{"secret":"PASTE-THE-SECRET","name":"Test","work_email":"test@test.com","company":"Test Co","units":1,"message":"curl test","created_at":"2026-01-01T00:00:00Z","id":0}'
```

It should print `{"ok":true}` and add a row. `{"ok":false,"error":"unauthorized"}`
means the secret in the script doesn't match the one you sent.

**If rows don't appear:** Apps Script can't return an error status, so
from the backend's side a wrong secret still looks delivered. Check
these, in order:

1. The secret matches exactly in Render and in the script.
2. You redeployed after editing the script (next section).
3. The script editor's **Executions** page (left sidebar), which lists
   every call and any error.

## Changing the script later

Edits don't go live until you redeploy. Click **Deploy → Manage
deployments**, then the pencil icon, set **Version** to **New
version**, and click **Deploy**. The URL stays the same, so Render
needs no change. Choosing **New deployment** instead would create a
different URL.

## Turning it off

Delete `DEMO_REQUEST_SHEET_WEBHOOK_URL` in Render. To shut it off from
the Google side too, use **Deploy → Manage deployments → Archive**.
