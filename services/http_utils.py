from __future__ import annotations

import json
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

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, format, *args):
        return
