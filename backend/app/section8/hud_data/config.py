"""
Feature flag and storage location for the HUD reference-data store.

Both are read from the environment on every call (not cached at import)
so tests and the refresh CLI can flip them without reloading modules.
"""
import os

FLAG_ENV = "SECTION8_HUD_DATA_ENABLED"
DB_PATH_ENV = "HUD_DATA_DB_PATH"

_TRUTHY = {"1", "true", "yes", "on"}

_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


class HudDataDisabled(RuntimeError):
    """Raised by every public entry point while the feature flag is off."""


def is_enabled() -> bool:
    return os.environ.get(FLAG_ENV, "").strip().lower() in _TRUTHY


def require_enabled() -> None:
    if not is_enabled():
        raise HudDataDisabled(
            f"HUD data is disabled. Set {FLAG_ENV}=1 to enable it."
        )


def db_path() -> str:
    """
    Where the HUD store lives. Its own SQLite file, never the app's
    portfolio database:
      1. HUD_DATA_DB_PATH, if set;
      2. hud_data.db next to DB_PATH, so it rides the same persistent
         disk as the app database on deployments that have one;
      3. backend/hud_data.db for local dev (gitignored by *.db).
    """
    explicit = os.environ.get(DB_PATH_ENV, "").strip()
    if explicit:
        return explicit
    app_db = os.environ.get("DB_PATH", "").strip()
    if app_db:
        return os.path.join(os.path.dirname(os.path.abspath(app_db)), "hud_data.db")
    return os.path.join(_BACKEND_DIR, "hud_data.db")
