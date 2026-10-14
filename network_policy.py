"""Bounded server backoff; accepts Retry-After seconds and HTTP dates."""
import math
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime


def retry_seconds(value, default=60):
    try:
        seconds = float(str(value).strip())
    except (TypeError, ValueError):
        try:
            seconds = (parsedate_to_datetime(str(value)) - datetime.now(timezone.utc)).total_seconds()
        except (TypeError, ValueError, OverflowError):
            return default
    if not math.isfinite(seconds):
        return default
    return max(1, min(3600, int(seconds)))
