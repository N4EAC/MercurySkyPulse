"""Loopback-only embedded HTTP server for read-only application views."""

from __future__ import annotations

from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
from threading import Thread
from urllib.parse import urlsplit

from application.web_dashboard import WebDashboardSnapshot


NAV = (("/", "Dashboard"), ("/messages", "Messages"),
       ("/transfers", "Transfers"), ("/station", "Station Status"),
       ("/logs", "Logs"))


class _LoopbackServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, address, snapshot: WebDashboardSnapshot):
        self.snapshot = snapshot
        super().__init__(address, _LocalHandler)

    def verify_request(self, request, client_address) -> bool:
        try:
            return ipaddress.ip_address(client_address[0]).is_loopback
        except ValueError:
            return False


class _LocalHandler(BaseHTTPRequestHandler):
    server_version = "MercurySkyPulseLocal/1"

    def do_HEAD(self) -> None:  # noqa: N802
        self._serve(include_body=False)

    def do_GET(self) -> None:  # noqa: N802
        self._serve(include_body=True)

    def do_POST(self) -> None:  # noqa: N802
        self._error(405, "Read-only interface", allow="GET, HEAD")

    do_PUT = do_POST
    do_PATCH = do_POST
    do_DELETE = do_POST

    def _serve(self, include_body: bool) -> None:
        path = urlsplit(self.path).path
        data = self.server.snapshot.read()
        if path.startswith("/api/"):
            key = path.removeprefix("/api/")
            aliases = {"dashboard": data, "messages": {
                "conversations": data["conversations"], "messages": data["messages"]},
                "transfers": data["transfers"], "station": data["station"],
                "logs": data["logs"], "plugins": data["plugins"]}
            if key not in aliases:
                self._error(404, "Not found", include_body=include_body)
                return
            self._send(json.dumps(aliases[key], ensure_ascii=False).encode(),
                       "application/json; charset=utf-8", include_body)
            return
        renderers = {"/": _dashboard, "/messages": _messages,
                     "/transfers": _transfers, "/station": _station, "/logs": _logs}
        renderer = renderers.get(path)
        if renderer is None:
            self._error(404, "Not found", include_body=include_body)
            return
        body = _page(dict(NAV)[path], path, renderer(data)).encode()
        self._send(body, "text/html; charset=utf-8", include_body)

    def _send(self, body: bytes, content_type: str, include_body: bool) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        if include_body:
            self.wfile.write(body)

    def _error(self, status: int, message: str, allow: str | None = None,
               include_body: bool = True) -> None:
        body = message.encode()
        self.send_response(status)
        if allow:
            self.send_header("Allow", allow)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if include_body:
            self.wfile.write(body)

    def log_message(self, _format: str, *_args) -> None:
        return


class LocalWebServer:
    """Lifecycle wrapper that can bind only to IPv4 loopback."""

    def __init__(self, snapshot: WebDashboardSnapshot, port: int = 8765) -> None:
        if not 0 <= port <= 65535:
            raise ValueError("Local web port must be between 0 and 65535")
        self.snapshot = snapshot
        self.port = port
        self._server: _LoopbackServer | None = None
        self._thread: Thread | None = None

    @property
    def url(self) -> str | None:
        return None if self._server is None else f"http://127.0.0.1:{self._server.server_port}/"

    def start(self) -> str:
        if self._server is not None:
            return self.url or ""
        self._server = _LoopbackServer(("127.0.0.1", self.port), self.snapshot)
        self._thread = Thread(target=self._server.serve_forever,
                              name="local-web-interface", daemon=True)
        self._thread.start()
        return self.url or ""

    def stop(self) -> None:
        server, thread = self._server, self._thread
        self._server = self._thread = None
        if server is not None:
            server.shutdown()
            server.server_close()
        if thread is not None:
            thread.join(timeout=2)


def _page(title: str, current: str, content: str) -> str:
    nav = "".join(f'<a class="{"active" if path == current else ""}" href="{path}">{label}</a>'
                  for path, label in NAV)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{title} · MercurySkyPulse</title>
<style>:root{{color-scheme:dark light;--bg:#0c1118;--card:#151d28;--text:#e9eff8;--muted:#91a0b5;--accent:#68a4ff;--line:#293547}}*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font:15px system-ui,-apple-system,"Segoe UI",sans-serif}}header{{padding:24px clamp(18px,5vw,64px);border-bottom:1px solid var(--line)}}h1{{margin:0 0 6px;font-size:24px}}small{{color:var(--muted)}}nav{{display:flex;gap:8px;flex-wrap:wrap;margin-top:18px}}nav a{{color:var(--muted);text-decoration:none;padding:8px 12px;border-radius:9px}}nav a.active,nav a:hover{{background:var(--card);color:var(--text)}}main{{padding:28px clamp(18px,5vw,64px);max-width:1400px}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:14px}}.card{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px;overflow:auto}}.metric{{font-size:25px;font-weight:650;margin-top:8px}}table{{width:100%;border-collapse:collapse}}th,td{{padding:11px 10px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}}th{{color:var(--muted);font-size:12px;text-transform:uppercase}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;margin:0;color:var(--text)}}.muted{{color:var(--muted)}}@media(prefers-color-scheme:light){{:root{{--bg:#f4f6f9;--card:#fff;--text:#17202c;--muted:#667487;--accent:#1769d1;--line:#dce2ea}}}}</style></head>
<body><header><h1>MercurySkyPulse</h1><small>Local read-only interface · 127.0.0.1</small><nav>{nav}</nav></header><main><h2>{title}</h2>{content}</main></body></html>"""


def _value(value, suffix="") -> str:
    return "—" if value is None else f"{escape(str(value))}{suffix}"


def _dashboard(data: dict) -> str:
    station = data["station"]
    cards = (("Mercury", station["engine"]), ("Modem", station["modem"]),
             ("SNR", _value(station["snr_db"], " dB")),
             ("Bitrate", _value(station["bitrate_bps"], " bps")),
             ("Conversations", len(data["conversations"])),
             ("Transfers", len(data["transfers"])),
             ("Edition", str(data["license"]["edition"]).title()))
    return '<div class="grid">' + "".join(
        f'<section class="card"><small>{escape(str(label))}</small><div class="metric">{escape(str(value))}</div></section>'
        for label, value in cards) + "</div>"


def _table(headers, rows) -> str:
    head = "".join(f"<th>{escape(str(item))}</th>" for item in headers)
    body = "".join("<tr>" + "".join(f"<td>{escape(str(cell))}</td>" for cell in row) + "</tr>" for row in rows)
    return f'<section class="card"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></section>'


def _messages(data: dict) -> str:
    by_id = {item["id"]: item for item in data["conversations"]}
    rows = []
    for item in reversed(data["messages"]):
        conversation = by_id.get(item.get("conversation_id"), {})
        rows.append((item.get("sent_at", ""), conversation.get("remote_call", ""),
                     item.get("direction", ""), item.get("status", ""), item.get("body", "")))
    return _table(("Timestamp", "Station", "Direction", "Status", "Message"), rows)


def _transfers(data: dict) -> str:
    rows = [(item.get("name", ""), item.get("direction", ""), item.get("status", ""),
             f'{item.get("transferred", 0)} / {item.get("size", 0)}',
             f'{item.get("progress", 0)}%') for item in data["transfers"]]
    return _table(("File", "Direction", "Status", "Bytes", "Progress"), rows)


def _station(data: dict) -> str:
    station = data["station"]
    return _table(("Property", "Value"), [(key.replace("_", " ").title(), _value(value))
                                           for key, value in station.items()])


def _logs(data: dict) -> str:
    return '<section class="card"><pre>' + escape("\n".join(data["logs"])) + "</pre></section>"
