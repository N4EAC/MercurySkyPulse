"""Application entry point and dependency composition root."""

from __future__ import annotations

import os
from pathlib import Path
import sys

from PySide6.QtCore import QCoreApplication, QStandardPaths
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from .main_window import MainWindow
from .plugin_bootstrap import create_builtin_registry
from .themes import Appearance, apply_appearance
from application.chat_service import ChatService
from application.file_transfer import FileTransferService
from application.location import LocationService
from application.beacon import BeaconService
from application.ping import PingService
from application.bbs import BbsService
from application.web_dashboard import WebDashboardSnapshot
from application.licensing import LicenseStatus
from persistence.chat_repository import ChatRepository
from platform_runtime.image_processor import ImageProcessor
from platform_runtime.gps_receiver import GpsReceiver
from platform_runtime.location_exporter import LocationExporter
from platform_runtime.local_web import LocalWebServer
from platform_runtime.licensing import LicenseDeployment
from application_protocol import ApplicationMessagingClient
from transport.mercury.tnc import MercuryTncTransport
from application_protocol.beacon import BeaconProtocolClient
from transport.mercury.beacon import MercuryBroadcastTransport


def create_application(argv: list[str] | None = None) -> QApplication:
    """Create the Qt application without starting its event loop."""
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")

    existing = QApplication.instance()
    if existing is not None:
        return existing

    QCoreApplication.setOrganizationName("MercurySkyPulse")
    QCoreApplication.setApplicationName("MercurySkyPulse")
    QCoreApplication.setApplicationVersion("0.1.0")

    app = QApplication(argv if argv is not None else sys.argv)

    font = QFont(app.font())
    font.setPointSizeF(max(font.pointSizeF(), 10.0))
    app.setFont(font)
    apply_appearance(app, Appearance.system())
    return app


def main() -> int:
    app = create_application()
    data_directory = Path(
        QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    )
    repository = ChatRepository(data_directory / "chat-history.sqlite3")
    mercury_transport = MercuryTncTransport()
    client = ApplicationMessagingClient(mercury_transport)
    chat_service = ChatService(client, repository)
    downloads = Path(
        QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.DownloadLocation
        )
    ) / "MercurySkyPulse"
    file_transfer_service = FileTransferService(
        client, repository, downloads, image_processor=ImageProcessor()
    )
    location_service = LocationService(
        client, repository, GpsReceiver(), exporter=LocationExporter()
    )
    capabilities = (
        "bbs", "beacon", "chat", "file-transfer", "gps-history", "image", "location"
    )
    mercury_broadcast = MercuryBroadcastTransport()
    beacon_service = BeaconService(
        BeaconProtocolClient(mercury_broadcast),
        repository,
        QCoreApplication.applicationVersion(),
        capabilities,
    )
    ping_service = PingService(client)
    bbs_service = BbsService(
        client, repository, file_transfer_service, data_directory / "bbs-files"
    )
    web_snapshot = WebDashboardSnapshot()
    license_state = LicenseDeployment(data_directory).load()
    web_snapshot.update_license(license_state)
    if license_state.status not in {LicenseStatus.COMMUNITY, LicenseStatus.VALID}:
        web_snapshot.append_log(f"License {license_state.status}: {license_state.reason}")
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
        license_features=license_state.features,
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
        bbs_service=bbs_service,
        web_snapshot=web_snapshot,
        web_server=web_server,
        license_state=license_state,
        plugin_registry=plugins,
    )
    window.show()
    return app.exec()
