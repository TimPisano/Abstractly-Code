"""
The password rules for any password a person chooses on a public page
(self-serve signup, forgot-password reset). The server is the authority;
frontend/app/auth-common.js shows the same rules live as you type, and
its COMMON_PASSWORDS list is kept identical to the one below by
tests/test_auth_flow.py, so the checklist never promises something the
server then rejects.

Modern guidance (NIST SP 800-63B), not composition rules: length matters,
"must contain a symbol" doesn't -- it just produces "Password1!". So:
  - at least MIN_LENGTH characters
  - at most MAX_BYTES bytes of UTF-8. bcrypt only reads the first 72
    bytes, and the bcrypt library this app uses raises (a 500) on
    anything longer rather than truncating silently.
  - not a well-known common password
  - not your own email address or name
"""

MIN_LENGTH = 10
MAX_BYTES = 72

# Lower-cased. Only passwords at least MIN_LENGTH long matter here --
# anything shorter already fails the length rule.
COMMON_PASSWORDS = frozenset("""
1234567890 12345678910 123456789a 1234567890a 0123456789 0987654321
1q2w3e4r5t 1qaz2wsx3edc qwertyuiop qwerty1234 qwerty12345 asdfghjkl1
asdfghjkl; zxcvbnm123 1q2w3e4r5t6y qazwsxedc123 password12 password123
password1234 password01 password1! password!1 passw0rd12 p@ssword12
p@ssw0rd12 p@ssw0rd123 iloveyou12 iloveyou123 sunshine12 princess12
football12 baseball12 welcome123 welcome1234 letmein123 abc1234567
abcdefghij aaaaaaaaaa 1111111111 0000000000 1212121212 1234554321
abstractly abstractly1 abstractly123 changeme123 trustno1234 superman12
dragon1234 monkey1234 michael123 jennifer12 starwars12 whatever12
computer12 internet12 administrator admin12345 admin123456 rootroot12
realestate realestate1 multifamily apartments rentroll123 qwerty123456
""".split())


def problems(password: str, email: str = "", name: str = "") -> list:
    """
    Every rule this password breaks, as short machine codes:
    'too_short', 'too_long', 'common', 'personal'. Empty list = OK.
    """
    password = password or ""
    found = []
    if len(password) < MIN_LENGTH:
        found.append("too_short")
    if len(password.encode("utf-8")) > MAX_BYTES:
        found.append("too_long")

    lowered = password.strip().lower()
    if lowered in COMMON_PASSWORDS or (lowered and len(set(lowered)) == 1):
        found.append("common")

    personal = set()
    email = (email or "").strip().lower()
    if email:
        personal.add(email)
        local = email.split("@")[0]
        if len(local) >= 4:
            personal.add(local)
    for part in (name or "").lower().split():
        if len(part) >= 4:
            personal.add(part)
    full_name = "".join((name or "").lower().split())
    if len(full_name) >= 4:
        personal.add(full_name)
    # "Contains" for the whole email; "is basically just" for name parts
    # -- "Jordan2026Spring!" is fine, "jordan12345" is not.
    compact = "".join(lowered.split())
    if email and email in lowered:
        found.append("personal")
    elif any(compact.rstrip("0123456789!@#$%^&*.") == p for p in personal):
        found.append("personal")
    return found


_MESSAGES = {
    "too_short": f"Use at least {MIN_LENGTH} characters.",
    "too_long": "That password is too long. Use 72 characters or fewer.",
    "common": "That password is too common. Try something less guessable.",
    "personal": "Don't use your email address or name as your password.",
}


def first_problem_message(password: str, email: str = "", name: str = ""):
    """A single human-readable error for the first broken rule, or None if the password is acceptable."""
    found = problems(password, email, name)
    return _MESSAGES[found[0]] if found else None


def too_long_for_bcrypt(password: str) -> bool:
    """For the older routes that keep their own 8-character minimum (change-password, team-setup, admin-created members): just the crash guard."""
    return len((password or "").encode("utf-8")) > MAX_BYTES
