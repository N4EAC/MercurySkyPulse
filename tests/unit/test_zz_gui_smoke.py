"""Headless construction tests for the real Qt window.

This module sorts last because Qt owns process-level application teardown.
"""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from application.radio import HamlibRig
    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QDockWidget, QPushButton, QTabWidget

    from presentation.app import create_application
    from presentation.main_window import MainWindow
    from presentation.radio_page import RadioPage
    from presentation.audio_setup_page import AudioSetupPage
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
        self.window.navigation_panel.navigation.setCurrentRow(3)
        self.app.processEvents()
        self.assertFalse(activity.isHidden())

        inspector = self.window._docks["inspector"]
        inspector.hide()
        self.window.navigation_panel.navigation.setCurrentRow(4)
        self.app.processEvents()
        self.assertFalse(inspector.isHidden())

    def test_spectrum_and_waterfall_can_be_hidden_independently(self) -> None:
        self.window.dashboard.spectrum_enabled.setChecked(False)
        self.assertTrue(self.window.dashboard.spectrum_card.isHidden())
        self.assertFalse(self.window.dashboard.waterfall_card.isHidden())
        self.window.dashboard.waterfall_enabled.setChecked(False)
        self.assertTrue(self.window.dashboard.waterfall_card.isHidden())

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
        self.assertTrue(page.scroll_area.verticalScrollBar().maximum() > 0)
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


if __name__ == "__main__":
    unittest.main()
