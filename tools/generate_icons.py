"""Generate platform icon assets from the transparent master PNG."""

from __future__ import annotations

from pathlib import Path
import shutil

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
ICON_DIR = ROOT / "assets" / "icons"
MASTER = ICON_DIR / "mercuryskypulse.png"
SIZES = (16, 32, 48, 64, 128, 256, 512, 1024)


def main() -> None:
    with Image.open(MASTER) as source:
        image = source.convert("RGBA").resize((1024, 1024), Image.Resampling.LANCZOS)
        image.save(MASTER, optimize=True)
        image.save(
            ICON_DIR / "mercuryskypulse.ico",
            format="ICO",
            sizes=tuple((size, size) for size in SIZES if size <= 256),
        )

        linux = ICON_DIR / "linux"
        linux.mkdir(parents=True, exist_ok=True)
        for size in SIZES:
            image.resize((size, size), Image.Resampling.LANCZOS).save(
                linux / f"mercuryskypulse-{size}.png", optimize=True
            )

        image.save(ICON_DIR / "mercuryskypulse.icns", format="ICNS")

        resources = ROOT / "src" / "presentation" / "resources"
        resources.mkdir(parents=True, exist_ok=True)
        shutil.copy2(MASTER, resources / "mercuryskypulse.png")

    print(f"Generated icons in {ICON_DIR}")


if __name__ == "__main__":
    main()
