import unittest

from presentation.themes import Appearance, DARK, PlatformPreset, Theme, _stylesheet


class ThemeTests(unittest.TestCase):
    def test_dark_stylesheet_colors_tabs_inputs_and_viewports(self) -> None:
        stylesheet = _stylesheet(
            DARK, Appearance(theme=Theme.DARK, platform=PlatformPreset.WINDOWS)
        )
        self.assertIn("QTabWidget::pane", stylesheet)
        self.assertIn("QTabBar::tab:selected", stylesheet)
        self.assertIn("QAbstractScrollArea::viewport", stylesheet)
        self.assertIn("QLineEdit", stylesheet)
        self.assertIn(DARK["window"], stylesheet)
        self.assertIn(DARK["text"], stylesheet)


if __name__ == "__main__":
    unittest.main()
