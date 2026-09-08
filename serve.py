"""Serve the dashboard locally and let its Refresh button run the pipeline on demand.

Why this exists
---------------
The page cannot fetch from Business Central itself. BC is on-prem behind a self-signed
certificate, sends no CORS headers, and its Basic-auth credentials must never reach a
browser. So a "refresh" button in the page has to ask something on THIS machine to run
refresh.py -- that something is this server.

It replaces the hourly scheduled task, which was removed. The task did two things on a
clean run: rebuild the page, then commit and push so Vercel redeployed. The button does
exactly the same, by running run_refresh.ps1, which is the same wrapper the task used --
so the publish path stays the one that has been exercised for weeks rather than a second
copy of it written here.

Usage
-----
    python serve.py            # then open http://127.0.0.1:8787/
    refresh-dashboard.cmd      # does both, from a double-click

Standard library only, in keeping with the rest of this project: no package manager, no
dependencies to install.
"""

import http.server
import json
import os
import socketserver
import subprocess
import sys
import threading
import time
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("DASHBOARD_PORT", "8787"))
HOST = "127.0.0.1"

# Only these are ever served, and only from this directory. config.json holds the BC
# credentials and is deliberately absent -- serving the folder wholesale would publish it
# to anything that could reach the port.
SERVEABLE = {
    "dashboard.html": "text/html; charset=utf-8",
    "data.json": "application/json; charset=utf-8",
    "refresh.log": "text/plain; charset=utf-8",
}

# The wrapper the scheduled task used: refresh, and on a clean run commit and push so
# Vercel redeploys. Kept as the single publish path rather than reimplemented here.
WRAPPER = os.path.join(HERE, "run_refresh.ps1")

TAIL_LINES = 40


class Job(object):
    """The one refresh that may be in flight, and how the last one ended."""

    def __init__(self):
        self.lock = threading.Lock()
        self.running = False
        self.started = None
        self.finished = None
        self.code = None
        self.lines = []

    def snapshot(self):
        with self.lock:
            return {
                "running": self.running,
                "startedAt": self.started,
                "finishedAt": self.finished,
                "elapsed": round(time.time() - self.started, 1) if self.started and self.running else None,
                "exitCode": self.code,
                "tail": list(self.lines[-TAIL_LINES:]),
            }

    def start(self):
        """True if this call started a run; False if one was already going."""
        with self.lock:
            if self.running:
                return False
            self.running = True
            self.started = time.time()
            self.finished = None
            self.code = None
            self.lines = []
        threading.Thread(target=self._run, daemon=True).start()
        return True

    def _run(self):
        try:
            proc = subprocess.Popen(
                ["powershell", "-NoProfile", "-NonInteractive",
                 "-ExecutionPolicy", "Bypass", "-File", WRAPPER],
                cwd=HERE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", bufsize=1,
            )
            for line in proc.stdout:
                line = line.rstrip()
                if line:
                    with self.lock:
                        self.lines.append(line)
                        # Unbounded output would grow forever on a long run.
                        if len(self.lines) > 400:
                            del self.lines[:-400]
            code = proc.wait()
        except Exception as exc:                     # noqa: BLE001 - reported to the page
            with self.lock:
                self.lines.append("serve.py could not start the refresh: %s" % exc)
            code = -1
        with self.lock:
            self.running = False
            self.finished = time.time()
            self.code = code


JOB = Job()


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "BCDashboard/1.0"

    def log_message(self, fmt, *args):
        sys.stderr.write("  %s\n" % (fmt % args))

    # A browser on another site cannot read our responses, but it could still POST to us
    # blind. Requiring a loopback Host defeats the DNS-rebinding version of that.
    def _local_only(self):
        host = (self.headers.get("Host") or "").split(":")[0]
        if host in ("127.0.0.1", "localhost", "::1", "[::1]"):
            return True
        self._json(403, {"error": "this server only answers to localhost"})
        return False

    def _json(self, code, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/status":
            if not self._local_only():
                return
            return self._json(200, JOB.snapshot())

        name = "dashboard.html" if path in ("/", "/index.html") else path.lstrip("/")
        if name not in SERVEABLE:
            return self._json(404, {"error": "not found"})
        full = os.path.join(HERE, name)
        if not os.path.exists(full):
            return self._json(404, {"error": name + " has not been built yet"})
        with open(full, "rb") as fh:
            body = fh.read()
        self.send_response(200)
        self.send_header("Content-Type", SERVEABLE[name])
        self.send_header("Content-Length", str(len(body)))
        # Always revalidate: the whole point is to see the page the refresh just wrote.
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path.split("?", 1)[0] != "/api/refresh":
            return self._json(404, {"error": "not found"})
        if not self._local_only():
            return
        if not os.path.exists(WRAPPER):
            return self._json(500, {"error": "run_refresh.ps1 is missing"})
        if JOB.start():
            return self._json(202, JOB.snapshot())
        return self._json(409, JOB.snapshot())   # already running; the page just polls on


class Server(socketserver.ThreadingTCPServer):
    # Threaded so the page can poll /api/status while a refresh is in flight, and so a
    # stale socket does not block a restart.
    allow_reuse_address = True
    daemon_threads = True


def main():
    os.chdir(HERE)
    url = "http://%s:%d/" % (HOST, PORT)
    try:
        srv = Server((HOST, PORT), Handler)
    except OSError as exc:
        sys.exit("Could not bind %s -- is it already running?\n  %s" % (url, exc))
    print("Sales Margin Control")
    print("  serving   %s" % url)
    print("  refresh   click Refresh data in the page, or POST %sapi/refresh" % url)
    print("  stop      Ctrl+C")
    if "--no-browser" not in sys.argv:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
