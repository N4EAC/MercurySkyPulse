"""Main dockable desktop window."""

from __future__ import annotations

from pathlib import Path
from PySide6.QtCore import Qt, QSize, QSettings, QTimer, QUrl
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QDesktopServices, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QDockWidget,
    QLabel,
    QMainWindow,
    QMessageBox,
    QStyle,
    QTabWidget,
    QToolBar,
)

from application.chat_service import ChatService
from application.file_transfer import FileTransferService
from application.location import LocationService
from application.beacon import BeaconService
from application.ping import PingService
from application.radio import RadioStationService
from application.bbs import BbsService
from application.web_dashboard import WebDashboardSnapshot
from application.licensing import LicenseState, community_state
from application.plugins import PluginRegistry
from application.endpoints import MercuryEndpointProfile
from platform_runtime.local_web import LocalWebServer
from .bbs_page import BbsPage
from .beacon_page import BeaconPage
from .chat_page import ChatPage
from .ping_page import PingPage
from .setup_window import SetupWindow
from .panels import (
    ActivityPanel,
    Dashboard,
    FrequencyPanel,
    create_navigation_panel,
)
from .themes import Appearance, PlatformPreset, Theme, apply_appearance
from platform_runtime import MercuryProcessConfig, MercuryProcessSupervisor
from transport.mercury.telemetry import MercuryTelemetryClient


class MainWindow(QMainWindow):
    """Presentation-only shell with real docking and appearance controls."""

    def __init__(
        self,
        app: QApplication,
        chat_service: ChatService | None = None,
        file_transfer_service: FileTransferService | None = None,
        location_service: LocationService | None = None,
        beacon_service: BeaconService | None = None,
        ping_service: PingService | None = None,
        radio_service: RadioStationService | None = None,
        tx_level_service=None,
        psk_reporter_service=None,
        bbs_service: BbsService | None = None,
        web_snapshot: WebDashboardSnapshot | None = None,
        web_server: LocalWebServer | None = None,
        license_state: LicenseState | None = None,
        plugin_registry: PluginRegistry | None = None,
        endpoint_profile: MercuryEndpointProfile | None = None,
        supervisor: MercuryProcessSupervisor | None = None,
        telemetry: MercuryTelemetryClient | None = None,
        diagnostic_log_path: Path | None = None,
        auto_start: bool = True,
    ) -> None:
        super().__init__()
        self._app = app
        self._settings = QSettings()
        self._appearance = self._load_appearance()
        apply_appearance(self._app, self._appearance)
        self._docks: dict[str, QDockWidget] = {}
        self.dashboard = Dashboard()
        self.chat_page = ChatPage()
        self.beacon_service = beacon_service
        self.beacon_page = BeaconPage(
            beacon_service.capabilities if beacon_service else ()
        )
        self.ping_service = ping_service
        self.ping_page = PingPage()
        self.radio_service = radio_service
        self.tx_level_service = tx_level_service
        self.psk_reporter_service = psk_reporter_service
        self.bbs_service = bbs_service
        self.bbs_page = BbsPage()
        self.web_snapshot = web_snapshot
        self.web_server = web_server
        self.license_state = license_state or community_state()
        self.plugin_registry = plugin_registry
        self.chat_service = chat_service
        self.file_transfer_service = file_transfer_service
        self.location_service = location_service
        self.activity_panel = ActivityPanel()
        self.frequency_panel = FrequencyPanel()
        self.endpoint_profile = endpoint_profile or MercuryEndpointProfile.default()
        self.supervisor = supervisor or MercuryProcessSupervisor(
            MercuryProcessConfig(), self
        )
        self.telemetry = telemetry or MercuryTelemetryClient(parent=self)
        self.diagnostic_log_path = diagnostic_log_path
        self._transfer_diagnostics: dict[str, tuple] = {}
        self.setup_window = (
            SetupWindow(
                radio_service, beacon_service, location_service,
                tx_level_service, psk_reporter_service, self,
            )
            if radio_service and beacon_service and location_service else None
        )
        if self.supervisor.parent() is None:
            self.supervisor.setParent(self)
        if self.telemetry.parent() is None:
            self.telemetry.setParent(self)

        self.setObjectName("MercurySkyPulseMainWindow")
        self.setWindowTitle("MercurySkyPulse")
        self.setMinimumSize(860, 600)
        self.resize(1280, 820)
        self.setDockOptions(
            QMainWindow.DockOption.AnimatedDocks
            | QMainWindow.DockOption.AllowNestedDocks
            | QMainWindow.DockOption.AllowTabbedDocks
            | QMainWindow.DockOption.GroupedDragging
        )
        self.tabs = QTabWidget()
        self.tabs.setMovable(True)
        self.tabs.addTab(self.dashboard, "Overview")
        self.tabs.addTab(self.chat_page, "Chat")
        self.tabs.addTab(self.beacon_page, "Beacon")
        self.tabs.addTab(self.ping_page, "Ping")
        self.tabs.addTab(self.bbs_page, "BBS")
        self._restore_tab_order()
        self.setCentralWidget(self.tabs)

        self._create_docks()
        self._create_toolbar()
        self._create_status_bar()
        self._create_menus()
        self._connect_mercury_services()
        self._connect_chat_service()
        self._connect_beacon_service()
        self._connect_ping_service()
        if self.radio_service:
            self.radio_service.error_received.connect(
                lambda error: self.activity_panel.append_log(f"Radio error: {error}")
            )
        if self.location_service:
            self.location_service.error_received.connect(
                lambda error: self.activity_panel.append_log(f"Location error: {error}")
            )
        self._connect_bbs_service()
        self._connect_web_snapshot()
        if not self.restoreGeometry(self._settings.value("main/geometry", b"")):
            self.resize(1280, 820)
        if not self.restoreState(self._settings.value("main/state", b""), 1):
            self._reset_layout(clear_saved=False)
        if auto_start:
            QTimer.singleShot(0, self._start_mercury)

    def _make_dock(
        self,
        key: str,
        title: str,
        widget,
        area: Qt.DockWidgetArea,
        minimum_width: int = 220,
    ) -> QDockWidget:
        dock = QDockWidget(title, self)
        dock.setObjectName(f"{key}Dock")
        dock.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable
            | QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        widget.setMinimumWidth(minimum_width)
        dock.setWidget(widget)
        self.addDockWidget(area, dock)
        self._docks[key] = dock
        return dock

    def _create_docks(self) -> None:
        self.navigation_panel = create_navigation_panel()
        self.navigation_panel.destination_requested.connect(
            self._navigate_workspace
        )
        self._make_dock(
            "navigation",
            "Navigator",
            self.navigation_panel,
            Qt.DockWidgetArea.LeftDockWidgetArea,
            190,
        )
        activity = self._make_dock(
            "activity",
            "Activity",
            self.activity_panel,
            Qt.DockWidgetArea.BottomDockWidgetArea,
            300,
        )
        activity.setMinimumHeight(140)
        frequency = self._make_dock(
            "frequency",
            "Radio Frequency",
            self.frequency_panel,
            Qt.DockWidgetArea.RightDockWidgetArea,
            220,
        )
        frequency.setMinimumHeight(150)

    def _navigate_workspace(self, destination: str) -> None:
        key = destination.casefold()
        if key in {"overview", "signal"}:
            self.tabs.setCurrentWidget(self.dashboard)
            QTimer.singleShot(0, lambda: self.dashboard.show_section(key))
        elif key == "activity":
            self._docks["activity"].show()
            self._docks["activity"].raise_()
            self.activity_panel.output.setFocus()
        elif key == "diagnostics":
            self._docks["activity"].show()
            self._docks["activity"].raise_()
            self.activity_panel.output.setFocus()
            self.statusBar().showMessage("Activity diagnostics shown", 2500)

    def _create_toolbar(self) -> None:
        toolbar = QToolBar("Main", self)
        toolbar.setObjectName("MainToolBar")
        toolbar.setMovable(True)
        toolbar.setIconSize(QSize(18, 18))
        self.addToolBar(toolbar)

        connect_action = QAction(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DialogApplyButton),
            "Restart Mercury",
            self,
        )
        connect_action.setToolTip("Restart the supervised Mercury process")
        connect_action.triggered.connect(self._restart_mercury)
        toolbar.addAction(connect_action)
        toolbar.addSeparator()

        for key in ("navigation", "frequency", "activity"):
            toolbar.addAction(self._docks[key].toggleViewAction())
        self._toolbar = toolbar

    def _create_status_bar(self) -> None:
        self.statusBar().showMessage("Starting Mercury")
        self._telemetry_status = QLabel("Telemetry: disconnected")
        self._telemetry_status.setObjectName("Muted")
        self._engine_status = QLabel("Mercury: starting")
        self._engine_status.setObjectName("StatusPill")
        self.statusBar().addPermanentWidget(self._telemetry_status)
        self.statusBar().addPermanentWidget(self._engine_status)
        self._license_status = QLabel(f"Edition: {self.license_state.edition.title()}")
        self._license_status.setObjectName("Muted")
        self.statusBar().addPermanentWidget(self._license_status)

    def _create_menus(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        new_window = QAction("New Window", self)
        new_window.setShortcut(QKeySequence.StandardKey.New)
        new_window.setEnabled(False)
        new_window.setToolTip("Reserved for a future application workflow")
        file_menu.addAction(new_window)
        file_menu.addSeparator()
        exit_action = QAction("E&xit", self)
        exit_action.setShortcut(QKeySequence.StandardKey.Quit)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        edit_menu = self.menuBar().addMenu("&Edit")
        preferences = QAction("Setup…", self)
        preferences.setShortcut(QKeySequence.StandardKey.Preferences)
        preferences.setEnabled(self.setup_window is not None)
        preferences.triggered.connect(self._show_setup)
        edit_menu.addAction(preferences)

        view_menu = self.menuBar().addMenu("&View")
        view_menu.addAction(self._toolbar.toggleViewAction())
        view_menu.addSeparator()
        panels_menu = view_menu.addMenu("Panels")
        for dock in self._docks.values():
            panels_menu.addAction(dock.toggleViewAction())

        appearance_menu = self.menuBar().addMenu("&Appearance")
        self._add_theme_menu(appearance_menu)
        self._add_platform_menu(appearance_menu)
        self._add_scale_menu(appearance_menu)

        window_menu = self.menuBar().addMenu("&Window")
        reset = QAction("Reset Panel Layout", self)
        reset.setShortcut("Ctrl+Shift+0")
        reset.triggered.connect(self._reset_layout)
        window_menu.addAction(reset)
        window_menu.addSeparator()
        for dock in self._docks.values():
            window_menu.addAction(dock.toggleViewAction())

        help_menu = self.menuBar().addMenu("&Help")
        about = QAction("About MercurySkyPulse", self)
        about.triggered.connect(self._show_about)
        help_menu.addAction(about)
        licensing = QAction("License Information", self)
        licensing.triggered.connect(self._show_license)
        help_menu.addAction(licensing)
        plugins = QAction("Plugin Information", self)
        plugins.triggered.connect(self._show_plugins)
        help_menu.addAction(plugins)

        mercury_menu = self.menuBar().addMenu("&Mercury")
        restart = QAction("Restart Mercury", self)
        restart.setShortcut("Ctrl+Shift+R")
        restart.triggered.connect(self._restart_mercury)
        mercury_menu.addAction(restart)
        stop = QAction("Stop Mercury", self)
        stop.triggered.connect(self._stop_mercury)
        mercury_menu.addAction(stop)

        if self.web_server and self.web_server.url:
            mercury_menu.addSeparator()
            web = QAction("Open Local Web Interface", self)
            web.triggered.connect(
                lambda: QDesktopServices.openUrl(QUrl(self.web_server.url or ""))
            )
            mercury_menu.addAction(web)
        if self.diagnostic_log_path:
            mercury_menu.addSeparator()
            diagnostics = QAction("Open Diagnostic Log Folder", self)
            diagnostics.triggered.connect(
                lambda: QDesktopServices.openUrl(
                    QUrl.fromLocalFile(str(self.diagnostic_log_path.parent))
                )
            )
            mercury_menu.addAction(diagnostics)

    def _add_theme_menu(self, parent_menu) -> None:
        menu = parent_menu.addMenu("Theme")
        group = QActionGroup(self)
        group.setExclusive(True)
        for label, theme in (
            ("System", Theme.SYSTEM),
            ("Light", Theme.LIGHT),
            ("Dark", Theme.DARK),
        ):
            action = QAction(label, self, checkable=True)
            action.setChecked(theme is self._appearance.theme)
            action.triggered.connect(lambda checked=False, value=theme: self._set_theme(value))
            group.addAction(action)
            menu.addAction(action)

    def _add_platform_menu(self, parent_menu) -> None:
        menu = parent_menu.addMenu("Platform Style")
        group = QActionGroup(self)
        group.setExclusive(True)
        for label, preset in (
            ("System Native", PlatformPreset.SYSTEM),
            ("macOS", PlatformPreset.MACOS),
            ("Windows", PlatformPreset.WINDOWS),
        ):
            action = QAction(label, self, checkable=True)
            action.setChecked(preset is self._appearance.platform)
            action.triggered.connect(
                lambda checked=False, value=preset: self._set_platform(value)
            )
            group.addAction(action)
            menu.addAction(action)

    def _add_scale_menu(self, parent_menu) -> None:
        menu = parent_menu.addMenu("UI Scale")
        group = QActionGroup(self)
        group.setExclusive(True)
        for label, scale in (("90%", 0.9), ("100%", 1.0), ("110%", 1.1), ("125%", 1.25), ("150%", 1.5)):
            action = QAction(label, self, checkable=True)
            action.setChecked(scale == self._appearance.scale)
            action.triggered.connect(lambda checked=False, value=scale: self._set_scale(value))
            group.addAction(action)
            menu.addAction(action)

        menu.addSeparator()
        zoom_in = QAction("Increase Scale", self)
        zoom_in.setShortcut(QKeySequence.StandardKey.ZoomIn)
        zoom_in.triggered.connect(lambda: self._set_scale(self._appearance.scale + 0.1))
        menu.addAction(zoom_in)
        zoom_out = QAction("Decrease Scale", self)
        zoom_out.setShortcut(QKeySequence.StandardKey.ZoomOut)
        zoom_out.triggered.connect(lambda: self._set_scale(self._appearance.scale - 0.1))
        menu.addAction(zoom_out)

    def _set_theme(self, theme: Theme) -> None:
        self._appearance = self._appearance.with_theme(theme)
        apply_appearance(self._app, self._appearance)
        self.statusBar().showMessage(f"Theme: {theme.value}", 2500)
        self._save_appearance()

    def _set_platform(self, preset: PlatformPreset) -> None:
        self._appearance = self._appearance.with_platform(preset)
        apply_appearance(self._app, self._appearance)
        self.statusBar().showMessage(f"Platform style: {preset.value}", 2500)
        self._save_appearance()

    def _set_scale(self, scale: float) -> None:
        self._appearance = self._appearance.with_scale(scale)
        apply_appearance(self._app, self._appearance)
        self.statusBar().showMessage(f"UI scale: {self._appearance.scale:.0%}", 2500)
        self._save_appearance()

    def _reset_layout(self, checked: bool = False, clear_saved: bool = True) -> None:
        del checked
        for dock in self._docks.values():
            dock.setFloating(False)
            dock.show()
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self._docks["navigation"])
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._docks["frequency"])
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self._docks["activity"])
        self.resizeDocks(
            [self._docks["frequency"]],
            [240],
            Qt.Orientation.Horizontal,
        )
        self.resizeDocks(
            [self._docks["navigation"]],
            [220],
            Qt.Orientation.Horizontal,
        )
        self.resizeDocks(
            [self._docks["activity"]],
            [185],
            Qt.Orientation.Vertical,
        )
        self.statusBar().showMessage("Panel layout reset", 2500)
        if clear_saved:
            self._settings.remove("main/geometry")
            self._settings.remove("main/state")

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            "About MercurySkyPulse",
            "<b>MercurySkyPulse</b><br>"
            "Supervised Mercury telemetry shell<br><br>"
            "Displays modem status, SNR, bitrate, and station workflows, "
            "with station-to-station text chat.",
        )

    def _show_license(self) -> None:
        state = self.license_state
        expiration = state.expires_at.isoformat() if state.expires_at else "No expiration"
        organization = state.organization or "Individual / not specified"
        features = ", ".join(sorted(state.features)) or "None"
        QMessageBox.information(
            self, "License Information",
            f"Edition: {state.edition.title()}\nStatus: {state.status.value}\n"
            f"Organization: {organization}\nExpiration: {expiration}\n\n"
            f"Enabled features: {features}\n\n{state.reason}",
        )

    def _show_plugins(self) -> None:
        records = [] if self.plugin_registry is None else self.plugin_registry.snapshot()
        lines = [
            f"{item['name']} {item['version']} — {item['state']}"
            + (f" ({item['reason']})" if item["reason"] else "")
            for item in records
        ]
        lines.append("Encryption provider — no provider installed")
        QMessageBox.information(
            self, "Plugin Information",
            "Built-in plugins\n\n" + ("\n".join(lines) if lines else "Plugin registry unavailable"),
        )

    def _show_setup(self) -> None:
        if self.setup_window is None:
            return
        self.setup_window.show()
        self.setup_window.raise_()
        self.setup_window.activateWindow()

    def _connect_mercury_services(self) -> None:
        self.supervisor.state_changed.connect(self._on_engine_state)
        self.supervisor.output_received.connect(self.activity_panel.append_log)
        self.supervisor.restart_scheduled.connect(
            lambda delay: self.activity_panel.append_log(
                f"Automatic Mercury restart in {delay / 1000:.1f} seconds"
            )
        )
        self.supervisor.executable_resolved.connect(
            lambda path: self.activity_panel.append_log(f"Mercury executable: {path}")
        )
        self.telemetry.state_changed.connect(self._on_telemetry_state)
        self.telemetry.error_received.connect(
            lambda error: self.activity_panel.append_log(f"Telemetry error: {error}")
        )
        self.telemetry.status_received.connect(self.dashboard.update_status)
        self.telemetry.status_received.connect(self.frequency_panel.update_status)
        if self.ping_service:
            self.telemetry.status_received.connect(self.ping_service.update_status)
        if hasattr(self.telemetry, "set_spectrum_processing_enabled"):
            self._update_spectrum_processing()
        if self.setup_window:
            self.telemetry.audio_devices_received.connect(
                self.setup_window.set_audio_devices
            )
            self.telemetry.spectrum_received.connect(
                self.setup_window.audio_page.update_spectrum
            )
            self.telemetry.status_received.connect(
                self.setup_window.audio_page.update_status
            )
            self.setup_window.audio_diagnostics_changed.connect(
                lambda _active: self._update_spectrum_processing()
            )

    def _update_spectrum_processing(self) -> None:
        audio_diagnostics = bool(
            self.setup_window
            and self.setup_window.isVisible()
            and self.setup_window.tabs.currentWidget() is self.setup_window.audio_page
        )
        self.telemetry.set_spectrum_processing_enabled(
            audio_diagnostics
        )

    def _connect_chat_service(self) -> None:
        if not self.chat_service:
            self.chat_page.setEnabled(False)
            return
        service = self.chat_service
        self.chat_page.listen_requested.connect(service.listen)
        self.chat_page.connect_requested.connect(service.connect_station)
        self.chat_page.disconnect_requested.connect(service.disconnect_station)
        self.chat_page.send_requested.connect(service.send_text)
        self.chat_page.conversation_selected.connect(service.select_conversation)
        service.state_changed.connect(self.chat_page.set_state)
        service.state_changed.connect(
            lambda state: self.activity_panel.append_log(f"ARQ state: {state}")
        )
        service.conversations_changed.connect(self.chat_page.set_conversations)
        service.messages_changed.connect(self.chat_page.set_messages)
        service.active_conversation_changed.connect(
            self.chat_page.set_active_conversation
        )
        service.error_received.connect(self.chat_page.show_error)
        service.error_received.connect(
            lambda error: self.activity_panel.append_log(f"Chat error: {error}")
        )
        service.client.control_event.connect(
            lambda event: self.activity_panel.append_log(f"TNC: {event}")
        )
        service.client.session_connected.connect(
            lambda source, destination, bandwidth: self.activity_panel.append_log(
                f"ARQ session connected source={source} destination={destination} "
                f"bandwidth_hz={bandwidth}"
            )
        )
        service.client.session_connected.connect(self.chat_page.set_connected_peer)
        service.client.session_disconnected.connect(
            lambda: self.activity_panel.append_log("ARQ session disconnected")
        )
        service.client.session_disconnected.connect(self.chat_page.set_disconnected)
        service.client.message_sent.connect(
            lambda message_id: self.activity_panel.append_log(
                f"Chat message queued id={message_id}"
            )
        )
        service.client.message_delivered.connect(
            lambda message_id: self.activity_panel.append_log(
                f"Chat message acknowledged id={message_id}"
            )
        )
        service.client.message_received.connect(
            lambda envelope: self.activity_panel.append_log(
                f"Chat message received id={envelope.message_id}"
            )
        )
        service.client.ping_event_received.connect(
            lambda envelope: self.activity_panel.append_log(
                f"Ping event kind={envelope.kind} id={envelope.message_id}"
            )
        )
        service.client.bbs_event_received.connect(
            lambda envelope: self.activity_panel.append_log(
                f"BBS event kind={envelope.kind} id={envelope.message_id}"
            )
        )
        if self.file_transfer_service:
            transfers = self.file_transfer_service
            self.chat_page.file_requested.connect(transfers.send_file)
            self.chat_page.transfer_pause_requested.connect(transfers.pause)
            self.chat_page.transfer_resume_requested.connect(transfers.resume)
            self.chat_page.transfer_folder_requested.connect(self._open_transfer_folder)
            transfers.transfers_changed.connect(self.chat_page.set_transfers)
            transfers.transfers_changed.connect(self._log_transfers)
            transfers.incoming_offer.connect(self._confirm_incoming_file)
            transfers.transfer_completed.connect(self._transfer_completed)
            transfers.error_received.connect(self.chat_page.show_error)
            transfers.error_received.connect(
                lambda error: self.activity_panel.append_log(
                    f"File transfer error: {error}"
                )
            )

    def _start_mercury(self) -> None:
        self.activity_panel.append_log(
            f"Starting Mercury profile: {self.endpoint_profile.mode.value}"
        )
        self.supervisor.start()
        self.telemetry.start()
        if self.chat_service:
            self.chat_service.start()
        if self.location_service:
            self.location_service.start()
            self.location_service.publish_current()
        if self.beacon_service:
            self.beacon_service.start()
        if self.bbs_service:
            self.bbs_service.start()
        if self.radio_service:
            self.radio_service.start()
        if self.psk_reporter_service:
            self.psk_reporter_service.start()

    def _connect_beacon_service(self) -> None:
        if not self.beacon_service:
            self.beacon_page.setEnabled(False)
            return
        service = self.beacon_service
        self.beacon_page.configure_requested.connect(
            lambda interval, include_gps: service.configure(
                service.config.callsign, service.config.grid, interval, include_gps
            )
        )
        self.beacon_page.send_requested.connect(service.send_now)
        self.beacon_page.disable_requested.connect(service.disable)
        service.config_changed.connect(self.beacon_page.set_config)
        service.config_changed.connect(self._apply_station_callsign_defaults)
        service.state_changed.connect(self.beacon_page.set_state)
        service.state_changed.connect(
            lambda state: self.activity_panel.append_log(f"Beacon state: {state}")
        )
        service.beacon_received.connect(self.beacon_page.set_received)
        service.error_received.connect(self.beacon_page.show_error)
        service.error_received.connect(
            lambda error: self.activity_panel.append_log(f"Beacon error: {error}")
        )
        if self.location_service:
            self.location_service.current_changed.connect(service.update_location)

    def _apply_station_callsign_defaults(self, config) -> None:
        callsign = config.callsign.strip()
        if not callsign:
            return
        self.chat_page.set_station_callsign_once(callsign)
        self.bbs_page.set_station_callsign_once(callsign)

    def _connect_ping_service(self) -> None:
        if not self.ping_service:
            self.ping_page.setEnabled(False)
            return
        service = self.ping_service
        self.ping_page.ping_requested.connect(service.ping)
        service.result_received.connect(self.ping_page.set_result)
        service.state_changed.connect(self.ping_page.set_state)
        service.state_changed.connect(
            lambda state: self.activity_panel.append_log(f"Ping state: {state}")
        )
        service.error_received.connect(self.ping_page.show_error)
        service.error_received.connect(
            lambda error: self.activity_panel.append_log(f"Ping error: {error}")
        )

    def _connect_bbs_service(self) -> None:
        if not self.bbs_service:
            self.bbs_page.setEnabled(False)
            return
        service = self.bbs_service
        self.bbs_page.folder_requested.connect(service.select_folder)
        self.bbs_page.private_requested.connect(service.send_private)
        self.bbs_page.bulletin_requested.connect(service.post_bulletin)
        self.bbs_page.upload_requested.connect(service.upload)
        self.bbs_page.download_requested.connect(service.download)
        self.bbs_page.authenticate_requested.connect(service.authenticate)
        self.bbs_page.enable_protection_requested.connect(service.enable_protection)
        self.bbs_page.unlock_commander_requested.connect(service.unlock_commander)
        self.bbs_page.disable_protection_requested.connect(service.disable_protection)
        self.bbs_page.role_requested.connect(service.set_role)
        service.folders_changed.connect(self.bbs_page.set_folders)
        service.messages_changed.connect(self.bbs_page.set_messages)
        service.files_changed.connect(self.bbs_page.set_files)
        service.security_changed.connect(self.bbs_page.set_security)
        service.roles_changed.connect(self.bbs_page.set_roles)
        service.auth_changed.connect(self.bbs_page.set_auth)
        service.status_changed.connect(self.bbs_page.set_status)
        service.error_received.connect(self.bbs_page.show_error)
        service.error_received.connect(
            lambda error: self.activity_panel.append_log(f"BBS error: {error}")
        )

    def _connect_web_snapshot(self) -> None:
        snapshot = self.web_snapshot
        if snapshot is None:
            return
        self.activity_panel.log_added.connect(snapshot.append_log)
        self.supervisor.state_changed.connect(
            lambda state: snapshot.update_station(engine=state)
        )
        self.telemetry.state_changed.connect(
            lambda state: snapshot.update_station(telemetry=state)
        )
        self.telemetry.status_received.connect(self._update_web_modem)
        if self.chat_service:
            self.chat_service.state_changed.connect(
                lambda state: snapshot.update_station(link=state)
            )
            self.chat_service.conversations_changed.connect(
                lambda _items: self._refresh_web_messages()
            )
            self.chat_service.messages_changed.connect(
                lambda _items: self._refresh_web_messages()
            )
            self.chat_service.client.session_connected.connect(
                lambda source, destination, bandwidth: snapshot.update_station(
                    source_call=source, destination_call=destination,
                    bandwidth_hz=bandwidth,
                )
            )
            self.chat_service.client.session_disconnected.connect(
                lambda: snapshot.update_station(
                    source_call=None, destination_call=None, bandwidth_hz=None
                )
            )
        if self.file_transfer_service:
            self.file_transfer_service.transfers_changed.connect(
                snapshot.update_transfers
            )
        if self.web_server and self.web_server.url:
            self.activity_panel.append_log(
                f"Local read-only web interface: {self.web_server.url}"
            )

    def _refresh_web_messages(self) -> None:
        if not self.web_snapshot or not self.chat_service:
            return
        conversations = self.chat_service.repository.list_conversations()
        messages = [
            message for conversation in conversations
            for message in self.chat_service.repository.list_messages(conversation.id)
        ]
        self.web_snapshot.update_messages(conversations, messages)

    def _update_web_modem(self, status) -> None:
        if self.web_snapshot:
            self.web_snapshot.update_station(
                modem="linked" if status.sync else "listening",
                direction=status.direction,
                snr_db=round(status.snr_db, 1),
                bitrate_bps=status.bitrate_bps,
            )

    def _restart_mercury(self) -> None:
        self.activity_panel.append_log("Manual Mercury restart requested")
        self.telemetry.reconnect_now()
        self.supervisor.restart_now()

    def _stop_mercury(self) -> None:
        self.activity_panel.append_log("Stopping Mercury")
        self.telemetry.stop()
        self.supervisor.stop()

    def _on_engine_state(self, state: str) -> None:
        self.dashboard.set_engine_state(state)
        self._engine_status.setText(f"Mercury: {state}")
        self.statusBar().showMessage(f"Mercury process: {state}", 3000)
        self.activity_panel.append_log(f"Mercury process state: {state}")

    def _on_telemetry_state(self, state: str) -> None:
        self.dashboard.set_telemetry_state(state)
        self._telemetry_status.setText(f"Telemetry: {state}")
        self.activity_panel.append_log(f"Telemetry state: {state}")

    def _log_transfers(self, transfers) -> None:
        for transfer in transfers:
            state = (
                transfer.direction, transfer.status, transfer.transferred, transfer.size
            )
            if self._transfer_diagnostics.get(transfer.id) == state:
                continue
            self._transfer_diagnostics[transfer.id] = state
            self.activity_panel.append_log(
                "File transfer "
                f"id={transfer.id} direction={transfer.direction} "
                f"status={transfer.status} bytes={transfer.transferred}/{transfer.size} "
                f"checksum={transfer.checksum[:12]}"
            )

    def _confirm_incoming_file(self, transfer) -> None:
        size = f"{transfer.size:,} bytes"
        answer = QMessageBox.question(
            self,
            "Incoming File",
            f"Accept {transfer.name} ({size}) from the connected station?\n\n"
            f"SHA-256: {transfer.checksum}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.file_transfer_service.accept(transfer.id)
            self.activity_panel.append_log(f"Incoming file accepted id={transfer.id}")
        else:
            self.file_transfer_service.reject(transfer.id)
            self.activity_panel.append_log(f"Incoming file rejected id={transfer.id}")

    def _transfer_completed(self, transfer) -> None:
        outcome = (
            "already exists and was checksum verified"
            if transfer.status == "duplicate" else "was checksum verified"
        )
        self.statusBar().showMessage(f"File {transfer.name} {outcome}", 10_000)
        self.activity_panel.append_log(
            f"File transfer complete id={transfer.id} status={transfer.status} path={transfer.path}"
        )

    @staticmethod
    def _open_transfer_folder(path_value: str) -> None:
        path = Path(path_value)
        folder = path if path.is_dir() else path.parent
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt API
        self._settings.setValue("main/geometry", self.saveGeometry())
        self._settings.setValue("main/state", self.saveState(1))
        self._settings.setValue(
            "main/tab_order",
            [self.tabs.tabText(index) for index in range(self.tabs.count())],
        )
        if self.setup_window:
            self._settings.setValue("setup/geometry", self.setup_window.saveGeometry())
        self._settings.sync()
        if self.web_server:
            self.web_server.stop()
        if self.plugin_registry:
            self.plugin_registry.stop_all()
        if self.ping_service:
            self.ping_service.stop()
        if self.tx_level_service:
            self.tx_level_service.stop()
        if self.psk_reporter_service:
            self.psk_reporter_service.stop()
        if self.radio_service:
            self.radio_service.stop()
        if self.beacon_service:
            self.beacon_service.stop()
        if self.location_service:
            self.location_service.stop()
        if self.file_transfer_service:
            self.file_transfer_service.stop()
        if self.chat_service:
            self.chat_service.close()
        self.telemetry.stop()
        self.supervisor.shutdown_blocking()
        event.accept()

    def _load_appearance(self) -> Appearance:
        try:
            theme = Theme(str(self._settings.value("appearance/theme", "system")))
            platform = PlatformPreset(
                str(self._settings.value("appearance/platform", "system"))
            )
            scale = float(self._settings.value("appearance/scale", 1.0))
            return Appearance(theme, platform, max(0.9, min(1.5, scale)))
        except (TypeError, ValueError):
            return Appearance.system()

    def _save_appearance(self) -> None:
        self._settings.setValue("appearance/theme", self._appearance.theme.value)
        self._settings.setValue("appearance/platform", self._appearance.platform.value)
        self._settings.setValue("appearance/scale", self._appearance.scale)
        self._settings.sync()

    def _restore_tab_order(self) -> None:
        saved = self._settings.value("main/tab_order", [])
        if isinstance(saved, str):
            saved = [saved]
        for target, label in enumerate(saved or []):
            for current in range(target, self.tabs.count()):
                if self.tabs.tabText(current) == label:
                    self.tabs.tabBar().moveTab(current, target)
                    break
