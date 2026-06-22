"""Secret/PII detectors and the ``Span`` type they emit.

A :class:`Detector` is a named pattern with a ``token_prefix`` and an optional
``validate`` callback (Luhn, checksum, key-prefix). Calling :func:`detect`
returns a list of :class:`Span` — half-open ``[start, end)`` slices of the input
text, each tagged with the detector ``name`` and token ``prefix`` plus the
matched ``text``.

The shared types here (``Span``, ``Detector``, ``BUILTINS``) are the vocabulary
downstream modules (``engine``, the adapters) import — they are concrete. Only
the detection *logic* (``detect`` and each detector's ``pattern``/``validate``)
is stubbed.

Built-in detectors are ordered **most-specific-first** so the overlap resolver
in the engine prefers the high-confidence, narrowly-scoped match (e.g. an AWS
key prefix wins over a generic token) when two detectors cover the same bytes.

Policy (see ``docs/REDACTION-POLICY.md``): redact high-confidence *values*,
validate numbers before masking (never versions/ports/line-numbers), and leave
person-names to opt-in user rules rather than blanket NER.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class Span:
    """A detected region of text to be replaced by a token.

    Attributes:
        start: Start offset into the source text (inclusive).
        end: End offset into the source text (exclusive); ``text == source[start:end]``.
        name: Name of the detector (or user rule) that produced this span.
        prefix: Token family prefix, e.g. ``"EMAIL"`` → ``«EMAIL_<salt>_N»``.
        text: The exact matched secret value (the literal to be tokenized).
    """

    start: int
    end: int
    name: str
    prefix: str
    text: str


@dataclass(frozen=True)
class Detector:
    """A named, validated secret/PII pattern.

    Attributes:
        name: Stable detector identifier (also the ``Span.name``).
        pattern: Regex (as a string) located against request text.
        token_prefix: Token family for minted tokens, e.g. ``"AWS_KEY"``.
        validate: Optional predicate applied to a candidate match string;
            returns ``True`` to keep the match, ``False`` to discard it
            (e.g. Luhn for credit cards, prefix/length for keys). ``None``
            means every regex hit is accepted.
    """

    name: str
    pattern: str
    token_prefix: str
    validate: Callable[[str], bool] | None = None


# ---------------------------------------------------------------------------
# Built-in detectors — ORDERED MOST-SPECIFIC-FIRST.
#
# The names, ordering, and token_prefix values are the contract; the regex
# bodies and validators are stubbed (empty pattern + TODO) until implemented.
# Most-specific (narrow, prefix/checksum-anchored) detectors come first so the
# engine's overlap resolver prefers them over broader ones.
# ---------------------------------------------------------------------------
BUILTINS: tuple[Detector, ...] = (
    # --- Credentials (highest confidence: prefix/format-anchored) ---
    Detector(name="aws_access_key", pattern="", token_prefix="AWS_KEY"),       # TODO: AKIA/ASIA prefix
    Detector(name="aws_secret_key", pattern="", token_prefix="AWS_SECRET"),    # TODO: 40-char base64-ish
    Detector(name="github_token", pattern="", token_prefix="GH_TOKEN"),        # TODO: ghp_/gho_/ghs_ …
    Detector(name="openai_key", pattern="", token_prefix="OPENAI_KEY"),        # TODO: sk-… / sk-proj-…
    Detector(name="anthropic_key", pattern="", token_prefix="ANTHROPIC_KEY"),  # TODO: sk-ant-…
    Detector(name="slack_token", pattern="", token_prefix="SLACK_TOKEN"),      # TODO: xox[baprs]-…
    Detector(name="google_api_key", pattern="", token_prefix="GOOGLE_KEY"),    # TODO: AIza…
    Detector(name="private_key", pattern="", token_prefix="PRIVATE_KEY"),      # TODO: -----BEGIN … KEY-----
    Detector(name="jwt", pattern="", token_prefix="JWT"),                      # TODO: base64url.base64url.sig
    Detector(name="bearer_token", pattern="", token_prefix="BEARER"),          # TODO: Authorization: Bearer …
    Detector(name="connection_string", pattern="", token_prefix="CONN_STR"),   # TODO: proto://user:pass@host
    # --- Validated numerics (validate BEFORE masking) ---
    Detector(name="credit_card", pattern="", token_prefix="CC", validate=None),  # TODO: 13-19 digits + Luhn
    # --- PII (lower specificity → later) ---
    Detector(name="email", pattern="", token_prefix="EMAIL"),                  # TODO: local@domain
    Detector(name="phone", pattern="", token_prefix="PHONE"),                  # TODO: E.164-ish + validate
    Detector(name="ip_address", pattern="", token_prefix="IP"),               # TODO: IPv4/IPv6, exclude loopback
)


def detect(text: str, detectors: tuple[Detector, ...] = BUILTINS) -> list[Span]:
    """Run ``detectors`` against ``text`` and return all matched spans.

    Each regex hit becomes a :class:`Span`; if the detector has a ``validate``
    callback the candidate is dropped when it returns ``False``. Spans are
    returned in the order detectors are evaluated (most-specific-first), which
    the engine relies on for deterministic overlap resolution. Offsets are
    half-open ``[start, end)`` into ``text``.

    This function only *finds* spans — it does not mutate text, drop
    allowlisted values, or mint tokens (that is the engine's job).

    TODO(scaffold): implement regex scanning + validation.
    """
    raise NotImplementedError("detectors.detect is not yet implemented")
