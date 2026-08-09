"""Cross-platform serial-port discovery for CAT and GPS receivers."""

from __future__ import annotations

from dataclasses import dataclass
import os

from PySide6.QtCore import QObject, Signal
from PySide6.QtMultimedia import QMediaDevices
from PySide6.QtSerialPort import QSerialPortInfo


@dataclass(frozen=True, slots=True)
class SerialPort:
    identifier: str
    label: str


@dataclass(frozen=True, slots=True)
class StationAudioDevice:
    name: str
    identifier: str


class StationDeviceCatalog(QObject):
    serial_ports_loaded = Signal(object)
    audio_inputs_loaded = Signal(object)
    audio_outputs_loaded = Signal(object)

    def load(self) -> None:
        ports = []
        for info in QSerialPortInfo.availablePorts():
            identifier = (
                info.portName()
                if os.name == "nt"
                else info.systemLocation() or info.portName()
            )
            details = [part for part in (info.description(), info.manufacturer()) if part]
            label = f"{info.portName()} — {' · '.join(details)}" if details else info.portName()
            ports.append(SerialPort(identifier, label))
        self.serial_ports_loaded.emit(tuple(ports))
        self.audio_inputs_loaded.emit(self._audio_devices(QMediaDevices.audioInputs()))
        self.audio_outputs_loaded.emit(self._audio_devices(QMediaDevices.audioOutputs()))

    @staticmethod
    def _audio_devices(devices) -> tuple[StationAudioDevice, ...]:
        """Use display names that Mercury can resolve to its native backend IDs."""
        found = []
        seen = set()
        for device in devices:
            name = device.description().strip()
            key = name.casefold()
            if not name or key in seen:
                continue
            seen.add(key)
            found.append(StationAudioDevice(name, name))
        return tuple(found)
