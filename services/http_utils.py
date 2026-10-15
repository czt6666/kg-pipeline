from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler


@dataclass
class ApiResult:
    status: int
    body: object


def to_json_bytes(body) -> bytes:
    return json.dumps(body, ensure_ascii=False).encode("utf-8")


class JsonHandler(BaseHTTPRequestHandler):
    def send_bytes(self, code: int, body: bytes, ctype: str = "application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_api(self, result: ApiResult):
        self.send_bytes(result.status, to_json_bytes(result.body))

    def send_api_with_heartbeat(self, compute, interval_s: float = 15.0):
        """Send `compute()`'s ApiResult, writing a space every `interval_s` until it is ready.

        For slow handlers (the QA agent can take minutes): nginx's proxy_read_timeout
        (default 60s) counts the gap between upstream reads, so a request that is silent
        that long gets a 504 even though it would succeed. Headers go out right away
        and the leading whitespace keeps the connection alive. JSON.parse ignores it.
        Because the status line is already sent, a failure comes back as 200 with an
        `error` field, so the client must check for that field.
        """
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")  # stop nginx holding the heartbeat bytes
        self.end_headers()
        self.close_connection = True  # no Content-Length: the body ends when we close

        done = threading.Event()
        box = {}

        def run():
            try:
                box["result"] = compute()
            except Exception as e:  # noqa: BLE001 -- must still answer the client
                box["result"] = ApiResult(500, {"error": f"internal error: {e}"})
            finally:
                done.set()

        threading.Thread(target=run, daemon=True).start()
        try:
            while not done.wait(interval_s):
                self.wfile.write(b" ")
                self.wfile.flush()
            result = box["result"]
            body = result.body
            if result.status >= 400 and isinstance(body, dict):
                body = {**body, "status": result.status}
            self.wfile.write(to_json_bytes(body))
        except (BrokenPipeError, ConnectionResetError):
            pass  # client went away; nothing left to tell it

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, format, *args):
        return
