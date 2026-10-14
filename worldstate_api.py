"""
Warframe Worldstate API client.

Uses the community-maintained, officially-tolerated Worldstate API
(https://docs.warframestat.us/) to fetch world info - NOT player data.
Nothing here ever touches the player's own account or inventory.

All requests run in a background thread with a short timeout, so a slow
or unreachable connection never freezes the overlay.
"""

import json
from datetime import datetime, timezone
import threading
import urllib.request
import urllib.error

BASE_URL = "https://api.warframestat.us/pc"
TIMEOUT_SECONDS = 6


def _get_json(endpoint):
    url = f"{BASE_URL}/{endpoint}?language=en"
    req = urllib.request.Request(url, headers={"User-Agent": "WarframeFarmTracker/1.0"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
        return json.loads(resp.read().decode("utf-8"))


_ENDPOINTS = ["sortie", "invasions", "fissures", "cetusCycle", "voidTrader", "dailyDeals",
              "vallisCycle", "cambionCycle", "arbitration", "events", "alerts", "news",
              "globalUpgrades"]


def _safe_get(endpoint):
    """One endpoint failing (the community API sometimes hiccups on a
    single path) must not blank out everything else."""
    try:
        return _get_json(endpoint), True
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None, False


def fetch_worldstate_summary():
    """Returns a dict with the pieces relevant to farming decisions. Each
    endpoint is fetched independently (in parallel); one that fails just
    yields an empty section. Returns None (and never raises) only if the
    API could not be reached at all."""
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = dict(zip(_ENDPOINTS, pool.map(_safe_get, _ENDPOINTS)))
    if not any(ok for _, ok in results.values()):
        return None
    raw = {name: payload for name, (payload, _) in results.items()}

    return {
        "sortie": _summarize_sortie(raw["sortie"]),
        "invasions": _summarize_invasions(raw["invasions"]),
        "fissures": _summarize_fissures(raw["fissures"]),
        "cetus_cycle": _summarize_cycle(raw["cetusCycle"]),
        "vallis_cycle": _summarize_cycle(raw["vallisCycle"]),
        "cambion_cycle": _summarize_cycle(raw["cambionCycle"]),
        "void_trader": _summarize_void_trader(raw["voidTrader"]),
        "daily_deals": _summarize_daily_deals(raw["dailyDeals"]),
        "arbitration": _summarize_arbitration(raw["arbitration"]),
        "events": _summarize_events(raw["events"]),
        "alerts": _summarize_alerts(raw["alerts"]),
        "news": _summarize_news(raw["news"]),
        "global_upgrades": _summarize_global_upgrades(raw["globalUpgrades"]),
    }


def _summarize_sortie(sortie):
    if not sortie or "variants" not in sortie:
        return None
    return {
        "boss": sortie.get("boss"),
        "faction": sortie.get("faction"),
        "expiry": sortie.get("expiry"),
        "missions": [
            {"node": v.get("node"), "missionType": v.get("missionType")}
            for v in sortie.get("variants", [])
        ],
    }


def _reward_text(reward):
    """Reward dict from the API -> 'Orokin Cell x2, Detonite Injector, 10000 cr'."""
    if not isinstance(reward, dict):
        return ""
    parts = []
    for it in reward.get("countedItems") or []:
        name, count = it.get("type") or it.get("name") or "", it.get("count") or 1
        if name:
            parts.append(f"{name} x{count}" if count and count > 1 else name)
    for name in reward.get("items") or []:
        if isinstance(name, str):
            parts.append(name)
    credits = reward.get("credits")
    if credits:
        parts.append(f"{credits} cr")
    return ", ".join(parts)


def _summarize_invasions(invasions):
    if not invasions:
        return []
    out = []
    for inv in invasions:
        if inv.get("completed"):
            continue
        attacker = _reward_text(inv.get("attackerReward"))
        defender = _reward_text(inv.get("defenderReward"))
        out.append({
            "node": inv.get("node"),
            "desc": inv.get("desc"),
            "attacker": inv.get("attackingFaction") or (inv.get("attacker") or {}).get("faction"),
            "defender": inv.get("defendingFaction") or (inv.get("defender") or {}).get("faction"),
            "attacker_reward": attacker,
            "defender_reward": defender,
            # Combined text, used for the "hot right now" cross-reference.
            "reward": ", ".join(x for x in (attacker, defender) if x) or None,
            "completion": inv.get("completion"),
        })
    return out[:15]


def _summarize_fissures(fissures):
    if not fissures:
        return []
    return [
        {
            "tier": f.get("tierNum"),
            "tier_name": f.get("tier"),
            "node": f.get("node"),
            "missionType": f.get("missionType"),
            "enemy": f.get("enemy"),
            "expiry": f.get("expiry"),
            "is_hard": bool(f.get("isHard")),    # Steel Path
            "is_storm": bool(f.get("isStorm")),  # Railjack Void Storm
        }
        for f in fissures
        if f.get("active", True) and not f.get("expired", False)
    ]


def _summarize_cycle(cycle):
    if not cycle:
        return None
    return {"state": cycle.get("state"), "expiry": cycle.get("expiry")}


def _summarize_arbitration(arb):
    """The arbitration feed sometimes returns an empty placeholder
    (node 'SolNode000', already expired). Treat that as 'no data'."""
    if not isinstance(arb, dict):
        return None
    node = arb.get("node")
    if not node or str(node).startswith("SolNode000") or arb.get("expired"):
        return None
    return {
        "node": node,
        "type": arb.get("type"),
        "enemy": arb.get("enemy"),
        "expiry": arb.get("expiry"),
        "archwing": bool(arb.get("archwing")),
    }


def _summarize_events(events):
    if not events:
        return []
    out = []
    for ev in events:
        rewards = [t for t in (_reward_text(r) for r in ev.get("rewards") or []) if t]
        out.append({
            "name": ev.get("description"),
            "tooltip": ev.get("tooltip"),
            "node": ev.get("node"),
            "expiry": ev.get("expiry"),
            "rewards": rewards,
            "score": ev.get("currentScore"),
            "max_score": ev.get("maximumScore"),
            "tag": ev.get("tag"),
        })
    return out


def _summarize_alerts(alerts):
    if not alerts:
        return []
    out = []
    for al in alerts:
        mission = al.get("mission") or {}
        out.append({
            "node": mission.get("node"),
            "type": mission.get("type"),
            "reward": _reward_text(mission.get("reward")),
            "expiry": al.get("expiry"),
        })
    return out


def _summarize_news(news):
    """Newest-first dev announcements. Entries dated 1970 are permanent
    links (Discord/Wiki/Forums), not news - skipped."""
    if not news:
        return []
    out = []
    for n in news:
        date = str(n.get("date") or "")
        if date.startswith("1970"):
            continue
        out.append({
            "message": n.get("message"),
            "date": date,
            "update": bool(n.get("update")),
            "prime_access": bool(n.get("primeAccess")),
            "stream": bool(n.get("stream")),
        })
    out.sort(key=lambda n: n["date"], reverse=True)
    return out[:10]


def _summarize_global_upgrades(upgrades):
    """Global boosters (double credits/resources weekends etc.). Usually
    an empty list."""
    if not upgrades:
        return []
    out = []
    for u in upgrades:
        out.append({
            "desc": u.get("desc") or u.get("upgrade"),
            "upgrade": u.get("upgrade"),
            "expiry": u.get("end") or u.get("expiry"),
        })
    return out


def _parse_iso(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _trader_is_active(trader, now=None):
    """The API response does not always carry an 'active' flag, so work it
    out from the visit's start/end times (falling back to the flag)."""
    now = now or datetime.now(timezone.utc)
    start, end = _parse_iso(trader.get("activation")), _parse_iso(trader.get("expiry"))
    if start and end:
        return start <= now < end
    return bool(trader.get("active"))


def _summarize_void_trader(trader):
    """Baro Ki'Teer. 'active' tells us whether he's currently at his
    relay selling things, vs. still travelling to the next one."""
    if not trader:
        return None
    is_active = _trader_is_active(trader)
    inventory = [
        {"item": i.get("item"), "ducats": i.get("ducats"), "credits": i.get("credits")}
        for i in trader.get("inventory", [])
    ] if is_active else []
    return {
        "active": is_active,
        "location": trader.get("location"),
        "activation": trader.get("activation"),
        "expiry": trader.get("expiry"),
        "inventory": inventory,
    }


def _summarize_daily_deals(deals):
    """Darvo's one-item-a-day discount in the in-game Market."""
    if not deals:
        return []
    out = []
    for d in deals:
        out.append({
            "item": d.get("item"),
            "discount": d.get("discount"),
            "original_price": d.get("originalPrice"),
            "sale_price": d.get("salePrice"),
            "total": d.get("total"),
            "sold": d.get("sold"),
            "expiry": d.get("expiry"),
        })
    return out


def fetch_worldstate_async(callback):
    """Fetch in a background thread; `callback(result_or_none)` is called
    on completion from that background thread (the caller is responsible
    for marshalling back to the GUI thread if needed)."""
    def _worker():
        result = fetch_worldstate_summary()
        callback(result)
    threading.Thread(target=_worker, daemon=True).start()
