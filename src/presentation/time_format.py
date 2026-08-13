"""Consistent UTC formatting for operator-facing MSP timestamps."""

from datetime import UTC, datetime


def format_utc_timestamp(value: str, pattern: str = "%Y-%m-%d %H:%M:%S UTC") -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC).strftime(pattern)
    except (TypeError, ValueError):
        return value
