# ADR 0005: Automatic image preparation

## Status

Accepted.

## Decision

Recognized raster images are prepared automatically before file transfer. EXIF
orientation is applied during decoding and the longest edge is bounded to 1920
pixels. Decoding requests the bounded size up front when supported, reducing peak
memory for very large source images.

Opaque images are encoded as optimized JPEG at quality 82. Images with alpha use
lossless PNG with maximum compression. If recompression would enlarge an image
whose dimensions did not change, the original is sent instead. The original file
is never modified.

Every recognized image also receives a JPEG preview with a longest edge no larger
than 128 pixels. Thumbnail quality and dimensions step down until the preview is
at most 4 KiB, preserving the messaging frame limit. The preview is metadata; the
received full image must still pass the transfer SHA-256 verification.

Temporary optimized images are application-owned and removed during orderly
shutdown. Non-image files bypass this adapter unchanged.

## Consequences

- JPEG, PNG, WebP, HEIC/HEIF, TIFF, and BMP inputs are supported when the bundled
  Qt image plugins can decode them.
- Animated images are not treated as supported inputs in this initial version.
- Image preparation currently occurs before transfer on the UI thread; moving it
  to a bounded worker is a future responsiveness improvement.
