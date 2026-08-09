"""MercurySkyPulse desktop presentation package."""

from __future__ import annotations


def main() -> int:
    """Set native launch metadata before importing Qt application modules."""
    from platform_runtime.macos_application import set_macos_program_name

    set_macos_program_name("MercurySkyPulse")

    from .app import main as run_application

    return run_application()

__all__ = ["main"]
