#!/usr/bin/env python3
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


HOST = os.getenv("MOCK_HEALTH_HOST", "0.0.0.0")
PORT = int(os.getenv("MOCK_HEALTH_PORT", "18081"))
INITIAL_HEALTHY = os.getenv("MOCK_INITIAL_HEALTHY", "true").strip().lower() in {"1", "true", "yes", "on"}
TOKEN = os.getenv("MOCK_HEALTH_TOKEN", "devtoken")


class State:
    healthy = INITIAL_HEALTHY


class Handler(BaseHTTPRequestHandler):
    def _write(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        parsed = urlparse(self.path)

        if parsed.path == "/health":
            self._write(200 if State.healthy else 503, {"healthy": State.healthy})
            return

        if parsed.path == "/state":
            self._write(200, {"healthy": State.healthy, "port": PORT})
            return

        self._write(404, {"error": "not_found"})

    def do_POST(self):  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/set":
            self._write(404, {"error": "not_found"})
            return

        query = parse_qs(parsed.query)
        token = query.get("token", [""])[0]
        if token != TOKEN:
            self._write(403, {"error": "forbidden"})
            return

        value = query.get("healthy", [""])[0].strip().lower()
        if value not in {"true", "false", "1", "0", "yes", "no"}:
            self._write(400, {"error": "invalid_healthy_value"})
            return

        State.healthy = value in {"true", "1", "yes"}
        self._write(200, {"healthy": State.healthy})

    def log_message(self, _format, *_args):
        return


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"mock-health-service listening on {HOST}:{PORT}, initial_healthy={State.healthy}")
    server.serve_forever()


if __name__ == "__main__":
    main()
