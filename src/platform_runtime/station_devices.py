"""Cross-platform discovery of serial ports used for Mercury CAT control."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal
from PySide6.QtSerialPort import QSerialPortInfo


@dataclass(frozen=True, slots=True)
class SerialPort:
    identifier: str
    label: str


class StationDeviceCatalog(QObject):
    serial_ports_loaded = Signal(object)

    def load(self) -> None:
        ports = []
        for info in QSerialPortInfo.availablePorts():
            identifier = info.systemLocation() or info.portName()
            details = [part for part in (info.description(), info.manufacturer()) if part]
            label = f"{info.portName()} — {' · '.join(details)}" if details else info.portName()
            ports.append(SerialPort(identifier, label))
        self.serial_ports_loaded.emit(tuple(ports))
