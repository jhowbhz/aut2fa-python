import json
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


@dataclass
class Reply:
    status: int = 202
    body: bytes = b"{}"
    headers: dict[str, str] = field(default_factory=lambda: {"Content-Type": "application/json"})
    delay: float = 0
    body_delay: float = 0


def json_reply(payload: Any, status: int = 202, **headers: str) -> Reply:
    return Reply(
        status,
        json.dumps(payload).encode("utf-8"),
        headers
        or {
            "Content-Type": "application/json",
        },
    )


@dataclass
class ReceivedRequest:
    method: str
    path: str
    headers: dict[str, str]
    body: bytes


class LocalApi:
    def __init__(self, *replies: Reply):
        self.requests: list[ReceivedRequest] = []
        self.replies = deque(replies)
        api = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.respond()

            def do_POST(self):
                self.respond()

            def respond(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                api.requests.append(
                    ReceivedRequest(
                        self.command,
                        self.path,
                        {key.lower(): value for key, value in self.headers.items()},
                        body,
                    )
                )
                reply = api.replies.popleft() if api.replies else Reply(500)
                if reply.delay:
                    time.sleep(reply.delay)
                try:
                    self.send_response(reply.status)
                    for key, value in reply.headers.items():
                        self.send_header(key, value)
                    if not any(key.lower() == "content-length" for key in reply.headers):
                        self.send_header("Content-Length", str(len(reply.body)))
                    self.send_header("Connection", "close")
                    self.end_headers()
                    if reply.body_delay:
                        time.sleep(reply.body_delay)
                    self.wfile.write(reply.body)
                except ConnectionError:
                    pass

            def log_message(self, format, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            kwargs={"poll_interval": 0.01},
            daemon=True,
        )

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
