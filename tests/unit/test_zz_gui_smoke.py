"""Headless construction tests for the real Qt window.

This module sorts last because Qt owns process-level application teardown.
"""

from __future__ import annotations

import os
from types import SimpleNamespace
from datetime import UTC, datetime
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from application.radio import HamlibRig
    from application.modem import ModemStatus, SpectrumFrame
    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QDockWidget, QMessageBox, QPushButton

    from presentation.app import create_application
    from presentation.main_window import MainWindow
    from presentation.radio_page import RadioPage
    from presentation.audio_setup_page import AudioSetupPage
    from presentation.location_page import LocationPage
    from presentation.reporting_setup_page import ReportingSetupPage
    from presentation.weather_setup_page import WeatherSetupPage
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
        self.assertEqual(self.app.applicationDisplayName(), "Mercury SkyPulse")
        self.assertEqual(self.app.applicationVersion(), "0.1.5")
        self.assertFalse(self.app.windowIcon().isNull())
        self.assertEqual(8, len(self.window.findChildren(QDockWidget)))
        self.assertGreater(len(self.window.menuBar().actions()), 0)
        self.assertIsNotNone(self.window.statusBar())
        self.assertIsNotNone(self.window.centralWidget())
        self.assertFalse(hasattr(self.window, "_license_status"))
        help_action = next(
            action for action in self.window.menuBar().actions()
            if action.text().replace("&", "") == "Help"
        )
        help_menu = help_action.menu()
        self.assertNotIn(
            "License Information", [action.text() for action in help_menu.actions()]
        )

    def test_about_displays_version_and_release_codename(self) -> None:
        with patch.object(QMessageBox, "about") as about:
            self.window._show_about()
        about.assert_called_once_with(
            self.window,
            "About Mercury SkyPulse",
            "Mercury SkyPulse 0.1.5 — Arcturus\n\n"
            "Created by N4EAC Eduardo\n"
            "K5CG Danny (Contributor)",
        )

    def test_validation_roles_have_operator_facing_labels(self) -> None:
        self.window.chat_page.set_state("validating-sending")
        self.assertEqual(
            self.window.chat_page.link_state.text(),
            "TNC: verifying peer",
        )
        self.window._display_link_state("validating-receiving")
        self.assertEqual(
            self.window.station_summary.values["link"].text(),
            "Verifying Peer",
        )

    def test_chat_is_central_and_operational_pages_are_dockable(self) -> None:
        self.assertIs(self.window.centralWidget(), self.window.chat_page)
        self.assertEqual(
            {
                "summary", "frequency", "beacon", "ping",
                "location", "reporting", "bbs", "activity",
            },
            set(self.window._docks),
        )
        self.assertIs(self.window._docks["beacon"].widget(), self.window.beacon_page)
        self.assertIs(self.window._docks["ping"].widget(), self.window.ping_page)
        self.assertIs(self.window._docks["bbs"].widget(), self.window.bbs_page)

    def test_voice_chat_and_second_audio_configuration_are_removed(self) -> None:
        self.assertFalse(hasattr(self.window.chat_page, "voice_record_button"))
        page = AudioSetupPage()
        self.assertFalse(hasattr(page, "voice_input_device"))
        self.assertFalse(hasattr(page, "voice_output_device"))
        page.deleteLater()

    def test_docks_are_resizable_movable_and_floatable(self) -> None:
        self.assertTrue(self.window._toolbar.isMovable())
        for dock in self.window.findChildren(QDockWidget):
            features = dock.features()
            self.assertTrue(features & QDockWidget.DockWidgetFeature.DockWidgetMovable)
            self.assertTrue(features & QDockWidget.DockWidgetFeature.DockWidgetFloatable)

    def test_navigator_workspace_is_removed(self) -> None:
        self.assertNotIn("navigation", self.window._docks)
        self.assertFalse(hasattr(self.window, "navigation_panel"))

    def test_operator_summary_and_location_are_available_without_tab_change(self) -> None:
        self.window.station_summary.set_value("peer", "K1ABC")
        self.assertEqual(self.window.station_summary.values["peer"].text(), "K1ABC")
        self.window.location_panel.set_peer("K1ABC")
        self.assertIn("K1ABC", self.window.location_panel.peer.text())
        self.assertEqual(
            self.window.location_panel.share.text(),
            "Send Location to Connected Station",
        )

    def test_mercury_startup_issue_is_actionable_in_arq_status(self) -> None:
        action = (
            "Mercury could not open the configured CAT/Hamlib radio. "
            "Open Setup → Radio or disable Hamlib control."
        )
        self.window._on_mercury_startup_issue("Radio setup required", action)

        self.assertEqual(
            self.window.station_summary.values["link"].text(),
            "Radio setup required",
        )
        self.assertEqual(self.window.chat_page.link_state.text(), "Radio setup required")
        self.assertIn("Setup → Radio", self.window.chat_page.link_state.toolTip())
        self.assertIn("Operator action:", self.window.activity_panel.output.toPlainText())

    def test_session_cleanup_does_not_overwrite_listening_presentation(self) -> None:
        page = self.window.chat_page
        page.set_connected_peer("N0CALL", "K1ABC", 2300)
        page.set_state("listening")
        page.set_disconnected()
        self.window.station_summary.set_value("link", "Listening")
        self.window._session_disconnected()

        self.assertEqual(page.link_state.text(), "TNC: listening")
        self.assertEqual(
            self.window.station_summary.values["link"].text(), "Listening"
        )
        self.assertEqual(self.window.station_summary.values["peer"].text(), "None")

    def test_station_grid_card_uses_compact_saved_or_position_grid(self) -> None:
        self.assertIn("grid", self.window.station_summary.values)
        self.assertNotIn("gps", self.window.station_summary.values)
        self.window._station_grid_config_changed(SimpleNamespace(grid="fn30as"))
        self.assertEqual(
            self.window.station_summary.values["grid"].text(), "FN30AS"
        )
        self.window._position_summary_changed(SimpleNamespace(
            latitude=40.7128, longitude=-74.0060,
        ))
        self.assertEqual(
            self.window.station_summary.values["grid"].text(), "FN20XR"
        )

    def test_tx_rx_status_led_is_compact_and_changes_color(self) -> None:
        self.assertEqual(self.window._tx_rx_led.size().width(), 10)
        self.assertGreaterEqual(
            self.window._tx_rx_container.layout().contentsMargins().left(), 8
        )
        self.window._set_tx_rx_indicator("tx")
        self.assertEqual(self.window._tx_rx_led.toolTip(), "Radio transmit")
        self.assertIn("#e53935", self.window._tx_rx_led.styleSheet())
        self.window._set_tx_rx_indicator("rx")
        self.assertEqual(self.window._tx_rx_led.toolTip(), "Radio receive")
        self.assertIn("#2fbf71", self.window._tx_rx_led.styleSheet())
        self.assertFalse(hasattr(self.window, "_rx_blink_timer"))

    def test_default_console_reserves_space_for_chat(self) -> None:
        self.window._reset_layout(clear_saved=False)
        for key in ("activity", "reporting", "bbs"):
            self.assertTrue(self.window._docks[key].isHidden())
        for key in ("summary", "frequency", "beacon"):
            self.assertFalse(self.window._docks[key].isHidden())
        self.assertEqual(15, len(self.window.station_summary.values))

    def test_station_status_formats_next_beacon_or_manual_mode(self) -> None:
        self.window.station_summary.set_next_beacon(None)
        self.assertEqual(
            self.window.station_summary.values["next_beacon"].text(), "Manual"
        )
        beacon_value = self.window.station_summary.values["next_beacon"]
        self.assertEqual("", beacon_value.styleSheet())
        self.window.station_summary.set_next_beacon(65_001)
        self.assertEqual(
            self.window.station_summary.values["next_beacon"].text(), "01:06"
        )
        self.assertEqual("", beacon_value.styleSheet())
        self.window.station_summary.set_next_beacon(10_000)
        self.assertIn("#ff3131", beacon_value.styleSheet())
        self.window.station_summary.set_next_beacon(9_000)
        self.assertEqual("", beacon_value.styleSheet())
        self.window.station_summary.set_next_beacon(0)
        self.assertEqual("", beacon_value.styleSheet())
        self.window.station_summary.set_next_beacon_paused()
        self.assertEqual("Paused", beacon_value.text())
        self.assertEqual("", beacon_value.styleSheet())

    def test_chat_displays_and_selects_a_bounded_cq_caller(self) -> None:
        requested = []
        self.window.chat_page.answer_cq_requested.connect(requested.append)
        self.window.chat_page.add_cq_caller(SimpleNamespace(
            callsign="K1ABC", grid="FN31",
            timestamp=datetime.now(UTC).isoformat(),
        ))
        self.assertEqual(self.window.chat_page.cq_callers.count(), 1)
        self.assertIn("K1ABC", self.window.chat_page.cq_callers.currentText())
        self.window.chat_page._answer_cq()
        self.assertEqual(requested, ["K1ABC"])
        self.assertEqual(self.window.chat_page.remote_call.text(), "K1ABC")
        self.assertEqual(self.window.chat_page.cq_callers.count(), 0)
        self.assertFalse(self.window.chat_page.answer_cq_button.isEnabled())

    def test_helper_text_is_inserted_without_being_sent(self) -> None:
        sent = []
        self.window.chat_page.send_requested.connect(sent.append)
        self.window.chat_page.composer.setPlainText("Existing draft")
        self.window.chat_page.insert_composer_text("WX FN30AS Clear 22°C")
        self.assertEqual(
            self.window.chat_page.composer.toPlainText(),
            "Existing draft\nWX FN30AS Clear 22°C",
        )
        self.assertEqual(sent, [])

    def test_conversation_list_has_heading_delete_control_and_utc_contact(self) -> None:
        self.window.chat_page.set_conversations([SimpleNamespace(
            id=7, local_call="N4EAC", remote_call="K1ABC",
            updated_at="2026-08-13T08:30:00-04:00",
        )])
        item = self.window.chat_page.conversations.item(0)
        self.assertEqual(item.text(), "K1ABC\n2026-08-13 12:30 UTC")
        self.window.chat_page.conversations.setCurrentRow(0)
        self.assertTrue(
            self.window.chat_page.delete_conversation_button.isEnabledTo(
                self.window.chat_page
            )
        )
        self.assertEqual(self.window.chat_page.chat_splitter.handleWidth(), 1)

    def test_confirmed_conversation_delete_emits_selected_id(self) -> None:
        requested = []
        page = self.window.chat_page
        page.conversation_delete_requested.connect(requested.append)
        page.set_conversations([SimpleNamespace(
            id=7, local_call="N4EAC", remote_call="K1ABC",
            updated_at="2026-08-13T12:30:00+00:00",
        )])
        page.conversations.setCurrentRow(0)
        with patch(
            "presentation.chat_page.QMessageBox.question",
            return_value=QMessageBox.StandardButton.Yes,
        ):
            page._delete_conversation()
        self.assertEqual(requested, [7])

    def test_wx_button_obeys_consent_and_fetch_state(self) -> None:
        button = self.window.chat_page.weather_button
        self.assertEqual(button.text(), "WX")
        self.assertFalse(button.isEnabledTo(self.window.chat_page))
        self.window.chat_page.set_weather_enabled(True)
        self.assertFalse(button.isEnabledTo(self.window.chat_page))
        self.assertIn("Connect to a station", button.toolTip())
        self.window.chat_page.set_connected_peer("N0CALL", "K1ABC", 500)
        self.assertTrue(button.isEnabledTo(self.window.chat_page))
        self.window.chat_page.set_weather_state("Fetching weather…")
        self.assertEqual(button.text(), "WX…")
        self.assertFalse(button.isEnabledTo(self.window.chat_page))
        self.window.chat_page.set_weather_state("Ready")
        self.assertEqual(button.text(), "WX")
        self.assertTrue(button.isEnabledTo(self.window.chat_page))
        self.window.chat_page.set_disconnected()
        self.assertFalse(button.isEnabledTo(self.window.chat_page))

    def test_weather_setup_preview_has_no_chat_insertion_control(self) -> None:
        page = WeatherSetupPage()
        self.assertFalse(hasattr(page, "insert"))
        self.assertFalse(hasattr(page, "insert_requested"))
        page.deleteLater()

    def test_status_bar_displays_utc_date_and_time(self) -> None:
        self.assertRegex(
            self.window._utc_status.text(),
            r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC$",
        )

    def test_station_status_contains_former_overview_modem_metrics(self) -> None:
        self.window.station_summary.update_status(
            ModemStatus(
                sync=True, direction="tx", snr_db=7.25,
                bitrate_bps=2400, radio_frequency_hz=14_105_000,
                modem_mode="ARQ", arq_tx_mode="DATAC3", arq_rx_mode="DATAC4",
            )
        )
        values = self.window.station_summary.values
        self.assertEqual(values["modem"].text(), "Linked")
        self.assertEqual(values["radio"].text(), "Transmitting")
        self.assertEqual(values["snr"].text(), "7.2 dB")
        self.assertEqual(values["bitrate"].text(), "2,400 bps")
        self.assertEqual(values["frequency"].text(), "14.105000 MHz")
        self.assertEqual(values["datac_mode"].text(), "TX DATAC3 · RX DATAC4")

    def test_bbs_opens_as_a_large_floating_dock_without_crushing_chat(self) -> None:
        self.window._reset_layout(clear_saved=False)
        dock = self.window._docks["bbs"]
        self.assertTrue(dock.isFloating())
        self.assertTrue(dock.isHidden())
        dock.show()
        self.app.processEvents()
        self.assertTrue(dock.isFloating())
        self.assertGreaterEqual(dock.width(), 720)
        self.assertGreaterEqual(dock.height(), 520)

    def test_signal_plot_presentations_are_removed(self) -> None:
        self.assertNotIn("spectrum", self.window._docks)
        self.assertFalse(hasattr(self.window, "spectrum_panel"))
        self.assertFalse(hasattr(self.window, "dashboard"))

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
        self.assertFalse(hasattr(page, "tx_acknowledgement"))
        self.assertEqual(page.tx_test_button.text(), "Start TX Level Test")
        self.assertTrue(page.tx_test_button.isEnabled())
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
        self.assertEqual(
            self.window.frequency_panel.detail.text(), "Read only · Mercury Hamlib"
        )
        self.assertNotIn("old", self.window.frequency_panel.detail.text())

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
        self.assertEqual(page.capture_state.parentWidget().title(), "Live Audio Diagnostics")
        self.assertGreaterEqual(page.capture_state.minimumHeight(), 1)
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
