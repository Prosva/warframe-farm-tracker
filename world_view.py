"""
Text renderers for the World tab sections. Pure functions (no GUI): they
take the summary dict from worldstate_api and a translate function `t`,
and return the text to show. Planet / node / mission / item names are left
exactly as the game API gives them (English), only the headings and
connecting words are translated.
"""

from datetime import datetime, timezone

SECTIONS = ["summary", "system", "cycles", "arbitration", "fissures", "steel", "invasions", "special"]
SECTION_LABELS = {
    "summary": "Baro, Darvo, Sortie",
    "system": "System events",
    "cycles": "Planet cycles",
    "arbitration": "Arbitration",
    "fissures": "Void fissures",
    "steel": "Steel Path fissures",
    "invasions": "Invasions",
    "special": "Special events",
}

# Which state follows which, so a cycle line can say what comes next.
_NEXT_STATE = {"day": "night", "night": "day", "warm": "cold", "cold": "warm",
               "fass": "vome", "vome": "fass"}


def remaining(iso, now=None):
    """'1h 05m', '12m', '2d 3h', or None for missing/unparseable, 'ended'
    once the time has passed."""
    if not iso:
        return None
    try:
        target = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return None
    now = now or datetime.now(timezone.utc)
    seconds = int((target - now).total_seconds())
    if seconds <= 0:
        return "ended"
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes:02d}m"
    return f"{minutes}m"


def _left(iso, t, now):
    r = remaining(iso, now)
    if r is None:
        return ""
    return t("ended") if r == "ended" else f"{r} {t('left')}"


def _empty(t):
    return t("Nothing here right now.")


def render_section(section, data, t, now=None):
    now = now or datetime.now(timezone.utc)
    fn = _RENDERERS.get(section, _summary)
    text = fn(data or {}, t, now)
    return text if text.strip() else _empty(t)


# ----------------------------------------------------------------------
def _summary(data, t, now):
    lines = []
    trader = data.get("void_trader")
    if trader:
        lines.append(t("Void Trader (Baro Ki'Teer):"))
        if trader.get("active"):
            lines.append(f"  {t('Here now at')} {trader.get('location')} ({_left(trader.get('expiry'), t, now)})")
            inv = trader.get("inventory") or []
            if inv:
                lines.append(f"  {t('His inventory:')}")
                for item in inv:
                    lines.append(f"    - {item['item']} ({item['ducats']} {t('ducats')} "
                                 f"+ {item['credits']} {t('credits')})")
        else:
            until = remaining(trader.get("activation"), now)
            loc = f" - {trader.get('location')}" if trader.get("location") else ""
            lines.append(f"  {t('Not here right now. Next visit:')} {until}{loc}")
        lines.append("")

    deals = data.get("daily_deals") or []
    if deals:
        lines.append(t("Darvo's Deal of the Day:"))
        for d in deals:
            lines.append(f"  - {d['item']}: {d['sale_price']} cr ({d['discount']}% {t('off')}, "
                         f"{d['sold']}/{d['total']} {t('sold')})")
        lines.append("")

    sortie = data.get("sortie")
    if sortie:
        lines.append(f"{t('Sortie')} - {sortie.get('faction')} ({sortie.get('boss')}):")
        for m in sortie.get("missions", []):
            lines.append(f"  - {m['node']}: {m['missionType']}")
    return "\n".join(lines)


def _system(data, t, now):
    lines = []
    upgrades = data.get("global_upgrades") or []
    lines.append(t("Global boosters:"))
    if upgrades:
        for u in upgrades:
            lines.append(f"  - {u.get('desc')} ({_left(u.get('expiry'), t, now)})")
    else:
        lines.append(f"  {t('No active boosters.')}")
    lines.append("")

    news = data.get("news") or []
    if news:
        lines.append(t("Latest announcements:"))
        for n in news:
            tags = []
            if n.get("update"):
                tags.append(t("Update"))
            if n.get("prime_access"):
                tags.append("Prime Access")
            if n.get("stream"):
                tags.append(t("Stream"))
            tag = f" [{', '.join(tags)}]" if tags else ""
            lines.append(f"  {n.get('date', '')[:10]}  {n.get('message')}{tag}")
    return "\n".join(lines)


def _cycles(data, t, now):
    lines = []
    rows = [("Cetus (Plains of Eidolon)", data.get("cetus_cycle")),
            ("Orb Vallis", data.get("vallis_cycle")),
            ("Cambion Drift", data.get("cambion_cycle"))]
    for name, cycle in rows:
        if not cycle:
            lines.append(f"{name}: {t('no data')}")
            lines.append("")
            continue
        state = str(cycle.get("state") or "").lower()
        nxt = _NEXT_STATE.get(state)
        left = remaining(cycle.get("expiry"), now)
        lines.append(f"{name}: {state.upper()}")
        if left and left != "ended":
            tail = f"  {t('ends in')} {left}"
            if nxt:
                tail += f"  ->  {nxt.upper()}"
            lines.append(tail)
        lines.append("")
    return "\n".join(lines)


def _arbitration(data, t, now):
    arb = data.get("arbitration")
    if not arb:
        return t("No arbitration data right now (the data source returned nothing).")
    lines = [f"{arb.get('node')}",
             f"  {arb.get('type')}  [{arb.get('enemy')}]" + (f"  ({t('Archwing')})" if arb.get("archwing") else "")]
    left = _left(arb.get("expiry"), t, now)
    if left:
        lines.append(f"  {left}")
    return "\n".join(lines)


def _fissure_lines(items, t, now):
    by_tier = {}
    for f in items:
        by_tier.setdefault((f.get("tier") or 0, f.get("tier_name") or "?"), []).append(f)
    lines = []
    for (_, tier_name), group in sorted(by_tier.items()):
        lines.append(f"{tier_name}")
        for f in sorted(group, key=lambda x: x.get("expiry") or ""):
            storm = "  [Void Storm]" if f.get("is_storm") else ""
            left = _left(f.get("expiry"), t, now)
            lines.append(f"  {f.get('node')} - {f.get('missionType')}  [{f.get('enemy')}]{storm}  {left}")
        lines.append("")
    return "\n".join(lines)


def _fissures(data, t, now):
    return _fissure_lines([f for f in data.get("fissures") or [] if not f.get("is_hard")], t, now)


def _steel(data, t, now):
    return _fissure_lines([f for f in data.get("fissures") or [] if f.get("is_hard")], t, now)


def _invasions(data, t, now):
    lines = []
    for inv in data.get("invasions") or []:
        pct = inv.get("completion")
        try:
            pct_txt = f"  {float(pct):.0f}%"
        except (TypeError, ValueError):
            pct_txt = ""
        lines.append(f"{inv.get('node')}{pct_txt}")
        if inv.get("desc"):
            lines.append(f"  {inv['desc']}")
        if inv.get("attacker_reward"):
            lines.append(f"  {inv.get('attacker') or t('Attackers')}: {inv['attacker_reward']}")
        if inv.get("defender_reward"):
            lines.append(f"  {inv.get('defender') or t('Defenders')}: {inv['defender_reward']}")
        lines.append("")
    return "\n".join(lines)


def _special(data, t, now):
    lines = []
    events = data.get("events") or []
    if events:
        lines.append(t("Events:"))
        for ev in events:
            lines.append(f"{ev.get('name')}  ({_left(ev.get('expiry'), t, now)})")
            if ev.get("tooltip"):
                lines.append(f"  {ev['tooltip']}")
            if ev.get("node"):
                lines.append(f"  {ev['node']}")
            if ev.get("max_score"):
                lines.append(f"  {t('Progress')}: {ev.get('score', 0)} / {ev['max_score']}")
            for r in ev.get("rewards") or []:
                lines.append(f"  {t('Reward')}: {r}")
            lines.append("")
    alerts = data.get("alerts") or []
    if alerts:
        lines.append(t("Alerts:"))
        for al in alerts:
            lines.append(f"{al.get('node')} - {al.get('type')}  ({_left(al.get('expiry'), t, now)})")
            if al.get("reward"):
                lines.append(f"  {t('Reward')}: {al['reward']}")
            lines.append("")
    return "\n".join(lines)


_RENDERERS = {
    "summary": _summary, "system": _system, "cycles": _cycles,
    "arbitration": _arbitration, "fissures": _fissures, "steel": _steel,
    "invasions": _invasions, "special": _special,
}
