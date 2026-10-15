"""
Warframe Farm Tracker - overlay app.

A small, always-on-top window you keep open while playing Warframe.
Track several resources at once, each with its own quick +/- buttons,
progress bar, and farm-rate/ETA estimate. Banners surface live game
events worth acting on. English/Russian UI switch (planet and node
names always stay in English, since that's how the game shows them).

Run with:  python main.py
Build to a standalone .exe with PyInstaller - see README.md.
"""

import queue
import time as time_module
from datetime import datetime, timezone
import tkinter as tk
from tkinter import messagebox, filedialog

import customtkinter as ctk

import storage
import ee_log_reader
import pickup_ocr
import session as session_module
import mastery
import worldstate_api
import world_view
import about_info
import webbrowser
import theme
import locales
from resources_data import CATEGORIES, RARITY_ORDER

HOTKEY_ERROR = ""
try:
    from pynput import keyboard as pynput_keyboard
    HOTKEY_AVAILABLE = True
except Exception as _exc:   # ImportError, or a backend that failed to load
    HOTKEY_AVAILABLE = False
    HOTKEY_ERROR = repr(_exc)


APP_TITLE = "Farm Tracker"
DEFAULT_HOTKEY = "<ctrl>+<shift>+f"
GHOST_HOTKEY = "<ctrl>+<shift>+g"
TAB_KEYS = ["resources", "session", "world", "mastery", "settings", "support"]
TAB_LABELS = {"resources": "Resources", "session": "Session", "world": "World",
              "mastery": "Mastery", "settings": "More", "support": "Support"}
SESSION_TICK_MS = 5 * 1000
NOTICE_SECONDS = 90
QUICK_DELTAS = [-10, -1, 1, 5, 10, 50]
WORLDSTATE_POLL_MS = 5 * 60 * 1000  # 5 minutes
ARGON_TICK_MS = 30 * 1000           # 30 seconds
ARGON_WARNING_SECONDS = 3 * 3600    # warn when < 3 hours left

ctk.set_appearance_mode("dark")

ROTATION_SEQUENCE = ["A", "A", "B", "C"]


def fmt_num(n):
    """1234567 -> '1 234 567' (credits get big)."""
    return f"{int(n):,}".replace(",", " ")


def rotation_letter(count):
    """count = how many 5-min ticks / waves / rounds have passed.
    Returns None if no rotation has triggered yet."""
    if count < 1:
        return None
    return ROTATION_SEQUENCE[(count - 1) % 4]


def _format_time_remaining(iso_string):
    if not iso_string:
        return None
    try:
        cleaned = iso_string.replace("Z", "+00:00")
        target = datetime.fromisoformat(cleaned)
    except ValueError:
        return None
    now = datetime.now(timezone.utc)
    delta = target - now
    total_seconds = int(delta.total_seconds())
    sign = "-" if total_seconds < 0 else ""
    total_seconds = abs(total_seconds)
    days, rem = divmod(total_seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    if days:
        return f"{sign}{days}d {hours}h"
    if hours:
        return f"{sign}{hours}h {minutes}m"
    return f"{sign}{minutes}m"


class FarmTrackerApp:
    def __init__(self, root):
        self.root = root
        storage.auto_backup()
        self.state = storage.load_state()
        self.lang = storage.get_language(self.state)
        self.compact = storage.get_compact_mode(self.state)
        self.event_queue = queue.Queue()
        self._row_widgets = {}
        self._latest_worldstate = None
        self._mission_banner = None
        self._hot_banner = None

        self.root.title(APP_TITLE)
        self.root.configure(fg_color=theme.BG)
        self.root.attributes("-topmost", bool(self.state["settings"].get("always_on_top", True)))
        try:
            self.root.attributes("-alpha", float(self.state["settings"].get("opacity", 0.95)))
        except tk.TclError:
            pass
        self.root.geometry("470x500+80+80")
        self.root.minsize(330, 260)
        self.root.resizable(True, True)

        # Mission kill counter (estimated from EE.log spawn counters).
        self._kills_total = None      # estimate for the current mission
        self._kills_baseline = 0      # value at the last manual "Reset"
        self._last_spawned = None     # used to detect a new mission

        # Auto-pickup (OCR) state.
        self._pickup_watcher = None
        self._pickup_status = ""
        self._pickup_pending = {}     # normalized text -> amount seen before it was assigned
        self._pickup_asking = None    # normalized text currently being asked about
        self._pickup_ask_queue = []
        self._pickup_banner = None
        self._pickup_display_names = {}

        # Session stats, mastery checklist, world tab, ghost mode.
        self._session = session_module.Session()
        self._active_tab = storage.get_setting(self.state, "active_tab", "resources")
        self._mastery_items = mastery.load_cache()
        self._mastery_loading = False
        self._mastery_limit = 40
        self._worldstate_loaded = False
        self._ghost = False

        self._build_ui()
        self._rebuild_tracked_panel()

        self._collapsed = False
        self._start_ee_log_watcher()
        if self.pickup_var.get():
            self._start_pickup_watcher()
        self._start_hotkey_listener()
        self._poll_worldstate_loop()
        self._tick_argon_decay()
        self.root.after(SESSION_TICK_MS, self._tick_session)

        self.root.after(200, self._poll_events)

    # ------------------------------------------------------------------
    # Translation helpers
    # ------------------------------------------------------------------
    def t(self, text):
        if self.lang == "ru":
            return locales.TRANSLATIONS.get(text, text)
        return text

    def rarity_text(self, rarity):
        if self.lang == "ru":
            return locales.RARITY_RU.get(rarity, rarity.upper())
        return rarity.upper()

    def category_display(self, category):
        if self.lang == "ru":
            return locales.CATEGORY_RU.get(category, category)
        return category

    def category_choices_display(self):
        return [self.category_display(c) for c in CATEGORIES]

    def category_from_display(self, display_text):
        for cat in CATEGORIES:
            if self.category_display(cat) == display_text:
                return cat
        return display_text  # fallback: already English

    def farm_tip(self, resource_name, info):
        english_tip = info.get("best_farm", "No farm tip saved yet.")
        if self.lang == "ru":
            return locales.RESOURCE_TIPS_RU.get(resource_name, english_tip)
        return english_tip

    def _set_language(self, code):
        if code == self.lang:
            return
        self.lang = code
        storage.set_language(self.state, code)
        self._rebuild_everything()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _rebuild_everything(self):
        self._cancel_rotation_job()
        self.outer.destroy()
        if getattr(self, "_collapsed", False):
            self._collapsed = False
            self.root.minsize(300, 220)
            w, h = getattr(self, "_expanded_geometry", (380, 380))
            self.root.geometry(f"{w}x{h}")
        self._row_widgets.clear()
        self._mission_banner = None
        self._hot_banner = None
        self._pickup_banner = None
        if self._pickup_asking is not None:   # its banner is gone: ask again
            self._pickup_ask_queue.insert(0, self._pickup_asking)
            self._pickup_asking = None
        self._build_ui()
        self._show_next_pickup_question()
        self._rebuild_tracked_panel()

    def _build_ui(self):
        self.outer = ctk.CTkFrame(self.root, fg_color=theme.BG)
        self.outer.pack(fill="both", expand=True, padx=8, pady=8)

        # --- header -------------------------------------------------------
        header = ctk.CTkFrame(self.outer, fg_color="transparent")
        header.pack(fill="x", pady=(0, 2))
        ctk.CTkLabel(
            header, text=f"⚡ {self.t('Farm Tracker')}", font=(theme.FONT_FAMILY, 16, "bold"),
            text_color=theme.ACCENT,
        ).pack(side="left")
        ctk.CTkButton(
            header, text="—", width=28, height=28, fg_color=theme.BG_CARD,
            hover_color=theme.BG_CARD_HOVER, command=self._toggle_collapse,
        ).pack(side="right")
        ctk.CTkLabel(
            header, text=f"Created by {about_info.AUTHOR}", font=(theme.FONT_FAMILY, 10),
            text_color=theme.TEXT_DIM,
        ).pack(side="right", padx=(0, 8))

        # Everything below the header lives in one frame so collapsing is a
        # single pack_forget plus a window shrink.
        self.content = ctk.CTkFrame(self.outer, fg_color="transparent")
        self.content.pack(fill="both", expand=True)

        # --- mission kill counter (always visible, above the tabs) -------------
        kills_row = ctk.CTkFrame(self.content, fg_color=theme.BG_CARD, corner_radius=8)
        kills_row.pack(fill="x", pady=(0, 6))
        self.kills_label = ctk.CTkLabel(
            kills_row, text="", font=(theme.FONT_FAMILY, 13, "bold"),
            text_color=theme.TEXT, anchor="w",
        )
        self.kills_label.pack(side="left", padx=10, pady=4)
        ctk.CTkButton(
            kills_row, text=self.t("Reset"), width=56, height=24,
            fg_color=theme.ACCENT, hover_color=theme.ACCENT_HOVER,
            command=self._reset_kills,
        ).pack(side="right", padx=6, pady=4)
        self._refresh_kills_label()

        # --- banners / notices (mission complete, hot right now, goal reached...)
        self.banner_area = ctk.CTkFrame(self.content, fg_color="transparent", height=0)
        self.banner_area.pack(fill="x")

        # --- tab bar -----------------------------------------------------------
        labels = [self.t(TAB_LABELS[k]) for k in TAB_KEYS]
        self._tab_label_to_key = dict(zip(labels, TAB_KEYS))
        self.tab_bar = ctk.CTkSegmentedButton(
            self.content, values=labels, command=self._on_tab_selected,
            fg_color=theme.BG_CARD, selected_color=theme.ACCENT,
            selected_hover_color=theme.ACCENT_HOVER, unselected_color=theme.BG_CARD,
            unselected_hover_color=theme.BG_CARD_HOVER, font=(theme.FONT_FAMILY, 10, "bold"),
        )
        self.tab_bar.pack(fill="x", pady=(0, 6))

        self.tab_container = ctk.CTkFrame(self.content, fg_color="transparent")
        self.tab_container.pack(fill="both", expand=True)
        self.tab_frames = {
            key: ctk.CTkFrame(self.tab_container, fg_color="transparent") for key in TAB_KEYS
        }
        self._build_resources_tab(self.tab_frames["resources"])
        self._build_session_tab(self.tab_frames["session"])
        self._build_world_tab(self.tab_frames["world"])
        self._build_mastery_tab(self.tab_frames["mastery"])
        self._build_settings_tab(self.tab_frames["settings"])
        self._build_support_tab(self.tab_frames["support"])
        self._show_tab(self._active_tab)

    # ------------------------------------------------------------------
    # Tabs
    # ------------------------------------------------------------------
    def _on_tab_selected(self, label):
        self._show_tab(self._tab_label_to_key.get(label, "resources"))

    def _show_tab(self, key):
        if key not in self.tab_frames:
            key = "resources"
        for frame in self.tab_frames.values():
            frame.pack_forget()
        self.tab_frames[key].pack(fill="both", expand=True)
        self._active_tab = key
        self.tab_bar.set(self.t(TAB_LABELS[key]))
        if storage.get_setting(self.state, "active_tab") != key:
            storage.set_setting(self.state, "active_tab", key)
        if key == "session":
            self._refresh_session_tab()
        elif key == "world":
            self._render_world_tab()
        elif key == "mastery":
            self._on_mastery_tab_shown()

    # ---------------------------------------------------------------- Resources tab
    def _build_resources_tab(self, parent):
        # Bottom buttons first (side="bottom") so they never get squeezed out.
        bottom = ctk.CTkFrame(parent, fg_color="transparent")
        bottom.pack(side="bottom", fill="x", pady=(6, 0))
        for text, kind in (("+ New resource", "add_resource"), ("Rotation Tracker", "rotation"),
                           ("Presets", "presets")):
            ctk.CTkButton(
                bottom, text=self.t(text), height=28, fg_color=theme.BG_CARD,
                hover_color=theme.BG_CARD_HOVER, font=(theme.FONT_FAMILY, 11),
                command=lambda k=kind: self._toggle_panel(k),
            ).pack(side="left", padx=(0, 4))

        # --- auto-pickup (OCR) switch ------------------------------------------
        pickup_row = ctk.CTkFrame(parent, fg_color="transparent")
        pickup_row.pack(fill="x", pady=(0, 6))
        self.pickup_var = tk.BooleanVar(value=bool(storage.get_setting(self.state, "auto_pickup", False)))
        ctk.CTkSwitch(
            pickup_row, text=self.t("Auto-pickup (OCR)"), variable=self.pickup_var,
            command=self._on_toggle_pickup, progress_color=theme.ACCENT,
            font=(theme.FONT_FAMILY, 11),
        ).pack(anchor="w")
        self.pickup_status_label = ctk.CTkLabel(
            pickup_row, text="", text_color=theme.WARNING, font=(theme.FONT_FAMILY, 10),
            wraplength=360, justify="left", anchor="w",
        )   # packed under the switch only when there is something to say
        self._refresh_pickup_status()

        self.body = ctk.CTkFrame(parent, fg_color="transparent")
        self.body.pack(fill="both", expand=True)

        # --- add-resource row -----------------------------------------------
        add_frame = ctk.CTkFrame(self.body, fg_color="transparent")
        add_frame.pack(fill="x", pady=(0, 8))

        # Search box + a small scrollable list that opens under it. Typing
        # filters the list; clicking a result (or Enter) starts tracking it.
        self._picker_open = False
        self.picker_entry = ctk.CTkEntry(
            add_frame,
            placeholder_text=self.t("Search resource..."),
            fg_color=theme.BG_INPUT, border_color=theme.BORDER,
        )
        self.picker_entry.pack(side="left", fill="x", expand=True)
        self.picker_entry.bind("<KeyRelease>", self._on_picker_key)
        self.picker_entry.bind("<Return>", lambda e: self._track_first_match())
        self.picker_entry.bind("<Escape>", lambda e: self._close_picker())
        ctk.CTkButton(
            add_frame, text="▾", width=30, fg_color=theme.BG_CARD,
            hover_color=theme.BG_CARD_HOVER, command=self._toggle_picker,
        ).pack(side="left", padx=(4, 0))
        ctk.CTkButton(
            add_frame, text=self.t("Track"), width=64, fg_color=theme.ACCENT,
            hover_color=theme.ACCENT_HOVER, command=self._track_first_match,
        ).pack(side="left", padx=(4, 0))
        self.picker_list = ctk.CTkScrollableFrame(
            self.body, height=120, fg_color=theme.BG_CARD,
            scrollbar_button_color=theme.ACCENT,
        )   # packed only while open (see _open_picker)

        # --- inline panel slot (Rotation Tracker / Presets / New resource) -----
        # Only one of these is open at a time, right here in the main window -
        # no separate popup windows for these three.
        self.panel_container = ctk.CTkFrame(self.body, fg_color="transparent", height=0)
        self.panel_container.pack(fill="x")
        self._active_panel_kind = None
        self._active_panel_frame = None
        self._rotation_job = None

        # --- scrollable tracked-resources panel -------------------------------
        self.tracked_frame = ctk.CTkScrollableFrame(
            self.body, fg_color="transparent", scrollbar_button_color=theme.ACCENT,
        )
        self.tracked_frame.pack(fill="both", expand=True)

    # ---------------------------------------------------------------- Session tab
    def _build_session_tab(self, parent):
        top = ctk.CTkFrame(parent, fg_color="transparent")
        top.pack(fill="x")
        self.session_time_label = ctk.CTkLabel(
            top, text="", font=(theme.FONT_FAMILY, 12, "bold"), text_color=theme.TEXT, anchor="w")
        self.session_time_label.pack(side="left")
        ctk.CTkButton(
            top, text=self.t("Reset session"), width=120, height=26, fg_color=theme.ACCENT,
            hover_color=theme.ACCENT_HOVER, command=self._reset_session,
        ).pack(side="right")
        self.session_kills_label = ctk.CTkLabel(
            parent, text="", font=(theme.FONT_FAMILY, 11), text_color=theme.TEXT_DIM, anchor="w")
        self.session_kills_label.pack(fill="x", pady=(2, 6))

        # EE.log context line sits at the bottom of this tab.
        self.context_label = ctk.CTkLabel(
            parent, text=self.t("Game context: unknown"), text_color=theme.TEXT_DIM,
            font=(theme.FONT_FAMILY, 10), anchor="w",
        )
        self.context_label.pack(side="bottom", fill="x", pady=(6, 0))

        self.session_list = ctk.CTkScrollableFrame(
            parent, fg_color="transparent", scrollbar_button_color=theme.ACCENT)
        self.session_list.pack(fill="both", expand=True)
        self._refresh_session_tab()

    def _reset_session(self):
        self._session.reset()
        self._refresh_session_tab()

    def _tick_session(self):
        if self._active_tab == "session":
            self._refresh_session_tab()
        self.root.after(SESSION_TICK_MS, self._tick_session)

    def _refresh_session_tab(self):
        sess = self._session
        self.session_time_label.configure(
            text=f"{self.t('Session:')} {session_module.format_duration(sess.elapsed())}")
        total_kills = sess.kills_finished + (self._kills_total or 0)
        self.session_kills_label.configure(
            text=f"☠ {self.t('Kills this session:')} ~{total_kills}")

        for child in self.session_list.winfo_children():
            child.destroy()
        gained = sess.gained()
        if not gained:
            ctk.CTkLabel(
                self.session_list, text=self.t("Nothing gained yet. Pick things up or press + on a resource."),
                text_color=theme.TEXT_DIM, wraplength=340, justify="left",
            ).pack(anchor="w", pady=6)
        per_hour = self.t("/h")
        for name, amount in sorted(gained.items(), key=lambda kv: -kv[1]):
            card = ctk.CTkFrame(self.session_list, fg_color=theme.BG_CARD, corner_radius=8)
            card.pack(fill="x", pady=3)
            sign = "+" if amount >= 0 else ""
            ctk.CTkLabel(
                card, text=f"{name}: {sign}{fmt_num(amount)}", font=(theme.FONT_FAMILY, 12, "bold"),
                text_color=theme.TEXT, anchor="w",
            ).pack(fill="x", padx=10, pady=(6, 0))
            detail = []
            rate = sess.rate_per_hour(name)
            if rate:
                detail.append(f"≈ {fmt_num(round(rate))}{per_hour}")
            tracked = self.state["tracked"].get(name, {})
            goal = tracked.get("goal")
            if goal:
                remaining = goal - tracked.get("amount", 0)
                if remaining <= 0:
                    detail.append(self.t("goal reached"))
                else:
                    eta = sess.eta_hours(name, remaining)
                    if eta is not None:
                        detail.append(f"{self.t('goal in')} ~{session_module.format_hours(eta)}")
            if detail:
                ctk.CTkLabel(
                    card, text="  ·  ".join(detail), font=(theme.FONT_FAMILY, 10),
                    text_color=theme.TEXT_DIM, anchor="w",
                ).pack(fill="x", padx=10, pady=(0, 6))
            else:
                ctk.CTkFrame(card, fg_color="transparent", height=4).pack()
        self._bind_mousewheel(self.session_list, self.session_list)

    # ---------------------------------------------------------------- World tab
    def _build_world_tab(self, parent):
        top = ctk.CTkFrame(parent, fg_color="transparent")
        top.pack(fill="x", pady=(0, 4))
        self._world_labels = {k: self.t(world_view.SECTION_LABELS[k]) for k in world_view.SECTIONS}
        cur = storage.get_setting(self.state, "world_section", "summary")
        if cur not in world_view.SECTIONS:
            cur = "summary"
        self._world_section = cur
        self.world_menu = ctk.CTkOptionMenu(
            top, values=[self._world_labels[k] for k in world_view.SECTIONS],
            command=self._on_world_section, fg_color=theme.BG_CARD,
            button_color=theme.ACCENT, button_hover_color=theme.ACCENT_HOVER,
        )
        self.world_menu.set(self._world_labels[cur])
        self.world_menu.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(
            top, text=self.t("Refresh"), width=76, fg_color=theme.BG_CARD,
            hover_color=theme.BG_CARD_HOVER, command=self._refresh_world,
        ).pack(side="left", padx=(4, 0))

        # Baro watchlist: only shown on the summary section.
        self.baro_watch_frame = ctk.CTkFrame(parent, fg_color="transparent")
        ctk.CTkLabel(
            self.baro_watch_frame, text=self.t("Baro watchlist (comma-separated):"),
            font=(theme.FONT_FAMILY, 10), text_color=theme.TEXT_DIM, anchor="w",
        ).pack(fill="x")
        entry_row = ctk.CTkFrame(self.baro_watch_frame, fg_color="transparent")
        entry_row.pack(fill="x", pady=(2, 6))
        self.baro_watch_entry = ctk.CTkEntry(
            entry_row, placeholder_text="Primed Flow, Primed Continuity",
            fg_color=theme.BG_INPUT, border_color=theme.BORDER,
        )
        self.baro_watch_entry.pack(side="left", fill="x", expand=True)
        existing = storage.get_setting(self.state, "baro_watch", "")
        if existing:
            self.baro_watch_entry.insert(0, existing)
        ctk.CTkButton(
            entry_row, text=self.t("Save"), width=56, fg_color=theme.ACCENT,
            hover_color=theme.ACCENT_HOVER, command=self._save_baro_watch,
        ).pack(side="left", padx=(4, 0))

        self.world_box = ctk.CTkTextbox(parent, fg_color=theme.BG_INPUT, text_color=theme.TEXT)
        self.world_box.pack(fill="both", expand=True)
        self.world_box.configure(state="disabled")
        self._update_world_watch_visibility()
        self._world_tick()

    def _update_world_watch_visibility(self):
        if self._world_section == "summary":
            self.baro_watch_frame.pack(fill="x", before=self.world_box)
        else:
            self.baro_watch_frame.pack_forget()

    def _on_world_section(self, label):
        for key, text in self._world_labels.items():
            if text == label:
                self._world_section = key
                break
        storage.set_setting(self.state, "world_section", self._world_section)
        self._update_world_watch_visibility()
        self._render_world_tab(reset_scroll=True)

    def _world_tick(self):
        """Re-render every 30 s so 'time left' stays accurate."""
        if self._active_tab == "world":
            self._render_world_tab()
        self.root.after(30000, self._world_tick)

    def _save_baro_watch(self):
        storage.set_setting(self.state, "baro_watch", self.baro_watch_entry.get().strip())
        # Re-check right away against the data we already have.
        if self._latest_worldstate:
            self._check_baro(self._latest_worldstate, force=True)

    def _refresh_world(self):
        worldstate_api.fetch_worldstate_async(
            lambda data: self.event_queue.put(("worldstate_background", data)))

    def _render_world_tab(self, reset_scroll=False):
        if not self._worldstate_loaded:
            text = self.t("Loading live data from Warframe Worldstate API...")
        elif not self._latest_worldstate:
            text = self.t("Could not reach the Warframe API. Check your internet connection.")
        else:
            text = world_view.render_section(
                self._world_section, self._latest_worldstate, self.t)
        try:
            top = 0.0 if reset_scroll else self.world_box.yview()[0]
        except Exception:
            top = 0.0
        self.world_box.configure(state="normal")
        self.world_box.delete("1.0", "end")
        self.world_box.insert("1.0", text)
        self.world_box.configure(state="disabled")
        self.world_box.yview_moveto(top)

    # ---------------------------------------------------------------- Support tab
    def _build_support_tab(self, parent):
        card = ctk.CTkFrame(parent, fg_color=theme.BG_CARD, corner_radius=10)
        card.pack(fill="x", pady=(8, 0), padx=2)
        ctk.CTkLabel(card, text="Farm Tracker", font=(theme.FONT_FAMILY, 18, "bold"),
                     text_color=theme.TEXT).pack(pady=(16, 0))
        ctk.CTkLabel(card, text=f"Created by {about_info.AUTHOR}",
                     font=(theme.FONT_FAMILY, 12), text_color=theme.ACCENT).pack(pady=(2, 10))
        ctk.CTkFrame(card, fg_color="transparent", height=4).pack()
        if about_info.DONATE_URL:
            ctk.CTkButton(
                card, text=self.t("Support"), height=36, font=(theme.FONT_FAMILY, 13, "bold"),
                fg_color=theme.ACCENT, hover_color=theme.ACCENT_HOVER,
                command=lambda: webbrowser.open(about_info.DONATE_URL),
            ).pack(fill="x", padx=24, pady=(0, 10))
        if about_info.DISCORD:
            row = ctk.CTkFrame(card, fg_color="transparent")
            row.pack(fill="x", padx=24, pady=(0, 16))
            ctk.CTkLabel(row, text=f"Discord: {about_info.DISCORD}",
                         font=(theme.FONT_FAMILY, 12), text_color=theme.TEXT).pack(side="left")
            self._copy_btn = ctk.CTkButton(
                row, text=self.t("Copy"), width=64, fg_color=theme.BG_INPUT,
                hover_color=theme.BG_CARD_HOVER, command=self._copy_discord)
            self._copy_btn.pack(side="right")
        else:
            ctk.CTkFrame(card, fg_color="transparent", height=6).pack()

    def _copy_discord(self):
        self.root.clipboard_clear()
        self.root.clipboard_append(about_info.DISCORD)
        self._copy_btn.configure(text=self.t("Copied"))
        self.root.after(1500, lambda: self._copy_btn.configure(text=self.t("Copy")))

    # ---------------------------------------------------------------- Mastery tab
    def _build_mastery_tab(self, parent):
        row1 = ctk.CTkFrame(parent, fg_color="transparent")
        row1.pack(fill="x")
        self.mastery_search = ctk.CTkEntry(
            row1, placeholder_text=self.t("Search item..."),
            fg_color=theme.BG_INPUT, border_color=theme.BORDER,
        )
        self.mastery_search.pack(side="left", fill="x", expand=True)
        self.mastery_search.bind("<KeyRelease>", lambda e: self._mastery_filter_changed())
        self._mastery_all_label = self.t("All")
        self.mastery_cat_var = tk.StringVar(value=self._mastery_all_label)
        self.mastery_cat = ctk.CTkComboBox(
            row1, variable=self.mastery_cat_var, width=130, fg_color=theme.BG_INPUT,
            border_color=theme.BORDER, button_color=theme.ACCENT,
            dropdown_fg_color=theme.BG_CARD, values=[self._mastery_all_label] + mastery.categories(self._mastery_items),
            command=lambda v: self._mastery_filter_changed(),
        )
        self.mastery_cat.pack(side="left", padx=(4, 0))

        row2 = ctk.CTkFrame(parent, fg_color="transparent")
        row2.pack(fill="x", pady=(4, 0))
        ctk.CTkLabel(row2, text=self.t("My MR:"), text_color=theme.TEXT_DIM,
                     font=(theme.FONT_FAMILY, 10)).pack(side="left")
        self.mastery_mr_entry = ctk.CTkEntry(
            row2, width=44, fg_color=theme.BG_INPUT, border_color=theme.BORDER)
        self.mastery_mr_entry.pack(side="left", padx=(4, 8))
        my_mr = storage.get_setting(self.state, "my_mr", 0)
        if my_mr:
            self.mastery_mr_entry.insert(0, str(my_mr))
        self.mastery_mr_entry.bind("<KeyRelease>", lambda e: self._on_my_mr_changed())
        self.mastery_hide_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            row2, text=self.t("Hide mastered"), variable=self.mastery_hide_var,
            command=self._mastery_filter_changed, checkbox_width=18, checkbox_height=18,
            fg_color=theme.ACCENT, hover_color=theme.ACCENT_HOVER, font=(theme.FONT_FAMILY, 10),
        ).pack(side="left", padx=(0, 8))
        self.mastery_avail_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            row2, text=self.t("Within my MR"), variable=self.mastery_avail_var,
            command=self._mastery_filter_changed, checkbox_width=18, checkbox_height=18,
            fg_color=theme.ACCENT, hover_color=theme.ACCENT_HOVER, font=(theme.FONT_FAMILY, 10),
        ).pack(side="left")

        row3 = ctk.CTkFrame(parent, fg_color="transparent")
        row3.pack(fill="x", pady=(4, 4))
        self.mastery_status = ctk.CTkLabel(
            row3, text="", font=(theme.FONT_FAMILY, 10), text_color=theme.TEXT_DIM,
            anchor="w", wraplength=260, justify="left")
        self.mastery_status.pack(side="left", fill="x", expand=True)
        self.mastery_dl_btn = ctk.CTkButton(
            row3, text=self.t("Update item list"), width=120, height=24, fg_color=theme.BG_CARD,
            hover_color=theme.BG_CARD_HOVER, command=self._load_mastery_catalog,
        )
        self.mastery_dl_btn.pack(side="right")

        self.mastery_list = ctk.CTkScrollableFrame(
            parent, fg_color="transparent", scrollbar_button_color=theme.ACCENT)
        self.mastery_list.pack(fill="both", expand=True)
        self._refresh_mastery_list()

    def _on_mastery_tab_shown(self):
        if not self._mastery_items and not self._mastery_loading:
            self._load_mastery_catalog()
        else:
            self._refresh_mastery_list()

    def _load_mastery_catalog(self):
        if self._mastery_loading:
            return
        self._mastery_loading = True
        self.mastery_status.configure(text=self.t("Downloading item list..."))

        def worker():
            items, errors = mastery.fetch_catalog()
            if items:
                mastery.save_cache(items)
            self.event_queue.put(("mastery_loaded", (items, errors)))

        import threading
        threading.Thread(target=worker, daemon=True).start()

    def _on_mastery_loaded(self, items, errors):
        self._mastery_loading = False
        if items:
            self._mastery_items = items
            self.mastery_cat.configure(values=[self._mastery_all_label] + mastery.categories(items))
        else:
            self.mastery_status.configure(
                text=self.t("Could not download the item list. Check your internet connection."))
            return
        self._refresh_mastery_list()

    def _mastery_filter_changed(self):
        self._mastery_limit = 40
        self._refresh_mastery_list()

    def _my_mr(self):
        raw = self.mastery_mr_entry.get().strip()
        try:
            return max(0, int(raw))
        except ValueError:
            return None

    def _on_my_mr_changed(self):
        mr = self._my_mr()
        storage.set_setting(self.state, "my_mr", mr or 0)
        if self.mastery_avail_var.get():
            self._mastery_filter_changed()

    def _toggle_mastered(self, name, value):
        storage.set_mastered(self.state, name, bool(value))
        self._update_mastery_status()

    def _current_mastery_category(self):
        cat = self.mastery_cat_var.get()
        return "" if cat == self._mastery_all_label else cat

    def _update_mastery_status(self, shown=None, matched=None):
        done = storage.mastery_done(self.state)
        mastered, total = mastery.progress(self._mastery_items, done, self._current_mastery_category())
        text = f"{self.t('Mastered')}: {mastered} / {total}"
        if matched is not None:
            text += f"  ·  {matched}"
        self.mastery_status.configure(text=text)

    def _refresh_mastery_list(self):
        for child in self.mastery_list.winfo_children():
            child.destroy()
        if not self._mastery_items:
            self.mastery_status.configure(
                text=self.t("Downloading item list...") if self._mastery_loading
                else self.t("Download the item list to start."))
            return
        done = storage.mastery_done(self.state)
        my_mr = self._my_mr() if self.mastery_avail_var.get() else None
        matches = mastery.filter_items(
            self._mastery_items, done, query=self.mastery_search.get(),
            category=self._current_mastery_category(), my_mr=my_mr,
            hide_done=bool(self.mastery_hide_var.get()))
        for item in matches[:self._mastery_limit]:
            row = ctk.CTkFrame(self.mastery_list, fg_color="transparent")
            row.pack(fill="x")
            var = tk.BooleanVar(value=bool(done.get(item["name"])))
            ctk.CTkCheckBox(
                row, text=item["name"], variable=var, checkbox_width=18, checkbox_height=18,
                fg_color=theme.ACCENT, hover_color=theme.ACCENT_HOVER,
                font=(theme.FONT_FAMILY, 11),
                command=lambda n=item["name"], v=var: self._toggle_mastered(n, v.get()),
            ).pack(side="left", pady=2)
            ctk.CTkLabel(
                row, text=f"MR {item['mr']}", font=(theme.FONT_FAMILY, 10),
                text_color=theme.TEXT_DIM,
            ).pack(side="right", padx=4)
        if len(matches) > self._mastery_limit:
            ctk.CTkButton(
                self.mastery_list,
                text=f"{self.t('Show more')} ({len(matches) - self._mastery_limit})",
                height=26, fg_color=theme.BG_CARD, hover_color=theme.BG_CARD_HOVER,
                command=self._mastery_show_more,
            ).pack(pady=6)
        self._update_mastery_status(matched=len(matches))
        self._bind_mousewheel(self.mastery_list, self.mastery_list)

    def _mastery_show_more(self):
        self._mastery_limit += 40
        self._refresh_mastery_list()

    # ---------------------------------------------------------------- Settings tab
    def _setting_switch(self, parent, text, key, default=True, extra=None):
        var = tk.BooleanVar(value=bool(storage.get_setting(self.state, key, default)))

        def on_change():
            storage.set_setting(self.state, key, bool(var.get()))
            if extra:
                extra(bool(var.get()))

        ctk.CTkSwitch(
            parent, text=self.t(text), variable=var, command=on_change,
            progress_color=theme.ACCENT, font=(theme.FONT_FAMILY, 11),
        ).pack(anchor="w", pady=3)
        return var

    def _section_label(self, parent, text):
        ctk.CTkLabel(
            parent, text=self.t(text), font=(theme.FONT_FAMILY, 11, "bold"),
            text_color=theme.ACCENT, anchor="w",
        ).pack(fill="x", pady=(10, 2))

    def _build_settings_tab(self, parent):
        sf = ctk.CTkScrollableFrame(parent, fg_color="transparent", scrollbar_button_color=theme.ACCENT)
        sf.pack(fill="both", expand=True)
        self.settings_frame = sf

        self._section_label(sf, "Language")
        lang_frame = ctk.CTkFrame(sf, fg_color="transparent")
        lang_frame.pack(fill="x")
        for code, label in (("en", "EN"), ("ru", "RU")):
            is_active = self.lang == code
            ctk.CTkButton(
                lang_frame, text=label, width=44, height=26,
                fg_color=theme.ACCENT if is_active else theme.BG_CARD,
                hover_color=theme.ACCENT_HOVER if is_active else theme.BG_CARD_HOVER,
                command=lambda c=code: self._set_language(c),
            ).pack(side="left", padx=(0, 4))

        self._section_label(sf, "Window")
        self.compact_var = tk.BooleanVar(value=self.compact)
        ctk.CTkSwitch(
            sf, text=self.t("Compact mode"), variable=self.compact_var,
            command=self._toggle_compact_mode, progress_color=theme.ACCENT,
            font=(theme.FONT_FAMILY, 11),
        ).pack(anchor="w", pady=3)
        self._setting_switch(sf, "Always on top", "always_on_top", True, self._apply_always_on_top)
        self.ghost_var = tk.BooleanVar(value=False)
        ghost_switch = ctk.CTkSwitch(
            sf, text=self.t("Ghost mode (clicks pass through)"), variable=self.ghost_var,
            command=lambda: self._set_ghost(bool(self.ghost_var.get())),
            progress_color=theme.ACCENT, font=(theme.FONT_FAMILY, 11),
        )
        ghost_switch.pack(anchor="w", pady=3)
        if not HOTKEY_AVAILABLE:
            ghost_switch.configure(state="disabled")
        ctk.CTkLabel(sf, text=self.t("Opacity"), font=(theme.FONT_FAMILY, 10),
                     text_color=theme.TEXT_DIM, anchor="w").pack(fill="x", pady=(6, 0))
        self.opacity_slider = ctk.CTkSlider(
            sf, from_=0.35, to=1.0, number_of_steps=26, command=self._on_opacity,
            progress_color=theme.ACCENT, button_color=theme.ACCENT,
            button_hover_color=theme.ACCENT_HOVER,
        )
        self.opacity_slider.set(float(storage.get_setting(self.state, "opacity", 0.92)))
        self.opacity_slider.pack(fill="x", pady=(0, 2))
        self.opacity_slider.bind("<ButtonRelease-1>", lambda e: self._save_opacity())
        hotkey_note = (self.t("Ctrl+Shift+F - show/hide, Ctrl+Shift+G - ghost mode")
                       if HOTKEY_AVAILABLE else self.t("(install 'pynput' for hotkey)"))
        if HOTKEY_AVAILABLE:
            hotkey_note += "\n" + self.t("If hotkeys do nothing while Warframe is focused, run the tracker as administrator.")
        ctk.CTkLabel(sf, text=hotkey_note, font=(theme.FONT_FAMILY, 9),
                     text_color=theme.TEXT_DIM, anchor="w", wraplength=340,
                     justify="left").pack(fill="x")

        self._section_label(sf, "Notifications")
        self._setting_switch(sf, "Notify when a goal is reached", "notify_goal", True)
        self._setting_switch(sf, "Notify when Baro arrives", "notify_baro", True)
        self._setting_switch(sf, "Sound", "sound", True)

        self._section_label(sf, "Backup")
        btn_row = ctk.CTkFrame(sf, fg_color="transparent")
        btn_row.pack(fill="x")
        ctk.CTkButton(
            btn_row, text=self.t("Export backup"), height=28, fg_color=theme.BG_CARD,
            hover_color=theme.BG_CARD_HOVER, command=self._export_backup,
        ).pack(side="left", padx=(0, 4))
        ctk.CTkButton(
            btn_row, text=self.t("Import backup"), height=28, fg_color=theme.BG_CARD,
            hover_color=theme.BG_CARD_HOVER, command=self._import_backup,
        ).pack(side="left")
        ctk.CTkLabel(
            sf, text=self.t("A daily automatic backup is kept in the 'backups' folder."),
            font=(theme.FONT_FAMILY, 9), text_color=theme.TEXT_DIM, anchor="w",
            wraplength=340, justify="left",
        ).pack(fill="x", pady=(4, 0))
        self._bind_mousewheel(sf, sf)

    # ---------------------------------------------------------------- window options
    def _apply_always_on_top(self, enabled):
        self.root.attributes("-topmost", bool(enabled))

    def _on_opacity(self, value):
        try:
            self.root.attributes("-alpha", float(value))
        except tk.TclError:
            pass

    def _save_opacity(self):
        storage.set_setting(self.state, "opacity", round(float(self.opacity_slider.get()), 2))

    def _set_ghost(self, enabled):
        """Click-through window: mouse clicks pass to the game underneath.
        Never saved - the app always starts in normal mode - and always
        reversible with the Ctrl+Shift+G hotkey."""
        if enabled and not HOTKEY_AVAILABLE:
            self.ghost_var.set(False)
            return
        if not self._apply_click_through(enabled):
            self.ghost_var.set(False)
            self._ghost = False
            return
        self._ghost = enabled
        self.ghost_var.set(enabled)
        if enabled:
            self._show_notice(self.t("Ghost mode ON - press Ctrl+Shift+G to turn it off"))

    def _apply_click_through(self, enabled):
        try:
            import ctypes
            self.root.update_idletasks()
            user32 = ctypes.windll.user32
            hwnd = user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
            GWL_EXSTYLE, WS_EX_LAYERED, WS_EX_TRANSPARENT = -20, 0x80000, 0x20
            style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            if enabled:
                style |= WS_EX_LAYERED | WS_EX_TRANSPARENT
            else:
                style &= ~WS_EX_TRANSPARENT
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
            return True
        except Exception:
            return False

    # ---------------------------------------------------------------- backup
    def _export_backup(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".json", initialfile="farm_tracker_backup.json",
            filetypes=[("JSON", "*.json")])
        if not path:
            return
        try:
            storage.save_state(self.state)
            storage.export_backup(path)
            messagebox.showinfo(APP_TITLE, self.t("Backup saved"))
        except OSError as exc:
            messagebox.showerror(APP_TITLE, str(exc))

    def _import_backup(self):
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if not path:
            return
        try:
            storage.import_backup(path)
        except (OSError, ValueError):
            messagebox.showerror(APP_TITLE, self.t("This is not a Farm Tracker backup."))
            return
        self.state = storage.load_state()
        self.lang = storage.get_language(self.state)
        self.compact = storage.get_compact_mode(self.state)
        self._rebuild_everything()
        messagebox.showinfo(APP_TITLE, self.t("Backup restored"))

    # ---------------------------------------------------------------- notices
    def _beep(self):
        if not storage.get_setting(self.state, "sound", True):
            return
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
        except Exception:
            try:
                self.root.bell()
            except Exception:
                pass

    def _show_notice(self, text, color=None, seconds=NOTICE_SECONDS):
        """A closable banner above the tabs (visible from every tab)."""
        banner = ctk.CTkFrame(self.banner_area, fg_color=color or theme.ACCENT_BLUE, corner_radius=8)
        banner.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(
            banner, text=text, text_color="#0d0d1a", font=(theme.FONT_FAMILY, 11, "bold"),
            wraplength=340, justify="left", anchor="w",
        ).pack(side="left", padx=8, pady=6, fill="x", expand=True)

        def close():
            try:
                banner.destroy()
            except Exception:
                pass

        ctk.CTkButton(
            banner, text="✕", width=20, height=20, fg_color="transparent",
            text_color="#0d0d1a", hover_color=theme.ACCENT_HOVER, command=close,
        ).pack(side="right", padx=4)
        self.root.after(int(seconds * 1000), close)
        return banner

    # ------------------------------------------------------------------
    # Resource search picker
    # ------------------------------------------------------------------
    def _picker_matches(self):
        merged = storage.all_resources(self.state)
        tracked = set(self.state["tracked"].keys())
        query = self.picker_entry.get().strip().lower()
        results = []
        for name, info in merged.items():
            if name in tracked:
                continue
            category = info.get("category", "")
            haystack = f"{name} {category} {self.category_display(category)}".lower()
            if query and query not in haystack:
                continue
            starts = 0 if name.lower().startswith(query) else 1
            results.append((starts, category, name))
        results.sort()
        return [name for _, _, name in results]

    def _refresh_picker(self):
        for child in self.picker_list.winfo_children():
            child.destroy()
        merged = storage.all_resources(self.state)
        matches = self._picker_matches()
        if not matches:
            ctk.CTkLabel(self.picker_list, text=self.t("No matches"),
                         text_color=theme.TEXT_DIM).pack(pady=6)
        for name in matches:
            category = self.category_display(merged[name].get("category", ""))
            ctk.CTkButton(
                self.picker_list, text=f"{name}    ·  {category}", anchor="w", height=26,
                fg_color="transparent", hover_color=theme.BG_CARD_HOVER,
                text_color=theme.TEXT, font=(theme.FONT_FAMILY, 11),
                command=lambda n=name: self._pick_resource(n),
            ).pack(fill="x", pady=1)
        self._bind_mousewheel(self.picker_list, self.picker_list)

    def _refresh_add_resource_list(self):
        # Called whenever the tracked set / resource DB changes.
        if self._picker_open:
            self._refresh_picker()

    def _open_picker(self):
        self._refresh_picker()
        if not self._picker_open:
            self.picker_list.pack(fill="x", pady=(0, 6), before=self.panel_container)
            self._picker_open = True

    def _close_picker(self):
        if self._picker_open:
            self.picker_list.pack_forget()
            self._picker_open = False

    def _toggle_picker(self):
        if self._picker_open:
            self._close_picker()
        else:
            self._open_picker()

    def _on_picker_key(self, event):
        if event.keysym in ("Return", "Escape", "Tab", "Shift_L", "Shift_R",
                            "Control_L", "Control_R", "Alt_L", "Alt_R"):
            return
        self._open_picker()

    def _track_first_match(self):
        matches = self._picker_matches()
        query = self.picker_entry.get().strip().lower()
        exact = [n for n in matches if n.lower() == query]
        chosen = exact[0] if exact else (matches[0] if matches and query else None)
        if chosen:
            self._pick_resource(chosen)
        else:
            self._open_picker()

    def _pick_resource(self, name):
        storage.start_tracking(self.state, name)
        self.picker_entry.delete(0, "end")
        self._close_picker()
        self._rebuild_tracked_panel()

    # ------------------------------------------------------------------
    # Mission kill counter
    # ------------------------------------------------------------------
    def _refresh_kills_label(self):
        if self._kills_total is None:
            value = "—"
        else:
            value = f"~{max(0, self._kills_total - self._kills_baseline)}"
        self.kills_label.configure(text=f"☠ {self.t('Kills this mission:')} {value}")

    def _reset_kills(self):
        """Start counting from zero right now (e.g. at the start of a run)."""
        self._kills_baseline = self._kills_total or 0
        self._refresh_kills_label()

    def _on_agent_event(self, live, spawned, ally):
        # The game's spawn counter restarts at 0 for every new mission, so a
        # drop means a new mission began: reset the baseline automatically.
        if self._last_spawned is not None and spawned < self._last_spawned:
            self._kills_baseline = 0
            self._session.kills_finished += self._kills_total or 0   # bank the finished mission
        self._last_spawned = spawned
        self._kills_total = ee_log_reader.estimate_kills(live, spawned, ally)
        self._refresh_kills_label()

    # ------------------------------------------------------------------
    # Auto-pickup (OCR)
    # ------------------------------------------------------------------
    def _refresh_pickup_status(self):
        text = self.t(self._pickup_status) if (self.pickup_var.get() and self._pickup_status) else ""
        if text:
            color = theme.SUCCESS if self._pickup_status == "OCR ready" else theme.WARNING
            self.pickup_status_label.configure(text=text, text_color=color)
            self.pickup_status_label.pack(anchor="w", pady=(2, 0))
        else:
            self.pickup_status_label.pack_forget()

    def _pickup_name_map(self):
        merged = dict(pickup_ocr.DEFAULT_NAME_MAP)
        merged.update(storage.get_pickup_names(self.state))
        return merged

    def _on_toggle_pickup(self):
        enabled = self.pickup_var.get()
        storage.set_setting(self.state, "auto_pickup", enabled)
        if enabled:
            self._start_pickup_watcher()
        else:
            self._stop_pickup_watcher()
        self._refresh_pickup_status()

    def _start_pickup_watcher(self):
        self._stop_pickup_watcher()
        self._pickup_status = "OCR ready"

        def on_pickup(display, norm, amount):
            self.event_queue.put(("pickup", (display, norm, amount)))

        def on_status(msg):
            self._pickup_status = msg
            self.event_queue.put(("pickup_status", None))

        self._pickup_watcher = pickup_ocr.PickupWatcher(
            on_pickup, on_status=on_status,
            debug=bool(storage.get_setting(self.state, "pickup_debug", True)),
            known_names=self._pickup_name_map().keys(),
        )
        self._pickup_watcher.start()

    def _stop_pickup_watcher(self):
        if self._pickup_watcher is not None:
            self._pickup_watcher.stop()
            self._pickup_watcher = None

    def _on_pickup_event(self, display, norm, amount):
        target = self._pickup_name_map().get(norm)
        limit = pickup_ocr.MAX_CREDITS_PICKUP if target == "Credits" else pickup_ocr.MAX_SINGLE_PICKUP
        if amount > limit:
            return  # almost certainly an OCR misread
        if target == pickup_ocr.IGNORE:
            return
        if target is None:
            # Never seen before: remember the amount and ask the player once.
            self._pickup_pending[norm] = self._pickup_pending.get(norm, 0) + amount
            if norm != self._pickup_asking and norm not in self._pickup_ask_queue:
                self._pickup_ask_queue.append((norm))
                self._pickup_display_names[norm] = display
            self._show_next_pickup_question()
            return
        if target in self.state["tracked"]:
            self._on_quick_add(target, amount)

    def _show_next_pickup_question(self):
        if self._pickup_asking is not None or not self._pickup_ask_queue:
            return
        norm = self._pickup_ask_queue.pop(0)
        self._pickup_asking = norm
        display = self._pickup_display_names.get(norm, norm)

        banner = ctk.CTkFrame(self.banner_area, fg_color=theme.ACCENT_BLUE, corner_radius=8)
        banner.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(
            banner, text=f"{self.t('New pickup text:')} \"{display}\" - {self.t('Which resource is this?')}",
            text_color="#0d0d1a", font=(theme.FONT_FAMILY, 10, "bold"), wraplength=300, justify="left",
        ).pack(anchor="w", padx=8, pady=(6, 2))
        row = ctk.CTkFrame(banner, fg_color="transparent")
        row.pack(fill="x", padx=8, pady=(0, 6))
        choices = sorted(storage.all_resources(self.state).keys())
        var = tk.StringVar(value=choices[0] if choices else "")
        ctk.CTkComboBox(row, variable=var, values=choices, width=170, fg_color=theme.BG_INPUT,
                        dropdown_fg_color=theme.BG_CARD).pack(side="left")

        def finish(target):
            storage.set_pickup_name(self.state, norm, target)
            if self._pickup_watcher is not None:
                self._pickup_watcher.add_known_name(norm)
            pending = self._pickup_pending.pop(norm, 0)
            if target != pickup_ocr.IGNORE and pending and target in self.state["tracked"]:
                self._on_quick_add(target, pending)
            banner.destroy()
            self._pickup_banner = None
            self._pickup_asking = None
            self._show_next_pickup_question()

        ctk.CTkButton(row, text=self.t("OK"), width=40, fg_color=theme.ACCENT,
                      hover_color=theme.ACCENT_HOVER,
                      command=lambda: finish(var.get())).pack(side="left", padx=4)
        ctk.CTkButton(row, text=self.t("Ignore"), width=80, fg_color=theme.BG_CARD,
                      hover_color=theme.BG_CARD_HOVER,
                      command=lambda: finish(pickup_ocr.IGNORE)).pack(side="left")
        self._pickup_banner = banner

    def _toggle_collapse(self):
        self._collapsed = not getattr(self, "_collapsed", False)
        self.root.update_idletasks()
        if self._collapsed:
            self._expanded_geometry = (self.root.winfo_width(), self.root.winfo_height())
            self.content.pack_forget()
            self.root.minsize(200, 40)
            self.root.geometry(f"{self._expanded_geometry[0]}x56")
        else:
            self.content.pack(fill="both", expand=True)
            self.root.minsize(300, 220)
            w, h = getattr(self, "_expanded_geometry", (380, 380))
            self.root.geometry(f"{w}x{h}")

    def _toggle_compact_mode(self):
        self.compact = not self.compact
        storage.set_compact_mode(self.state, self.compact)
        self._rebuild_tracked_panel()

    # ------------------------------------------------------------------
    # Inline panel slot (Rotation Tracker / Presets / New resource) -
    # these live INSIDE the main window instead of popping up separate
    # windows, so the overlay never spawns extra clutter on screen.
    # ------------------------------------------------------------------
    def _toggle_panel(self, kind):
        self._cancel_rotation_job()
        if self._active_panel_kind == kind:
            self._close_active_panel()
            return
        self._close_active_panel()

        frame = ctk.CTkFrame(self.panel_container, fg_color=theme.BG_CARD, corner_radius=10)
        frame.pack(fill="x", pady=(0, 8))

        builders = {
            "add_resource": self._build_add_resource_panel,
            "rotation": self._build_rotation_panel,
            "presets": self._build_presets_panel,
        }
        builders[kind](frame)

        self._active_panel_kind = kind
        self._active_panel_frame = frame

    def _close_active_panel(self):
        self._cancel_rotation_job()
        if self._active_panel_frame is not None:
            self._active_panel_frame.destroy()
        self._active_panel_frame = None
        self._active_panel_kind = None

    def _cancel_rotation_job(self):
        if self._rotation_job is not None:
            try:
                self.root.after_cancel(self._rotation_job)
            except Exception:
                pass
            self._rotation_job = None

    # ------------------------------------------------------------------
    # Tracked-resources panel
    # ------------------------------------------------------------------
    def _rebuild_tracked_panel(self):
        for child in self.tracked_frame.winfo_children():
            child.destroy()
        self._row_widgets.clear()

        tracked_names = sorted(self.state["tracked"].keys())
        if not tracked_names:
            ctk.CTkLabel(
                self.tracked_frame,
                text=self.t("No resources tracked yet.\nPick one above and hit 'Track'."),
                text_color=theme.TEXT_DIM, justify="left",
            ).pack(anchor="w", pady=12, padx=4)
        else:
            for name in tracked_names:
                if self.compact:
                    self._build_resource_row_compact(name)
                else:
                    self._build_resource_row(name)

        self._refresh_add_resource_list()
        self._bind_mousewheel(self.tracked_frame)

    def _bind_mousewheel(self, widget, frame=None):
        """CTkScrollableFrame doesn't always catch the mouse wheel when
        the cursor is over a child widget (a label, button, etc. inside
        a card) rather than the empty background - so we bind it to
        every widget in the tree, recursively, and forward the scroll
        to the frame's underlying canvas."""
        frame = frame or self.tracked_frame

        def _on_wheel(event):
            canvas = getattr(frame, "_parent_canvas", None)
            if canvas is None:
                return
            if getattr(event, "num", None) == 4:      # Linux scroll up
                canvas.yview_scroll(-2, "units")
            elif getattr(event, "num", None) == 5:    # Linux scroll down
                canvas.yview_scroll(2, "units")
            else:                                      # Windows / macOS
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        widget.bind("<MouseWheel>", _on_wheel)
        widget.bind("<Button-4>", _on_wheel)
        widget.bind("<Button-5>", _on_wheel)
        for child in widget.winfo_children():
            self._bind_mousewheel(child, frame)

    def _build_resource_row_compact(self, name):
        merged = storage.all_resources(self.state)
        info = merged.get(name, {})
        tracked = self.state["tracked"].get(name, {"amount": 0, "goal": None})

        row = ctk.CTkFrame(self.tracked_frame, fg_color=theme.BG_CARD, corner_radius=8)
        row.pack(fill="x", pady=2, padx=2)

        ctk.CTkLabel(
            row, text=name, font=(theme.FONT_FAMILY, 10, "bold"), text_color=theme.TEXT, width=100,
            anchor="w",
        ).pack(side="left", padx=(8, 4), pady=4)

        progress = ctk.CTkProgressBar(
            row, progress_color=theme.ACCENT, fg_color=theme.BG_INPUT, height=8, width=70,
        )
        progress.pack(side="left", padx=4)
        progress.set(0)

        amount_lbl = ctk.CTkLabel(
            row, text=fmt_num(tracked.get('amount', 0)), font=(theme.FONT_FAMILY, 10),
            text_color=theme.TEXT_DIM, width=56,
        )
        amount_lbl.pack(side="left", padx=2)

        ctk.CTkButton(
            row, text="+1", width=30, height=22, fg_color=theme.ACCENT,
            hover_color=theme.ACCENT_HOVER,
            command=lambda n=name: self._on_quick_add(n, 1),
        ).pack(side="left", padx=2)
        ctk.CTkButton(
            row, text="✕", width=22, height=22, fg_color="transparent",
            hover_color=theme.DANGER, text_color=theme.TEXT_DIM,
            command=lambda n=name: self._on_remove_tracked(n),
        ).pack(side="right", padx=4)

        self._row_widgets[name] = {
            "amount_lbl": amount_lbl, "progress": progress, "goal_var": None,
            "tip_lbl": None, "eta_lbl": None, "last_delta": None, "compact": True,
        }
        self._update_row_display(name)

    def _build_resource_row(self, name):
        merged = storage.all_resources(self.state)
        info = merged.get(name, {})
        tracked = self.state["tracked"].get(name, {"amount": 0, "goal": None})

        card = ctk.CTkFrame(self.tracked_frame, fg_color=theme.BG_CARD, corner_radius=10)
        card.pack(fill="x", pady=4, padx=2)

        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=(8, 2))
        ctk.CTkLabel(
            header, text=name, font=(theme.FONT_FAMILY, 12, "bold"), text_color=theme.TEXT,
        ).pack(side="left")
        rarity = info.get("rarity", "common")
        ctk.CTkLabel(
            header, text=self.rarity_text(rarity), text_color="#0d0d1a",
            fg_color=theme.RARITY_COLORS.get(rarity, theme.TEXT_DIM),
            corner_radius=6, font=(theme.FONT_FAMILY, 9, "bold"), width=1, height=18,
        ).pack(side="left", padx=(6, 0))
        ctk.CTkButton(
            header, text="✕", width=22, height=22, fg_color="transparent",
            hover_color=theme.DANGER, text_color=theme.TEXT_DIM,
            command=lambda n=name: self._on_remove_tracked(n),
        ).pack(side="right")

        tip_lbl = ctk.CTkLabel(
            card, text=self.farm_tip(name, info), text_color=theme.ACCENT_BLUE,
            font=(theme.FONT_FAMILY, 10), wraplength=300, justify="left", anchor="w",
        )
        tip_lbl.pack(fill="x", padx=10, pady=(0, 6))

        stats_row = ctk.CTkFrame(card, fg_color="transparent")
        stats_row.pack(fill="x", padx=10)
        amount_lbl = ctk.CTkLabel(
            stats_row, text=f"{self.t('Have')}: {fmt_num(tracked.get('amount', 0))}",
            font=(theme.FONT_FAMILY, 13, "bold"), text_color=theme.TEXT,
        )
        amount_lbl.pack(side="left")

        ctk.CTkLabel(stats_row, text=self.t("Goal:"), text_color=theme.TEXT_DIM).pack(side="left", padx=(12, 2))
        goal_var = tk.StringVar(value=str(tracked["goal"]) if tracked.get("goal") else "")
        goal_entry = ctk.CTkEntry(
            stats_row, textvariable=goal_var, width=60, fg_color=theme.BG_INPUT,
            border_color=theme.BORDER,
        )
        goal_entry.pack(side="left")
        goal_entry.bind("<Return>", lambda e, n=name, v=goal_var: self._on_set_goal(n, v))

        eta_lbl = ctk.CTkLabel(card, text="", text_color=theme.TEXT_DIM, font=(theme.FONT_FAMILY, 9))
        eta_lbl.pack(fill="x", padx=10, anchor="w")

        progress = ctk.CTkProgressBar(
            card, progress_color=theme.ACCENT, fg_color=theme.BG_INPUT, height=10,
        )
        progress.pack(fill="x", padx=10, pady=(4, 6))
        progress.set(0)

        quick_row = ctk.CTkFrame(card, fg_color="transparent")
        quick_row.pack(fill="x", padx=10, pady=(0, 4))
        for delta in QUICK_DELTAS:
            text = f"+{delta}" if delta > 0 else str(delta)
            color = theme.DANGER if delta < 0 else theme.ACCENT
            ctk.CTkButton(
                quick_row, text=text, width=42, height=26, fg_color=color,
                hover_color=theme.ACCENT_HOVER if delta > 0 else "#c23b3f",
                font=(theme.FONT_FAMILY, 10),
                command=lambda n=name, d=delta: self._on_quick_add(n, d),
            ).pack(side="left", padx=1)

        custom_row = ctk.CTkFrame(card, fg_color="transparent")
        custom_row.pack(fill="x", padx=10, pady=(0, 10))
        custom_var = tk.StringVar()
        ctk.CTkEntry(
            custom_row, textvariable=custom_var, width=56, fg_color=theme.BG_INPUT,
            border_color=theme.BORDER, placeholder_text=self.t("qty"),
        ).pack(side="left")
        ctk.CTkButton(
            custom_row, text=self.t("Add"), width=44, height=26, fg_color=theme.ACCENT,
            hover_color=theme.ACCENT_HOVER,
            command=lambda n=name, v=custom_var: self._on_custom_add(n, v),
        ).pack(side="left", padx=2)
        ctk.CTkButton(
            custom_row, text=self.t("Undo"), width=50, height=26, fg_color=theme.BG_INPUT,
            hover_color=theme.BG_CARD_HOVER, text_color=theme.TEXT_DIM,
            command=lambda n=name: self._on_undo(n),
        ).pack(side="left", padx=2)
        ctk.CTkButton(
            custom_row, text=self.t("History"), width=60, height=26, fg_color=theme.BG_INPUT,
            hover_color=theme.BG_CARD_HOVER, text_color=theme.TEXT_DIM,
            command=lambda n=name: self._open_history_window(n),
        ).pack(side="left", padx=2)

        self._row_widgets[name] = {
            "amount_lbl": amount_lbl, "progress": progress, "goal_var": goal_var,
            "tip_lbl": tip_lbl, "eta_lbl": eta_lbl, "last_delta": None, "compact": False,
        }
        self._update_row_display(name)

    def _update_row_display(self, name):
        widgets = self._row_widgets.get(name)
        if not widgets:
            return
        tracked = self.state["tracked"].get(name, {"amount": 0, "goal": None})
        amount = tracked.get("amount", 0)
        goal = tracked.get("goal")

        if widgets["compact"]:
            widgets["amount_lbl"].configure(text=fmt_num(amount))
        else:
            widgets["amount_lbl"].configure(text=f"{self.t('Have')}: {fmt_num(amount)}")

        if goal and goal > 0:
            widgets["progress"].set(max(0.0, min(1.0, amount / goal)))
        else:
            widgets["progress"].set(0)

        if widgets["compact"]:
            return  # compact rows skip tip/ETA text entirely

        merged = storage.all_resources(self.state)
        info = merged.get(name, {})
        widgets["tip_lbl"].configure(text=self.farm_tip(name, info))

        rate = storage.compute_farm_rate(self.state, name)
        eta = storage.estimate_days_to_goal(self.state, name)
        parts = []
        if rate:
            parts.append(f"~{rate:.0f}/day")
        if eta is not None:
            parts.append("goal reached!" if eta == 0 else f"ETA ~{eta:.1f} days")

        if name == "Argon Crystal":
            secs = storage.seconds_until_argon_decay()
            hours = int(secs // 3600)
            minutes = int((secs % 3600) // 60)
            decay_text = f"{self.t('Argon decays at daily reset (00:00 UTC) in')} {hours}h {minutes}m"
            parts.append(decay_text)

        widgets["eta_lbl"].configure(text="  ·  ".join(parts))

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def _on_remove_tracked(self, name):
        msg = f"{self.t('Stop tracking')} {name}?\n{self.t('(Its farm history is kept.)')}"
        if messagebox.askyesno(APP_TITLE, msg):
            storage.remove_tracked(self.state, name)
            self._rebuild_tracked_panel()

    def _on_quick_add(self, name, delta):
        self._record_gain(name, delta)

    def _record_gain(self, name, delta):
        """Every gain (manual buttons and OCR pickups) goes through here:
        saves it, logs it for the session stats, refreshes the card and
        fires the goal-reached alert."""
        old_amount = self.state["tracked"].get(name, {}).get("amount", 0)
        storage.add_farm_entry(self.state, name, delta)
        self._session.add(name, delta)
        if name in self._row_widgets:
            self._row_widgets[name]["last_delta"] = delta
        self._update_row_display(name)
        self._maybe_warn_argon()
        self._check_goal(name, old_amount)

    def _check_goal(self, name, old_amount):
        if not storage.get_setting(self.state, "notify_goal", True):
            return
        tracked = self.state["tracked"].get(name, {})
        goal, amount = tracked.get("goal"), tracked.get("amount", 0)
        if goal and goal > 0 and old_amount < goal <= amount:
            self._beep()
            self._show_notice(
                f"🎯 {self.t('Goal reached:')} {name} ({fmt_num(amount)} / {fmt_num(goal)})",
                color=theme.SUCCESS)

    def _on_custom_add(self, name, var):
        raw = var.get().strip()
        if not raw:
            return
        try:
            delta = int(raw)
        except ValueError:
            messagebox.showerror(APP_TITLE, self.t("Enter a whole number."))
            return
        var.set("")
        self._record_gain(name, delta)

    def _on_undo(self, name):
        last_delta = self._row_widgets.get(name, {}).get("last_delta")
        if last_delta is None:
            messagebox.showinfo(APP_TITLE, self.t("Nothing to undo yet this session."))
            return
        storage.undo_last_delta(self.state, name, last_delta)
        self._session.add(name, -last_delta)
        self._row_widgets[name]["last_delta"] = None
        self._update_row_display(name)

    def _on_set_goal(self, name, var, event=None):
        raw = var.get().strip()
        if raw == "":
            storage.set_goal(self.state, name, None)
        else:
            try:
                goal = int(raw)
            except ValueError:
                messagebox.showerror(APP_TITLE, self.t("Goal must be a whole number."))
                return
            storage.set_goal(self.state, name, goal)
        self._update_row_display(name)

    # ------------------------------------------------------------------
    # Banners
    # ------------------------------------------------------------------
    def _show_mission_banner(self):
        self._clear_mission_banner()
        tracked_names = sorted(self.state["tracked"].keys())
        banner = ctk.CTkFrame(self.banner_area, fg_color=theme.ACCENT, corner_radius=8)
        banner.pack(fill="x", pady=(0, 6))
        top = ctk.CTkFrame(banner, fg_color="transparent")
        top.pack(fill="x", padx=8, pady=(6, 2))
        ctk.CTkLabel(
            top, text=self.t("Mission complete - quick log:"), text_color="#0d0d1a",
            font=(theme.FONT_FAMILY, 11, "bold"),
        ).pack(side="left")
        ctk.CTkButton(
            top, text="✕", width=20, height=20, fg_color="transparent",
            text_color="#0d0d1a", hover_color=theme.ACCENT_HOVER,
            command=self._clear_mission_banner,
        ).pack(side="right")

        if not tracked_names:
            ctk.CTkLabel(
                banner, text=self.t("(track a resource below to log it here)"),
                text_color="#1a1a2e", font=(theme.FONT_FAMILY, 9),
            ).pack(anchor="w", padx=8, pady=(0, 6))
        else:
            quick = ctk.CTkFrame(banner, fg_color="transparent")
            quick.pack(fill="x", padx=8, pady=(0, 6))
            for name in tracked_names[:6]:
                chip = ctk.CTkFrame(quick, fg_color="#0d0d1a", corner_radius=6)
                chip.pack(side="left", padx=2, pady=2)
                ctk.CTkLabel(chip, text=name, text_color=theme.TEXT, font=(theme.FONT_FAMILY, 9)).pack(
                    side="left", padx=(6, 2))
                ctk.CTkButton(
                    chip, text="+1", width=28, height=22, fg_color=theme.BG_CARD,
                    hover_color=theme.BG_CARD_HOVER,
                    command=lambda n=name: self._on_quick_add(n, 1),
                ).pack(side="left", padx=(0, 4))

        self._mission_banner = banner

    def _clear_mission_banner(self):
        if self._mission_banner is not None:
            self._mission_banner.destroy()
            self._mission_banner = None

    def _show_hot_banner(self, matches):
        self._clear_hot_banner()
        if not matches:
            return
        banner = ctk.CTkFrame(self.banner_area, fg_color=theme.WARNING, corner_radius=8)
        banner.pack(fill="x", pady=(0, 6))
        top = ctk.CTkFrame(banner, fg_color="transparent")
        top.pack(fill="x", padx=8, pady=4)
        text = f"{self.t('Hot right now:')} " + "; ".join(matches)
        ctk.CTkLabel(
            top, text=text, text_color="#1a1a2e", font=(theme.FONT_FAMILY, 10, "bold"),
            wraplength=300, justify="left",
        ).pack(side="left")
        ctk.CTkButton(
            top, text="✕", width=20, height=20, fg_color="transparent",
            text_color="#1a1a2e", hover_color="#f7b94d",
            command=self._clear_hot_banner,
        ).pack(side="right")
        self._hot_banner = banner

    def _clear_hot_banner(self):
        if self._hot_banner is not None:
            self._hot_banner.destroy()
            self._hot_banner = None

    def _maybe_warn_argon(self):
        tracked = self.state["tracked"].get("Argon Crystal")
        if not tracked or tracked.get("amount", 0) <= 0:
            return
        secs = storage.seconds_until_argon_decay()
        if secs <= ARGON_WARNING_SECONDS:
            hours = int(secs // 3600)
            minutes = int((secs % 3600) // 60)
            messagebox.showwarning(
                APP_TITLE,
                f"⚠️ {self.t('You have')} {tracked['amount']} Argon Crystal "
                f"{self.t('unspent - log it or craft with it before it decays!')} "
                f"({hours}h {minutes}m)",
            )

    # ------------------------------------------------------------------
    # Secondary windows
    # ------------------------------------------------------------------
    def _build_add_resource_panel(self, parent):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=12, pady=12)

        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        ctk.CTkLabel(header, text=self.t("Add new resource to the database"),
                     font=(theme.FONT_FAMILY, 11, "bold"), text_color=theme.ACCENT).pack(side="left")
        ctk.CTkButton(header, text="✕", width=22, height=22, fg_color="transparent",
                      hover_color=theme.DANGER, command=self._close_active_panel).pack(side="right")

        ctk.CTkLabel(frame, text=self.t("Name:"), text_color=theme.TEXT).grid(row=1, column=0, sticky="w", pady=4)
        name_var = tk.StringVar()
        ctk.CTkEntry(frame, textvariable=name_var, width=180, fg_color=theme.BG_INPUT).grid(
            row=1, column=1, pady=4)

        ctk.CTkLabel(frame, text=self.t("Category:"), text_color=theme.TEXT).grid(row=2, column=0, sticky="w", pady=4)
        category_display_var = tk.StringVar(value=self.category_choices_display()[0])
        ctk.CTkComboBox(frame, variable=category_display_var, values=self.category_choices_display(),
                         width=180, fg_color=theme.BG_INPUT, dropdown_fg_color=theme.BG_CARD).grid(
            row=2, column=1, pady=4)

        ctk.CTkLabel(frame, text=self.t("Rarity:"), text_color=theme.TEXT).grid(row=3, column=0, sticky="w", pady=4)
        rarity_var = tk.StringVar(value=RARITY_ORDER[0])
        ctk.CTkComboBox(frame, variable=rarity_var, values=RARITY_ORDER, width=180,
                         fg_color=theme.BG_INPUT, dropdown_fg_color=theme.BG_CARD).grid(row=3, column=1, pady=4)

        ctk.CTkLabel(frame, text=self.t("Best farm tip:"), text_color=theme.TEXT).grid(row=4, column=0, sticky="w", pady=4)
        tip_var = tk.StringVar()
        ctk.CTkEntry(frame, textvariable=tip_var, width=180, fg_color=theme.BG_INPUT).grid(
            row=4, column=1, pady=4)

        def save():
            name = name_var.get().strip()
            tip = tip_var.get().strip() or "No tip yet."
            if not name:
                messagebox.showerror(APP_TITLE, self.t("Name is required."))
                return
            existing = storage.all_resources(self.state)
            if name in existing:
                messagebox.showerror(APP_TITLE, self.t("A resource with this name already exists."))
                return
            category = self.category_from_display(category_display_var.get())
            storage.add_custom_resource(self.state, name, category, rarity_var.get(), tip)
            self._refresh_add_resource_list()
            self._close_active_panel()

        ctk.CTkButton(frame, text=self.t("Save"), fg_color=theme.ACCENT, hover_color=theme.ACCENT_HOVER,
                      command=save).grid(row=5, column=0, columnspan=2, pady=(10, 0))

    def _open_history_window(self, name):
        win = ctk.CTkToplevel(self.root)
        win.title(f"{self.t('History - ')}{name}")
        win.configure(fg_color=theme.BG)
        win.attributes("-topmost", True)
        win.geometry("340x380")

        log = self.state["history"].get(name, [])
        text_box = ctk.CTkTextbox(win, fg_color=theme.BG_INPUT, text_color=theme.TEXT)
        text_box.pack(padx=10, pady=10, fill="both", expand=True)
        if not log:
            text_box.insert("1.0", self.t("No farm history logged yet for this resource."))
        else:
            lines = [f"{entry['date']}: {'+' if entry['delta'] >= 0 else ''}{entry['delta']}"
                     for entry in reversed(log)]
            text_box.insert("1.0", "\n".join(lines))
        text_box.configure(state="disabled")

        edit_frame = ctk.CTkFrame(win, fg_color="transparent")
        edit_frame.pack(padx=10, pady=(0, 10), fill="x")
        ctk.CTkLabel(edit_frame, text=self.t("Farm tip:"), text_color=theme.TEXT_DIM).pack(anchor="w")

        merged = storage.all_resources(self.state)
        current_tip = merged.get(name, {}).get("best_farm", "")
        tip_var = tk.StringVar(value=current_tip)
        row = ctk.CTkFrame(edit_frame, fg_color="transparent")
        row.pack(fill="x", pady=(2, 0))
        ctk.CTkEntry(row, textvariable=tip_var, fg_color=theme.BG_INPUT).pack(
            side="left", fill="x", expand=True)

        def save_tip():
            storage.override_resource(self.state, name, best_farm=tip_var.get().strip())
            self._update_row_display(name)
            win.destroy()

        ctk.CTkButton(row, text=self.t("Save"), width=56, fg_color=theme.ACCENT,
                      hover_color=theme.ACCENT_HOVER, command=save_tip).pack(side="left", padx=(4, 0))

    # ------------------------------------------------------------------
    # Rotation tracker (Survival/Defense/Excavation/Interception A-A-B-C)
    # ------------------------------------------------------------------
    def _build_rotation_panel(self, parent):
        header = ctk.CTkFrame(parent, fg_color="transparent")
        header.pack(fill="x", padx=12, pady=(12, 2))
        ctk.CTkLabel(header, text=self.t("Rotation Tracker"), font=(theme.FONT_FAMILY, 11, "bold"),
                     text_color=theme.ACCENT).pack(side="left")
        ctk.CTkButton(header, text="✕", width=22, height=22, fg_color="transparent",
                      hover_color=theme.DANGER, command=self._close_active_panel).pack(side="right")

        state = {"running": False, "start_time": None, "count": 0}

        ctk.CTkLabel(parent, text=self.t("Mission type:"), text_color=theme.TEXT).pack(
            anchor="w", padx=12, pady=(4, 2))
        mission_options = [
            self.t("Survival (time-based)"),
            self.t("Defense (every 5 waves)"),
            self.t("Excavation (every extractor)"),
            self.t("Interception (every round)"),
        ]
        mission_var = tk.StringVar(value=mission_options[0])
        ctk.CTkComboBox(parent, variable=mission_var, values=mission_options, width=250,
                         fg_color=theme.BG_INPUT, dropdown_fg_color=theme.BG_CARD).pack(padx=12, pady=(0, 10))

        rotation_lbl = ctk.CTkLabel(parent, text="—", font=(theme.FONT_FAMILY, 28, "bold"),
                                     text_color=theme.ACCENT)
        rotation_lbl.pack(pady=4)
        detail_lbl = ctk.CTkLabel(parent, text="", text_color=theme.TEXT_DIM)
        detail_lbl.pack()

        button_row = ctk.CTkFrame(parent, fg_color="transparent")
        button_row.pack(pady=10)
        start_btn = ctk.CTkButton(button_row, text=self.t("Start"), fg_color=theme.ACCENT,
                                   hover_color=theme.ACCENT_HOVER, width=80)
        start_btn.pack(side="left", padx=4)
        increment_btn = ctk.CTkButton(button_row, text="+1", fg_color=theme.BG_CARD,
                                       hover_color=theme.BG_CARD_HOVER, width=80)
        increment_btn.pack(side="left", padx=4)
        increment_btn.configure(state="disabled")

        def is_time_based():
            return mission_var.get() == mission_options[0]

        def refresh_display():
            if not state["running"] or not rotation_lbl.winfo_exists():
                return
            if is_time_based():
                elapsed = time_module.time() - state["start_time"]
                count = int(elapsed // 300)
                next_boundary = (count + 1) * 300
                remaining = next_boundary - elapsed
                letter = rotation_letter(count)
                rotation_lbl.configure(text=letter or "...")
                mins, secs = divmod(int(remaining), 60)
                next_letter = rotation_letter(count + 1)
                detail_lbl.configure(
                    text=f"{self.t('Next rotation in:')} {mins}:{secs:02d}  (-> {next_letter})"
                )
                self._rotation_job = self.root.after(1000, refresh_display)
            else:
                letter = rotation_letter(state["count"])
                rotation_lbl.configure(text=letter or "...")
                detail_lbl.configure(text=f"{self.t('Current rotation:')} #{state['count']}")

        def start():
            state["running"] = True
            state["start_time"] = time_module.time()
            state["count"] = 0
            start_btn.configure(text=self.t("Stop"), command=stop)
            increment_btn.configure(state="disabled" if is_time_based() else "normal")
            refresh_display()

        def stop():
            state["running"] = False
            self._cancel_rotation_job()
            rotation_lbl.configure(text="—")
            detail_lbl.configure(text="")
            start_btn.configure(text=self.t("Start"), command=start)

        def increment():
            if not state["running"] or is_time_based():
                return
            state["count"] += 1
            refresh_display()

        start_btn.configure(command=start)
        increment_btn.configure(text=self.t("+1 wave/round/extractor"), command=increment, width=180)

    # ------------------------------------------------------------------
    # Presets
    # ------------------------------------------------------------------
    def _build_presets_panel(self, parent):
        header = ctk.CTkFrame(parent, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=(10, 2))
        ctk.CTkLabel(header, text=self.t("Presets"), font=(theme.FONT_FAMILY, 11, "bold"),
                     text_color=theme.ACCENT).pack(side="left")
        ctk.CTkButton(header, text="✕", width=22, height=22, fg_color="transparent",
                      hover_color=theme.DANGER, command=self._close_active_panel).pack(side="right")

        ctk.CTkLabel(
            parent, text=self.t("Pick resources and target amounts, then save as a preset you can apply later in one click."),
            text_color=theme.TEXT_DIM, wraplength=320, justify="left",
        ).pack(padx=10, pady=(0, 6), anchor="w")

        existing_frame = ctk.CTkFrame(parent, fg_color="transparent")
        existing_frame.pack(fill="x", padx=10, pady=(0, 10))

        def refresh_existing():
            for child in existing_frame.winfo_children():
                child.destroy()
            presets = self.state.get("presets", {})
            if not presets:
                ctk.CTkLabel(existing_frame, text=self.t("No presets saved yet."),
                             text_color=theme.TEXT_DIM).pack(anchor="w")
                return
            for preset_name, goals in presets.items():
                row = ctk.CTkFrame(existing_frame, fg_color=theme.BG_CARD, corner_radius=6)
                row.pack(fill="x", pady=2)
                summary = ", ".join(f"{k}={v}" for k, v in list(goals.items())[:3])
                ctk.CTkLabel(row, text=f"{preset_name}  ({summary})", text_color=theme.TEXT,
                             font=(theme.FONT_FAMILY, 10)).pack(side="left", padx=6, pady=4)
                ctk.CTkButton(
                    row, text=self.t("Apply"), width=60, height=22, fg_color=theme.ACCENT,
                    hover_color=theme.ACCENT_HOVER,
                    command=lambda p=preset_name: (storage.apply_preset(self.state, p), self._rebuild_tracked_panel()),
                ).pack(side="right", padx=4)
                ctk.CTkButton(
                    row, text=self.t("Delete"), width=60, height=22, fg_color=theme.BG_INPUT,
                    hover_color=theme.DANGER,
                    command=lambda p=preset_name: (storage.delete_preset(self.state, p), refresh_existing()),
                ).pack(side="right", padx=4)

        refresh_existing()

        ctk.CTkLabel(parent, text=self.t("Build a preset"), font=(theme.FONT_FAMILY, 11, "bold"),
                     text_color=theme.ACCENT).pack(anchor="w", padx=10, pady=(6, 2))

        builder_rows = []
        builder_frame = ctk.CTkFrame(parent, fg_color="transparent")
        builder_frame.pack(fill="x", padx=10)

        merged = storage.all_resources(self.state)
        all_names = sorted(merged.keys())

        def add_builder_row():
            row_frame = ctk.CTkFrame(builder_frame, fg_color="transparent")
            row_frame.pack(fill="x", pady=2)
            name_var = tk.StringVar(value=all_names[0] if all_names else "")
            ctk.CTkComboBox(row_frame, variable=name_var, values=all_names, width=160,
                             fg_color=theme.BG_INPUT, dropdown_fg_color=theme.BG_CARD).pack(side="left")
            amount_var = tk.StringVar()
            ctk.CTkEntry(row_frame, textvariable=amount_var, width=60, fg_color=theme.BG_INPUT,
                         placeholder_text=self.t("qty")).pack(side="left", padx=4)

            def remove_row():
                row_frame.destroy()
                builder_rows.remove((name_var, amount_var))

            ctk.CTkButton(row_frame, text="✕", width=24, height=24, fg_color="transparent",
                          hover_color=theme.DANGER, command=remove_row).pack(side="left")
            builder_rows.append((name_var, amount_var))

        add_builder_row()
        ctk.CTkButton(parent, text="+ " + self.t("Add"), fg_color=theme.BG_CARD,
                      hover_color=theme.BG_CARD_HOVER, command=add_builder_row).pack(
            anchor="w", padx=10, pady=(4, 10))

        save_row = ctk.CTkFrame(parent, fg_color="transparent")
        save_row.pack(fill="x", padx=10, pady=(0, 10))
        ctk.CTkLabel(save_row, text=self.t("Preset name:"), text_color=theme.TEXT_DIM).pack(anchor="w")
        preset_name_var = tk.StringVar()
        name_row = ctk.CTkFrame(save_row, fg_color="transparent")
        name_row.pack(fill="x", pady=(2, 0))
        ctk.CTkEntry(name_row, textvariable=preset_name_var, fg_color=theme.BG_INPUT).pack(
            side="left", fill="x", expand=True)

        def save_preset():
            preset_name = preset_name_var.get().strip()
            if not preset_name:
                messagebox.showerror(APP_TITLE, self.t("Name is required."))
                return
            goals = {}
            for name_var, amount_var in builder_rows:
                name = name_var.get().strip()
                raw_amount = amount_var.get().strip()
                if not name or not raw_amount:
                    continue
                try:
                    goals[name] = int(raw_amount)
                except ValueError:
                    continue
            if not goals:
                messagebox.showerror(APP_TITLE, self.t("Enter a whole number."))
                return
            storage.save_preset(self.state, preset_name, goals)
            refresh_existing()
            preset_name_var.set("")

        ctk.CTkButton(name_row, text=self.t("Save"), width=60, fg_color=theme.ACCENT,
                      hover_color=theme.ACCENT_HOVER, command=save_preset).pack(side="left", padx=(4, 0))

    # ------------------------------------------------------------------
    # Worldstate auto-poll + "hot right now" cross-reference
    # ------------------------------------------------------------------
    def _poll_worldstate_loop(self):
        def on_result(data):
            self.event_queue.put(("worldstate_background", data))

        worldstate_api.fetch_worldstate_async(on_result)
        self.root.after(WORLDSTATE_POLL_MS, self._poll_worldstate_loop)

    def _handle_worldstate_background(self, data):
        self._latest_worldstate = data
        self._worldstate_loaded = True
        if self._active_tab == "world":
            self._render_world_tab()
        if not data:
            return
        self._check_baro(data)

        tracked_names = set(self.state["tracked"].keys())
        if not tracked_names:
            self._clear_hot_banner()
            return

        matches = []
        for inv in data.get("invasions", []):
            reward = inv.get("reward") or ""
            for name in tracked_names:
                if name.lower() in reward.lower():
                    matches.append(f"{name} {self.t('via invasion at')} {inv.get('node')}")

        darvo_label = self.t("Darvo's Deal of the Day:")
        for deal in data.get("daily_deals", []):
            item = deal.get("item") or ""
            for name in tracked_names:
                if name.lower() in item.lower():
                    matches.append(f"{name}: {darvo_label}")

        self._show_hot_banner(matches)

    def _check_baro(self, data, force=False):
        """Announce Baro once per visit, and say so if he sells anything
        from the player's watchlist."""
        trader = data.get("void_trader")
        if not trader or not trader.get("active"):
            return
        if not storage.get_setting(self.state, "notify_baro", True):
            return
        visit = trader.get("activation") or ""
        already = storage.get_setting(self.state, "last_baro_notified", "") == visit
        watch = [w.strip().lower() for w in
                 storage.get_setting(self.state, "baro_watch", "").split(",") if w.strip()]
        found = []
        for entry in trader.get("inventory", []):
            name = entry.get("item") or ""
            if any(w in name.lower() for w in watch):
                found.append(name)
        if already and not (force and found):
            return
        storage.set_setting(self.state, "last_baro_notified", visit)
        text = f"{self.t("Baro Ki'Teer has arrived at")} {trader.get('location')}"
        if found:
            text += f"\n⭐ {self.t('He sells what you watch:')} " + ", ".join(found)
        self._beep()
        self._show_notice(text, color=theme.WARNING if found else theme.ACCENT_BLUE)

    # ------------------------------------------------------------------
    # Argon decay ticker
    # ------------------------------------------------------------------
    def _tick_argon_decay(self):
        if "Argon Crystal" in self.state.get("tracked", {}):
            self._update_row_display("Argon Crystal")
        self.root.after(ARGON_TICK_MS, self._tick_argon_decay)

    # ------------------------------------------------------------------
    # EE.log watcher (auto-detect game context)
    # ------------------------------------------------------------------
    def _start_ee_log_watcher(self):
        def on_event(event_name, data):
            if event_name == "agent_created":
                self.event_queue.put(("agent_created", data))
            else:
                self.event_queue.put(("ee_log", event_name))

        self._ee_watcher = ee_log_reader.EELogWatcher(on_event)
        self._ee_watcher.start()

    _EVENT_LABELS = {
        "loading_mission": "Loading a mission...",
        "mission_complete": "Mission complete - log your resources!",
        "mission_failed": "Mission ended.",
        "loading_scene": "Loading...",
        "scene_switch": "Scene changed.",
    }

    # ------------------------------------------------------------------
    # Global hotkey (show/hide overlay)
    # ------------------------------------------------------------------
    def _start_hotkey_listener(self):
        if not HOTKEY_AVAILABLE:
            return

        def on_hotkey():
            self.event_queue.put(("toggle_visibility", None))

        def on_ghost():
            self.event_queue.put(("toggle_ghost", None))

        try:
            hotkey = pynput_keyboard.GlobalHotKeys({DEFAULT_HOTKEY: on_hotkey, GHOST_HOTKEY: on_ghost})
            hotkey.start()
            self._hotkey_listener = hotkey
        except Exception as exc:
            # Don't fail silently: remember why, so Settings can show it.
            global HOTKEY_ERROR
            HOTKEY_ERROR = repr(exc)

    def _toggle_visibility(self):
        if self.root.state() == "withdrawn":
            self.root.deiconify()
        else:
            self.root.withdraw()

    # ------------------------------------------------------------------
    # Cross-thread event pump
    # ------------------------------------------------------------------
    def _poll_events(self):
        try:
            while True:
                kind, payload = self.event_queue.get_nowait()
                if kind == "ee_log":
                    label = self.t(self._EVENT_LABELS.get(payload, payload))
                    self.context_label.configure(text=f"{self.t('Game context: unknown').split(':')[0]}: {label}")
                    if payload == "mission_complete":
                        self._show_mission_banner()
                elif kind == "agent_created":
                    self._on_agent_event(*payload)
                elif kind == "pickup":
                    self._on_pickup_event(*payload)
                elif kind == "pickup_status":
                    self._refresh_pickup_status()
                elif kind == "mastery_loaded":
                    self._on_mastery_loaded(*payload)
                elif kind == "toggle_ghost":
                    self._set_ghost(not self._ghost)
                elif kind == "worldstate_background":
                    self._handle_worldstate_background(payload)
                elif kind == "toggle_visibility":
                    self._toggle_visibility()
        except queue.Empty:
            pass
        self.root.after(200, self._poll_events)


def main():
    root = ctk.CTk()
    app = FarmTrackerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
