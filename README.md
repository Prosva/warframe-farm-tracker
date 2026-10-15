# Warframe Farm Tracker

## Быстрый старт (для тех, кто просто хочет пользоваться)

1. Скачай **FarmTracker.exe** со страницы *Releases* этого репозитория и положи в любую папку
   (рядом создастся файл `user_data.json` с твоими данными — поэтому лучше не в защищённую
   системную папку).
2. Запусти. Windows может показать предупреждение SmartScreen («неизвестный издатель») —
   программа не подписана. Нажми «Подробнее» → «Выполнить в любом случае».
   Если антивирус ругается, это ложное срабатывание типичное для программ, собранных
   PyInstaller; исходный код лежит рядом, его можно прочитать или собрать самому (`build_exe.bat`).
3. **Авто-подбор ресурсов (по желанию):** установи **Tesseract OCR** для Windows
   (установщик от UB-Mannheim: https://github.com/UB-Mannheim/tesseract/wiki, папка по умолчанию).
   Русские данные уже встроены в exe. В игре включи режим «Окно без рамки» (Borderless),
   в программе включи переключатель «Авто-подбор (OCR)». Без Tesseract всё остальное работает.
4. Всё, что программа делает с игрой: читает файл `EE.log` и делает снимки небольшой области экрана
   (как WFInfo). В память игры она не лезет и ничего не нажимает за тебя.

## Quick start (English)

Download `FarmTracker.exe` from the repo's *Releases* page, run it (click "More info" → "Run anyway"
on the SmartScreen prompt - the exe is unsigned). For the optional auto-pickup feature also install
Tesseract OCR for Windows (UB-Mannheim build); the Russian OCR data is bundled inside the exe. Use
Borderless/Windowed mode in-game.

---

A small always-on-top overlay for tracking farmed resources, with farm
location tips, live Worldstate data (sorties/fissures/invasions), and
auto-detected mission context from the game's own EE.log file.

## What it does

- Track **several resources at once** — each one gets its own card
  with +1/+5/+10/+50 buttons, an Undo, a goal, and a progress bar.
- **Farm rate + ETA**: each card shows roughly how much you farm per
  day (from your own logged history) and how many days until you hit
  your goal at that pace.
- A **"mission complete" banner** pops up automatically (detected from
  the game's own log file) with one-tap +1 buttons for everything
  you're tracking, so you don't have to scroll after every run.
- A **"hot right now" banner** checks live invasions every 5 minutes
  and tells you if one of your tracked resources is currently an
  invasion reward somewhere.
- "World State" button: live sorties, fissures, invasions, Cetus
  day/night cycle, pulled from the public Warframe Worldstate API.
- Add your own resources to **any** category (not just Duviri) via
  "+ New resource", with an editable farm-tip.
- Dark blue/purple themed UI (CustomTkinter), always-on-top, draggable,
  collapsible.
- Hotkey `Ctrl+Shift+F` shows/hides the overlay instantly. If it does nothing while Warframe is focused (e.g. Warframe runs as administrator), run FarmTracker.exe as administrator too: Windows doesn't let a normal program see keys pressed in an elevated one.
- Everything is saved to `user_data.json` next to the program — it
  survives restarts and app updates.

## Tabs

- **Resources** - tracked resources, search/add, auto-pickup switch,
  new resource, rotation tracker, presets.
- **Session** - what you gained this session, per-hour rate and a
  realistic ETA to each goal at *this session's* pace, kills this
  session, game context. Kept in memory; "Reset session" starts over.
- **World** - sortie, fissures, invasions, Cetus cycle, Baro, Darvo,
  plus a Baro watchlist (get a notification when he sells something
  you want).
- **Mastery** - checklist of every masterable item (downloaded once from
  the public warframestat.us database and cached in
  `mastery_cache.json`). Tick what you have mastered, search, filter by
  category, hide mastered, show only what your Mastery Rank allows
  (sorted lowest requirement first). Warframe has no API for your own
  inventory, so ticking is manual.
- **More** - language, compact mode, always-on-top, opacity slider,
  ghost mode (clicks pass through the overlay; Ctrl+Shift+G toggles it
  and it always starts OFF), notification switches (goal reached,
  Baro, sound), backup export/import. A copy of your data is also kept
  automatically once a day in the `backups` folder (last 7 days).

## Auto-pickup (OCR) - optional

The "Auto-pickup (OCR)" switch reads the small "143 ВТОРСЫРЬЁ" popups
that Warframe shows when you pick something up, and adds them to the
matching tracked resource. It only takes screenshots of a small strip
of the screen (like WFInfo does) and never touches the game.

Setup (once):
1. Install **Tesseract OCR** for Windows (the installer from the
   UB-Mannheim build, https://github.com/UB-Mannheim/tesseract/wiki).
2. The Russian language data (`tessdata` folder) is bundled inside
   `FarmTracker.exe` by `build_exe.bat`. When running from source keep
   the `tessdata` folder next to `main.py`. A `tessdata` folder placed
   next to the exe takes priority if you ever want to override it.
3. Run the game in **Borderless/Windowed** mode (exclusive fullscreen can
   give a black capture), then turn the switch on.

The first time a popup text is not recognised the app asks which
resource it is (or to ignore it) and remembers the answer. Every OCR
read is logged to `pickup_debug.log` (and the last captured strip to
`pickup_last_crop.png`) next to the program - handy for checking or
tuning accuracy. Only resources you are *tracking* are counted, and
the Undo button reverts the last automatic add.

## Running it from source (for testing/tweaking)

```
pip install -r requirements.txt
python main.py
```

Requires Python 3.9+ on Windows. `tkinter` ships with the standard
Windows Python installer (no separate install needed).

## Building a standalone .exe

This has to be done **on a Windows machine** (PyInstaller builds for
the OS it runs on, it can't cross-compile a Windows .exe from Linux).

1. Install Python 3.9+ from python.org if you don't have it (check
   "Add python.exe to PATH" during install).
2. Open a terminal in this folder and run:
   ```
   pip install -r requirements.txt
   pyinstaller --onefile --windowed --name "FarmTracker" main.py
   ```
3. Your .exe will appear in the `dist/` folder as `FarmTracker.exe`.
   You can move that single file anywhere — it will create
   `user_data.json` next to itself the first time it runs.

`--windowed` hides the console window; drop it if you want to see
error output while testing.

## Editing the resource database

Open `resources_data.py` in any text editor. Each resource is a
dictionary entry — add one, fix a location, whatever. You don't need
to know Python, just copy the pattern of an existing entry.

You can *also* edit a single resource's farm tip from inside the running
app: select it, open "History", edit the tip field, hit Save. That edit
is saved to `user_data.json` and will **not** be lost even if you later
update `resources_data.py`, since overrides always take priority.

## Notes on accuracy

- Resource locations were checked against multiple sources as of
  October 2026 but Warframe changes constantly (vaulting, reworks,
  new tilesets). Treat tips as a strong starting point, not gospel —
  and fix them in-app if you find a better spot.
- Duviri/Circuit resources are intentionally NOT pre-filled — add your
  own as you see them, since reliable public data on exact names was
  too inconsistent to trust blindly.
- The Worldstate API shows *the game world's* state (sorties, fissures,
  etc.) — never your own account/inventory. There is no official API
  for reading a player's personal inventory, which is why resource
  counts are tracked manually in this app.

## Project files

| File                | Purpose                                             |
|---------------------|------------------------------------------------------|
| `main.py`            | The GUI (entry point)                              |
| `theme.py`            | Color palette for the UI                            |
| `resources_data.py`  | Editable resource database                          |
| `storage.py`         | Reading/writing `user_data.json`, farm-rate/ETA math |
| `ee_log_reader.py`   | Tails Warframe's EE.log for mission context          |
| `worldstate_api.py`  | Fetches live world data from warframestat.us         |

## A note on this update

This version switched the UI library to CustomTkinter for the dark
blue/purple look. If `build_exe.bat` ever complains about a missing
theme/font file at runtime (a known PyInstaller + CustomTkinter
gotcha), make sure `--collect-all customtkinter --collect-all
darkdetect` are in the PyInstaller command (they already are in
`build_exe.bat` — just flagging it in case you build manually).


## Вкладка «Мир» / World tab

Список сверху переключает разделы: Баро/Дарво/Сорти, события системы, циклы планет, арбитраж, разрывы Бездны, разрывы Стального пути, вторжения, особые события. Данные — с warframestat.us. «Благословения мастеров» в реле никакой API не отдаёт, поэтому их нет.

The dropdown switches sections (Baro/Darvo/Sortie, system events, planet cycles, arbitration, fissures, Steel Path fissures, invasions, special events). Relay 'blessings' are not exposed by any API, so they are not included.

## Без установки Tesseract / Portable Tesseract

Можно не ставить Tesseract: положи его папку `Tesseract-OCR` (с `tesseract.exe` внутри, из установленного Tesseract) рядом с `FarmTracker.exe`. Программа найдёт её сама.
You can skip installing Tesseract: put a `Tesseract-OCR` folder (containing `tesseract.exe`) next to `FarmTracker.exe`; the app finds it automatically.
