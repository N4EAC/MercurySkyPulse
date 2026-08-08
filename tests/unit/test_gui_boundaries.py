"""Static dependency tests for the presentation-only skeleton."""

from __future__ import annotations

import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
PRESENTATION = ROOT / "src" / "presentation"


class GuiBoundaryTests(unittest.TestCase):
    def test_gui_has_no_forbidden_runtime_imports(self) -> None:
        forbidden_roots = {
            "sqlite3",
            "socket",
            "websocket",
            "requests",
            "httpx",
            "aiohttp",
            "mercury",
        }
        violations: list[str] = []

        for path in PRESENTATION.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                names: list[str] = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module]
                for name in names:
                    if name.split(".", 1)[0] in forbidden_roots:
                        violations.append(f"{path.relative_to(ROOT)} imports {name}")

        self.assertEqual([], violations)

    def test_expected_gui_modules_exist(self) -> None:
        expected = {
            "__init__.py",
            "__main__.py",
            "app.py",
            "main_window.py",
            "panels.py",
            "themes.py",
        }
        self.assertTrue(expected.issubset({path.name for path in PRESENTATION.iterdir()}))


if __name__ == "__main__":
    unittest.main()

