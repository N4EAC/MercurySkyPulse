"""Managed Mercury TX-gain migration tests."""

from pathlib import Path
import tempfile
import unittest

from persistence.chat_repository import ChatRepository
from presentation.app import _load_tx_gain


class TxGainMigrationTests(unittest.TestCase):
    def test_imports_existing_bounded_mercury_gain_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "mercury.ini"
            config.write_text("[audio]\ntx_gain_db = 3.00\n", encoding="utf-8")
            repository = ChatRepository(":memory:")
            try:
                self.assertEqual(_load_tx_gain(repository, config), 3.0)
                self.assertEqual(repository.get_setting("radio.tx_gain_db"), "3.00")
                config.write_text("[audio]\ntx_gain_db = -5.00\n", encoding="utf-8")
                self.assertEqual(_load_tx_gain(repository, config), 3.0)
            finally:
                repository.close()

    def test_rejects_out_of_range_legacy_gain(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "mercury.ini"
            config.write_text("[audio]\ntx_gain_db = 10.00\n", encoding="utf-8")
            repository = ChatRepository(":memory:")
            try:
                self.assertEqual(_load_tx_gain(repository, config), 0.0)
                self.assertIsNone(repository.get_setting("radio.tx_gain_db"))
            finally:
                repository.close()


if __name__ == "__main__":
    unittest.main()
