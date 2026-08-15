"""Transport-neutral modem status projections consumed by application services."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ModemStatus:
    bitrate_bps: int = 0
    snr_db: float = 0.0
    sync: bool = False
    direction: str = "rx"
    user_callsign: str = ""
    destination_callsign: str = ""
    client_connected: bool = False
    bytes_transmitted: int = 0
    bytes_received: int = 0
    waterfall_enabled: bool = False
    modem_mode: str = "idle"
    arq_tx_mode: str = ""
    arq_rx_mode: str = ""
    tx_gain_db: float = 0.0
    tx_peak_dbfs: float = -120.0
    radio_frequency_hz: int | None = None
    radio_frequency_age_ms: int | None = None


@dataclass(frozen=True, slots=True)
class SpectrumFrame:
    sample_rate_hz: int
    bins_db: tuple[float, ...]
