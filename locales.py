"""
Localization for the Farm Tracker UI.

How it works: every user-facing string in the app is written in English
and passed through `t(text)`. If the current language is Russian and a
translation exists in TRANSLATIONS below, that's shown instead;
otherwise the original English text is shown (so a missing translation
never breaks the app, it just stays in English).

Planet/node names and other in-game proper nouns are deliberately left
in English everywhere (including inside RESOURCE_TIPS_RU), since that's
what the game itself displays regardless of your system language.
"""

TRANSLATIONS = {
    "Farm Tracker": "Трекер фарма",
    "Track": "Трекать",
    "No resources tracked yet.\nPick one above and hit 'Track'.":
        "Пока нет ресурсов для отслеживания.\nВыбери выше и нажми 'Трекать'.",
    "Game context: unknown": "Контекст игры: неизвестно",
    "World State": "Мир сейчас",
    "+ New resource": "+ Новый ресурс",
    "Ctrl+Shift+F to hide/show": "Ctrl+Shift+F — показать/скрыть",
    "(install 'pynput' for hotkey)": "(установи 'pynput' для горячей клавиши)",
    "Have": "Есть",
    "Goal": "Цель",
    "Goal:": "Цель:",
    "History": "История",
    "Undo": "Отмена",
    "Add": "Добавить",
    "qty": "кол-во",
    "No farm tip saved yet.": "Подсказка по фарму пока не добавлена.",
    "Mission complete - quick log:": "Миссия завершена — быстрый лог:",
    "(track a resource below to log it here)": "(добавь ресурс для трекинга ниже)",
    "Hot right now:": "Горячо прямо сейчас:",
    "via invasion at": "через вторжение на",
    "Worldstate - live game events": "Мир сейчас — события в реальном времени",
    "What's happening in the game world right now,\nto help decide what's worth farming.":
        "Что сейчас происходит в игровом мире —\nчтобы понять, что выгодно фармить.",
    "Loading live data from Warframe Worldstate API...":
        "Загружаю актуальные данные из Warframe Worldstate API...",
    "Could not reach the Worldstate API right now. Check your internet connection and try again.":
        "Не получилось получить данные от Worldstate API. Проверь интернет-соединение и попробуй снова.",
    "Active Void Fissures:": "Активные разломы Пустоты:",
    "Active Invasions:": "Активные вторжения:",
    "reward:": "награда:",
    "No notable world events right now.": "Сейчас нет заметных событий в мире.",
    "History - ": "История — ",
    "No farm history logged yet for this resource.": "История фарма по этому ресурсу пока пуста.",
    "Farm tip:": "Подсказка по фарму:",
    "Save": "Сохранить",
    "Add new resource to the database": "Добавить новый ресурс в базу",
    "Name:": "Название:",
    "Category:": "Категория:",
    "Rarity:": "Редкость:",
    "Best farm tip:": "Лучшая подсказка по фарму:",
    "Name is required.": "Название обязательно.",
    "A resource with this name already exists.": "Ресурс с таким названием уже существует.",
    "Enter a whole number.": "Введи целое число.",
    "Goal must be a whole number.": "Цель должна быть целым числом.",
    "Nothing to undo yet this session.": "В этой сессии пока нечего отменять.",
    "Stop tracking": "Прекратить отслеживание",
    "(Its farm history is kept.)": "(История фарма сохранится.)",

    # --- Baro Ki'Teer / Darvo ------------------------------------------------
    "Void Trader (Baro Ki'Teer):": "Баро Ки'Тиер (Торговец Пустоты):",
    "Here now at": "Сейчас здесь, на",
    "until": "до",
    "Not here right now. Next visit:": "Сейчас его нет. Следующий визит:",
    "His inventory:": "Его товары:",
    "ducats": "дукатов",
    "credits": "кредитов",
    "Darvo's Deal of the Day:": "Сделка дня от Дарво:",
    "off": "скидка",
    "sold": "продано",
    "left": "осталось",

    # --- Argon decay --------------------------------------------------------
    "Argon decays at daily reset (00:00 UTC) in": "Аргон сгорит при сбросе (00:00 UTC) через",
    "You have": "У тебя есть",
    "unspent - log it or craft with it before it decays!":
        "непотраченных — успей использовать до сброса!",

    # --- Rotation tracker -----------------------------------------------------
    "Rotation Tracker": "Счётчик ротаций",
    "Mission type:": "Тип миссии:",
    "Start": "Старт",
    "Stop": "Стоп",
    "+1 wave/round/extractor": "+1 волна/раунд/экстрактор",
    "Current rotation:": "Текущая ротация:",
    "Next rotation in:": "Следующая ротация через:",
    "Survival (time-based)": "Выживание (по времени)",
    "Defense (every 5 waves)": "Оборона (каждые 5 волн)",
    "Excavation (every extractor)": "Раскопки (каждый экстрактор)",
    "Interception (every round)": "Перехват (каждый раунд)",

    # --- Presets -------------------------------------------------------------
    "Presets": "Пресеты",
    "Build a preset": "Создать пресет",
    "Preset name:": "Название пресета:",
    "Apply": "Применить",
    "Delete": "Удалить",
    "No presets saved yet.": "Пресеты пока не созданы.",
    "Pick resources and target amounts, then save as a preset you can apply later in one click.":
        "Выбери ресурсы и нужное количество, сохрани как пресет — потом применяй в один клик.",

    # --- Compact mode ----------------------------------------------------------
    "Compact mode": "Компактный режим",

    # --- Kill counter --------------------------------------------------------
    "Kills this mission:": "Убийств за миссию:",
    "Reset": "Сброс",
    "Search resource...": "Поиск ресурса...",

    # --- Tabs ----------------------------------------------------------------
    "Resources": "Ресурсы",
    "Session": "Сессия",
    "World": "Мир",
    "Mastery": "Мастерство",
    "More": "Ещё",

    # --- Session tab -----------------------------------------------------------
    "Session:": "Сессия:",
    "Reset session": "Сбросить сессию",
    "Kills this session:": "Убийств за сессию:",
    "Nothing gained yet. Pick things up or press + on a resource.":
        "Пока ничего. Подбирай ресурсы или жми «+» у ресурса.",
    "/h": "/ч",
    "goal in": "до цели",
    "goal reached": "цель достигнута",
    "Goal reached:": "Цель достигнута:",

    # --- World tab / Baro --------------------------------------------------------
    "Baro watchlist (comma-separated):": "Следить за товарами Баро (через запятую):",
    "Refresh": "Обновить",
    "Baro Ki'Teer has arrived at": "Баро Ки'Тиер прилетел на",
    "He sells what you watch:": "Продаёт то, что ты ждал:",

    # --- Mastery tab ----------------------------------------------------------------
    "Search item...": "Поиск предмета...",
    "All": "Все",
    "My MR:": "Мой MR:",
    "Hide mastered": "Скрыть освоенное",
    "Within my MR": "Доступно по моему MR",
    "Update item list": "Обновить список",
    "Downloading item list...": "Скачиваю список предметов...",
    "Download the item list to start.": "Скачай список предметов, чтобы начать.",
    "Could not download the item list. Check your internet connection.":
        "Не удалось скачать список. Проверь интернет.",
    "Mastered": "Освоено",
    "Show more": "Показать ещё",

    # --- Settings tab ------------------------------------------------------------------
    "Language": "Язык",
    "Window": "Окно",
    "Always on top": "Поверх всех окон",
    "Ghost mode (clicks pass through)": "Призрачный режим (клики проходят сквозь окно)",
    "Ghost mode ON - press Ctrl+Shift+G to turn it off":
        "Призрачный режим включён — Ctrl+Shift+G чтобы выключить",
    "Opacity": "Прозрачность",
    "Ctrl+Shift+F - show/hide, Ctrl+Shift+G - ghost mode":
        "Ctrl+Shift+F — показать/скрыть, Ctrl+Shift+G — призрачный режим",
    "If hotkeys do nothing while Warframe is focused, run the tracker as administrator.":
        "Если горячие клавиши не срабатывают в Warframe, запусти трекер от имени администратора.",
    "Notifications": "Уведомления",
    "Notify when a goal is reached": "Уведомлять о достижении цели",
    "Notify when Baro arrives": "Уведомлять о прилёте Баро",
    "Sound": "Звук",
    "Backup": "Резервная копия",
    "Export backup": "Сохранить копию",
    "Import backup": "Загрузить копию",
    "Backup saved": "Копия сохранена",
    "Backup restored": "Копия загружена",
    "This is not a Farm Tracker backup.": "Это не резервная копия трекера.",
    "A daily automatic backup is kept in the 'backups' folder.":
        "Ежедневная копия хранится в папке 'backups' рядом с программой.",
    "No matches": "Ничего не найдено",

    # --- Auto-pickup (OCR) ---------------------------------------------------
    "Auto-pickup (OCR)": "Авто-подбор (OCR)",
    "OCR ready": "OCR готов",
    "Tesseract not found - see README": "Tesseract не найден — см. README",
    "Russian OCR data missing (tessdata folder)": "Нет русских данных OCR (папка tessdata)",
    "Pillow missing - run: pip install Pillow": "Нет Pillow — выполни: pip install Pillow",
    "Screen capture only works on Windows": "Захват экрана работает только в Windows",
    "New pickup text:": "Новая надпись:",
    "Which resource is this?": "Какой это ресурс?",
    "Ignore": "Игнорировать",
    "OK": "OK",
    "picked up": "подобрано",
}

# Rarity badge text, shown on each resource card.
RARITY_RU = {
    "common": "ОБЫЧНЫЙ",
    "uncommon": "НЕОБЫЧНЫЙ",
    "rare": "РЕДКИЙ",
    "special": "ОСОБЫЙ",
}

# Category names (used in the "+ New resource" category picker and
# anywhere a category is shown). Kept here rather than resources_data.py
# so the English category list stays the single source of truth.
CATEGORY_RU = {
    "Origin System": "Солнечная система",
    "Plains of Eidolon": "Равнины Эйдолона",
    "Orb Vallis": "Долина Орб",
    "Cambion Drift": "Камбионский Дрифт",
    "Railjack (Empyrean)": "Рейлджек (Эмпиреи)",
    "Duviri / Circuit": "Дувири / Виток",
}

# Russian farm tips. Planet/node/mission names are intentionally left in
# English (that's how the game itself displays them), only the
# sentence structure around them is translated. Resources without an
# entry here just fall back to the English tip - nothing breaks.
RESOURCE_TIPS_RU = {
    "Ferrite": "Tikal (Earth) - Раскопки/Выживание, или любая Пустота (Выживание/Оборона).",
    "Rubedo": "Mars или Phobos; падает массово с врагов Grineer почти везде.",
    "Salvage": "Mars - Arcadia (Выживание, Corpus), падает большими стопками с врагов/контейнеров Corpus.",
    "Alloy Plate": "Ceres - Gabii или Draco, либо Venus - Malva.",
    "Polymer Bundle": "Saturn - Helene (Оборона), даёт крупные стопки за забег.",
    "Nano Spores": "Saturn - Helene (Оборона) или Eris - Akkad; тайлы Infested дают постоянно.",
    "Circuits": "Venus - Kiliken, либо Ceres - Gabii.",
    "Plastids": "Eris - Akkad или Zabala, либо Uranus - Ophelia.",
    "Cryotic": "Любая миссия Раскопки; популярны Europa - Valefor или Pluto - Hieracon.",
    "Oxium": "Neptune - Galatea или Despina (узлы с Corpus, хороший дроп Oxium).",
    "Hexenon": "Только тайлсет Jupiter - любая миссия Corpus на Jupiter с хорошей плотностью врагов.",
    "Tellurium": "Падает с крупных юнитов Corpus/Grineer (Bursa, хеви) на Jupiter/Europa, либо покупается у Little Duck за репутацию.",
    "Neural Sensors": "Jupiter - Cameria/Elara, либо фарми Alad V (Themisto) для гарантированного дропа.",
    "Orokin Cell": "Ceres - Draco, Saturn - Piscinas, либо боссы (Sargas Ruk / Vor).",
    "Neurodes": "Earth - Tikal (Раскопки) или узлы Deimos.",
    "Gallium": "Mars - Wahiba (Выживание, Infested) даёт хороший дроп Gallium.",
    "Morphics": "Mercury - Apollodorus, либо Mars - Wahiba.",
    "Control Module": "Neptune - Triton (Выживание), либо любая Пустота (Выживание/Оборона).",
    "Argon Crystal": "Пустота - Mot (Выживание) или Ukko (Захват). Сгорает при дневном сбросе - фарми перед использованием!",
    "Kuva": "Kuva Fortress - Taveuni (Выживание), либо любая активная миссия Kuva Сифон/Наводнение.",
    "Credits": "Падает со всех врагов и контейнеров, а также выдаётся наградой за миссии. Впиши сюда свой любимый способ фарма кредитов.",
    "Endo": "Награды сорти, Арбитраций, либо продажа дублей модов/конверсия звёзд Ayatan.",
}

# World tab sections (planet / node / mission / item names stay English).
TRANSLATIONS.update({
    "Baro, Darvo, Sortie": "Баро, Дарво, Сорти",
    "System events": "События системы",
    "Planet cycles": "Циклы планет",
    "Arbitration": "Арбитраж",
    "Void fissures": "Разрывы Бездны",
    "Steel Path fissures": "Разрывы Стального пути",
    "Invasions": "Вторжения",
    "Special events": "Особые события",
    "Sortie": "Сорти",
    "Nothing here right now.": "Сейчас здесь ничего нет.",
    "ended": "закончилось",
    "left": "осталось",
    "Global boosters:": "Глобальные бонусы (x2 ресурсы/кредиты и т.п.):",
    "No active boosters.": "Сейчас нет активных бонусов.",
    "Latest announcements:": "Последние объявления:",
    "Update": "Обновление",
    "Stream": "Стрим",
    "no data": "нет данных",
    "ends in": "смена через",
    "No arbitration data right now (the data source returned nothing).":
        "Данных об арбитраже нет (источник данных сейчас ничего не вернул).",
    "Attackers": "Атакующие",
    "Defenders": "Защитники",
    "Events:": "События:",
    "Alerts:": "Тревоги:",
    "Progress": "Прогресс",
    "Reward": "Награда",
    "Could not reach the Warframe API. Check your internet connection.":
        "Не удалось связаться с Warframe API. Проверь интернет.",
})
TRANSLATIONS["Archwing"] = "Арчвинг"
TRANSLATIONS.update({
    "Support": "Поддержка",
    "Copy": "Копировать",
    "Copied": "Скопировано",
    "Free and made in spare time. If it helps your farming, you can support the project.":
        "Бесплатно и сделано в свободное время. Если трекер помогает с фармом, можешь поддержать проект.",
})
