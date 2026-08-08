"""Headless construction tests for the real Qt window.

This module sorts last because Qt owns process-level application teardown.
"""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QDockWidget, QTabWidget

    from presentation.app import create_application
    from presentation.main_window import MainWindow
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
        self.assertEqual(3, len(self.window.findChildren(QDockWidget)))
        self.assertGreater(len(self.window.menuBar().actions()), 0)
        self.assertIsNotNone(self.window.statusBar())
        self.assertIsNotNone(self.window.centralWidget())

    def test_all_primary_pages_construct_offscreen(self) -> None:
        tabs = self.window.findChild(QTabWidget)
        self.assertEqual(
            [tabs.tabText(index) for index in range(tabs.count())],
            ["Overview", "Chat", "Location", "Beacon", "Ping", "BBS"],
        )
        self.assertTrue(all(tabs.widget(index) is not None for index in range(tabs.count())))

    def test_docks_are_resizable_movable_and_floatable(self) -> None:
        for dock in self.window.findChildren(QDockWidget):
            features = dock.features()
            self.assertTrue(features & QDockWidget.DockWidgetFeature.DockWidgetMovable)
            self.assertTrue(features & QDockWidget.DockWidgetFeature.DockWidgetFloatable)


if __name__ == "__main__":
    unittest.main()
