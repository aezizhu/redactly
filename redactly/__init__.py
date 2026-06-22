"""Redactly — a local, FAIL-CLOSED redaction proxy for AI coding tools.

Redactly puts a tiny redaction proxy on *your own machine*, between an AI
coding tool (Claude Code, Codex, Aider, …) and the cloud. Every outbound
request body is buffered and inspected; real secrets are swapped for stable,
typed, reversible tokens («EMAIL_1») *before the wire*, and the streamed reply
is un-masked locally via a session vault so the answer stays useful while the
real value never leaves your laptop.

Design posture (the inversion of Headroom's fail-OPEN proxy):

    FAIL-CLOSED EVERYWHERE. If a request body cannot be parsed or redacted, if
    an unknown path/content-type arrives, or if the redactor raises, the proxy
    BLOCKS with a 5xx and forwards NOTHING. There is no forward-original-on-error
    path and no passthrough default. Default-DENY.

Package layout
--------------
- ``redactly.config``           — runtime configuration (upstream, host/port, rules, vault).
- ``redactly.detectors``        — ``Detector`` / ``Span`` + built-in detectors (most-specific-first).
- ``redactly.vault``            — reversible token <-> secret store (0600 file / 0700 dir).
- ``redactly.engine``           — ``Redactor``: gather spans, resolve overlaps, mint tokens, splice.
- ``redactly.adapters.base``    — the ``Adapter`` Protocol (per-provider body shapes).
- ``redactly.adapters.anthropic``  — Anthropic Messages adapter.
- ``redactly.adapters.openai_chat`` — OpenAI Chat Completions adapter.
- ``redactly.proxy``            — FastAPI app: buffer → pick adapter → redact → forward → un-mask.
- ``redactly.cli``              — ``redactly proxy`` / ``redactly wrap claude`` (click group ``main``).
"""

from __future__ import annotations

__version__ = "0.0.1"

__all__ = ["__version__"]
