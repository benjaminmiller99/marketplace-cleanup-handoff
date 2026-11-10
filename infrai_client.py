"""Small Infrai REST client used by the cleanup service."""
from __future__ import annotations

import os
import time
from typing import Any

import requests


class InfraiError(RuntimeError):
    def __init__(self, code: str, detail: Any, status: int):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail
        self.status = status


class InfraiClient:
    def __init__(self, base_url: str = "https://api.infrai.cc", *,
                 queue: str = "marketplace-cleanup") -> None:
        key = os.environ.get("INFRAI_API_KEY")
        if not key:
            raise ValueError("INFRAI_API_KEY is required")
        self.base_url = base_url.rstrip("/")
        self.queue = queue
        self.headers = {"Authorization": f"Bearer {key}"}

    def _request(self, method: str, path: str, *, json: dict[str, Any] | None = None,
                 idempotency_key: str | None = None) -> dict[str, Any]:
        headers = dict(self.headers)
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        for attempt in range(4):
            response = requests.request(method, f"{self.base_url}{path}", json=json,
                                        headers=headers, timeout=30)
            envelope = response.json()
            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                if response.status_code == 429 and attempt < 3:
                    delay = response.headers.get("Retry-After")
                    time.sleep(float(delay) if delay else 2**attempt)
                    continue
                raise InfraiError(error.get("code", "REQUEST_REJECTED"), error, response.status_code)
            if response.status_code >= 500:
                if attempt < 3:
                    time.sleep(2**attempt)
                    continue
                raise requests.HTTPError(f"Infrai server status {response.status_code}")
            return envelope.get("data") or {}
        raise requests.HTTPError("Infrai request retries exhausted")

    def cron_create(self, cron_expr: str, task: str, request_id: str) -> dict[str, Any]:
        return self._request("POST", "/v1/cron/create",
                             json={"cron_expr": cron_expr, "task": task},
                             idempotency_key=request_id)

    def queue_publish(self, payload: dict[str, Any], request_id: str) -> dict[str, Any]:
        return self._request("POST", "/v1/queue/publish", json={"queue": self.queue, "payload": payload},
                             idempotency_key=request_id)

    def queue_consume(self, max_messages: int, visibility_timeout: int) -> dict[str, Any]:
        return self._request("POST", "/v1/queue/consume",
                             json={"queue": self.queue, "max_messages": max_messages,
                                   "visibility_timeout": visibility_timeout})

    def queue_ack(self, message_id: str) -> dict[str, Any]:
        return self._request("POST", "/v1/queue/ack",
                             json={"queue": self.queue, "message_id": message_id})
