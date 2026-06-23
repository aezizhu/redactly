"""The session vault — reversible token <-> secret mapping.

The vault makes redaction *reversible*: the engine mints a stable typed token via
:meth:`Vault.token_for`, and the proxy calls :meth:`Vault.unmask` on the streamed
reply to swap the token back for the real value locally — so the user sees a
complete answer while the secret never left the machine.

Determinism is load-bearing for correctness AND prompt-cache survival: the same
secret maps to the **same** token for the whole session (so redacted bytes are
stable across turns). The per-session ``salt`` is minted once at construction;
token shape is ``«PREFIX_<salt>_N»`` with a per-prefix counter ``N``.

Persistence: in-memory by default (session-lifetime, never written). When backed
by a file it is created ``0600`` inside a ``0700`` directory — it holds real
secrets in cleartext and must never be group/world readable.

Opt-in **encrypt mode** (``encrypt=True``) removes cleartext-at-rest entirely:
the token IS an AES-SIV ciphertext (``«PREFIX~<hex>»``), the key lives only in
memory, and nothing is written to disk. AES-SIV is deterministic, so the same
secret still yields the same token (dedup + prompt-cache stability hold), and
``unmask`` decrypts the self-contained token rather than consulting a stored map.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import tempfile
from contextvars import ContextVar
from pathlib import Path

VAULT_FILE_MODE = 0o600
VAULT_DIR_MODE = 0o700

# Guillemets are rare in real content, so tokens are reliable to locate.
TOKEN_OPEN = "«"
TOKEN_CLOSE = "»"

# Token grammar for scanning a reply: «UPPER_PREFIX_<6 hex>_<digits>». Matches
# are only substituted when present in this vault's reverse map, so an imperfect
# match never causes a false substitution.
_TOKEN_SCAN = re.compile(r"«[A-Z0-9_]+_[0-9a-f]{6}_\d+»")

# Encrypt-mode token grammar: «PREFIX~<hex ciphertext>». The uppercase prefix
# and lowercase-hex body are split by ``~`` (which appears in neither), so the
# token is self-contained — ``unmask`` decrypts it; no stored map is needed.
_ENCRYPT_SCAN = re.compile(r"«([A-Z0-9_]+)~([0-9a-f]+)»")


def _make_siv():
    """Build an in-memory AES-SIV cipher (deterministic AEAD; key never persists).

    Imported lazily so the ``cryptography`` dependency is only required when the
    opt-in encrypt vault is actually used.
    """
    from cryptography.hazmat.primitives.ciphers.aead import AESSIV

    return AESSIV(secrets.token_bytes(64))  # AES-256-SIV, random per-session key

# A token prefix must live in this alphabet or the minted «PREFIX_salt_N» token
# falls outside _TOKEN_SCAN and unmask can never restore it (silent leak of the
# reverse-mapping, i.e. the secret stays masked forever in the reply).
_PREFIX_OK = re.compile(r"[A-Z0-9_]+")


def normalize_token_prefix(prefix: str) -> str:
    """Coerce a token prefix into the reversible ``[A-Z0-9_]+`` alphabet.

    Upper-cases and maps ``-`` → ``_`` (common in user-chosen names like
    ``my-key``); raises ``ValueError`` on anything that still falls outside the
    alphabet (spaces, punctuation, empty), because such a prefix would mint a
    token ``unmask`` can never match. Idempotent, so it is safe to apply both at
    config load and at mint time.
    """
    candidate = prefix.upper().replace("-", "_")
    if not _PREFIX_OK.fullmatch(candidate):
        raise ValueError(
            f"token_prefix {prefix!r} is invalid: after upper-casing and "
            "'-'→'_' it must match [A-Z0-9_]+ so the «PREFIX_salt_N» token "
            "stays reversible"
        )
    return candidate


class Vault:
    """A session-scoped, reversible token store."""

    def __init__(self, session_id: str, path: Path | None = None, encrypt: bool = False) -> None:
        self.session_id = session_id
        self.path = Path(path) if path is not None else None
        self.encrypt = encrypt
        self._secret_to_token: dict[str, str] = {}
        self._token_to_secret: dict[str, str] = {}
        self._counters: dict[str, int] = {}
        # Session-constant salt (minted once) → same secret yields same token.
        self._salt: str = secrets.token_hex(3)  # 6 hex chars
        # Opt-in encrypt mode: the token IS the AES-SIV ciphertext, the key is
        # in-memory only, and NOTHING is written to disk (no cleartext-at-rest).
        self._siv = _make_siv() if encrypt else None
        if not encrypt and self.path is not None and self.path.exists():
            self._load()

    def token_for(self, secret: str, prefix: str) -> str:
        """Return the stable token for ``secret`` under family ``prefix``.

        Mints ``«PREFIX_<salt>_N»`` on first sight, dedups thereafter, and
        persists when file-backed.
        """
        existing = self._secret_to_token.get(secret)
        if existing is not None:
            return existing
        # Belt-and-braces: guarantee the prefix is reversible no matter how the
        # span got here (built-ins are already clean; user rules are normalized
        # at config load, but a bad prefix must never mint an un-unmaskable token).
        prefix = normalize_token_prefix(prefix)
        if self.encrypt:
            # Token IS the ciphertext (AES-SIV is deterministic → same secret +
            # prefix → same token, so dedup + prompt-cache stability hold). The
            # prefix is bound as associated data so a token can't be re-typed.
            ciphertext = self._siv.encrypt(secret.encode("utf-8"), [prefix.encode("utf-8")])
            token = f"{TOKEN_OPEN}{prefix}~{ciphertext.hex()}{TOKEN_CLOSE}"
        else:
            n = self._counters.get(prefix, 0) + 1
            self._counters[prefix] = n
            token = f"{TOKEN_OPEN}{prefix}_{self._salt}_{n}{TOKEN_CLOSE}"
        self._secret_to_token[secret] = token
        self._token_to_secret[token] = secret
        if not self.encrypt:
            self._persist()  # encrypt mode writes nothing — no cleartext-at-rest
        return token

    def unmask(self, text: str) -> str:
        """Replace every token known to this vault with its real secret.

        Only tokens minted by this vault are substituted; unknown ``«…»`` runs
        are left untouched. The reverse of :meth:`token_for`.
        """
        if TOKEN_OPEN not in text:
            return text
        if self.encrypt:
            # Self-contained tokens: decrypt each «PREFIX~hex» (the in-memory key
            # is the only state). A token that isn't ours / won't decrypt is left
            # untouched, exactly like an unknown token in the map-based path.
            return _ENCRYPT_SCAN.sub(self._decrypt_match, text)
        if not self._token_to_secret:
            return text
        return _TOKEN_SCAN.sub(
            lambda m: self._token_to_secret.get(m.group(0), m.group(0)), text
        )

    def _decrypt_match(self, m: re.Match[str]) -> str:
        prefix, hex_ct = m.group(1), m.group(2)
        try:
            plaintext = self._siv.decrypt(bytes.fromhex(hex_ct), [prefix.encode("utf-8")])
            return plaintext.decode("utf-8")
        except Exception:
            return m.group(0)

    # --- persistence ------------------------------------------------------

    def _load(self) -> None:
        assert self.path is not None
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self._salt = data.get("salt", self._salt)
        self._token_to_secret = dict(data.get("tokens", {}))
        self._secret_to_token = {v: k for k, v in self._token_to_secret.items()}
        for token in self._token_to_secret:
            # «PREFIX_salt_N» → recover the max N per prefix.
            inner = token[len(TOKEN_OPEN) : -len(TOKEN_CLOSE)]
            prefix, _salt, n = inner.rsplit("_", 2)
            self._counters[prefix] = max(self._counters.get(prefix, 0), int(n))

    def _persist(self) -> None:
        """Atomically write the maps to ``self.path`` (0600 file / 0700 dir).

        No-op when in-memory. The file holds cleartext secrets, so the dir is
        forced to ``0700`` and the file to ``0600``.
        """
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.path.parent, VAULT_DIR_MODE)
        except OSError:
            pass
        payload = json.dumps(
            {"salt": self._salt, "tokens": self._token_to_secret},
            ensure_ascii=False,
        )
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), prefix=".vault-")
        try:
            os.fchmod(fd, VAULT_FILE_MODE)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
            os.replace(tmp, self.path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise


# --- per-session active-vault ContextVar ---------------------------------

_current_vault: ContextVar[Vault | None] = ContextVar("scrimward_current_vault", default=None)


def current_vault() -> Vault | None:
    """Return the vault bound to the current execution context, if any."""
    return _current_vault.get()


def set_current_vault(vault: Vault | None) -> object:
    """Bind ``vault`` as the current-context vault; return the reset token."""
    return _current_vault.set(vault)
