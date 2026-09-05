"""
Email account linking (send-as) via OAuth2 authorization-code flow,
for Google (Gmail API) and Microsoft (Graph API).

We never see or store a user's real email password -- only short-lived
OAuth access tokens and a refresh token, both encrypted at rest via
token_encryption.py. This module owns three things: building the
provider authorize URL, exchanging an authorization code for tokens on
callback, and using a (possibly refreshed) access token to send mail
as that user. Every HTTP call to a provider takes an injectable `http`
(default: the real `requests` module) so tests can substitute a fake
without a live Google/Microsoft app registration.

Route-level ownership checks (a user can only see/disconnect/send-as
their own linked accounts) live in api.py, mirroring how thread
isolation is enforced in messaging.py -- this module has no concept of
"the current user," only account ids and user ids passed in explicitly.
"""
import base64
import os
import secrets
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from typing import Any, Dict
from urllib.parse import urlencode

import requests

from . import database
from .token_encryption import encrypt_token, decrypt_token

VALID_PROVIDERS = {"google", "microsoft"}

PROVIDER_CONFIG = {
    "google": {
        "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "userinfo_url": "https://www.googleapis.com/oauth2/v2/userinfo",
        "revoke_url": "https://oauth2.googleapis.com/revoke",
        "send_url": "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
        "scopes": ["https://www.googleapis.com/auth/gmail.send", "https://www.googleapis.com/auth/userinfo.email", "openid"],
        "client_id_env": "GOOGLE_OAUTH_CLIENT_ID",
        "client_secret_env": "GOOGLE_OAUTH_CLIENT_SECRET",
        "redirect_uri_env": "GOOGLE_OAUTH_REDIRECT_URI",
    },
    "microsoft": {
        "authorize_url": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        "token_url": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        "userinfo_url": "https://graph.microsoft.com/v1.0/me",
        "revoke_url": None,  # no single-call revoke on the v2 multi-tenant endpoint; disconnect just drops our copy of the token
        "send_url": "https://graph.microsoft.com/v1.0/me/sendMail",
        "scopes": ["Mail.Send", "offline_access", "User.Read"],
        "client_id_env": "MICROSOFT_OAUTH_CLIENT_ID",
        "client_secret_env": "MICROSOFT_OAUTH_CLIENT_SECRET",
        "redirect_uri_env": "MICROSOFT_OAUTH_REDIRECT_URI",
    },
}


class EmailAccountError(Exception):
    """Any OAuth/provider-API failure -- routes catch this and turn it into a clean 4xx/502, never a raw traceback."""


class ProviderNotConfigured(EmailAccountError):
    """The admin hasn't set this provider's client id/secret/redirect env vars yet."""


def _provider_credentials(provider: str) -> Dict[str, str]:
    cfg = PROVIDER_CONFIG[provider]
    client_id = os.environ.get(cfg["client_id_env"])
    client_secret = os.environ.get(cfg["client_secret_env"])
    redirect_uri = os.environ.get(cfg["redirect_uri_env"])
    if not client_id or not client_secret or not redirect_uri:
        raise ProviderNotConfigured(
            f"{provider} email linking is not configured yet. An admin needs to set "
            f"{cfg['client_id_env']}, {cfg['client_secret_env']}, and {cfg['redirect_uri_env']} "
            "in the environment (see the OAuth app registration walkthrough in PROGRESS.md)."
        )
    return {"client_id": client_id, "client_secret": client_secret, "redirect_uri": redirect_uri}


def build_authorize_url(provider: str, user_id: int) -> str:
    if provider not in VALID_PROVIDERS:
        raise EmailAccountError(f"Unknown provider: {provider}")
    creds = _provider_credentials(provider)
    cfg = PROVIDER_CONFIG[provider]
    state = secrets.token_urlsafe(32)
    database.create_oauth_state(state, user_id, provider)

    params = {
        "client_id": creds["client_id"],
        "redirect_uri": creds["redirect_uri"],
        "response_type": "code",
        "scope": " ".join(cfg["scopes"]),
        "state": state,
    }
    if provider == "google":
        # Without both of these Google only issues a refresh_token on the
        # very first consent ever granted -- prompt=consent forces one on
        # every link (including a reconnect after disconnecting).
        params["access_type"] = "offline"
        params["prompt"] = "consent"
    else:
        params["response_mode"] = "query"

    return f"{cfg['authorize_url']}?{urlencode(params)}"


def handle_oauth_callback(provider: str, code: str, state: str, http=requests) -> Dict[str, Any]:
    """Validates state, exchanges the code for tokens, fetches the linked account's email address, and stores it (encrypted) as a linked_email_accounts row. Raises EmailAccountError on any failure along the way -- invalid/expired state, provider rejection, missing refresh token, missing email."""
    if provider not in VALID_PROVIDERS:
        raise EmailAccountError(f"Unknown provider: {provider}")

    state_row = database.consume_oauth_state(state)
    if state_row is None or state_row["provider"] != provider:
        raise EmailAccountError("Invalid or expired sign-in attempt -- please try connecting again.")
    user_id = state_row["user_id"]

    creds = _provider_credentials(provider)
    cfg = PROVIDER_CONFIG[provider]

    token_resp = http.post(
        cfg["token_url"],
        data={
            "client_id": creds["client_id"],
            "client_secret": creds["client_secret"],
            "redirect_uri": creds["redirect_uri"],
            "grant_type": "authorization_code",
            "code": code,
        },
        timeout=15,
    )
    if token_resp.status_code != 200:
        raise EmailAccountError(f"{provider} rejected the authorization code: {token_resp.text[:300]}")
    tokens = token_resp.json()
    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token")
    expires_in = tokens.get("expires_in", 3600)
    if not access_token:
        raise EmailAccountError(f"{provider} did not return an access token.")
    if not refresh_token:
        raise EmailAccountError(
            f"{provider} did not return a refresh token. This usually means this account was linked "
            f"before without being disconnected first -- remove Abstractly's access in your {provider} "
            "account's security settings, then try linking again."
        )

    userinfo_resp = http.get(cfg["userinfo_url"], headers={"Authorization": f"Bearer {access_token}"}, timeout=15)
    if userinfo_resp.status_code != 200:
        raise EmailAccountError(f"Could not fetch the account's email address from {provider}: {userinfo_resp.text[:300]}")
    info = userinfo_resp.json()
    provider_email = info.get("email") or info.get("mail") or info.get("userPrincipalName")
    if not provider_email:
        raise EmailAccountError(f"{provider} did not return an email address for this account.")

    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat()
    account_id = database.upsert_linked_email_account(
        user_id=user_id,
        provider=provider,
        provider_email=provider_email,
        access_token_encrypted=encrypt_token(access_token),
        refresh_token_encrypted=encrypt_token(refresh_token),
        token_expires_at=expires_at,
        scopes=" ".join(cfg["scopes"]),
    )
    return account_detail(database.get_linked_email_account(account_id))


def _refresh_access_token(account: Dict[str, Any], http=requests) -> str:
    """Returns a valid access token, refreshing first if the stored one is expired or within 60s of expiring. Updates the DB row in place on a successful refresh."""
    expires_at = datetime.fromisoformat(account["token_expires_at"])
    now = datetime.now(timezone.utc)
    access_token = decrypt_token(account["access_token_encrypted"])
    if access_token is not None and expires_at - now > timedelta(seconds=60):
        return access_token

    refresh_token = decrypt_token(account["refresh_token_encrypted"])
    if refresh_token is None:
        raise EmailAccountError("This account's stored credentials could not be read -- it needs to be reconnected.")

    provider = account["provider"]
    creds = _provider_credentials(provider)
    cfg = PROVIDER_CONFIG[provider]
    resp = http.post(
        cfg["token_url"],
        data={
            "client_id": creds["client_id"],
            "client_secret": creds["client_secret"],
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
        timeout=15,
    )
    if resp.status_code != 200:
        raise EmailAccountError(f"Failed to refresh the {provider} access token -- the account may need to be reconnected. ({resp.text[:300]})")
    tokens = resp.json()
    new_access_token = tokens.get("access_token")
    if not new_access_token:
        raise EmailAccountError(f"{provider} did not return a new access token on refresh.")
    new_expires_in = tokens.get("expires_in", 3600)
    new_expires_at = (now + timedelta(seconds=new_expires_in)).isoformat()
    new_refresh_token = tokens.get("refresh_token")  # only present if the provider rotated it

    database.update_linked_email_account_tokens(
        account["id"],
        access_token_encrypted=encrypt_token(new_access_token),
        token_expires_at=new_expires_at,
        refresh_token_encrypted=encrypt_token(new_refresh_token) if new_refresh_token else None,
    )
    return new_access_token


def send_email_as(account_id: int, to: str, subject: str, body: str, http=requests) -> None:
    account = database.get_linked_email_account(account_id)
    if account is None:
        raise EmailAccountError("Linked email account not found.")
    access_token = _refresh_access_token(account, http=http)
    provider = account["provider"]
    if provider == "google":
        _send_via_gmail(access_token, account["provider_email"], to, subject, body, http=http)
    elif provider == "microsoft":
        _send_via_graph(access_token, to, subject, body, http=http)
    else:
        raise EmailAccountError(f"Unknown provider: {provider}")


def _send_via_gmail(access_token: str, from_email: str, to: str, subject: str, body: str, http=requests) -> None:
    msg = MIMEText(body)
    msg["to"] = to
    msg["from"] = from_email
    msg["subject"] = subject
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    resp = http.post(
        PROVIDER_CONFIG["google"]["send_url"],
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        json={"raw": raw},
        timeout=15,
    )
    if resp.status_code not in (200, 202):
        raise EmailAccountError(f"Gmail send failed: {resp.text[:300]}")


def _send_via_graph(access_token: str, to: str, subject: str, body: str, http=requests) -> None:
    resp = http.post(
        PROVIDER_CONFIG["microsoft"]["send_url"],
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        json={
            "message": {
                "subject": subject,
                "body": {"contentType": "Text", "content": body},
                "toRecipients": [{"emailAddress": {"address": to}}],
            },
            "saveToSentItems": "true",
        },
        timeout=15,
    )
    if resp.status_code not in (200, 202):
        raise EmailAccountError(f"Outlook send failed: {resp.text[:300]}")


def disconnect_account(account: Dict[str, Any], http=requests) -> None:
    """Best-effort revoke with the provider, then always deletes the local row regardless of whether the revoke call succeeded -- what actually matters for 'can this app still send as me' is our copy being gone, not whether the provider's revoke endpoint was reachable."""
    cfg = PROVIDER_CONFIG.get(account["provider"], {})
    revoke_url = cfg.get("revoke_url")
    if revoke_url:
        access_token = decrypt_token(account["access_token_encrypted"])
        if access_token:
            try:
                http.post(revoke_url, params={"token": access_token}, timeout=10)
            except Exception:
                pass
    database.delete_linked_email_account(account["id"])


def account_detail(account: Dict[str, Any]) -> Dict[str, Any]:
    """Never includes the encrypted tokens themselves -- no caller needs them, only the send_email_as/refresh internals do."""
    return {
        "id": account["id"],
        "provider": account["provider"],
        "provider_email": account["provider_email"],
        "scopes": account["scopes"],
        "created_at": account["created_at"],
        "updated_at": account["updated_at"],
        "token_expires_at": account["token_expires_at"],
    }
