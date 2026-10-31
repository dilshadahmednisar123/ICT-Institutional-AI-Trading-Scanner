"""
Economic Calendar / News Filter (stub + interface)

When a real calendar provider is configured (e.g. FCS API, ForexFactory-compatible,
or broker calendar), this module blocks new signals inside blackout windows.

Without a provider the filter returns NEWS FILTER UNAVAILABLE and does not block.
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
import logging

logger = logging.getLogger("ict_scanner.news")

HIGH_IMPACT_KEYWORDS = {
    "CPI", "NFP", "FOMC", "INTEREST RATE", "GDP", "PCE",
    "UNEMPLOYMENT", "NON-FARM", "RATE DECISION", "PMI",
}


@dataclass
class NewsEvent:
    title: str
    currency: str
    impact: str  # high / medium / low
    time_utc: datetime
    source: str = "unavailable"


@dataclass
class NewsFilterResult:
    available: bool
    risk: str  # Low / Medium / High / Unknown
    blocking: bool
    events_nearby: List[Dict[str, Any]]
    message: str


class NewsFilter:
    def __init__(self, blackout_minutes_before: int = 30, blackout_minutes_after: int = 15):
        self.blackout_before = blackout_minutes_before
        self.blackout_after = blackout_minutes_after
        self._events: List[NewsEvent] = []

    def set_events(self, events: List[NewsEvent]) -> None:
        self._events = events

    def evaluate(
        self,
        symbol: str,
        now: Optional[datetime] = None,
    ) -> NewsFilterResult:
        now = now or datetime.now(timezone.utc)

        if not self._events:
            return NewsFilterResult(
                available=False,
                risk="Unknown",
                blocking=False,
                events_nearby=[],
                message="NEWS FILTER UNAVAILABLE — no calendar provider configured",
            )

        # Currencies involved in the pair
        pair = symbol.upper().replace("/", "")
        currencies = set()
        if len(pair) >= 6:
            currencies.add(pair[:3])
            currencies.add(pair[3:6])
        if "XAU" in pair:
            currencies.add("USD")

        nearby = []
        blocking = False
        highest = "Low"

        for ev in self._events:
            if ev.currency not in currencies and ev.currency != "ALL":
                continue
            delta = (ev.time_utc - now).total_seconds() / 60.0
            in_window = -self.blackout_after <= delta <= self.blackout_before
            if in_window:
                nearby.append({
                    "title": ev.title,
                    "currency": ev.currency,
                    "impact": ev.impact,
                    "time_utc": ev.time_utc.isoformat(),
                    "minutes_until": round(delta, 1),
                })
                if ev.impact.lower() == "high":
                    blocking = True
                    highest = "High"
                elif ev.impact.lower() == "medium" and highest != "High":
                    highest = "Medium"

        return NewsFilterResult(
            available=True,
            risk=highest,
            blocking=blocking,
            events_nearby=nearby,
            message="High-impact news blackout active" if blocking else "News filter clear",
        )


# Global default instance (empty until a provider loads events)
default_news_filter = NewsFilter()
