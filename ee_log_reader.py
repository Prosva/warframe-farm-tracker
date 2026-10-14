"""
EE.log reader.

Warframe (and the Overwolf/EE engine it's built on) writes a plain-text
log file while the game runs. It records things like mission starts,
loading screens, and host migrations. We tail this file (read only, we
never touch the game process or its memory) to figure out roughly what
the player is doing right now, so the overlay can show the right context
(e.g. "you're in an Excavation mission" -> highlight Cryotic).

This is the same general approach used by long-standing community tools
(e.g. WFInfo) and does not interact with the game's memory or network
traffic, which is why it's considered low-risk by the community -
though as always, third-party tools are used at the player's own
discretion.

Default EE.log location on Windows:
    %LOCALAPPDATA%\\Warframe\\EE.log
"""

import os
import re
import threading
import time


def default_log_path():
    local_appdata = os.environ.get("LOCALAPPDATA", "")
    if not local_appdata:
        return None
    path = os.path.join(local_appdata, "Warframe", "EE.log")
    return path if os.path.exists(path) else None


# A handful of recognizable line patterns. These are intentionally loose -
# EE.log formatting can shift between game updates, so we match on
# distinguishing keywords rather than exact strings.
_PATTERNS = [
    (re.compile(r"Mission\|Loading Mission", re.IGNORECASE), "loading_mission"),
    (re.compile(r"Mission\|Fail", re.IGNORECASE), "mission_failed"),
    (re.compile(r"Mission\|Success|Mission\|Complete", re.IGNORECASE), "mission_complete"),
    (re.compile(r"Net\|.*Loading.*Scene", re.IGNORECASE), "loading_scene"),
    (re.compile(r"SwitchToSceneName=(\w+)", re.IGNORECASE), "scene_switch"),
]


# Enemy spawn bookkeeping line, e.g.:
#   "AI [Info]: OnAgentCreated /Npc/Quadruped30 Live 11 Spawned 29 ... AllyLive 1 ..."
# "Spawned" = hostile enemies created so far this mission, "Live" = agents
# currently alive (allies such as your companion included, counted
# separately in AllyLive). There is no explicit "enemy killed" line in
# EE.log, so kills are estimated from these two counters.
_AGENT_RE = re.compile(r"OnAgentCreated\s+\S+\s+Live (\d+) Spawned (\d+).*?AllyLive (\d+)")


def estimate_kills(live, spawned, ally_live):
    """Enemies spawned minus enemies still alive. Updated each time a new
    enemy spawns (so it lags the real kill by a second or two)."""
    return max(0, spawned - (live - ally_live))


class EELogWatcher:
    """Tails EE.log in a background thread and calls `on_event(event_name,
    raw_line)` whenever a recognized line appears. Safe to run even if the
    game isn't open - it just waits for the file to exist."""

    def __init__(self, on_event, log_path=None, poll_interval=1.0):
        self.on_event = on_event
        self.log_path = log_path or default_log_path()
        self.poll_interval = poll_interval
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _run(self):
        while not self._stop.is_set():
            if self.log_path and os.path.exists(self.log_path):
                try:
                    self._tail(self.log_path)
                except OSError:
                    pass
            else:
                # Game not running / log not found yet - check again later,
                # and re-resolve the default path in case it appears.
                self.log_path = self.log_path or default_log_path()
                time.sleep(self.poll_interval * 3)

    def _tail(self, path):
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            f.seek(0, os.SEEK_END)  # only react to new lines from now on
            while not self._stop.is_set():
                pos = f.tell()
                line = f.readline()
                if not line or not line.endswith("\n"):
                    # Nothing new, or the game is mid-write of this line:
                    # rewind and wait so we never process half a line.
                    if line:
                        f.seek(pos)
                    time.sleep(0.25 if line else self.poll_interval)
                    continue
                agent = _AGENT_RE.search(line)
                if agent:
                    live, spawned, ally = (int(g) for g in agent.groups())
                    self.on_event("agent_created", (live, spawned, ally))
                    continue
                for pattern, event_name in _PATTERNS:
                    match = pattern.search(line)
                    if match:
                        self.on_event(event_name, line.strip())
                        break
