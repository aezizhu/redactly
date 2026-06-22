"""The redaction engine — turns raw text into tokenized text.

:class:`Redactor` is the provider-agnostic core. Per-provider adapters locate
*where the text lives* in a request body and call :meth:`Redactor.redact_text`
on each text field; the engine does the actual work:

1. Gather spans from the built-in detectors **and** the user rules.
2. Drop spans that fall on the allowlist (known-safe matches).
3. Resolve overlaps (prefer the most-specific / earliest-listed detector).
4. Mint a stable token for each surviving span via the vault.
5. Splice the tokens in **right-to-left** so earlier offsets stay valid as
   later (higher-offset) spans are replaced first.

Determinism is mandatory: the same input yields the same output (the vault
guarantees same-secret → same-token), so redacted bytes are stable across turns
and the provider's prompt cache still hits.
"""

from __future__ import annotations

from .config import Allowlist, UserRule
from .detectors import BUILTINS, Detector, Span
from .vault import Vault


class Redactor:
    """Gathers spans, resolves overlaps, mints tokens, and splices text.

    Args:
        vault: The session vault used to mint stable tokens (and later to
            un-mask the reply).
        detectors: Built-in detectors to run (default :data:`BUILTINS`).
        user_rules: User-declared rules; compiled into detectors and run
            alongside the built-ins (precise, opt-in).
        allowlist: Known-safe values to drop before tokenizing.
    """

    def __init__(
        self,
        vault: Vault,
        detectors: tuple[Detector, ...] = BUILTINS,
        user_rules: tuple[UserRule, ...] = (),
        allowlist: Allowlist | None = None,
    ) -> None:
        self.vault = vault
        self.detectors = detectors
        self.user_rules = user_rules
        self.allowlist = allowlist if allowlist is not None else Allowlist()

    def redact_text(self, s: str) -> str:
        """Return ``s`` with every detected secret replaced by a stable token.

        Pipeline: detect (built-ins + user rules) → drop allowlisted → resolve
        overlaps → mint tokens via ``self.vault.token_for`` → splice
        right-to-left. Pure and deterministic: no secret value appears in the
        returned string, and the same input always yields the same output.

        On empty / non-secret-bearing input this returns the input unchanged.
        It MUST NOT swallow detector/vault errors — a raise here is what makes
        the proxy fail closed (the caller blocks rather than forwarding raw
        text).

        TODO(scaffold): implement the gather → resolve → mint → splice pipeline.
        """
        raise NotImplementedError("Redactor.redact_text is not yet implemented")

    def _resolve_overlaps(self, spans: list[Span]) -> list[Span]:
        """Drop overlapping spans, keeping the most-specific (earliest) match.

        Detectors are ordered most-specific-first, so when two spans cover the
        same bytes the one whose detector was listed earlier wins. Returns a
        non-overlapping list sorted by ``start``.

        TODO(scaffold): implement overlap resolution.
        """
        raise NotImplementedError("Redactor._resolve_overlaps is not yet implemented")

    def _drop_allowlisted(self, spans: list[Span]) -> list[Span]:
        """Remove spans whose matched text is on the allowlist.

        Allowlisting un-redacts a known-safe value (``localhost``,
        ``example.com``, a common port) that happened to match a detector. It
        never adds redaction.

        TODO(scaffold): implement literal + pattern allowlist filtering.
        """
        raise NotImplementedError("Redactor._drop_allowlisted is not yet implemented")
