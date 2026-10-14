"""
Warframe Farm Tracker - Resource Database
===========================================
This file is intentionally kept separate from the app logic so it is easy
to edit by hand: add a resource, fix a farm location, add a new category.

Structure of each entry:
    "Resource Name": {
        "category": "Origin System" | "Plains of Eidolon" | "Orb Vallis" |
                     "Cambion Drift" | "Duviri / Circuit" | "Railjack (Empyrean)",
        "rarity": "common" | "uncommon" | "rare" | "special",
        "best_farm": "short human-readable tip on where/how to farm it",
    }

NOTE ON ACCURACY:
Warframe farming locations change over time (vaulting, reworks, new
tilesets, drop table changes). The locations below were cross-checked
across multiple sources as of October 2026, but Digital Extremes can
change any of this at any time. Everything here is editable at runtime
from the app itself (Settings -> Edit Resource DB), so if something is
wrong or outdated, just fix it in the app and it's saved to user_data.json
permanently - no need to touch this file or rebuild the app.

The Duviri / Circuit category intentionally has NO pre-filled resources.
Those names are too inconsistent across sources to trust blindly - add
your own as you see them drop in-game.
"""

RESOURCES = {

    # ---------------------------------------------------------------
    # ORIGIN SYSTEM - COMMON
    # ---------------------------------------------------------------
    "Ferrite": {
        "category": "Origin System",
        "rarity": "common",
        "best_farm": "Tikal (Earth) Excavation/Survival, or any Void Survival/Defense.",
    },
    "Rubedo": {
        "category": "Origin System",
        "rarity": "common",
        "best_farm": "Mars or Phobos nodes; drops heavily from Grineer enemies almost everywhere.",
    },
    "Salvage": {
        "category": "Origin System",
        "rarity": "common",
        "best_farm": "Mars - Arcadia (Corpus Survival), drops in bulk from Corpus enemies/containers.",
    },
    "Alloy Plate": {
        "category": "Origin System",
        "rarity": "common",
        "best_farm": "Ceres - Gabii or Draco, or Venus - Malva.",
    },
    "Polymer Bundle": {
        "category": "Origin System",
        "rarity": "common",
        "best_farm": "Saturn - Helene (Defense), yields large stacks per run.",
    },
    "Nano Spores": {
        "category": "Origin System",
        "rarity": "common",
        "best_farm": "Saturn - Helene (Defense) or Eris - Akkad; Infested tiles drop these constantly.",
    },
    "Circuits": {
        "category": "Origin System",
        "rarity": "common",
        "best_farm": "Venus - Kiliken, or Ceres - Gabii.",
    },

    # ---------------------------------------------------------------
    # ORIGIN SYSTEM - UNCOMMON
    # ---------------------------------------------------------------
    "Plastids": {
        "category": "Origin System",
        "rarity": "uncommon",
        "best_farm": "Eris - Akkad or Zabala, or Uranus - Ophelia.",
    },
    "Cryotic": {
        "category": "Origin System",
        "rarity": "uncommon",
        "best_farm": "Any Excavation mission; Europa - Valefor or Pluto - Hieracon are popular picks.",
    },
    "Oxium": {
        "category": "Origin System",
        "rarity": "uncommon",
        "best_farm": "Neptune - Galatea or Despina (Corpus-heavy nodes, high Oxium drop rate).",
    },
    "Hexenon": {
        "category": "Origin System",
        "rarity": "uncommon",
        "best_farm": "Jupiter tileset only - any Jupiter Corpus mission with good enemy density.",
    },
    "Tellurium": {
        "category": "Origin System",
        "rarity": "uncommon",
        "best_farm": "Dropped by larger Corpus/Grineer units (e.g. Bursas, heavy units) on Jupiter/Europa, or bought from Little Duck for standing.",
    },

    # ---------------------------------------------------------------
    # ORIGIN SYSTEM - RARE
    # ---------------------------------------------------------------
    "Neural Sensors": {
        "category": "Origin System",
        "rarity": "rare",
        "best_farm": "Jupiter - Cameria/Elara, or farm Alad V (Themisto) for guaranteed drops.",
    },
    "Orokin Cell": {
        "category": "Origin System",
        "rarity": "rare",
        "best_farm": "Ceres - Draco, Saturn - Piscinas, or boss runs (Sargas Ruk / Vor).",
    },
    "Neurodes": {
        "category": "Origin System",
        "rarity": "rare",
        "best_farm": "Earth - Tikal (Excavation) or Deimos nodes.",
    },
    "Gallium": {
        "category": "Origin System",
        "rarity": "rare",
        "best_farm": "Mars - Wahiba (Infested Survival) has a strong Gallium drop rate.",
    },
    "Morphics": {
        "category": "Origin System",
        "rarity": "rare",
        "best_farm": "Mercury - Apollodorus, or Mars - Wahiba.",
    },
    "Control Module": {
        "category": "Origin System",
        "rarity": "rare",
        "best_farm": "Neptune - Triton (Survival), or any Void Survival/Defense.",
    },
    "Argon Crystal": {
        "category": "Origin System",
        "rarity": "rare",
        "best_farm": "Void - Mot (Survival) or Ukko (Capture). Decays at daily reset - farm just before use.",
    },
    "Kuva": {
        "category": "Origin System",
        "rarity": "special",
        "best_farm": "Kuva Fortress - Taveuni (Survival) or any active Kuva Siphon/Flood mission.",
    },
    "Credits": {
        "category": "Origin System",
        "rarity": "common",
        "best_farm": "Dropped by enemies and containers in every mission and paid out as mission rewards. Edit this tip with your own favourite credit farm.",
    },
    "Endo": {
        "category": "Origin System",
        "rarity": "special",
        "best_farm": "Sortie rewards, Arbitrations, or selling duplicate mods/converting Ayatan Stars.",
    },

    # ---------------------------------------------------------------
    # PLAINS OF EIDOLON (Cetus)
    # ---------------------------------------------------------------
    "Cetus Wisp": {
        "category": "Plains of Eidolon",
        "rarity": "common",
        "best_farm": "Found near water on the Plains, mostly at night.",
    },
    "Mother Tooth": {
        "category": "Plains of Eidolon",
        "rarity": "uncommon",
        "best_farm": "Mined from rock outcrops on the Plains with the Plains Drill/Nosam Cutter.",
    },
    "Pyrotic Alloy": {
        "category": "Plains of Eidolon",
        "rarity": "uncommon",
        "best_farm": "Mined from rock outcrops, more common at higher mining tiers.",
    },

    # ---------------------------------------------------------------
    # ORB VALLIS (Fortuna)
    # ---------------------------------------------------------------
    "Venerdo": {
        "category": "Orb Vallis",
        "rarity": "common",
        "best_farm": "Mined from Orb Vallis outcrops with the Arctic Drill.",
    },
    "Calida": {
        "category": "Orb Vallis",
        "rarity": "uncommon",
        "best_farm": "Mined from warm vent outcrops in Orb Vallis.",
    },
    "Auroxium Alloy": {
        "category": "Orb Vallis",
        "rarity": "rare",
        "best_farm": "Dropped by Exploiter Orb and Profit-Taker Orb fights.",
    },

    # ---------------------------------------------------------------
    # CAMBION DRIFT (Deimos)
    # ---------------------------------------------------------------
    "Granum Crown": {
        "category": "Cambion Drift",
        "rarity": "special",
        "best_farm": "Bought from Daughter with standing, used to open Granum Void.",
    },
    "Fresh Thermia": {
        "category": "Cambion Drift",
        "rarity": "special",
        "best_farm": "Thermia Fracture events on Cambion Drift surface.",
    },
    "Mother's Blessing": {
        "category": "Cambion Drift",
        "rarity": "uncommon",
        "best_farm": "Isolation Vaults, Deimos.",
    },

    # ---------------------------------------------------------------
    # RAILJACK / EMPYREAN
    # ---------------------------------------------------------------
    "Cubic Diodes": {
        "category": "Railjack (Empyrean)",
        "rarity": "common",
        "best_farm": "Any Veil Proxima Railjack mission, destroy crewships/asteroids.",
    },
    "Pustrels": {
        "category": "Railjack (Empyrean)",
        "rarity": "common",
        "best_farm": "Any Railjack mission, mined from asteroids.",
    },
    "Copernics": {
        "category": "Railjack (Empyrean)",
        "rarity": "uncommon",
        "best_farm": "Veil Proxima nodes, Railjack.",
    },
    "Asterite": {
        "category": "Railjack (Empyrean)",
        "rarity": "rare",
        "best_farm": "Veil Proxima nodes, Railjack - lower drop rate, farm in longer missions.",
    },

    # ---------------------------------------------------------------
    # DUVIRI / CIRCUIT - intentionally empty, see module docstring
    # ---------------------------------------------------------------
}

CATEGORIES = [
    "Origin System",
    "Plains of Eidolon",
    "Orb Vallis",
    "Cambion Drift",
    "Railjack (Empyrean)",
    "Duviri / Circuit",
]

RARITY_ORDER = ["common", "uncommon", "rare", "special"]
