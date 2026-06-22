"""Anthropic Messages adapter.

Where the text lives (Anthropic Messages, ``POST /v1/messages``):

- ``system`` — a string OR a list of ``{"type": "text", "text": ...}`` blocks.
- ``messages[].content`` — a string OR a list of content blocks; redact the
  ``text`` of each ``{"type": "text", ...}`` block (and tool-result text).

Streamed response (SSE): text arrives in ``content_block_delta`` events whose
``delta`` is ``{"type": "text_delta", "text": "…"}``. The un-masker rewrites the
``text`` of those deltas, carry-buffering any token that splits across two
deltas.

This adapter satisfies the :class:`~redactly.adapters.base.Adapter` Protocol
structurally (no inheritance required).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping

from ..engine import Redactor
from ..vault import Vault

# Request path this adapter owns.
MESSAGES_PATH = "/v1/messages"


class AnthropicAdapter:
    """Adapter for the Anthropic Messages API."""

    def matches(self, path: str, headers: Mapping[str, str]) -> bool:
        """Return ``True`` for the Anthropic Messages endpoint.

        TODO(scaffold): match ``path`` against ``MESSAGES_PATH`` (and, if
        needed, Anthropic auth/version headers).
        """
        raise NotImplementedError("AnthropicAdapter.matches is not yet implemented")

    def redact_request(self, body: bytes, red: Redactor) -> bytes:
        """Redact ``system`` + ``messages[].content`` text, reserialize.

        FAIL-CLOSED: raise on a body that is not valid JSON or lacks the
        expected Messages shape — never forward the original bytes.

        TODO(scaffold): parse JSON, walk system/messages text fields through
        ``red.redact_text``, re-encode.
        """
        raise NotImplementedError("AnthropicAdapter.redact_request is not yet implemented")

    async def unmask_stream(
        self, aiter_bytes: AsyncIterator[bytes], vault: Vault
    ) -> AsyncIterator[bytes]:
        """Un-mask tokens in ``content_block_delta`` text, cross-chunk safe.

        Carry-buffer a trailing partial token / partial SSE event across chunk
        boundaries so a token split across two deltas is reassembled before
        ``vault.unmask`` runs.

        TODO(scaffold): implement the buffered SSE rewrite. (This ``async``
        generator must remain importable even while unimplemented.)
        """
        raise NotImplementedError("AnthropicAdapter.unmask_stream is not yet implemented")
        # Unreachable, but marks this coroutine as an async generator so the
        # Protocol's AsyncIterator return type holds once implemented.
        if False:  # pragma: no cover
            yield b""
