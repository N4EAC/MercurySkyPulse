"""Qt-backed image preparation for efficient radio transfer."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QSize, Qt
from PySide6.QtGui import QImage, QImageReader, QImageWriter, QPainter

from application.file_transfer import PreparedFile


IMAGE_SUFFIXES = {
    ".bmp", ".heic", ".heif", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"
}
MAX_IMAGE_DIMENSION = 1920
THUMBNAIL_DIMENSION = 128


class ImageProcessor:
    def __init__(self) -> None:
        self._temporary = TemporaryDirectory(prefix="mercury-skypulse-images-")

    def prepare(self, source: Path) -> PreparedFile:
        if source.suffix.lower() not in IMAGE_SUFFIXES:
            return PreparedFile(source, source.name)
        reader = QImageReader(str(source))
        reader.setAutoTransform(True)
        source_size = reader.size()
        if (
            source_size.isValid()
            and max(source_size.width(), source_size.height()) > MAX_IMAGE_DIMENSION
        ):
            reader.setScaledSize(
                source_size.scaled(
                    QSize(MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION),
                    Qt.AspectRatioMode.KeepAspectRatio,
                )
            )
        image = reader.read()
        if image.isNull():
            return PreparedFile(source, source.name)

        resized = self._bounded(image, MAX_IMAGE_DIMENSION)
        has_alpha = resized.hasAlphaChannel()
        extension = ".png" if has_alpha else ".jpg"
        output = Path(self._temporary.name) / f"{source.stem}{extension}"
        writer = QImageWriter(str(output), b"png" if has_alpha else b"jpeg")
        if has_alpha:
            writer.setCompression(9)
        else:
            writer.setQuality(82)
            writer.setOptimizedWrite(True)
        if not writer.write(resized):
            raise ValueError(f"Image optimization failed: {writer.errorString()}")

        thumbnail = self._thumbnail(resized)
        dimensions_changed = source_size.isValid() and resized.size() != source_size
        if output.stat().st_size >= source.stat().st_size and not dimensions_changed:
            return PreparedFile(source, source.name, thumbnail, optimized=False)
        return PreparedFile(output, output.name, thumbnail, optimized=True)

    def close(self) -> None:
        self._temporary.cleanup()

    @staticmethod
    def _bounded(image: QImage, maximum: int) -> QImage:
        if image.width() <= maximum and image.height() <= maximum:
            return image
        return image.scaled(
            QSize(maximum, maximum),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

    @classmethod
    def _thumbnail(cls, image: QImage) -> bytes:
        thumbnail = cls._bounded(image, THUMBNAIL_DIMENSION)
        if thumbnail.hasAlphaChannel():
            background = QImage(
                thumbnail.size(), QImage.Format.Format_RGB32
            )
            background.fill(Qt.GlobalColor.white)
            painter = QPainter(background)
            painter.drawImage(0, 0, thumbnail)
            painter.end()
            thumbnail = background
        for dimension in (128, 96, 64):
            candidate = cls._bounded(thumbnail, dimension)
            data = QByteArray()
            buffer = QBuffer(data)
            buffer.open(QIODevice.OpenModeFlag.WriteOnly)
            writer = QImageWriter(buffer, b"jpeg")
            writer.setQuality(45)
            writer.setOptimizedWrite(True)
            if not writer.write(candidate):
                raise ValueError(
                    f"Thumbnail generation failed: {writer.errorString()}"
                )
            buffer.close()
            encoded = bytes(data)
            if len(encoded) <= 4096:
                return encoded
        raise ValueError("Generated thumbnail exceeds 4 KiB")
