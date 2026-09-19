"""Local static server for previewing the site.

`python -m http.server` inherits socketserver's listen backlog of 5. Browsers
open ~15 parallel connections for the site's ES modules, so on macOS some are
dropped and a module import can stall for seconds — observed as an
intermittent "Loading…" hang in the browser tests. A larger backlog fixes it.
"""

from __future__ import annotations

import functools
import http.server
import threading
from pathlib import Path

REQUEST_BACKLOG = 128


class _Server(http.server.ThreadingHTTPServer):
    request_queue_size = REQUEST_BACKLOG
    daemon_threads = True


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args) -> None:  # noqa: D401 - silence per-request logs
        pass


def make_server(directory: str | Path, host: str = "127.0.0.1", port: int = 0,
                *, quiet: bool = True) -> http.server.ThreadingHTTPServer:
    handler_cls = _QuietHandler if quiet else http.server.SimpleHTTPRequestHandler
    handler = functools.partial(handler_cls, directory=str(directory))
    return _Server((host, port), handler)


def serve_in_background(directory: str | Path) -> tuple[http.server.ThreadingHTTPServer, str]:
    """Start a server on a free port; returns (server, base_url)."""
    server = make_server(directory)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    host, port = server.server_address[:2]
    return server, f"http://{host}:{port}/"
