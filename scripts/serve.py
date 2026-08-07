#!/usr/bin/env python3
"""Local server for the agent-privacy-news UI, with an on-demand Scan button.

Serves ui/ over http://127.0.0.1:8765 and exposes:
  GET  /api/status  -> {"running": bool}
  POST /api/scan    -> runs fetch_feeds.py + summarize.py run, returns {"ok", "log"}

The scan needs ANTHROPIC_API_KEY; this server loads it from the project .env
automatically. Bind is localhost-only, so the scan endpoint is not exposed to
the network.

Run:  .venv/bin/python scripts/serve.py   (or ./scripts/ui.sh)
"""
import json
import mimetypes
import os
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
UI = ROOT / "ui"
PORT = int(os.environ.get("PORT", "8765"))

# Load .env so the scan subprocess inherits ANTHROPIC_API_KEY.
env_file = ROOT / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

_scan_lock = threading.Lock()
_scanning = {"on": False}


def do_scan() -> dict:
    py = sys.executable
    steps = [
        ("fetch feeds", [py, str(ROOT / "scripts" / "fetch_feeds.py")]),
        ("summarize", [py, str(ROOT / "scripts" / "summarize.py"), "run"]),
    ]
    logs = []
    for name, cmd in steps:
        p = subprocess.run(cmd, cwd=str(ROOT), capture_output=True,
                           text=True, env=os.environ)
        logs.append(f"$ {name}\n{p.stdout}{p.stderr}".rstrip())
        if p.returncode != 0:
            return {"ok": False,
                    "error": f"{name} failed (exit {p.returncode})",
                    "log": "\n\n".join(logs)}
    return {"ok": True, "log": "\n\n".join(logs)}


def run_summarize(subcmd: list, name: str, read_file: str) -> dict:
    """Run a summarize.py subcommand and return the markdown it wrote."""
    cmd = [sys.executable, str(ROOT / "scripts" / "summarize.py")] + subcmd
    p = subprocess.run(cmd, cwd=str(ROOT), capture_output=True,
                       text=True, env=os.environ)
    log = (p.stdout + p.stderr).strip()
    if p.returncode != 0:
        return {"ok": False, "error": f"{name} failed (exit {p.returncode})", "log": log}
    f = ROOT / read_file
    return {"ok": True, "log": log,
            "markdown": f.read_text() if f.exists() else ""}


_SYNTH_SUFFIX = {"privacy": "", "security": ".sec", "legal": ".law"}


def _synthesis_task(params: dict) -> dict:
    lens = params.get("lens", "privacy")
    if lens not in _SYNTH_SUFFIX:
        lens = "privacy"
    return run_summarize(["synthesis", "--lens", lens], f"synthesis:{lens}",
                         f"data/reports/latest-synthesis{_SYNTH_SUFFIX[lens]}.md")


POST_TASKS = {
    "/api/scan": lambda params: do_scan(),
    "/api/report": lambda params: run_summarize(["report"], "report", "data/reports/latest.md"),
    "/api/synthesis": _synthesis_task,
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # quieter, single-line
        sys.stderr.write(f"  {self.command} {self.path} -> {args[1]}\n")

    def _json(self, code: int, obj: dict) -> None:
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = self.path.split("?")[0]
        if path == "/api/status":
            return self._json(200, {"running": _scanning["on"]})
        rel = "index.html" if path in ("/", "") else path.lstrip("/")
        target = (UI / rel).resolve()
        try:
            target.relative_to(UI)
        except ValueError:
            return self._json(403, {"error": "forbidden"})
        if not target.is_file():
            return self._json(404, {"error": "not found"})
        data = target.read_bytes()
        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")  # so data.js reload is fresh
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        task = POST_TASKS.get(parsed.path)
        if task is None:
            return self._json(404, {"error": "not found"})
        params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        if not _scan_lock.acquire(blocking=False):
            return self._json(409, {"ok": False, "error": "a task is already running"})
        _scanning["on"] = True
        try:
            result = task(params)
        finally:
            _scanning["on"] = False
            _scan_lock.release()
        return self._json(200 if result["ok"] else 500, result)


def main() -> None:
    os.chdir(ROOT)
    httpd = None
    for port in range(PORT, PORT + 20):
        try:
            httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
            break
        except OSError as e:
            if e.errno in (48, 98):  # address already in use
                print(f"port {port} busy, trying {port + 1}…")
                continue
            raise
    if httpd is None:
        sys.exit(f"No free port in range {PORT}-{PORT + 19}. "
                 f"Set PORT to a free one: PORT=9000 ./scripts/ui.sh")
    url = f"http://127.0.0.1:{httpd.server_address[1]}"
    print(f"Agent Privacy News UI  ->  {url}", flush=True)
    print("Scan button is live. Press Ctrl+C to stop.\n", flush=True)
    threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")


if __name__ == "__main__":
    main()
