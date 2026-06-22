"""Runtime configuration for the Redactly proxy.

This module is the single source of truth for *where* the proxy listens, *where*
it forwards, *which* rules and allowlist apply, and *where/how* the vault is
persisted. It is intentionally concrete (downstream modules import this shape);
only the loading helpers are stubbed.

Environment variables (all optional; sane local-first defaults):

- ``REDACT_UPSTREAM``   — upstream base URL to forward redacted requests to.
                          Default ``https://api.anthropic.com``. Tests point this
                          at a mock server.
- ``REDACT_HOST``       — bind host for the local proxy. Default ``127.0.0.1``
                          (NEVER bind to 0.0.0.0 by default — this is a *local*
                          proxy that handles real secrets in cleartext).
- ``REDACT_PORT``       — bind port for the local proxy. Default ``8788``.
- ``REDACT_RULES``      — path to the user rules + allowlist JSON. Default
                          ``config/rules.json`` (already gitignored — it may
                          name real secret-bearing terms).
- ``REDACT_VAULT``      — path to the on-disk session vault. Default is
                          *in-memory only* (None) — the vault lives for the
                          session and is never written unless this is set. When
                          set, the file is created 0600 inside a 0700 dir.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# --- Defaults -------------------------------------------------------------

DEFAULT_UPSTREAM = "https://api.anthropic.com"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8788
DEFAULT_RULES_PATH = "config/rules.json"

ENV_UPSTREAM = "REDACT_UPSTREAM"
ENV_HOST = "REDACT_HOST"
ENV_PORT = "REDACT_PORT"
ENV_RULES = "REDACT_RULES"
ENV_VAULT = "REDACT_VAULT"


@dataclass(frozen=True)
class UserRule:
    """A user-declared redaction rule.

    User rules are *precise by construction*: the user declares exactly what is
    sensitive (a name, an internal hostname, a company identifier), so the
    engine does not over-mask. A rule mints tokens under ``token_prefix`` just
    like a built-in detector.

    Attributes:
        name: Human-readable rule name (also the ``Span.name``).
        pattern: A regex (as a string) matched against request text.
        token_prefix: Token family for minted tokens, e.g. ``"PERSON"`` →
            ``«PERSON_<salt>_1»``.
    """

    name: str
    pattern: str
    token_prefix: str


@dataclass(frozen=True)
class Allowlist:
    """Known-safe values that match a detector pattern but are NOT secrets.

    Allowlisted spans are dropped *before* tokens are minted (e.g. ``localhost``,
    ``example.com``, common ports). Allowlisting un-redacts; it never adds
    redaction. ``literals`` are exact-match strings; ``patterns`` are regexes.
    """

    literals: frozenset[str] = field(default_factory=frozenset)
    patterns: tuple[str, ...] = ()


@dataclass(frozen=True)
class Config:
    """Resolved Redactly runtime configuration.

    Construct via :func:`load` (env + rules file) rather than by hand in
    production code, so env precedence and rule loading stay in one place.

    Attributes:
        upstream: Upstream base URL redacted requests are forwarded to.
        host: Local bind host (default loopback only).
        port: Local bind port.
        rules_path: Path to the user rules/allowlist JSON (gitignored).
        vault_path: Optional on-disk vault path; ``None`` = in-memory only.
        user_rules: Loaded user rules (precise, opt-in).
        allowlist: Loaded allowlist (un-redacts known-safe matches).
    """

    upstream: str = DEFAULT_UPSTREAM
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    rules_path: Path = field(default_factory=lambda: Path(DEFAULT_RULES_PATH))
    vault_path: Path | None = None
    user_rules: tuple[UserRule, ...] = ()
    allowlist: Allowlist = field(default_factory=Allowlist)


def load(*, rules_path: str | os.PathLike[str] | None = None) -> Config:
    """Resolve a :class:`Config` from environment + the rules file.

    Precedence: explicit argument (``rules_path``) > environment variable >
    built-in default. Reads ``REDACT_UPSTREAM`` / ``REDACT_HOST`` /
    ``REDACT_PORT`` / ``REDACT_RULES`` / ``REDACT_VAULT`` and parses the rules
    file via :func:`load_rules`.

    TODO(scaffold): implement env resolution + rules-file parsing.
    """
    raise NotImplementedError("config.load is not yet implemented")


def load_rules(path: str | os.PathLike[str]) -> tuple[tuple[UserRule, ...], Allowlist]:
    """Parse user rules and allowlist from a JSON file.

    Returns ``(user_rules, allowlist)``. A missing file yields empty rules and
    an empty allowlist (no rules is a valid state). A *present but unparseable*
    file MUST raise — a broken rules file is a fail-closed condition, not a
    silent "redact nothing".

    TODO(scaffold): implement JSON parsing into UserRule/Allowlist.
    """
    raise NotImplementedError("config.load_rules is not yet implemented")
