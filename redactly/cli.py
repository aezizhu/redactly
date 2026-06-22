"""Redactly command-line interface.

``main`` is the click group referenced by the ``redactly`` entry point
(``[project.scripts] redactly = "redactly.cli:main"``).

Commands:

- ``redactly proxy [--host] [--port] [--upstream]`` — run the redaction proxy
  under uvicorn in the foreground.
- ``redactly wrap claude [-- claude-args…]`` — ensure the proxy is up, point the
  wrapped tool at it, run the tool as a subprocess, and restore on exit.

The ``wrap`` flow models Headroom's launcher (cli/wrap.py): it sets
``ANTHROPIC_BASE_URL`` to the local proxy AND writes ``env.ANTHROPIC_BASE_URL``
into the project-local ``.claude/settings.local.json`` (Claude Code's daemon
re-reads settings fresh per conversation, so the env var alone is not enough —
issue #951). The previous value is captured and restored in a ``finally`` so the
settings file is never left pointing at a dead proxy.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click

from . import __version__
from .config import DEFAULT_HOST, DEFAULT_PORT, DEFAULT_UPSTREAM

# Project-local settings file Claude Code reads per conversation.
CLAUDE_SETTINGS_LOCAL = Path(".claude") / "settings.local.json"
CLAUDE_BASE_URL_KEY = "ANTHROPIC_BASE_URL"


@click.group()
@click.version_option(__version__, prog_name="redactly")
def main() -> None:
    """Redactly — mask your secrets before they leave your machine."""


@main.command("proxy")
@click.option("--host", default=DEFAULT_HOST, show_default=True, help="Bind host (loopback only by default).")
@click.option("--port", default=DEFAULT_PORT, show_default=True, type=int, help="Bind port.")
@click.option("--upstream", default=None, help=f"Upstream base URL (default: $REDACT_UPSTREAM or {DEFAULT_UPSTREAM}).")
def proxy_cmd(host: str, port: int, upstream: str | None) -> None:
    """Run the redaction proxy under uvicorn (foreground).

    Builds the app via :func:`redactly.proxy.create_app` and serves it with
    ``uvicorn.run``. ``--upstream`` overrides ``REDACT_UPSTREAM``.

    TODO(scaffold): load config, build app, uvicorn.run(app, host, port).
    """
    raise NotImplementedError("redactly proxy is not yet implemented")


@main.command(
    "wrap",
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
)
@click.argument("tool", type=click.Choice(["claude"]))
@click.option("--port", default=DEFAULT_PORT, show_default=True, type=int, help="Proxy port to ensure/route to.")
@click.argument("tool_args", nargs=-1, type=click.UNPROCESSED)
def wrap_cmd(tool: str, port: int, tool_args: tuple[str, ...]) -> None:
    """Run an AI coding tool with its traffic routed through Redactly.

    Steps (per Headroom's wrap launcher):

    1. Ensure the proxy is listening on ``--port`` (start it detached if not).
    2. Set ``ANTHROPIC_BASE_URL`` in the child env to the local proxy URL.
    3. Write ``env.ANTHROPIC_BASE_URL`` into ``.claude/settings.local.json``
       (capturing the previous value).
    4. ``subprocess.run`` the tool with ``tool_args``.
    5. In ``finally``: restore the settings file and stop any proxy we started.

    TODO(scaffold): implement proxy-up check, env + settings injection,
    subprocess launch, and restore-on-exit.
    """
    raise NotImplementedError("redactly wrap is not yet implemented")


def _write_base_url(proxy_url: str, settings_path: Path | None = None) -> str | None:
    """Set ``env.ANTHROPIC_BASE_URL`` in the project-local Claude settings.

    Returns the previous value (or ``None`` if unset) so the caller can restore
    it on exit. Creates the file/dir if absent; preserves any other settings.
    Models ``_write_claude_wrap_base_url`` in Headroom's cli/wrap.py (#951).

    TODO(scaffold): implement read-merge-write of settings.local.json.
    """
    raise NotImplementedError("cli._write_base_url is not yet implemented")


def _restore_base_url(previous: str | None, settings_path: Path | None = None) -> None:
    """Restore (or remove) the ``ANTHROPIC_BASE_URL`` env key in Claude settings.

    When ``previous`` is ``None`` the key is removed; otherwise it is restored —
    so the settings file is never left pointing at a dead proxy. Models
    ``_restore_claude_wrap_base_url`` in Headroom's cli/wrap.py.

    TODO(scaffold): implement read-modify-write of settings.local.json.
    """
    raise NotImplementedError("cli._restore_base_url is not yet implemented")


if __name__ == "__main__":  # pragma: no cover
    main()
