"""System and serial NMEA GPS receiver adapter."""

from __future__ import annotations

from PySide6.QtCore import QIODevice, QObject, Signal
from PySide6.QtPositioning import (
    QGeoPositionInfo,
    QGeoPositionInfoSource,
    QNmeaPositionInfoSource,
)
from PySide6.QtSerialPort import QSerialPort


class GpsReceiver(QObject):
    position_received = Signal(float, float, object)
    state_changed = Signal(str)
    error_received = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._source: QGeoPositionInfoSource | None = None
        self._serial: QSerialPort | None = None

    def start(self, serial_port: str = "") -> None:
        self.stop()
        if serial_port:
            self._start_serial(serial_port)
        else:
            self._start_system()

    def stop(self) -> None:
        if self._source:
            self._source.stopUpdates()
            self._source.deleteLater()
            self._source = None
        if self._serial:
            self._serial.close()
            self._serial.deleteLater()
            self._serial = None
        self.state_changed.emit("stopped")

    def _start_system(self) -> None:
        source = QGeoPositionInfoSource.createDefaultSource(self)
        if source is None:
            self.error_received.emit("No system GPS/location source is available")
            self.state_changed.emit("unavailable")
            return
        self._attach(source)
        source.startUpdates()
        self.state_changed.emit("acquiring-system")

    def _start_serial(self, port_name: str) -> None:
        serial = QSerialPort(self)
        serial.setPortName(port_name)
        serial.setBaudRate(4800)
        if not serial.open(QIODevice.OpenModeFlag.ReadOnly):
            self.error_received.emit(
                f"Cannot open GPS receiver {port_name}: {serial.errorString()}"
            )
            serial.deleteLater()
            self.state_changed.emit("unavailable")
            return
        source = QNmeaPositionInfoSource(
            QNmeaPositionInfoSource.UpdateMode.RealTimeMode, self
        )
        source.setDevice(serial)
        self._serial = serial
        self._attach(source)
        source.startUpdates()
        self.state_changed.emit(f"acquiring-serial:{port_name}")

    def _attach(self, source: QGeoPositionInfoSource) -> None:
        self._source = source
        source.positionUpdated.connect(self._position_updated)
        source.errorOccurred.connect(self._source_error)

    def _position_updated(self, info: QGeoPositionInfo) -> None:
        coordinate = info.coordinate()
        if not coordinate.isValid():
            return
        attribute = QGeoPositionInfo.Attribute.HorizontalAccuracy
        accuracy = info.attribute(attribute) if info.hasAttribute(attribute) else None
        self.position_received.emit(
            coordinate.latitude(), coordinate.longitude(), accuracy
        )
        self.state_changed.emit("fix")

    def _source_error(self, error: QGeoPositionInfoSource.Error) -> None:
        if error == QGeoPositionInfoSource.Error.UpdateTimeoutError:
            self.state_changed.emit("waiting-for-fix")
        elif error != QGeoPositionInfoSource.Error.NoError:
            self.error_received.emit(f"GPS receiver error: {error.name}")
            self.state_changed.emit("error")
