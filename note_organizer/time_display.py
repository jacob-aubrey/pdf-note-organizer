"""Consistent local display for persisted UTC timestamps."""
from datetime import datetime, timezone


def local_time(value, format="%H:%M"):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone().strftime(format)
    except (TypeError, ValueError, AttributeError):
        return "—"
