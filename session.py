"""
Farming session statistics (kept in memory, reset when the app restarts or
when the player presses "Reset session").

Every gain that reaches the tracker (manual +N buttons or the OCR
auto-pickup) is logged here with a timestamp, so the Session tab can show
what was gained, how fast (per hour), and a realistic ETA to each goal
based on THIS session's pace rather than a multi-day average.
"""

import time

MIN_SECONDS_FOR_RATE = 60   # don't quote an "per hour" rate off a few seconds


class Session:
    def __init__(self, now=None):
        self.start = now if now is not None else time.time()
        self.events = []            # (timestamp, resource_name, delta)
        self.kills_finished = 0     # kills from missions that already ended

    def reset(self, now=None):
        self.start = now if now is not None else time.time()
        self.events = []
        self.kills_finished = 0

    def add(self, name, delta, now=None):
        ts = now if now is not None else time.time()
        self.events.append((ts, name, delta))

    def elapsed(self, now=None):
        now = now if now is not None else time.time()
        return max(0.0, now - self.start)

    def gained(self):
        """resource name -> net amount gained this session."""
        totals = {}
        for _, name, delta in self.events:
            totals[name] = totals.get(name, 0) + delta
        return totals

    def rate_per_hour(self, name, now=None):
        """Net amount gained per hour, or None while the session is too
        young (or nothing was gained) to say anything meaningful."""
        elapsed = self.elapsed(now)
        if elapsed < MIN_SECONDS_FOR_RATE:
            return None
        gained = self.gained().get(name, 0)
        if gained <= 0:
            return None
        return gained / (elapsed / 3600.0)

    def eta_hours(self, name, remaining, now=None):
        """Hours until `remaining` more units at this session's pace."""
        if remaining <= 0:
            return 0.0
        rate = self.rate_per_hour(name, now)
        if not rate:
            return None
        return remaining / rate


def format_duration(seconds):
    seconds = int(max(0, seconds))
    h, rem = divmod(seconds, 3600)
    m = rem // 60
    if h:
        return f"{h}h {m:02d}m"
    return f"{m}m"


def format_hours(hours):
    """Hours (float) -> '45m' / '2.3h' / '1d 4h'."""
    if hours is None:
        return "—"
    if hours < 1:
        return f"{max(1, int(round(hours * 60)))}m"
    if hours < 48:
        return f"{hours:.1f}h"
    days = int(hours // 24)
    return f"{days}d {int(hours - days * 24)}h"
