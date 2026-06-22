"""OpenAI Chat Completions adapter.

Where the text lives (OpenAI Chat Completions, ``POST /v1/chat/completions``):

- ``messages[].content`` — a string OR a list of parts; redact the ``text`` of
  each ``{"type": "text", "text": ...}`` part.

Streamed response (SSE): text arrives in ``choices[].delta.content`` on each
``data:`` chunk (terminated by ``data: [DONE]``). The un-masker rewrites that
``content``, carry-buffering any token that splits across two chunks.

This adapter satisfies the :class:`~redactly.adapters.base.Adapter` Protocol
structurally (no inheritance required).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping

from ..engine import Redactor
from ..vault import Vault

# Request path this adapter owns.
CHAT_COMPLETIONS_PATH = "/v1/chat/completions"


class OpenAIChatAdapter:
    """Adapter for the OpenAI Chat Completions API."""

    def matches(self, path: str, headers: Mapping[str, str]) -> bool:
        """Return ``True`` for the OpenAI Chat Completions endpoint.

        TODO(scaffold): match ``path`` against ``CHAT_COMPLETIONS_PATH``.
        """
        raise NotImplementedError("OpenAIChatAdapter.matches is not yet implemented")

    def redact_request(self, body: bytes, red: Redactor) -> bytes:
        """Redact ``messages[].content`` text, reserialize.

        FAIL-CLOSED: raise on a body that is not valid JSON or lacks the
        expected Chat Completions shape — never forward the original bytes.

        TODO(scaffold): parse JSON, walk message content (str or parts) through
        ``red.redact_text``, re-encode.
        """
        raise NotImplementedError("OpenAIChatAdapter.redact_request is not yet implemented")

    async def unmask_stream(
        self, aiter_bytes: AsyncIterator[bytes], vault: Vault
    ) -> AsyncIterator[bytes]:
        """Un-mask tokens in ``choices[].delta.content``, cross-chunk safe.

        Carry-buffer a trailing partial token / partial SSE event across chunk
        boundaries so a token split across two chunks is reassembled before
        ``vault.unmask`` runs.

        TODO(scaffold): implement the buffered SSE rewrite. (This ``async``
        generator must remain importable even while unimplemented.)
        """
        raise NotImplementedError("OpenAIChatAdapter.unmask_stream is not yet implemented")
        # Unreachable, but marks this coroutine as an async generator so the
        # Protocol's AsyncIterator return type holds once implemented.
        if False:  # pragma: no cover
            yield b""
