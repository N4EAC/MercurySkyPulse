import csv
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import xml.etree.ElementTree as ET

from application.location import Location
from platform_runtime.location_exporter import LocationExporter


class LocationExporterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.locations = [
            Location(40.0, -74.0, "gps", "2026-01-01T00:00:00+00:00", 5.0),
            Location(40.1, -73.9, "gps", "2026-01-01T00:01:00+00:00", 4.0),
        ]
        self.exporter = LocationExporter()

    def test_exports_gpx_and_kml_xml(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            gpx = self.exporter.export(self.locations, root / "track.gpx")
            kml = self.exporter.export(self.locations, root / "track.kml")
            self.assertTrue(ET.parse(gpx).getroot().tag.endswith("gpx"))
            self.assertTrue(ET.parse(kml).getroot().tag.endswith("kml"))
            self.assertIn("-74.00000000,40.00000000,0", kml.read_text())

    def test_exports_geojson_longitude_first(self) -> None:
        with TemporaryDirectory() as directory:
            path = self.exporter.export(
                self.locations, Path(directory) / "track.geojson"
            )
            payload = json.loads(path.read_text())
            coordinates = payload["features"][0]["geometry"]["coordinates"]
            self.assertEqual(coordinates[0], [-74.0, 40.0])

    def test_exports_csv_with_mapping_headers(self) -> None:
        with TemporaryDirectory() as directory:
            path = self.exporter.export(
                self.locations, Path(directory) / "track.csv"
            )
            with path.open(newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(rows[0]["latitude"], "40.00000000")
            self.assertEqual(rows[0]["longitude"], "-74.00000000")

    def test_empty_track_is_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                self.exporter.export([], Path(directory) / "empty.gpx")


if __name__ == "__main__":
    unittest.main()
