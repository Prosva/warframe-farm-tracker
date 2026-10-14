"""
Mastery checklist data.

Warframe has no API for a player's own inventory, so "what have I
mastered" is a checklist the player ticks off. What we CAN get from the
public warframestat.us item database is the real list of masterable
items with their Mastery Rank requirement, so the checklist is complete
and correct without being typed in by hand. The downloaded list is
cached next to the program (mastery_cache.json) so it works offline
afterwards.
"""

import json
import os
import urllib.error
import urllib.request

import storage

BASE_URL = "https://api.warframestat.us"
# Item endpoints that contain masterable things. If one is missing or
# fails, the others still load.
SOURCES = ["warframes", "weapons", "archwing", "sentinels", "pets"]
TIMEOUT_SECONDS = 45


def cache_path():
    return os.path.join(os.path.dirname(storage.DATA_FILE), "mastery_cache.json")


def parse_items(raw_items, source=""):
    """Raw API list -> {name: {name, category, type, mr, prime}} keeping
    only items that give mastery."""
    out = {}
    for it in raw_items or []:
        if not isinstance(it, dict) or not it.get("masterable"):
            continue
        name = it.get("name")
        if not name or name in out:
            continue
        try:
            mr = int(it.get("masteryReq") or 0)
        except (TypeError, ValueError):
            mr = 0
        out[name] = {
            "name": name,
            "category": it.get("category") or source or "Other",
            "type": it.get("type") or "",
            "mr": mr,
            "prime": bool(it.get("isPrime")),
        }
    return out


def fetch_catalog():
    """Download every source. Returns (items_list, errors). Never raises."""
    merged, errors = {}, []
    for source in SOURCES:
        url = f"{BASE_URL}/{source}?language=en"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "WarframeFarmTracker/1.0"})
            with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            for name, item in parse_items(data, source).items():
                merged.setdefault(name, item)
        except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
            errors.append(f"{source}: {exc}")
    return sorted(merged.values(), key=lambda i: (i["mr"], i["name"])), errors


def save_cache(items):
    try:
        tmp = cache_path() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False)
        os.replace(tmp, cache_path())
    except OSError:
        pass


def load_cache():
    try:
        with open(cache_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def categories(items):
    return sorted({i["category"] for i in items})


def filter_items(items, done, query="", category="", my_mr=None, hide_done=False):
    """Pure filter: text search, category, hide mastered, and (when
    my_mr is given) only items whose MR requirement is within reach.
    Sorted lowest requirement first."""
    query = (query or "").strip().lower()
    out = []
    for it in items:
        if category and it["category"] != category:
            continue
        if query and query not in it["name"].lower():
            continue
        if hide_done and done.get(it["name"]):
            continue
        if my_mr is not None and it["mr"] > my_mr:
            continue
        out.append(it)
    out.sort(key=lambda i: (i["mr"], i["name"]))
    return out


def progress(items, done, category=""):
    pool = [i for i in items if not category or i["category"] == category]
    mastered = sum(1 for i in pool if done.get(i["name"]))
    return mastered, len(pool)
