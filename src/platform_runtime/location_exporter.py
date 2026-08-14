"""Atomic GPS track export for common mapping tools."""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from uuid import uuid4
import xml.etree.ElementTree as ET


class LocationExporter:
    SUPPORTED_SUFFIXES = {".gpx", ".kml", ".geojson", ".json", ".csv"}

    def export(self, locations: list[object], destination: Path) -> Path:
        if not locations:
            raise ValueError("There are no retained GPS positions to export")
        suffix = destination.suffix.lower()
        if suffix not in self.SUPPORTED_SUFFIXES:
            destination = destination.with_suffix(".gpx")
            suffix = ".gpx"
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(
            f".{destination.name}.{uuid4().hex}.tmp"
        )
        try:
            if suffix == ".gpx":
                self._write_gpx(locations, temporary)
            elif suffix == ".kml":
                self._write_kml(locations, temporary)
            elif suffix in {".geojson", ".json"}:
                self._write_geojson(locations, temporary)
            else:
                self._write_csv(locations, temporary)
            os.replace(temporary, destination)
        finally:
            if temporary.exists():
                temporary.unlink()
        return destination

    @staticmethod
    def _write_gpx(locations: list[object], path: Path) -> None:
        root = ET.Element(
            "gpx",
            version="1.1",
            creator="Mercury SkyPulse",
            xmlns="http://www.topografix.com/GPX/1/1",
        )
        track = ET.SubElement(root, "trk")
        ET.SubElement(track, "name").text = "Mercury SkyPulse GPS Track"
        segment = ET.SubElement(track, "trkseg")
        for location in locations:
            point = ET.SubElement(
                segment,
                "trkpt",
                lat=f"{location.latitude:.8f}",
                lon=f"{location.longitude:.8f}",
            )
            ET.SubElement(point, "time").text = location.timestamp
            if location.accuracy_m is not None:
                extensions = ET.SubElement(point, "extensions")
                ET.SubElement(
                    extensions, "{urn:mercury-skypulse}accuracy_m"
                ).text = f"{location.accuracy_m:.2f}"
        ET.indent(root)
        ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)

    @staticmethod
    def _write_kml(locations: list[object], path: Path) -> None:
        namespace = "http://www.opengis.net/kml/2.2"
        ET.register_namespace("", namespace)
        root = ET.Element(f"{{{namespace}}}kml")
        document = ET.SubElement(root, f"{{{namespace}}}Document")
        placemark = ET.SubElement(document, f"{{{namespace}}}Placemark")
        ET.SubElement(placemark, f"{{{namespace}}}name").text = (
            "Mercury SkyPulse GPS Track"
        )
        line = ET.SubElement(placemark, f"{{{namespace}}}LineString")
        ET.SubElement(line, f"{{{namespace}}}tessellate").text = "1"
        ET.SubElement(line, f"{{{namespace}}}coordinates").text = " ".join(
            f"{location.longitude:.8f},{location.latitude:.8f},0"
            for location in locations
        )
        ET.indent(root)
        ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)

    @staticmethod
    def _write_geojson(locations: list[object], path: Path) -> None:
        payload = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {
                        "name": "Mercury SkyPulse GPS Track",
                        "timestamps": [location.timestamp for location in locations],
                        "accuracy_m": [location.accuracy_m for location in locations],
                    },
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [
                            [location.longitude, location.latitude]
                            for location in locations
                        ],
                    },
                }
            ],
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    @staticmethod
    def _write_csv(locations: list[object], path: Path) -> None:
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["timestamp", "latitude", "longitude", "accuracy_m"])
            for location in locations:
                writer.writerow(
                    [
                        location.timestamp,
                        f"{location.latitude:.8f}",
                        f"{location.longitude:.8f}",
                        "" if location.accuracy_m is None else f"{location.accuracy_m:.2f}",
                    ]
                )
