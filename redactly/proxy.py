"""The FastAPI redaction proxy — FAIL-CLOSED, default-DENY.

Request lifecycle (every outbound request):

1. **Buffer** the entire request body (default-DENY: nothing is forwarded
   un-inspected).
2. **Pick an adapter** — the first registered adapter whose ``matches(path,
   headers)`` is ``True``. If **none** match → BLOCK (5xx), forward nothing.
   There is no passthrough default.
3. **Redact** via ``adapter.redact_request(body, redactor)``. If it raises (bad
   JSON, unexpected shape, redactor error) → BLOCK (5xx), forward nothing.
   Never forward the original body on error.
4. **Forward** to ``REDACT_UPSTREAM`` with httpx. Auth headers
   (``authorization``, ``x-api-key``, ``anthropic-version``, ``anthropic-beta``)
   are forwarded **verbatim**; hop-by-hop headers plus ``host`` and
   ``content-length`` are stripped; **no identifying headers are added**
   (subscription stealth — the proxy must be invisible to the provider).
5. **Un-mask** the streamed reply locally via ``adapter.unmask_stream`` and
   return it as a ``StreamingResponse``.

``GET /healthz`` is the liveness probe and is the only route that does not go
through the redaction pipeline.

This is the deliberate inversion of Headroom's fail-OPEN proxy: where Headroom
forwards the original on any compression failure, Redactly refuses.
"""

from __future__ import annotations

from .config import Config

# Hop-by-hop headers (RFC 7230 §6.1) plus ``host`` / ``content-length``. These
# are connection-scoped and must NOT be forwarded to the upstream; httpx sets
# its own. Auth headers are deliberately NOT in this set — they pass verbatim.
HOP_BY_HOP_HEADERS: frozenset[str] = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
        "host",
        "content-length",
        # accept-encoding is stripped so httpx negotiates an encoding it can
        # actually decode (Headroom hit this — a forwarded br/zstd accept that
        # httpx can't decompress corrupts the streamed body).
        "accept-encoding",
    }
)


def filter_upstream_headers(headers: dict[str, str]) -> dict[str, str]:
    """Return a copy of ``headers`` safe to forward upstream.

    Strips hop-by-hop + ``host`` + ``content-length`` + ``accept-encoding``
    (see :data:`HOP_BY_HOP_HEADERS`); forwards everything else — crucially the
    auth headers — **verbatim**. Adds NOTHING (no ``x-redactly-*``, no proxy
    fingerprint): the proxy must be invisible to the provider.

    TODO(scaffold): implement case-insensitive filtering.
    """
    raise NotImplementedError("proxy.filter_upstream_headers is not yet implemented")


def create_app(config: Config | None = None):  # -> fastapi.FastAPI
    """Build and return the FastAPI app for the Redactly proxy.

    Wires:

    - ``GET /healthz`` → liveness (bypasses the redaction pipeline).
    - catch-all ``POST`` → buffer → pick adapter (fail-closed if none) →
      ``redact_request`` (fail-closed on raise) → httpx forward to
      ``config.upstream`` with verbatim auth + stripped hop-by-hop headers →
      ``StreamingResponse`` via ``adapter.unmask_stream``.

    ``config`` defaults to :func:`redactly.config.load`. The upstream comes from
    ``config.upstream`` (``REDACT_UPSTREAM``) so tests can point it at a mock.

    TODO(scaffold): construct FastAPI app, register routes, build the per-request
    vault + redactor, and forward with httpx.
    """
    raise NotImplementedError("proxy.create_app is not yet implemented")
