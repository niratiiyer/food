import json
import os
import queue
import sys
import threading
import time
import urllib.request
from datetime import datetime, timezone

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

_dd_queue: "queue.Queue[dict]" = queue.Queue(maxsize=10_000)
_dd_started = False


def _ship_to_datadog(api_key: str) -> None:
    site = os.environ.get("DD_SITE", "datadoghq.com")
    url = f"https://http-intake.logs.{site}/api/v2/logs"
    while True:
        batch = [_dd_queue.get()]
        deadline = time.monotonic() + 5
        while len(batch) < 500 and time.monotonic() < deadline:
            try:
                batch.append(_dd_queue.get(timeout=max(deadline - time.monotonic(), 0.01)))
            except queue.Empty:
                break
        body = [
            {
                "ddsource": "python",
                "service": os.environ.get("DD_SERVICE", "leftover"),
                "ddtags": f"env:{os.environ.get('DD_ENV', 'dev')}",
                "message": json.dumps(entry),
                **entry,
            }
            for entry in batch
        ]
        request = urllib.request.Request(
            url,
            data=json.dumps(body).encode(),
            headers={"DD-API-KEY": api_key, "Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(request, timeout=10).read()
        except Exception as exc:
            print(f"Datadog log shipping failed: {exc}", file=sys.stderr)


def _start_datadog_shipper() -> None:
    global _dd_started
    api_key = os.environ.get("DD_API_KEY", "")
    if api_key and not _dd_started:
        _dd_started = True
        threading.Thread(target=_ship_to_datadog, args=(api_key,), daemon=True).start()


class RequestLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        _start_datadog_shipper()
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            route = request.scope.get("route")
            entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "method": request.method,
                "endpoint": getattr(route, "path", request.url.path),
                "path": request.url.path,
                "status": status,
                "duration_ms": round((time.perf_counter() - start) * 1000, 2),
            }
            print(json.dumps(entry), flush=True)
            if _dd_started:
                try:
                    _dd_queue.put_nowait(entry)
                except queue.Full:
                    pass
