from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage

from platform_runtime.image_processor import ImageProcessor


class ImageProcessorTests(unittest.TestCase):
    def test_resizes_compresses_and_generates_thumbnail(self) -> None:
        with TemporaryDirectory() as directory:
            source = Path(directory) / "large.bmp"
            image = QImage(2400, 1200, QImage.Format.Format_RGB32)
            image.fill(QColor("steelblue"))
            self.assertTrue(image.save(str(source), "BMP"))
            processor = ImageProcessor()
            prepared = processor.prepare(source)
            output = QImage(str(prepared.path))
            self.assertTrue(prepared.optimized)
            self.assertLessEqual(max(output.width(), output.height()), 1920)
            self.assertLess(prepared.path.stat().st_size, source.stat().st_size)
            self.assertGreater(len(prepared.thumbnail), 0)
            self.assertLessEqual(len(prepared.thumbnail), 4096)
            thumbnail = QImage.fromData(prepared.thumbnail)
            self.assertFalse(thumbnail.isNull())
            self.assertLessEqual(max(thumbnail.width(), thumbnail.height()), 128)
            processor.close()

    def test_transparency_uses_compressed_png(self) -> None:
        with TemporaryDirectory() as directory:
            source = Path(directory) / "alpha.png"
            image = QImage(2100, 1000, QImage.Format.Format_ARGB32)
            image.fill(Qt.GlobalColor.transparent)
            self.assertTrue(image.save(str(source), "PNG"))
            processor = ImageProcessor()
            prepared = processor.prepare(source)
            self.assertEqual(prepared.path.suffix, ".png")
            self.assertTrue(QImage(str(prepared.path)).hasAlphaChannel())
            processor.close()

    def test_non_image_is_unchanged(self) -> None:
        with TemporaryDirectory() as directory:
            source = Path(directory) / "notes.txt"
            source.write_text("hello")
            processor = ImageProcessor()
            prepared = processor.prepare(source)
            self.assertEqual(prepared.path, source)
            self.assertFalse(prepared.optimized)
            self.assertEqual(prepared.thumbnail, b"")
            processor.close()


if __name__ == "__main__":
    unittest.main()
