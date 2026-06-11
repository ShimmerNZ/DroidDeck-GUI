#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WALL-E Control System - Asynchronous HTTP Client

Qt-native HTTP requests that never block the GUI thread. Replaces direct
`requests` calls from slot handlers, where an unreachable camera proxy or
backend would freeze the entire UI for the full timeout.

Usage:

    from core.http_client import get_http_client

    def _on_status(response):
        if response.ok:
            data = response.json
        else:
            self.logger.warning(f"Status check failed: {response.error}")

    get_http_client().get("http://10.42.0.1:8081/stream/status", _on_status,
                          timeout_ms=3000)

Callbacks run on the GUI thread (Qt signal delivery), so they can touch
widgets directly. A request whose owner may be destroyed before completion
should pass `owner=self`; the callback is then skipped if the owner has
been deleted.
"""

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

from PyQt6.QtCore import QObject, QUrl, QByteArray
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply

from .logger import get_logger

DEFAULT_TIMEOUT_MS = 5000


@dataclass
class HttpResponse:
    """Result of an asynchronous HTTP request."""
    ok: bool
    status: int = 0
    text: str = ""
    error: str = ""
    json: Optional[Any] = field(default=None)


class HttpClient(QObject):
    """Asynchronous HTTP client wrapping QNetworkAccessManager."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = get_logger("http")
        self._manager = QNetworkAccessManager(self)
        # Keep references to in-flight replies so they are not garbage
        # collected before finishing
        self._active_replies = set()

    # ---- Public request methods ----

    def get(self, url: str, callback: Optional[Callable] = None,
            timeout_ms: int = DEFAULT_TIMEOUT_MS, owner: Optional[QObject] = None):
        """Asynchronous GET. callback(HttpResponse) runs on the GUI thread."""
        request = self._build_request(url, timeout_ms)
        reply = self._manager.get(request)
        self._track(reply, callback, owner)

    def post_json(self, url: str, payload: Dict[str, Any],
                  callback: Optional[Callable] = None,
                  timeout_ms: int = DEFAULT_TIMEOUT_MS, owner: Optional[QObject] = None):
        """Asynchronous POST with a JSON body."""
        request = self._build_request(url, timeout_ms)
        request.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader,
                          "application/json")
        body = QByteArray(json.dumps(payload).encode("utf-8"))
        reply = self._manager.post(request, body)
        self._track(reply, callback, owner)

    def post_form(self, url: str, data: Dict[str, Any],
                  callback: Optional[Callable] = None,
                  timeout_ms: int = DEFAULT_TIMEOUT_MS, owner: Optional[QObject] = None):
        """Asynchronous POST with form-encoded body."""
        request = self._build_request(url, timeout_ms)
        request.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader,
                          "application/x-www-form-urlencoded")
        encoded = "&".join(
            f"{QUrl.toPercentEncoding(str(k)).data().decode()}="
            f"{QUrl.toPercentEncoding(str(v)).data().decode()}"
            for k, v in data.items()
        )
        reply = self._manager.post(request, QByteArray(encoded.encode("utf-8")))
        self._track(reply, callback, owner)

    def post(self, url: str, callback: Optional[Callable] = None,
             timeout_ms: int = DEFAULT_TIMEOUT_MS, owner: Optional[QObject] = None):
        """Asynchronous POST with an empty body (e.g. /stream/start)."""
        request = self._build_request(url, timeout_ms)
        reply = self._manager.post(request, QByteArray())
        self._track(reply, callback, owner)

    # ---- Internals ----

    def _build_request(self, url: str, timeout_ms: int) -> QNetworkRequest:
        request = QNetworkRequest(QUrl(url))
        request.setTransferTimeout(timeout_ms)
        return request

    def _track(self, reply: QNetworkReply, callback: Optional[Callable],
               owner: Optional[QObject]):
        self._active_replies.add(reply)
        reply.finished.connect(lambda: self._on_finished(reply, callback, owner))

    def _on_finished(self, reply: QNetworkReply, callback: Optional[Callable],
                     owner: Optional[QObject]):
        self._active_replies.discard(reply)

        try:
            response = self._build_response(reply)
        finally:
            reply.deleteLater()

        if callback is None:
            return

        # Skip the callback if its owner widget has been destroyed
        if owner is not None:
            try:
                owner.objectName()
            except RuntimeError:
                return

        try:
            callback(response)
        except Exception as e:
            self.logger.error(f"HTTP callback error: {e}")

    def _build_response(self, reply: QNetworkReply) -> HttpResponse:
        status = reply.attribute(
            QNetworkRequest.Attribute.HttpStatusCodeAttribute) or 0

        if reply.error() != QNetworkReply.NetworkError.NoError:
            return HttpResponse(
                ok=False,
                status=int(status),
                error=reply.errorString(),
            )

        raw = bytes(reply.readAll())
        text = raw.decode("utf-8", errors="replace")

        parsed = None
        content_type = reply.header(
            QNetworkRequest.KnownHeaders.ContentTypeHeader) or ""
        if "json" in str(content_type) or text[:1] in ("{", "["):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = None

        return HttpResponse(
            ok=200 <= int(status) < 300,
            status=int(status),
            text=text,
            json=parsed,
        )


# Module-level singleton, created lazily so the QApplication exists first
_http_client: Optional[HttpClient] = None


def get_http_client() -> HttpClient:
    """Return the shared HttpClient instance."""
    global _http_client
    if _http_client is None:
        _http_client = HttpClient()
    return _http_client
