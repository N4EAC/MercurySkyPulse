"""Theme, platform appearance, and UI-scale support."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import os
import platform

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication, QStyleFactory


class Theme(str, Enum):
    SYSTEM = "system"
    LIGHT = "light"
    DARK = "dark"


class PlatformPreset(str, Enum):
    SYSTEM = "system"
    MACOS = "macos"
    WINDOWS = "windows"


@dataclass(frozen=True, slots=True)
class Appearance:
    theme: Theme = Theme.SYSTEM
    platform: PlatformPreset = PlatformPreset.SYSTEM
    scale: float = 1.0

    @classmethod
    def system(cls) -> "Appearance":
        return cls()

    def with_theme(self, theme: Theme) -> "Appearance":
        return replace(self, theme=theme)

    def with_platform(self, preset: PlatformPreset) -> "Appearance":
        return replace(self, platform=preset)

    def with_scale(self, scale: float) -> "Appearance":
        return replace(self, scale=max(0.9, min(1.5, scale)))


LIGHT = {
    "window": "#f3f5f8",
    "surface": "#ffffff",
    "surface_alt": "#eef1f5",
    "text": "#18202b",
    "muted": "#667085",
    "border": "#d8dee8",
    "accent": "#3478f6",
    "accent_hover": "#2568d8",
    "success": "#1b8f5a",
    "danger": "#c62828",
    "warning": "#b66a00",
}

DARK = {
    "window": "#11151b",
    "surface": "#1a2029",
    "surface_alt": "#222a35",
    "text": "#edf1f7",
    "muted": "#9ba8b8",
    "border": "#313b49",
    "accent": "#64a0ff",
    "accent_hover": "#82b2ff",
    "success": "#4cc38a",
    "danger": "#e53935",
    "warning": "#f0ad4e",
}


def _effective_dark(app: QApplication, theme: Theme) -> bool:
    if theme is Theme.DARK:
        return True
    if theme is Theme.LIGHT:
        return False
    window = app.palette().color(QPalette.ColorRole.Window)
    return window.lightness() < 128


def _set_qt_style(app: QApplication, preset: PlatformPreset) -> None:
    available = {name.lower(): name for name in QStyleFactory.keys()}
    candidates: list[str]
    if os.environ.get("QT_QPA_PLATFORM") in {"offscreen", "minimal"}:
        candidates = ["fusion"]
    elif preset is PlatformPreset.MACOS:
        candidates = ["macos", "macintosh", "fusion"]
    elif preset is PlatformPreset.WINDOWS:
        candidates = ["windowsvista", "windows11", "windows", "fusion"]
    elif platform.system() == "Darwin":
        candidates = ["macos", "macintosh", "fusion"]
    elif platform.system() == "Windows":
        candidates = ["windowsvista", "windows11", "windows", "fusion"]
    else:
        candidates = ["fusion"]

    for candidate in candidates:
        if candidate in available:
            app.setStyle(available[candidate])
            return


def _stylesheet(colors: dict[str, str], appearance: Appearance) -> str:
    mac = appearance.platform is PlatformPreset.MACOS or (
        appearance.platform is PlatformPreset.SYSTEM and platform.system() == "Darwin"
    )
    radius = 9 if mac else 5
    control_height = 30 if mac else 28
    padding_x = 14 if mac else 11

    return f"""
    QMainWindow, QDialog {{
        background: {colors['window']};
        color: {colors['text']};
    }}
    QWidget {{
        color: {colors['text']};
        selection-background-color: {colors['accent']};
    }}
    QDialog > QWidget, QMainWindow > QWidget,
    QScrollArea, QAbstractScrollArea::viewport {{
        background: {colors['window']};
    }}
    QFrame#Card {{
        background: {colors['surface']};
        border: 1px solid {colors['border']};
        border-radius: {radius}px;
    }}
    QLabel#PageTitle {{ font-size: 20px; font-weight: 650; }}
    QLabel#SectionTitle {{ font-size: 12px; font-weight: 650; }}
    QLabel#Muted, QLabel#MetricCaption {{ color: {colors['muted']}; }}
    QLabel#MetricValue {{ font-size: 18px; font-weight: 650; }}
    QLabel#StatusPill {{
        background: {colors['surface_alt']};
        color: {colors['muted']};
        border: 1px solid {colors['border']};
        border-radius: 10px;
        padding: 3px 9px;
    }}
    QPushButton, QToolButton, QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox {{
        min-height: {control_height}px;
        padding: 0 {padding_x}px;
        background: {colors['surface']};
        color: {colors['text']};
        border: 1px solid {colors['border']};
        border-radius: {radius}px;
    }}
    QPushButton:hover, QToolButton:hover, QComboBox:hover {{
        border-color: {colors['accent']};
        background: {colors['surface_alt']};
    }}
    QPushButton#PrimaryButton {{
        background: {colors['accent']};
        color: white;
        border-color: {colors['accent']};
        font-weight: 600;
    }}
    QPushButton#PrimaryButton:hover {{ background: {colors['accent_hover']}; }}
    QPushButton#VoiceRecordingButton {{
        background: {colors['danger']};
        color: white;
        border-color: {colors['danger']};
        font-weight: 600;
    }}
    QPushButton#VoicePlayingButton {{
        background: {colors['success']};
        color: white;
        border-color: {colors['success']};
        font-weight: 600;
    }}
    QListWidget, QTreeWidget, QTableWidget, QPlainTextEdit, QTextEdit {{
        background: {colors['surface']};
        alternate-background-color: {colors['surface_alt']};
        border: 1px solid {colors['border']};
        border-radius: {radius}px;
        padding: 4px;
    }}
    QListWidget::item, QTreeWidget::item {{
        min-height: 28px;
        border-radius: {max(radius - 2, 2)}px;
        padding: 3px 7px;
    }}
    QListWidget::item:selected, QTreeWidget::item:selected {{
        background: {colors['accent']};
        color: white;
    }}
    QTabWidget::pane {{
        background: {colors['surface']};
        border: 1px solid {colors['border']};
        border-radius: {radius}px;
    }}
    QTabBar::tab {{
        background: {colors['surface_alt']};
        color: {colors['text']};
        border: 1px solid {colors['border']};
        border-bottom: 0;
        padding: 7px 13px;
    }}
    QTabBar::tab:selected {{
        background: {colors['accent']};
        color: white;
    }}
    QTabBar::tab:hover:!selected {{ background: {colors['surface']}; }}
    QHeaderView::section {{
        background: {colors['surface_alt']};
        color: {colors['text']};
        border: 0;
        border-right: 1px solid {colors['border']};
        border-bottom: 1px solid {colors['border']};
        padding: 5px;
    }}
    QDockWidget {{
        background: {colors['surface']};
        titlebar-close-icon: none;
        titlebar-normal-icon: none;
    }}
    QDockWidget::title {{
        background: {colors['surface_alt']};
        border-bottom: 1px solid {colors['border']};
        padding: 8px 10px;
        font-weight: 600;
    }}
    QMenuBar, QMenu, QToolBar, QStatusBar {{
        background: {colors['surface']};
        color: {colors['text']};
    }}
    QMenuBar {{ border-bottom: 1px solid {colors['border']}; }}
    QStatusBar {{ border-top: 1px solid {colors['border']}; }}
    QToolBar {{
        border: 0;
        border-bottom: 1px solid {colors['border']};
        spacing: 6px;
        padding: 6px;
    }}
    QMenu::item {{ padding: 6px 28px 6px 24px; }}
    QMenu::item:selected {{ background: {colors['accent']}; color: white; }}
    QSplitter::handle {{ background: {colors['border']}; }}
    QSplitter#ChatSplitter::handle {{
        background: transparent;
        width: 1px;
        margin: 0;
    }}
    QScrollBar:vertical {{ width: 11px; background: transparent; }}
    QScrollBar::handle:vertical {{
        min-height: 24px;
        background: {colors['border']};
        border-radius: 5px;
    }}
    """


def apply_appearance(app: QApplication, appearance: Appearance) -> None:
    """Apply style, colors, and UI scale to the whole application."""
    _set_qt_style(app, appearance.platform)
    dark = _effective_dark(app, appearance.theme)
    colors = DARK if dark else LIGHT

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(colors["window"]))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(colors["text"]))
    palette.setColor(QPalette.ColorRole.Base, QColor(colors["surface"]))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(colors["surface_alt"]))
    palette.setColor(QPalette.ColorRole.Text, QColor(colors["text"]))
    palette.setColor(QPalette.ColorRole.Button, QColor(colors["surface"]))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(colors["text"]))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(colors["accent"]))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    app.setPalette(palette)

    font = QFont(app.font())
    font.setPointSizeF(9.0 * appearance.scale)
    app.setFont(font)
    app.setStyleSheet(_stylesheet(colors, appearance))
