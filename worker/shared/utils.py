from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Union


def to_epoch_seconds(dt_or_iso: Optional[Union[str, datetime]]) -> Optional[int]:
    """
    Convert a datetime or ISO-8601 string into epoch seconds (UTC).

    Accepted inputs:
    - datetime: naive or timezone-aware. Naive datetimes are assumed to be UTC.
    - ISO-8601 strings such as:
      "YYYY-MM-DD", "YYYY-MM-DDTHH:MM:SS", "YYYY-MM-DDTHH:MM:SS.sssZ", "YYYY-MM-DDTHH:MM:SSZ",
      or strings supported by datetime.fromisoformat (with a trailing 'Z' mapped to '+00:00').

    Returns:
    - int epoch seconds (UTC) when conversion succeeds
    - None if the input is None or cannot be parsed
    """
    if dt_or_iso is None:
        return None

    if isinstance(dt_or_iso, datetime):
        try:
            if dt_or_iso.tzinfo is None:
                # Assume naive datetimes are UTC
                dt_or_iso = dt_or_iso.replace(tzinfo=timezone.utc)
            return int(dt_or_iso.timestamp())
        except Exception:
            return None

    try:
        text = (dt_or_iso or '').strip()
        if not text:
            return None

        # Try common formats first for speed and clearer failure modes
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ"):
            try:
                dt = datetime.strptime(text, fmt)
                # Treat these as UTC
                dt = dt.replace(tzinfo=timezone.utc)
                return int(dt.timestamp())
            except Exception:
                continue

        # Fallback: fromisoformat (supports offsets; replace trailing 'Z' with '+00:00')
        try:
            dt = datetime.fromisoformat(text.replace('Z', '+00:00'))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return int(dt.timestamp())
        except Exception:
            return None
    except Exception:
        return None


