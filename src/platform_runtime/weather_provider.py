"""Bounded HTTPS client for operator-requested wttr.in observations."""

from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest


MAX_WEATHER_BYTES = 128 * 1024
WEATHER_TIMEOUT_MS = 10_000


class WttrWeatherProvider(QObject):
    received = Signal(bytes)
    error_received = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.manager = QNetworkAccessManager(self)
        self._reply: QNetworkReply | None = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._timeout)

    def fetch(self, latitude: float, longitude: float) -> None:
        if self._reply is not None:
            self._reply.abort()
            self._reply.deleteLater()
        url = QUrl(f"https://wttr.in/{latitude:.6f},{longitude:.6f}?format=j1")
        request = QNetworkRequest(url)
        request.setRawHeader(b"User-Agent", b"MercurySkyPulse/0.1 weather")
        request.setRawHeader(b"Accept", b"application/json")
        self._reply = self.manager.get(request)
        self._reply.finished.connect(self._finished)
        self._timer.start(WEATHER_TIMEOUT_MS)

    def _timeout(self) -> None:
        if self._reply is not None:
            self._reply.abort()
            self.error_received.emit("Weather request timed out")

    def _finished(self) -> None:
        reply = self._reply
        self._reply = None
        self._timer.stop()
        if reply is None:
            return
        if reply.error() != QNetworkReply.NetworkError.NoError:
            if reply.error() != QNetworkReply.NetworkError.OperationCanceledError:
                self.error_received.emit(f"Weather request failed: {reply.errorString()}")
            reply.deleteLater()
            return
        data = bytes(reply.readAll())
        reply.deleteLater()
        if not data or len(data) > MAX_WEATHER_BYTES:
            self.error_received.emit("Weather response was empty or too large")
            return
        self.received.emit(data)
