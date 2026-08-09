import unittest

from platform_runtime.station_devices import StationDeviceCatalog


class FakeAudioDevice:
    def __init__(self, description: str) -> None:
        self._description = description

    def description(self) -> str:
        return self._description


class StationDeviceCatalogTests(unittest.TestCase):
    def test_audio_fallback_uses_unique_names_mercury_can_resolve(self) -> None:
        devices = StationDeviceCatalog._audio_devices((
            FakeAudioDevice("USB Audio CODEC"),
            FakeAudioDevice("usb audio codec"),
            FakeAudioDevice("Built-in Microphone"),
            FakeAudioDevice(""),
        ))
        self.assertEqual(
            [(device.name, device.identifier) for device in devices],
            [
                ("USB Audio CODEC", "USB Audio CODEC"),
                ("Built-in Microphone", "Built-in Microphone"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
