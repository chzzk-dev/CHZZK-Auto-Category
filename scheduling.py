"""Independent wall-clock schedules with an enforced one-hour minimum."""
import time

HOUR_OPTIONS = (1, 3, 6, 12, 24)


def bounded_minutes(value, default=180):
    try:
        return max(60, min(10080, int(value)))
    except (TypeError, ValueError, OverflowError):
        return default


def seconds_until_check(config, now=None):
    if not config.get('auto_update', True):
        return None
    now = time.time() if now is None else now
    try:
        last = max(0.0, float(config.get('update_last_checked_at', 0)))
    except (TypeError, ValueError):
        last = 0
    if last > now:  # System clock correction must not defer checks indefinitely.
        last = now
    return max(0, last + bounded_minutes(config.get('update_check_minutes', 180)) * 60 - now)
