# credentials/

Put your Google service account JSON key file here, e.g.:

```
backend/credentials/google-service-account.json
```

Then set `GOOGLE_APPLICATION_CREDENTIALS` in `backend/.env` to that path
(see `backend/.env.example`). Every `*.json` file in this directory is
gitignored — only this README is tracked, so the directory itself
exists in a fresh checkout without ever risking a real key getting
committed.

See `backend/.env.example` for the full setup steps (Google Cloud
project, enabling the Sheets/Drive APIs, creating the service account,
and sharing access).
