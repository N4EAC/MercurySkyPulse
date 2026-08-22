#!/usr/bin/env python3
"""Run MercurySkyPulse's deterministic automated test suites."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

SUITES = {
    "modem": (
        "tests.unit.test_mercury_supervisor",
        "tests.unit.test_radio",
        "tests.contract.test_mercury_telemetry",
    ),
    "protocol": (
        "tests.contract.test_application_protocol_client",
        "tests.contract.test_chat_protocol",
        "tests.contract.test_beacon_broadcast",
        "tests.contract.test_transport_bounds",
    ),
    "transfer": (
        "tests.unit.test_file_transfer",
        "tests.unit.test_image_processor",
    ),
    "gui": (
        "tests.unit.test_gui_boundaries",
        "tests.unit.test_zz_gui_smoke",
    ),
}


def _install_offscreen_qt_filter() -> None:
    """Hide only Qt diagnostics known to be artifacts of the offscreen plugin."""
    if os.environ.get("QT_QPA_PLATFORM") != "offscreen":
        return
    from PySide6.QtCore import qInstallMessageHandler

    ignored = (
        "This plugin does not support propagateSizeHints()",
        "This plugin does not support raise()",
    )

    def handler(_message_type, _context, message: str) -> None:
        if message in ignored:
            return
        print(message, file=sys.stderr)

    qInstallMessageHandler(handler)


def main() -> int:
    _install_offscreen_qt_filter()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("suite", nargs="?", default="all",
                        choices=("all", *SUITES), help="test group to run")
    parser.add_argument("-q", "--quiet", action="store_true")
    arguments = parser.parse_args()
    loader = unittest.defaultTestLoader
    if arguments.suite == "all":
        selected = loader.discover(str(ROOT / "tests"), pattern="test_*.py",
                                   top_level_dir=str(ROOT))
    else:
        selected = loader.loadTestsFromNames(SUITES[arguments.suite])
    result = unittest.TextTestRunner(verbosity=1 if arguments.quiet else 2).run(selected)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
