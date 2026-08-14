"""File-transfer use cases layered on Mercury's reliable byte stream."""

from __future__ import annotations

import base64
from dataclasses import dataclass, replace
from datetime import UTC, datetime
import hashlib
import os
from pathlib import Path
import string
from uuid import uuid4

from PySide6.QtCore import QObject, QTimer, Signal

from persistence.chat_repository import ChatRepository


MAX_FILE_SIZE = 100 * 1024 * 1024
CHUNK_SIZE = 4096
ACTIVE_TRANSFER_STATES = {"offered", "transferring", "paused", "verifying"}


@dataclass(frozen=True, slots=True)
class PreparedFile:
    path: Path
    name: str
    thumbnail: bytes = b""
    optimized: bool = False


@dataclass(frozen=True, slots=True)
class FileTransfer:
    id: str
    name: str
    size: int
    checksum: str
    direction: str
    status: str
    transferred: int = 0
    path: str = ""
    thumbnail: bytes = b""
    optimized: bool = False

    @property
    def progress(self) -> int:
        if self.direction == "outgoing" and self.status not in {"received", "duplicate"}:
            return 0
        return 100 if self.size == 0 else min(100, int(self.transferred * 100 / self.size))


class FileTransferService(QObject):
    transfers_changed = Signal(object)
    error_received = Signal(str)
    incoming_offer = Signal(object)
    transfer_completed = Signal(object)

    def __init__(
        self,
        client,
        repository: ChatRepository,
        receive_directory: Path,
        image_processor=None,
        auto_pump: bool = True,
        auto_accept: bool = True,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.client = client
        self.repository = repository
        self.receive_directory = receive_directory
        self.image_processor = image_processor
        self.auto_pump = auto_pump
        self.auto_accept = auto_accept
        self._transfers: dict[str, FileTransfer] = {}
        self._timer = QTimer(self)
        self._timer.setInterval(10)
        self._timer.timeout.connect(self._pump)
        self._outgoing_id: str | None = None
        self._external_busy_check = None
        client.file_event_received.connect(self._on_event)

    def set_external_busy_check(self, callback) -> None:
        self._external_busy_check = callback

    def transfer_busy(self) -> bool:
        """Return whether any file transfer still owns the half-duplex session."""
        return any(
            transfer.status in ACTIVE_TRANSFER_STATES
            for transfer in self._transfers.values()
        )

    def send_file(self, path_value: str) -> None:
        self._begin_send(path_value, prepare_image=True)

    def send_raw_file(self, path_value: str) -> None:
        """Send an application-managed artifact without image transformation."""
        self._begin_send(path_value, prepare_image=False)

    def _begin_send(self, path_value: str, prepare_image: bool) -> None:
        path = Path(path_value)
        try:
            if self._external_busy_check and self._external_busy_check():
                raise ValueError("File transfer is unavailable while a voice message is pending")
            if any(
                transfer.direction == "outgoing"
                and transfer.status in ACTIVE_TRANSFER_STATES
                for transfer in self._transfers.values()
            ):
                raise ValueError("Finish the current outgoing file before sending another")
            if not path.is_file():
                raise ValueError("Select a regular file")
            prepared = (
                self.image_processor.prepare(path)
                if self.image_processor and prepare_image
                else PreparedFile(path, path.name)
            )
            path = prepared.path
            size = path.stat().st_size
            if size > MAX_FILE_SIZE:
                raise ValueError("Files are limited to 100 MiB")
            transfer_id = str(uuid4())
            transfer = FileTransfer(
                transfer_id, prepared.name, size, self._sha256(path), "outgoing",
                "offered", path=str(path), thumbnail=prepared.thumbnail,
                optimized=prepared.optimized,
            )
            self._transfers[transfer_id] = transfer
            self._outgoing_id = transfer_id
            self._emit()
            self._send(
                "file_offer", transfer_id, name=prepared.name, size=size,
                sha256=transfer.checksum,
                thumbnail=base64.b64encode(prepared.thumbnail).decode("ascii"),
                optimized=prepared.optimized,
            )
        except (OSError, ValueError, RuntimeError) as error:
            self.error_received.emit(str(error))

    def stop(self) -> None:
        self._timer.stop()
        if self.image_processor:
            self.image_processor.close()

    def accept(self, transfer_id: str) -> None:
        transfer = self._transfers.get(transfer_id)
        if not transfer or transfer.direction != "incoming" or transfer.status != "offered":
            return
        self.receive_directory.mkdir(parents=True, exist_ok=True)
        partial = self.receive_directory / f".{transfer_id}.part"
        partial.write_bytes(b"")
        self._update(transfer_id, status="transferring", path=str(partial))
        self._send("file_accept", transfer_id, offset=0)

    def reject(self, transfer_id: str) -> None:
        transfer = self._transfers.get(transfer_id)
        if not transfer or transfer.direction != "incoming" or transfer.status != "offered":
            return
        self._update(transfer_id, status="rejected")
        self._send("file_result", transfer_id, result="failed", reason="operator-rejected")

    def pause(self, transfer_id: str) -> None:
        transfer = self._transfers.get(transfer_id)
        if not transfer or transfer.status not in {"transferring", "offered"}:
            return
        self._update(transfer_id, status="paused")
        self._send_safely("file_pause", transfer_id)
        if transfer_id == self._outgoing_id:
            self._timer.stop()

    def resume(self, transfer_id: str) -> None:
        transfer = self._transfers.get(transfer_id)
        if not transfer or transfer.status != "paused":
            return
        self._update(transfer_id, status="transferring")
        self._send_safely("file_resume", transfer_id, offset=transfer.transferred)
        if transfer.direction == "outgoing":
            self._outgoing_id = transfer_id
            if self.auto_pump:
                self._timer.start()

    def _on_event(self, envelope) -> None:
        values = envelope.values or {}
        handlers = {
            "file_offer": self._receive_offer,
            "file_accept": self._receive_accept,
            "file_chunk": self._receive_chunk,
            "file_pause": self._receive_pause,
            "file_resume": self._receive_resume,
            "file_complete": self._receive_complete,
            "file_result": self._receive_result,
        }
        try:
            handlers[envelope.kind](envelope.message_id, values)
        except (KeyError, OSError, TypeError, ValueError) as error:
            self.error_received.emit(f"Invalid file transfer: {error}")

    def _receive_offer(self, transfer_id: str, values: dict[str, object]) -> None:
        if self._external_busy_check and self._external_busy_check():
            self._send("file_result", transfer_id, result="failed", reason="voice-busy")
            return
        name = Path(str(values["name"])).name
        size = int(values["size"])
        checksum = str(values["sha256"]).lower()
        thumbnail_encoded = str(values.get("thumbnail", ""))
        if len(thumbnail_encoded) > 6144:
            raise ValueError("thumbnail is too large")
        thumbnail = base64.b64decode(thumbnail_encoded, validate=True)
        if (
            not name
            or size < 0
            or size > MAX_FILE_SIZE
            or len(checksum) != 64
            or any(character not in string.hexdigits for character in checksum)
        ):
            raise ValueError("invalid file offer")
        duplicate = self._verified_duplicate(checksum)
        if duplicate:
            self._transfers[transfer_id] = FileTransfer(
                transfer_id, name, size, checksum, "incoming", "duplicate",
                size, duplicate, thumbnail=thumbnail,
                optimized=bool(values.get("optimized", False)),
            )
            self._emit()
            self.transfer_completed.emit(self._transfers[transfer_id])
            self._send("file_result", transfer_id, result="duplicate", path=Path(duplicate).name)
            return
        self._transfers[transfer_id] = FileTransfer(
            transfer_id, name, size, checksum, "incoming", "offered",
            thumbnail=thumbnail,
            optimized=bool(values.get("optimized", False)),
        )
        self._emit()
        if self.auto_accept:
            self.accept(transfer_id)
        else:
            self.incoming_offer.emit(self._transfers[transfer_id])

    def _receive_accept(self, transfer_id: str, values: dict[str, object]) -> None:
        transfer = self._transfers[transfer_id]
        offset = max(0, min(int(values.get("offset", 0)), transfer.size))
        self._update(transfer_id, status="transferring", transferred=offset)
        self._outgoing_id = transfer_id
        if self.auto_pump:
            self._timer.start()

    def _receive_chunk(self, transfer_id: str, values: dict[str, object]) -> None:
        transfer = self._transfers[transfer_id]
        if transfer.direction != "incoming" or transfer.status == "paused":
            return
        offset = int(values["offset"])
        chunk = base64.b64decode(str(values["data"]), validate=True)
        if offset != transfer.transferred or len(chunk) > CHUNK_SIZE:
            raise ValueError("unexpected file chunk offset or size")
        with Path(transfer.path).open("ab") as stream:
            stream.write(chunk)
        self._update(transfer_id, transferred=offset + len(chunk))

    def _receive_pause(self, transfer_id: str, _values: dict[str, object]) -> None:
        if transfer_id in self._transfers:
            self._update(transfer_id, status="paused")
            if transfer_id == self._outgoing_id:
                self._timer.stop()

    def _receive_resume(self, transfer_id: str, values: dict[str, object]) -> None:
        transfer = self._transfers[transfer_id]
        offset = int(values.get("offset", transfer.transferred))
        if transfer.direction == "outgoing":
            self._update(transfer_id, status="transferring", transferred=offset)
            self._outgoing_id = transfer_id
            if self.auto_pump:
                self._timer.start()
        else:
            self._update(transfer_id, status="transferring")

    def _receive_complete(self, transfer_id: str, _values: dict[str, object]) -> None:
        transfer = self._transfers[transfer_id]
        partial = Path(transfer.path)
        if transfer.transferred != transfer.size or self._sha256(partial) != transfer.checksum:
            self._update(transfer_id, status="checksum-failed")
            self._send("file_result", transfer_id, result="checksum-failed")
            return
        destination = self._unique_destination(transfer.name)
        os.replace(partial, destination)
        self.repository.set_setting(
            f"file.sha256.{transfer.checksum}", str(destination), self._now()
        )
        self._update(transfer_id, status="received", path=str(destination))
        self.transfer_completed.emit(self._transfers[transfer_id])
        self._send("file_result", transfer_id, result="received")

    def _receive_result(self, transfer_id: str, values: dict[str, object]) -> None:
        result = str(values.get("result", "failed"))
        if result not in {"received", "duplicate", "checksum-failed", "failed"}:
            result = "failed"
        transfer = self._transfers[transfer_id]
        transferred = transfer.size if result in {"received", "duplicate"} else transfer.transferred
        self._update(transfer_id, status=result, transferred=transferred)
        if result in {"received", "duplicate"}:
            self.transfer_completed.emit(self._transfers[transfer_id])

    def _pump(self) -> None:
        transfer = self._transfers.get(self._outgoing_id or "")
        if not transfer or transfer.status != "transferring":
            self._timer.stop()
            return
        if not self.client.file_write_ready():
            return
        try:
            with Path(transfer.path).open("rb") as stream:
                stream.seek(transfer.transferred)
                chunk = stream.read(CHUNK_SIZE)
            if not chunk:
                self._timer.stop()
                self._update(transfer.id, status="verifying")
                self._send("file_complete", transfer.id)
                return
            self._send(
                "file_chunk", transfer.id, offset=transfer.transferred,
                data=base64.b64encode(chunk).decode("ascii"),
            )
            self._update(transfer.id, transferred=transfer.transferred + len(chunk))
        except (OSError, RuntimeError) as error:
            self._timer.stop()
            self._update(transfer.id, status="failed")
            self.error_received.emit(str(error))

    def _verified_duplicate(self, checksum: str) -> str | None:
        value = self.repository.get_setting(f"file.sha256.{checksum}")
        if not value:
            return None
        path = Path(value)
        return str(path) if path.is_file() and self._sha256(path) == checksum else None

    def _unique_destination(self, name: str) -> Path:
        candidate = self.receive_directory / name
        counter = 1
        while candidate.exists():
            candidate = self.receive_directory / f"{Path(name).stem} ({counter}){Path(name).suffix}"
            counter += 1
        return candidate

    def _send(self, kind: str, transfer_id: str, **values: object) -> None:
        self.client.send_file_event(kind, transfer_id, self._now(), **values)

    def _send_safely(self, kind: str, transfer_id: str, **values: object) -> None:
        try:
            self._send(kind, transfer_id, **values)
        except RuntimeError as error:
            self.error_received.emit(str(error))

    def _update(self, transfer_id: str, **changes: object) -> None:
        self._transfers[transfer_id] = replace(self._transfers[transfer_id], **changes)
        self._emit()

    def _emit(self) -> None:
        self.transfers_changed.emit(list(self._transfers.values()))

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()
