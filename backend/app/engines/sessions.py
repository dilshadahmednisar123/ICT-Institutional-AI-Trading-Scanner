"""
ICT Session Engine

Accurate session windows with DST handling using America/New_York.
All internal times are UTC; display conversion to IST is left to the frontend.
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from typing import List, Optional, Literal, Tuple
import zoneinfo

NY_TZ = zoneinfo.ZoneInfo("America/New_York")
UTC = timezone.utc

# Default killzone windows in New York local time (approximate, configurable)
SESSION_WINDOWS = {
    "asian": (time(19, 0), time(0, 0)),       # 19:00 – 00:00 NY (crosses midnight)
    "london": (time(2, 0), time(5, 0)),       # 02:00 – 05:00 NY
    "newyork_am": (time(7, 0), time(10, 0)),  # 07:00 – 10:00 NY
    "newyork_pm": (time(13, 0), time(16, 0)), # 13:00 – 16:00 NY
    "london_close": (time(10, 0), time(12, 0)),
}

# Silver Bullet specific windows (NY time)
SILVER_BULLET_WINDOWS = [
    (time(3, 0), time(4, 0)),   # London open SB
    (time(10, 0), time(11, 0)), # NY AM SB
    (time(14, 0), time(15, 0)), # NY PM SB
]


@dataclass
class SessionInfo:
    name: str
    is_active: bool
    start_utc: Optional[datetime]
    end_utc: Optional[datetime]
    ny_local_now: str


def _ny_now(dt: Optional[datetime] = None) -> datetime:
    if dt is None:
        dt = datetime.now(UTC)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(NY_TZ)


def _window_to_utc(ny_date: datetime, start_t: time, end_t: time) -> Tuple[datetime, datetime]:
    """Convert a NY local time window to UTC datetimes. Handles midnight crossing."""
    start_local = datetime.combine(ny_date.date(), start_t, tzinfo=NY_TZ)
    end_local = datetime.combine(ny_date.date(), end_t, tzinfo=NY_TZ)
    if end_t <= start_t:  # crosses midnight
        end_local += timedelta(days=1)
    return start_local.astimezone(UTC), end_local.astimezone(UTC)


def get_current_sessions(dt: Optional[datetime] = None) -> List[SessionInfo]:
    """Return status of all major sessions at the given (or current) time."""
    ny = _ny_now(dt)
    results = []

    for name, (start_t, end_t) in SESSION_WINDOWS.items():
        start_utc, end_utc = _window_to_utc(ny, start_t, end_t)
        # For overnight windows we also check previous day
        if end_t <= start_t:
            prev_start, prev_end = _window_to_utc(ny - timedelta(days=1), start_t, end_t)
            active = (prev_start <= ny.astimezone(UTC) < prev_end) or (start_utc <= ny.astimezone(UTC) < end_utc)
        else:
            active = start_utc <= ny.astimezone(UTC) < end_utc

        results.append(
            SessionInfo(
                name=name,
                is_active=active,
                start_utc=start_utc,
                end_utc=end_utc,
                ny_local_now=ny.strftime("%Y-%m-%d %H:%M %Z"),
            )
        )
    return results


def is_in_silver_bullet_window(dt: Optional[datetime] = None) -> Tuple[bool, Optional[str]]:
    """Check whether current time falls inside a Silver Bullet window."""
    ny = _ny_now(dt)
    t = ny.time()
    for start_t, end_t in SILVER_BULLET_WINDOWS:
        if start_t <= t < end_t:
            label = f"{start_t.strftime('%H:%M')}-{end_t.strftime('%H:%M')} NY"
            return True, label
    return False, None


def active_session_names(dt: Optional[datetime] = None) -> List[str]:
    return [s.name for s in get_current_sessions(dt) if s.is_active]


def session_score(dt: Optional[datetime] = None) -> float:
    """
    Simple 0-5 score for confluence.
    Higher during killzones, especially Silver Bullet windows.
    """
    score = 0.0
    active = active_session_names(dt)
    if "london" in active or "newyork_am" in active:
        score += 3.0
    if "newyork_pm" in active:
        score += 2.0
    if "asian" in active:
        score += 1.0
    in_sb, _ = is_in_silver_bullet_window(dt)
    if in_sb:
        score = min(5.0, score + 2.0)
    return min(5.0, score)
