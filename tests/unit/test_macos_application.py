import ctypes
import platform
import unittest

from platform_runtime.macos_application import (
    macos_cocoa_process_name,
    set_macos_program_name,
)


class MacosApplicationTests(unittest.TestCase):
    @unittest.skipUnless(platform.system() == "Darwin", "macOS-specific process metadata")
    def test_native_program_name_is_set_for_interpreter_launch(self) -> None:
        self.assertTrue(set_macos_program_name("MercurySkyPulse"))
        getter = ctypes.CDLL(None).getprogname
        getter.argtypes = []
        getter.restype = ctypes.c_char_p
        self.assertEqual(getter().decode("utf-8"), "MercurySkyPulse")
        self.assertEqual(macos_cocoa_process_name(), "MercurySkyPulse")


if __name__ == "__main__":
    unittest.main()
