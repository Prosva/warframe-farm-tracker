"""
Persistent storage for the Farm Tracker.

Everything the user enters (current amounts, goals, farm history, custom
resources added under Duviri/Circuit, and edits to the built-in resource
database) is saved to a JSON file next to the executable, so it survives
restarts and app updates.
"""

import glob
import json
import os
import shutil
import sys
from datetime import datetime, timezone, timedelta

from resources_data import RESOURCES


def _app_dir():
    """Folder where the .exe (or script) lives - works both from source
    and from a PyInstaller-built executable."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


DATA_FILE = os.path.join(_app_dir(), "user_data.json")


def _default_state():
    return {
        "tracked": {},        # resource_name -> {"amount": int, "goal": int or None}
        "history": {},        # resource_name -> [ {"date": "YYYY-MM-DD", "delta": int} ]
        "custom_resources": {},  # user-added resources, same shape as RESOURCES entries
        "resource_overrides": {},  # edits to built-in entries (e.g. corrected farm tip)
        "presets": {},  # preset_name -> {resource_name: target_amount, ...}
        "pickup_names": {},  # OCR'd pickup text (normalized) -> resource name or "__ignore__"
        "mastery": {"done": {}},  # item name -> True once the player ticked it as mastered
        "settings": {
            "hotkey_toggle": "ctrl+shift+f",
            "always_on_top": True,
            "opacity": 0.92,
            "language": "en",
            "compact_mode": False,
            "auto_pickup": False,
            "pickup_debug": True,
            "active_tab": "resources",
            "notify_goal": True,
            "notify_baro": True,
            "sound": True,
            "baro_watch": "",        # comma-separated item names to watch for
            "last_baro_notified": "",  # activation time of the visit already announced
            "my_mr": 0,
        },
    }


def load_state():
    if not os.path.exists(DATA_FILE):
        state = _default_state()
        save_state(state)
        return state
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)
    except (json.JSONDecodeError, OSError):
        # Corrupt file - back it up and start fresh rather than crashing.
        backup = DATA_FILE + ".bak"
        try:
            os.replace(DATA_FILE, backup)
        except OSError:
            pass
        state = _default_state()
        save_state(state)
        return state

    # Fill in any keys that might be missing (e.g. after an app update).
    defaults = _default_state()
    for key, value in defaults.items():
        state.setdefault(key, value)
    # "settings" is a nested dict - an older save missing a newly-added
    # setting (e.g. "language") would otherwise crash on first use.
    for key, value in defaults["settings"].items():
        state["settings"].setdefault(key, value)
    return state


def save_state(state):
    tmp_file = DATA_FILE + ".tmp"
    with open(tmp_file, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp_file, DATA_FILE)


def all_resources(state):
    """Merge built-in resources with user overrides and custom additions
    into a single dict, ready to display."""
    merged = {}
    for name, info in RESOURCES.items():
        merged[name] = dict(info)
    for name, info in state.get("custom_resources", {}).items():
        merged[name] = dict(info)
    # Overrides apply last so edits always win, whether the resource is
    # built-in or user-added.
    for name, info in state.get("resource_overrides", {}).items():
        if name in merged:
            merged[name].update(info)
    return merged


def add_farm_entry(state, resource_name, delta):
    """Record `delta` units gained for resource_name, today."""
    tracked = state["tracked"].setdefault(resource_name, {"amount": 0, "goal": None})
    tracked["amount"] = tracked.get("amount", 0) + delta

    today = datetime.now().strftime("%Y-%m-%d")
    day_log = state["history"].setdefault(resource_name, [])
    if day_log and day_log[-1]["date"] == today:
        day_log[-1]["delta"] += delta
    else:
        day_log.append({"date": today, "delta": delta})

    save_state(state)


def set_goal(state, resource_name, goal):
    tracked = state["tracked"].setdefault(resource_name, {"amount": 0, "goal": None})
    tracked["goal"] = goal
    save_state(state)


def set_amount(state, resource_name, amount):
    tracked = state["tracked"].setdefault(resource_name, {"amount": 0, "goal": None})
    tracked["amount"] = amount
    save_state(state)


def undo_last_delta(state, resource_name, delta):
    """Reverse a single add_farm_entry call (meant for an accidental
    click, e.g. +50 instead of +5). Only safely reverses something added
    *today* - if the day has rolled over since, it still adjusts the
    total but can't un-merge an old day's history line, so the app only
    offers Undo right after an action in the same session."""
    tracked = state["tracked"].get(resource_name)
    if not tracked:
        return
    tracked["amount"] = tracked.get("amount", 0) - delta

    today = datetime.now().strftime("%Y-%m-%d")
    day_log = state["history"].get(resource_name, [])
    if day_log and day_log[-1]["date"] == today:
        day_log[-1]["delta"] -= delta
        if day_log[-1]["delta"] == 0:
            day_log.pop()
    save_state(state)


def compute_farm_rate(state, resource_name):
    """Rough farming speed for this resource: average amount gained per
    day the player actually logged something, based on history. Returns
    None if there's no history yet (nothing to estimate from)."""
    log = state["history"].get(resource_name, [])
    gained_entries = [e["delta"] for e in log if e["delta"] > 0]
    if not gained_entries:
        return None
    total_gained = sum(gained_entries)
    days_active = len(log)  # one entry per day that had any activity
    if days_active == 0:
        return None
    return total_gained / days_active


def estimate_days_to_goal(state, resource_name):
    """Returns an estimated number of days to reach the goal at the
    current average farm rate, or None if there's no goal, no rate yet,
    or the goal is already reached."""
    tracked = state["tracked"].get(resource_name)
    if not tracked or not tracked.get("goal"):
        return None
    remaining = tracked["goal"] - tracked.get("amount", 0)
    if remaining <= 0:
        return 0
    rate = compute_farm_rate(state, resource_name)
    if not rate or rate <= 0:
        return None
    return remaining / rate


def start_tracking(state, resource_name):
    """Add a resource to the tracked panel (amount 0, no goal) if it's
    not already being tracked. Does nothing if it's already there -
    never resets an existing amount."""
    if resource_name not in state["tracked"]:
        state["tracked"][resource_name] = {"amount": 0, "goal": None}
        save_state(state)


def remove_tracked(state, resource_name):
    """Stop showing this resource on the panel. History is kept, so if
    the user tracks it again later the farm log isn't lost."""
    if resource_name in state["tracked"]:
        del state["tracked"][resource_name]
        save_state(state)


def add_custom_resource(state, name, category, rarity, best_farm):
    state["custom_resources"][name] = {
        "category": category,
        "rarity": rarity,
        "best_farm": best_farm,
    }
    save_state(state)


def override_resource(state, name, **fields):
    entry = state["resource_overrides"].setdefault(name, {})
    entry.update({k: v for k, v in fields.items() if v is not None})
    save_state(state)


def get_language(state):
    return state["settings"].get("language", "en")


def set_language(state, language_code):
    state["settings"]["language"] = language_code
    save_state(state)


def get_compact_mode(state):
    return bool(state["settings"].get("compact_mode", False))


def set_compact_mode(state, enabled):
    state["settings"]["compact_mode"] = bool(enabled)
    save_state(state)


# ----------------------------------------------------------------------
# Presets - a user-defined set of (resource -> target amount) pairs that
# can be applied in one click (e.g. "everything I need for Wisp Prime").
# Deliberately NOT pre-filled with real blueprint costs: Warframe has
# hundreds of blueprints and getting exact numbers wrong would be worse
# than not having them, so the player builds their own from what they
# know they need.
# ----------------------------------------------------------------------

def save_preset(state, preset_name, resource_goals):
    """resource_goals: dict of {resource_name: target_amount}."""
    state["presets"][preset_name] = dict(resource_goals)
    save_state(state)


def delete_preset(state, preset_name):
    state["presets"].pop(preset_name, None)
    save_state(state)


def apply_preset(state, preset_name):
    """Starts tracking every resource in the preset (if not already) and
    sets its goal to the preset's target amount. Never lowers/overwrites
    an amount already farmed - only sets the goal."""
    preset = state["presets"].get(preset_name)
    if not preset:
        return
    for resource_name, target_amount in preset.items():
        start_tracking(state, resource_name)
        set_goal(state, resource_name, target_amount)


# ----------------------------------------------------------------------
# Argon Crystal daily decay.
# Confirmed game mechanic: any un-spent Argon Crystals are wiped at the
# Warframe daily reset, which happens at 00:00 UTC. This is a long-stable
# rule (unlike farm locations), so it's safe to rely on directly rather
# than making it user-editable.
# ----------------------------------------------------------------------

def seconds_until_argon_decay():
    now = datetime.now(timezone.utc)
    next_reset = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return (next_reset - now).total_seconds()


# ----------------------------------------------------------------------
# Auto-pickup (OCR) - which on-screen pickup text means which resource.
# ----------------------------------------------------------------------

def get_pickup_names(state):
    return state.get("pickup_names", {})


def set_pickup_name(state, normalized_text, target):
    """target: a resource name, or "__ignore__" for things not tracked
    (credits, energy...)."""
    state.setdefault("pickup_names", {})[normalized_text] = target
    save_state(state)


def get_setting(state, key, default=None):
    return state["settings"].get(key, default)


def set_setting(state, key, value):
    state["settings"][key] = value
    save_state(state)


# ----------------------------------------------------------------------
# Mastery checklist
# ----------------------------------------------------------------------

def mastery_done(state):
    return state.setdefault("mastery", {"done": {}}).setdefault("done", {})


def set_mastered(state, item_name, value):
    done = mastery_done(state)
    if value:
        done[item_name] = True
    else:
        done.pop(item_name, None)
    save_state(state)


# ----------------------------------------------------------------------
# Backups
# ----------------------------------------------------------------------

def export_backup(dest_path):
    shutil.copyfile(DATA_FILE, dest_path)


def import_backup(src_path):
    """Replace the current data with a backup file. Validates it first and
    keeps the old file as user_data.json.before_import. Raises ValueError
    for a file that is not a Farm Tracker backup."""
    with open(src_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict) or not isinstance(data.get("tracked"), dict):
        raise ValueError("not a Farm Tracker backup")
    if os.path.exists(DATA_FILE):
        shutil.copyfile(DATA_FILE, DATA_FILE + ".before_import")
    shutil.copyfile(src_path, DATA_FILE)


def auto_backup(keep=7):
    """One copy per day in a `backups` folder next to the data file; the
    newest `keep` are kept. Safe to call on every start-up."""
    if not os.path.exists(DATA_FILE):
        return
    folder = os.path.join(os.path.dirname(DATA_FILE), "backups")
    try:
        os.makedirs(folder, exist_ok=True)
        today = datetime.now().strftime("%Y-%m-%d")
        target = os.path.join(folder, f"user_data_{today}.json")
        if not os.path.exists(target):
            shutil.copyfile(DATA_FILE, target)
        old = sorted(glob.glob(os.path.join(folder, "user_data_*.json")))
        for path in old[:-keep]:
            os.remove(path)
    except OSError:
        pass
