"""Headless construction tests for the real Qt window.

This module sorts last because Qt owns process-level application teardown.
"""

from __future__ import annotations

import os
from types import SimpleNamespace
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from application.radio import HamlibRig
    from application.modem import ModemStatus, SpectrumFrame
    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QDockWidget, QPushButton, QTabWidget

    from presentation.app import create_application
    from presentation.main_window import MainWindow
    from presentation.radio_page import RadioPage
    from presentation.audio_setup_page import AudioSetupPage
    from presentation.location_page import LocationPage
    from presentation.reporting_setup_page import ReportingSetupPage
    from platform_runtime.station_devices import SerialPort
    from transport.mercury.telemetry.protocol import MercuryDevice
except ImportError:  # Allows static-only environments to run the boundary tests.
    QDockWidget = None
    create_application = None
    MainWindow = None


@unittest.skipIf(MainWindow is None, "PySide6 is not installed")
class GuiSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = create_application(["gui-smoke-test"])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self) -> None:
        self.window = MainWindow(self.app, auto_start=False)
        self.app.processEvents()

    def tearDown(self) -> None:
        self.window.deleteLater()
        self.app.processEvents()

    def test_main_window_has_required_shell_components(self) -> None:
        self.assertEqual(self.app.applicationDisplayName(), "MercurySkyPulse")
        self.assertFalse(self.app.windowIcon().isNull())
        self.assertEqual(3, len(self.window.findChildren(QDockWidget)))
        self.assertGreater(len(self.window.menuBar().actions()), 0)
        self.assertIsNotNone(self.window.statusBar())
        self.assertIsNotNone(self.window.centralWidget())

    def test_all_primary_pages_construct_offscreen(self) -> None:
        tabs = self.window.findChild(QTabWidget)
        self.assertEqual(
            [tabs.tabText(index) for index in range(tabs.count())],
            ["Overview", "Chat", "Beacon", "Ping", "BBS"],
        )
        self.assertTrue(all(tabs.widget(index) is not None for index in range(tabs.count())))

    def test_docks_are_resizable_movable_and_floatable(self) -> None:
        self.assertTrue(self.window.tabs.isMovable())
        self.assertTrue(self.window._toolbar.isMovable())
        for dock in self.window.findChildren(QDockWidget):
            features = dock.features()
            self.assertTrue(features & QDockWidget.DockWidgetFeature.DockWidgetMovable)
            self.assertTrue(features & QDockWidget.DockWidgetFeature.DockWidgetFloatable)

    def test_navigator_routes_to_dashboard_sections_and_docks(self) -> None:
        self.window.tabs.setCurrentWidget(self.window.chat_page)
        self.window.navigation_panel.navigation.setCurrentRow(1)
        self.app.processEvents()
        self.assertIs(self.window.tabs.currentWidget(), self.window.dashboard)

        activity = self.window._docks["activity"]
        activity.hide()
        self.window.navigation_panel.navigation.setCurrentRow(2)
        self.app.processEvents()
        self.assertFalse(activity.isHidden())

        activity.hide()
        self.window.navigation_panel.navigation.setCurrentRow(3)
        self.app.processEvents()
        self.assertFalse(activity.isHidden())

    def test_signal_plot_presentations_are_removed(self) -> None:
        self.assertNotIn("spectrum", self.window._docks)
        self.assertFalse(hasattr(self.window, "spectrum_panel"))
        self.assertFalse(hasattr(self.window.dashboard, "waterfall"))

    def test_radio_catalog_is_scrollable_and_searchable(self) -> None:
        page = RadioPage()
        page.set_catalog((
            HamlibRig(1035, "Yaesu", "FT-991", "1", "Stable", "RIG_MODEL_FT991"),
            HamlibRig(2026, "Elecraft", "K3", "1", "Stable", "RIG_MODEL_K3"),
        ))
        self.assertEqual(page.radio_list.count(), 2)
        self.assertGreaterEqual(page.radio_list.minimumHeight(), 200)
        page.search.setText("FT-991")
        self.assertFalse(page.radio_list.item(0).isHidden())
        self.assertTrue(page.radio_list.item(1).isHidden())
        page.deleteLater()

    def test_radio_catalog_does_not_overlap_cat_fields_when_height_is_constrained(self) -> None:
        page = RadioPage()
        page.resize(900, 560)
        page.show()
        self.app.processEvents()
        list_bottom = page.radio_list.mapTo(
            page.content, QPoint(0, page.radio_list.height())
        ).y()
        device_top = page.device.mapTo(page.content, QPoint(0, 0)).y()
        self.assertLessEqual(list_bottom, device_top)
        self.assertFalse(hasattr(page, "tune_button"))
        self.assertEqual(page.tx_test_button.text(), "Start TX Level Test")
        page.close()
        page.deleteLater()

    def test_station_io_lists_ports_and_mercury_audio_devices(self) -> None:
        radio_page = RadioPage()
        audio_page = AudioSetupPage()
        radio_page.set_serial_ports((SerialPort("COM4", "COM4 — USB UART"),))
        audio_page.set_devices(
            "capture_dev_list",
            (MercuryDevice("USB Audio CODEC", "capture:usb"),),
            "capture:usb",
        )
        audio_page.set_devices(
            "playback_dev_list",
            (MercuryDevice("USB Audio CODEC", "playback:usb"),),
            "playback:usb",
        )
        self.assertEqual(radio_page.device.findData("COM4"), 1)
        self.assertEqual(audio_page.input_device.currentData(), "capture:usb")
        self.assertEqual(audio_page.output_device.currentData(), "playback:usb")
        radio_page.deleteLater()
        audio_page.deleteLater()

    def test_gps_port_selector_lists_com_ports_and_allows_manual_entry(self) -> None:
        page = LocationPage()
        page.set_serial_ports((
            SerialPort("COM4", "COM4 — USB UART"),
            SerialPort("COM5", "COM5 — GPS Receiver"),
        ))
        self.assertEqual(page.serial_port.findData("COM5"), 2)
        page.serial_port.setCurrentIndex(2)
        self.assertEqual(page.selected_serial_port(), "COM5")
        page.serial_port.setEditText("COM9")
        self.assertEqual(page.selected_serial_port(), "COM9")
        page.deleteLater()

    def test_station_io_apply_emits_native_device_ids(self) -> None:
        page = AudioSetupPage()
        page.set_devices(
            "capture_dev_list",
            (MercuryDevice("Radio Capture", "capture:native"),),
            "capture:native",
        )
        page.set_devices(
            "playback_dev_list",
            (MercuryDevice("Radio Playback", "playback:native"),),
            "playback:native",
        )
        applied = []
        page.apply_requested.connect(lambda *values: applied.append(values))
        page.findChild(QPushButton, "PrimaryButton").click()
        self.assertEqual(
            applied[0],
            ("capture:native", "playback:native"),
        )
        page.deleteLater()

    def test_psk_reporter_setup_is_opt_in_with_mercury_frequency(self) -> None:
        page = ReportingSetupPage()
        self.assertFalse(page.enabled.isChecked())
        self.assertEqual(page.frequency.text(), "Unavailable")
        page.set_state("frequency-14105000-500")
        self.assertIn("14.105000 MHz", page.frequency.text())
        page.append_activity("REPORT sender_callsign=K1ABC frequency_hz=14105000")
        self.assertIn("sender_callsign=K1ABC", page.activity.toPlainText())
        page.deleteLater()

    def test_frequency_dock_is_read_only_and_updates_from_mercury(self) -> None:
        dock = self.window._docks["frequency"]
        self.assertEqual(dock.widget(), self.window.frequency_panel)
        self.window.frequency_panel.update_status(ModemStatus(
            radio_frequency_hz=14_105_000, radio_frequency_age_ms=500,
        ))
        self.assertEqual(self.window.frequency_panel.frequency.text(), "14.105000 MHz")
        self.assertIn("Read only", self.window.frequency_panel.detail.text())

    def test_audio_diagnostics_show_native_ids_capture_energy_and_snr(self) -> None:
        page = AudioSetupPage()
        page.set_devices(
            "capture_dev_list",
            (MercuryDevice("CABLE Output (VB-Audio)", "{capture-guid}"),),
            "{capture-guid}",
        )
        page.set_devices(
            "playback_dev_list",
            (MercuryDevice("CABLE Input (VB-Audio)", "{playback-guid}"),),
            "{playback-guid}",
        )
        page.set_diagnostics_active(True)
        page.update_spectrum(SpectrumFrame(8000, (-115.0, -72.5, -91.0)))
        page.update_status(ModemStatus(snr_db=8.25, direction="rx"))
        self.assertIn("{capture-guid}", page.capture_id.text())
        self.assertIn("{playback-guid}", page.playback_id.text())
        self.assertIn("-72.5 dBFS", page.capture_meter.format())
        self.assertIn("8.2 dB", page.snr_meter.format())
        self.assertIn("8,000 Hz", page.spectrum_format.text())
        self.assertIn("energy detected", page.capture_state.text().lower())
        page.deleteLater()

    def test_station_callsign_populates_chat_and_bbs_once(self) -> None:
        self.window._apply_station_callsign_defaults(
            SimpleNamespace(callsign="N0CALL")
        )
        self.assertEqual(self.window.chat_page.local_call.text(), "N0CALL")
        self.assertEqual(self.window.bbs_page.auth_call.text(), "N0CALL")

        self.window.chat_page.local_call.setText("K1CHAT")
        self.window.bbs_page.auth_call.setText("K1BBS")
        self.window._apply_station_callsign_defaults(
            SimpleNamespace(callsign="W2NEW")
        )
        self.assertEqual(self.window.chat_page.local_call.text(), "K1CHAT")
        self.assertEqual(self.window.bbs_page.auth_call.text(), "K1BBS")

    def test_bbs_access_cards_do_not_overlap_at_minimum_window_size(self) -> None:
        page = self.window.bbs_page
        page.resize(760, 560)
        page.show()
        page.tabs.setCurrentIndex(3)
        self.app.processEvents()

        cards = (page.sign_in_card, page.commander_card, page.roles_card)
        positions = [card.mapTo(page, QPoint(0, 0)).y() for card in cards]
        bottoms = [position + card.height() for position, card in zip(positions, cards)]
        self.assertLessEqual(bottoms[0], positions[1])
        self.assertLessEqual(bottoms[1], positions[2])
        self.assertGreaterEqual(
            page.commander_help.height(), page.fontMetrics().height() * 2
        )
        password_row, _ = page.commander_form.getWidgetPosition(
            page.commander_password
        )
        help_row, _ = page.commander_form.getWidgetPosition(page.commander_help)
        self.assertGreater(help_row, password_row)


if __name__ == "__main__":
    unittest.main()
