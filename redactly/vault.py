"""The session vault — reversible token <-> secret mapping.

The vault is what makes redaction *reversible*: when the engine masks a secret
it mints a stable typed token via :meth:`Vault.token_for`, and when the provider
reply streams back the proxy calls :meth:`Vault.unmask` to swap the token for
the real value locally — so the user sees a complete answer while the real value
never left the machine.

Determinism is load-bearing for *both* correctness and prompt-cache survival:

- The same secret maps to the **same** token for the whole session (so the model
  tracks identity across a conversation, and Anthropic's prompt cache still hits
  because the redacted bytes are stable across turns).
- The per-session ``salt`` is **session-constant** (minted once at vault
  construction, NOT per call). Token shape is ``«PREFIX_<salt>_N»`` where ``N``
  is a per-prefix counter. The salt namespaces tokens to a session so two
  sessions' ``«EMAIL_1»`` never collide in any shared on-disk store, while
  staying constant so determinism and caching hold within the session.

Persistence: the in-memory dict is the default (session-lifetime, never
written). When a vault is backed by a file it is created mode ``0600`` inside a
``0700`` directory — it contains real secrets in cleartext and must never be
group/world readable. The active vault is exposed per session via a ContextVar
(``current_vault`` / ``set_current_vault``) so the streaming un-masker can reach
it without threading it through every call.
"""

from __future__ import annotations

import os
from contextvars import ContextVar
from pathlib import Path

# File/dir permission constants — the vault holds cleartext secrets.
VAULT_FILE_MODE = 0o600
VAULT_DIR_MODE = 0o700

# Token delimiters. Guillemets are rare in real content, so they are reliable
# to locate for un-masking (see docs/REDACTION-POLICY.md "Token format").
TOKEN_OPEN = "«"   # «
TOKEN_CLOSE = "»"  # »


class Vault:
    """A session-scoped, reversible token store.

    A vault maps real secrets to stable typed tokens and back. It is created
    per redaction session (identified by ``session_id``); its in-memory maps
    live for the session's lifetime. When ``path`` is given the maps are
    persisted to a ``0600`` file under a ``0700`` directory.

    Args:
        session_id: Stable identifier for this session (used to namespace the
            on-disk store and to derive a session-constant salt).
        path: Optional on-disk vault path. ``None`` (default) = in-memory only.
    """

    def __init__(self, session_id: str, path: Path | None = None) -> None:
        self.session_id = session_id
        self.path = path
        # Per-secret token map and reverse map. token_for() and unmask()
        # operate over these; populated by the implementation.
        self._secret_to_token: dict[str, str] = {}
        self._token_to_secret: dict[str, str] = {}
        # Per-prefix counter for the trailing _N. Implemented later.
        self._counters: dict[str, int] = {}
        # Session-constant salt, minted ONCE here (not per token_for call) so
        # the same secret yields the same token for the whole session.
        self._salt: str = ""  # TODO(scaffold): derive a stable per-session salt
        # TODO(scaffold): load existing maps from `path` if it exists.

    def token_for(self, secret: str, prefix: str) -> str:
        """Return the stable token for ``secret`` under token family ``prefix``.

        Mints ``«PREFIX_<salt>_N»`` on first sight of ``secret`` (incrementing
        the per-prefix counter ``N``), stores both directions of the mapping,
        and returns the *same* token on every subsequent call with the same
        ``secret`` this session (deterministic / content-stable). Persists to
        disk when the vault is file-backed.

        TODO(scaffold): implement minting, dedup, counter, and persistence.
        """
        raise NotImplementedError("Vault.token_for is not yet implemented")

    def unmask(self, text: str) -> str:
        """Replace every known token in ``text`` with its real secret.

        Used on the locally-received provider reply (after the streaming
        adapter has reassembled any token that split across SSE deltas). Only
        tokens minted by this vault are substituted; unknown ``«…»`` runs are
        left untouched. The reverse of :meth:`token_for`.

        TODO(scaffold): implement token scan + reverse substitution.
        """
        raise NotImplementedError("Vault.unmask is not yet implemented")

    def _persist(self) -> None:
        """Write the vault maps to ``self.path`` (0600 file / 0700 dir).

        No-op when the vault is in-memory (``self.path is None``). The directory
        is created mode ``0700`` and the file mode ``0600`` — these contain real
        secrets in cleartext and must never be group/world readable.

        TODO(scaffold): implement atomic write + chmod enforcement.
        """
        raise NotImplementedError("Vault._persist is not yet implemented")


# ---------------------------------------------------------------------------
# Per-session active-vault ContextVar.
#
# Adapted from Headroom's ContextVar-per-session store pattern: the streaming
# un-masker reaches the active vault via this ContextVar rather than receiving
# it as an argument through every SSE callback.
# ---------------------------------------------------------------------------
_current_vault: ContextVar[Vault | None] = ContextVar("redactly_current_vault", default=None)


def current_vault() -> Vault | None:
    """Return the vault bound to the current execution context, if any."""
    return _current_vault.get()


def set_current_vault(vault: Vault | None) -> object:
    """Bind ``vault`` as the current-context vault; return the reset token.

    Pass the returned token to ``_current_vault.reset(token)`` to restore the
    previous binding when the request/session scope ends.
    """
    return _current_vault.set(vault)
