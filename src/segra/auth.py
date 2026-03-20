"""MSAL authentication for Entra ID — token acquisition and caching.

Supports two flows:
  1. Interactive (delegated) — desktop app, user signs in via browser
  2. Client credentials (app-only) — daemon, uses client secret

The interactive flow is recommended for AutoDocumentator because it
produces permission-trimmed results tied to the signed-in user.
"""

import logging
import os
import stat
import sys
import threading
from pathlib import Path

log = logging.getLogger(__name__)

# Scopes
GRAPH_SCOPES = ["https://graph.microsoft.com/Files.Read", "https://graph.microsoft.com/Sites.Read.All"]
AOAI_SCOPE = ["https://cognitiveservices.azure.com/.default"]

# Token cache location — secure per-user directory
_CACHE_DIR = Path(
    os.environ.get("LOCALAPPDATA")
    or Path.home() / "AppData" / "Local"
) / "AutoDocumentator"
_CACHE_FILE = _CACHE_DIR / ".msal_cache.bin"


def _restrict_file_permissions(path: Path):
    """Set file to owner-read/write only. Best-effort on Windows."""
    try:
        if sys.platform == "win32":
            # On Windows, use icacls to restrict to current user only
            import subprocess
            username = os.environ.get("USERNAME", "")
            if username:
                subprocess.run(
                    ["icacls", str(path), "/inheritance:r",
                     "/grant:r", f"{username}:(R,W)"],
                    capture_output=True, timeout=5,
                )
        else:
            path.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0o600
    except Exception as e:
        log.debug("Could not restrict permissions on %s: %s", path, e)


class EntraAuth:
    """Manages Entra ID authentication via MSAL."""

    def __init__(
        self,
        tenant_id: str,
        client_id: str,
        client_secret: str | None = None,
    ):
        import msal

        self._tenant_id = tenant_id
        self._client_id = client_id
        self._client_secret = client_secret
        self._lock = threading.Lock()

        authority = f"https://login.microsoftonline.com/{tenant_id}"

        # Persistent token cache
        self._cache = msal.SerializableTokenCache()
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        if _CACHE_FILE.exists():
            self._cache.deserialize(_CACHE_FILE.read_text(encoding="utf-8"))

        if client_secret:
            self._app = msal.ConfidentialClientApplication(
                client_id,
                authority=authority,
                client_credential=client_secret,
                token_cache=self._cache,
            )
        else:
            self._app = msal.PublicClientApplication(
                client_id,
                authority=authority,
                token_cache=self._cache,
            )

    def get_graph_token(self) -> str:
        """Acquire a token for Microsoft Graph API."""
        return self._acquire(GRAPH_SCOPES)

    def get_aoai_token(self) -> str:
        """Acquire a token for Azure OpenAI (Entra auth)."""
        return self._acquire(AOAI_SCOPE)

    def _acquire(self, scopes: list[str]) -> str:
        """Acquire a token, trying silent first, then interactive/credential."""
        with self._lock:
            accounts = self._app.get_accounts()
            if accounts:
                result = self._app.acquire_token_silent(scopes, account=accounts[0])
                if result and "access_token" in result:
                    self._persist_cache()
                    return result["access_token"]

            if self._client_secret:
                result = self._app.acquire_token_for_client(scopes=scopes)
            else:
                result = self._app.acquire_token_interactive(scopes=scopes)

            if not result:
                raise RuntimeError("MSAL returned no result")
            if "error" in result:
                # Log the full error for diagnostics, show only the code to the user
                error_code = result.get("error", "unknown_error")
                log.warning("MSAL error: %s", error_code)
                raise RuntimeError(
                    f"Authentication failed (error: {error_code}). "
                    "Check tenant/client configuration."
                )

            self._persist_cache()
            return result["access_token"]

    def _persist_cache(self):
        """Write the token cache to disk if it changed, with restricted permissions."""
        if self._cache.has_state_changed:
            try:
                _CACHE_FILE.write_text(
                    self._cache.serialize(), encoding="utf-8"
                )
                _restrict_file_permissions(_CACHE_FILE)
            except OSError as e:
                log.warning("Failed to persist token cache: %s", e)
