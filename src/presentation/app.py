"""Application entry point and dependency composition root."""

from __future__ import annotations

import os
from pathlib import Path
import sys

from PySide6.QtCore import QCoreApplication, QStandardPaths, QTimer
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication

from .main_window import MainWindow
from .plugin_bootstrap import create_builtin_registry
from .themes import Appearance, apply_appearance
from application.chat_service import ChatService
from application.file_transfer import FileTransferService
from application.location import LocationService
from application.beacon import BeaconService, DEFAULT_BEACON_CAPABILITIES
from application.ping import PingService
from application.bbs import BbsService
from application.web_dashboard import WebDashboardSnapshot
from application.endpoints import MercuryEndpointProfile, MercuryRunMode
from application.radio import RadioStationService, TxLevelTestService
from application.psk_reporter import PskReporterService
from application.weather import WeatherService
from persistence.chat_repository import ChatRepository
from platform_runtime.image_processor import ImageProcessor
from platform_runtime.gps_receiver import GpsReceiver
from platform_runtime.location_exporter import LocationExporter
from platform_runtime.diagnostic_log import DiagnosticLog
from platform_runtime.local_web import LocalWebServer
from application_protocol import ApplicationMessagingClient
from transport.mercury.tnc import MercuryTncTransport
from application_protocol.beacon import BeaconProtocolClient
from transport.mercury.beacon import MercuryBroadcastTransport
from transport.mercury.telemetry import MercuryTelemetryClient
from platform_runtime import MercuryProcessConfig, MercuryProcessSupervisor
from platform_runtime.station_devices import StationDeviceCatalog
from platform_runtime.hamlib_catalog import MercuryHamlibCatalog
from platform_runtime.macos_application import (
    set_macos_application_menu_name,
    set_macos_program_name,
)
from platform_runtime.psk_reporter import PskReporterUploader
from platform_runtime.weather_provider import WttrWeatherProvider
from platform_runtime.builtin_speech import BuiltinSpeechEngine
from .release import APPLICATION_VERSION


def create_application(argv: list[str] | None = None) -> QApplication:
    """Create the Qt application without starting its event loop."""
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    set_macos_program_name("Mercury SkyPulse")

    QCoreApplication.setOrganizationName("MercurySkyPulse")
    QCoreApplication.setApplicationName("MercurySkyPulse")
    QCoreApplication.setApplicationVersion(APPLICATION_VERSION)

    existing = QApplication.instance()
    if existing is not None:
        existing.setApplicationDisplayName("Mercury SkyPulse")
        _set_application_icon(existing)
        return existing

    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationDisplayName("Mercury SkyPulse")
    _set_application_icon(app)

    font = QFont(app.font())
    font.setPointSizeF(max(font.pointSizeF(), 9.0))
    app.setFont(font)
    apply_appearance(app, Appearance.system())
    return app


def _set_application_icon(app: QApplication) -> None:
    candidates = [
        Path(__file__).resolve().parent / "resources" / "mercuryskypulse.png",
    ]
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        candidates.append(
            Path(bundle_root) / "assets" / "icons" / "mercuryskypulse.png"
        )
    for candidate in candidates:
        if candidate.is_file():
            app.setWindowIcon(QIcon(str(candidate)))
            return


def main() -> int:
    app = create_application()
    endpoint_profile = MercuryEndpointProfile.default()
    data_directory = Path(
        QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    )
    diagnostic_log = DiagnosticLog(data_directory / "logs" / "mercuryskypulse.log")
    diagnostic_log.start_session(QCoreApplication.applicationVersion())
    diagnostic_log.install_exception_hooks()
    repository = ChatRepository(data_directory / "chat-history.sqlite3")
    try:
        saved_radio_model = int(repository.get_setting("radio.model_id") or "")
        if saved_radio_model <= 0:
            saved_radio_model = None
    except ValueError:
        saved_radio_model = None
    saved_radio_address = repository.get_setting("radio.device") or None
    saved_input_device = repository.get_setting("radio.input_device") or None
    saved_output_device = repository.get_setting("radio.output_device") or None
    try:
        saved_radio_speed = int(repository.get_setting("radio.serial_speed") or "0")
    except ValueError:
        saved_radio_speed = 0
    mercury_transport = MercuryTncTransport(
        host=endpoint_profile.control.host,
        control_port=endpoint_profile.control.port,
        data_host=endpoint_profile.data.host,
        data_port=endpoint_profile.data.port,
        reconnect_delay_ms=endpoint_profile.reconnect.socket_delay_ms,
        maximum_control_line_bytes=endpoint_profile.limits.control_line_bytes,
    )
    client = ApplicationMessagingClient(mercury_transport)
    chat_service = ChatService(client, repository)
    downloads = Path(
        QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.DownloadLocation
        )
    ) / "MercurySkyPulse"
    file_transfer_service = FileTransferService(
        client, repository, downloads, image_processor=ImageProcessor(), auto_accept=False
    )
    location_service = LocationService(
        client, repository, GpsReceiver(), exporter=LocationExporter()
    )
    capabilities = DEFAULT_BEACON_CAPABILITIES
    mercury_broadcast = MercuryBroadcastTransport(
        host=endpoint_profile.broadcast.host,
        port=endpoint_profile.broadcast.port,
        reconnect_delay_ms=endpoint_profile.reconnect.socket_delay_ms,
        maximum_frame_bytes=endpoint_profile.limits.kiss_frame_bytes,
        maximum_buffer_bytes=endpoint_profile.limits.kiss_buffer_bytes,
    )
    mercury_supervisor = MercuryProcessSupervisor(MercuryProcessConfig(
        managed=endpoint_profile.mode is MercuryRunMode.MANAGED_LOCAL,
        executable=endpoint_profile.executable,
        ui_port=endpoint_profile.telemetry.port,
        radio_model=saved_radio_model,
        radio_address=saved_radio_address if saved_radio_model is not None else None,
        radio_serial_speed=saved_radio_speed,
        input_device=saved_input_device,
        output_device=saved_output_device,
        config_file=data_directory / "mercury-skypulse.ini",
    ))
    mercury_telemetry = MercuryTelemetryClient(
        endpoint_profile.telemetry.url,
        reconnect_initial_ms=endpoint_profile.reconnect.initial_delay_ms,
        reconnect_maximum_ms=endpoint_profile.reconnect.maximum_delay_ms,
        reconnect_multiplier=endpoint_profile.reconnect.multiplier,
    )
    radio_service = RadioStationService(
        client,
        repository,
        MercuryHamlibCatalog(endpoint_profile.executable),
        mercury_supervisor,
        StationDeviceCatalog(),
        endpoint_profile.mode is MercuryRunMode.MANAGED_LOCAL,
    )
    beacon_service = BeaconService(
        BeaconProtocolClient(mercury_broadcast),
        repository,
        QCoreApplication.applicationVersion(),
        capabilities,
    )
    tx_level_service = TxLevelTestService(
        beacon_service, mercury_telemetry, client
    )
    psk_reporter_service = PskReporterService(
        beacon_service, mercury_telemetry, repository, PskReporterUploader(),
        QCoreApplication.applicationVersion(),
    )
    weather_service = WeatherService(repository, WttrWeatherProvider())
    location_service.current_changed.connect(weather_service.update_location)
    beacon_service.config_changed.connect(weather_service.update_grid)
    weather_service.update_grid(beacon_service.config)
    if location_service.current is not None:
        weather_service.update_location(location_service.current)
    ping_service = PingService(client)
    bbs_service = BbsService(
        client, repository, file_transfer_service, data_directory / "bbs-files"
    )
    web_snapshot = WebDashboardSnapshot()
    try:
        web_port = int(os.environ.get("MERCURYSKYPULSE_WEB_PORT", "8765"))
    except ValueError:
        web_port = 8765
        web_snapshot.append_log("Invalid local web port setting; using 8765")
    try:
        web_server = LocalWebServer(web_snapshot, web_port)
        web_server.start()
    except (OSError, ValueError) as error:
        web_snapshot.append_log(f"Local web interface unavailable: {error}")
        web_server = LocalWebServer(web_snapshot, 0)
    plugins = create_builtin_registry(
        event_sink=web_snapshot.append_log,
        mercury_transport=mercury_transport,
        beacon_transport=mercury_broadcast,
        location_service=location_service,
        bbs_service=bbs_service,
        web_server=web_server,
        web_snapshot=web_snapshot,
    )
    web_snapshot.update_plugins(plugins.snapshot())
    window = MainWindow(
        app,
        chat_service=chat_service,
        file_transfer_service=file_transfer_service,
        location_service=location_service,
        beacon_service=beacon_service,
        ping_service=ping_service,
        radio_service=radio_service,
        tx_level_service=tx_level_service,
        psk_reporter_service=psk_reporter_service,
        weather_service=weather_service,
        bbs_service=bbs_service,
        web_snapshot=web_snapshot,
        web_server=web_server,
        plugin_registry=plugins,
        endpoint_profile=endpoint_profile,
        supervisor=mercury_supervisor,
        telemetry=mercury_telemetry,
        diagnostic_log_path=diagnostic_log.path,
    )
    window.activity_panel.log_added.connect(diagnostic_log.write_activity)
    window.activity_panel.append_log(f"Persistent diagnostic log: {diagnostic_log.path}")
    speech_engine = BuiltinSpeechEngine(data_directory / "speech-cache", app)
    speech_engine.error_received.connect(window.activity_panel.append_log)
    app._msp_speech_engine = speech_engine
    app.aboutToQuit.connect(diagnostic_log.close)
    window.show()
    set_macos_application_menu_name("Mercury SkyPulse")
    QTimer.singleShot(
        0, lambda: set_macos_application_menu_name("Mercury SkyPulse")
    )
    def announce_startup() -> None:
        if speech_engine.speak("Mercury Sky Pulse"):
            window.activity_panel.append_log(
                "Local speech announcement requested: Mercury Sky Pulse"
            )

    QTimer.singleShot(750, announce_startup)
    return app.exec()
