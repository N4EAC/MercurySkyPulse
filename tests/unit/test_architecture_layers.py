"""Enforce the Mercury/application layering boundary statically."""

from __future__ import annotations

import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


def imports_under(directory: Path) -> list[tuple[Path, str]]:
    found = []
    for path in directory.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found.extend((path, alias.name) for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                found.append((path, node.module))
    return found


class LayerBoundaryTests(unittest.TestCase):
    def test_collaboration_services_do_not_import_transport_adapters(self) -> None:
        violations = [
            f"{path.relative_to(ROOT)} imports {name}"
            for path, name in imports_under(ROOT / "src/application")
            if name == "transport" or name.startswith("transport.")
        ]
        self.assertEqual(violations, [])

    def test_application_protocol_is_transport_and_feature_independent(self) -> None:
        forbidden = ("transport", "presentation", "persistence", "platform_runtime",
                     "application.bbs", "application.beacon", "application.chat_service",
                     "application.file_transfer", "application.location", "application.ping")
        violations = [
            f"{path.relative_to(ROOT)} imports {name}"
            for path, name in imports_under(ROOT / "src/application_protocol")
            if any(name == item or name.startswith(item + ".") for item in forbidden)
        ]
        self.assertEqual(violations, [])

    def test_mercury_adapters_do_not_import_application_features(self) -> None:
        allowed_application_imports = {"application.modem"}
        violations = [
            f"{path.relative_to(ROOT)} imports {name}"
            for path, name in imports_under(ROOT / "src/transport/mercury")
            if name.startswith("application.") and name not in allowed_application_imports
        ]
        self.assertEqual(violations, [])

    def test_mercury_adapters_contain_no_feature_protocol_identifiers(self) -> None:
        forbidden_tokens = ("MSP1", "MSPB", "bbs_auth_", "bbs_private",
                            "file_offer", "file_chunk", "ping_request",
                            "ping_response", '"location"')
        violations = []
        for path in (ROOT / "src/transport/mercury").rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for token in forbidden_tokens:
                if token in text:
                    violations.append(f"{path.relative_to(ROOT)} contains {token}")
        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
