"""D&D 3.5 language helpers for D&D Beside."""

from __future__ import annotations

SPEAK_LANGUAGE_SKILL = "Speak Language"

# Standard SRD languages (excluding secret Druidic from general picks).
STANDARD_LANGUAGES = (
    "Abyssal",
    "Aquan",
    "Auran",
    "Celestial",
    "Common",
    "Draconic",
    "Dwarven",
    "Elven",
    "Giant",
    "Gnome",
    "Goblin",
    "Gnoll",
    "Halfling",
    "Ignan",
    "Infernal",
    "Orc",
    "Sylvan",
    "Terran",
    "Undercommon",
)

SECRET_LANGUAGES = frozenset({"Druidic"})

CLASS_LANGUAGE_GRANTS = {
    "Druid": ("Druidic",),
}

TRAINED_ONLY_SKILLS = frozenset({SPEAK_LANGUAGE_SKILL})


def ability_modifier(score):
    try:
        return (int(score) - 10) // 2
    except (TypeError, ValueError):
        return 0


def int_bonus_language_count(int_score):
    """Extra languages from starting Intelligence bonus (+1 per point above +0)."""
    return max(0, ability_modifier(int_score))


def ability_score_improvement_bonus(data, ability_name):
    """+1 per saved ASI milestone applied to this ability."""
    choices = (data or {}).get("ability_score_improvements") or {}
    return sum(
        1 for chosen in choices.values()
        if str(chosen or "").strip() == ability_name
    )


def starting_intelligence_score(data, races_db=None):
    """Intelligence at 1st level for bonus languages: base + racial only.

    Excludes ability score increases, enhancement bonuses, and inherent bonuses.
    Legacy saves that left base at 10 but stored the real creation score in total
    are handled only when no item/ASI adjustments are recorded on Intelligence.
    """
    abilities = (data or {}).get("abilities") or {}
    int_entry = abilities.get("Intelligence") or {}
    try:
        base = int(int_entry.get("base", 10) or 10)
    except (TypeError, ValueError):
        base = 10
    try:
        racial = int(int_entry.get("racial", 0) or 0)
    except (TypeError, ValueError):
        racial = 0
    if racial == 0 and races_db:
        race = str((data or {}).get("race") or "").strip()
        race_data = (races_db or {}).get(race, {}) or {}
        try:
            racial = int(race_data.get("int", 0) or 0)
        except (TypeError, ValueError):
            racial = 0

    creation = base + racial
    asi = ability_score_improvement_bonus(data, "Intelligence")
    try:
        enh = int(int_entry.get("enh", 0) or 0)
    except (TypeError, ValueError):
        enh = 0
    try:
        inherent = int(int_entry.get("inherent", 0) or 0)
    except (TypeError, ValueError):
        inherent = 0
    try:
        total = int(int_entry.get("total", creation) or creation)
    except (TypeError, ValueError):
        total = creation

    # Older sheets sometimes never updated base from the default 10 even though
    # total still reflects the rolled/bought creation score (before ASI/items).
    if (
        not (data or {}).get("bonus_language_choices")
        and asi == 0
        and enh == 0
        and inherent == 0
        and base == 10
        and total > creation
    ):
        return total
    return creation


def pending_bonus_language_picks(data, races_db):
    """How many Int bonus languages still need to be chosen."""
    needed = int_bonus_language_count(starting_intelligence_score(data, races_db))
    if needed <= 0:
        return 0
    existing = len(list((data or {}).get("bonus_language_choices") or []))
    return max(0, needed - existing)


def needs_legacy_bonus_language_setup(data, races_db):
    """True when this character still owes Intelligence bonus language picks."""
    return pending_bonus_language_picks(data, races_db) > 0


def racial_automatic_languages(race_name, races_db):
    race = (races_db or {}).get(race_name, {}) or {}
    langs = list(race.get("languages") or [])
    if not langs and race_name == "Human":
        langs = ["Common"]
    return [str(lang).strip() for lang in langs if str(lang).strip()]


def racial_bonus_language_pool(race_name, races_db):
    """Return list of bonus options, or None if any non-secret language is allowed."""
    race = (races_db or {}).get(race_name, {}) or {}
    if race.get("bonus_languages_any"):
        return None
    bonus = list(race.get("bonus_languages") or [])
    return [str(lang).strip() for lang in bonus if str(lang).strip()]


def class_granted_languages(classes, levels):
    """Languages granted by class levels, e.g. Druidic for Druids."""
    granted = []
    class_list = list(classes or [])
    level_list = list(levels or [])
    while len(level_list) < len(class_list):
        level_list.append(0)
    for cls_name, lvl in zip(class_list, level_list):
        if not cls_name or cls_name == "None":
            continue
        try:
            level = int(lvl or 0)
        except (TypeError, ValueError):
            level = 0
        if level <= 0:
            continue
        for lang in CLASS_LANGUAGE_GRANTS.get(cls_name, ()):
            if lang not in granted:
                granted.append(lang)
    return granted


def selectable_languages(*, allow_any=False, exclude_secret=True):
    if allow_any:
        pool = list(STANDARD_LANGUAGES)
    else:
        pool = list(STANDARD_LANGUAGES)
    if not exclude_secret:
        pool.extend(lang for lang in SECRET_LANGUAGES if lang not in pool)
    return sorted(pool, key=str.lower)


def bonus_language_options(race_name, races_db):
    pool = racial_bonus_language_pool(race_name, races_db)
    if pool is None:
        return selectable_languages(allow_any=True)
    return sorted(pool, key=str.lower)


def speak_language_options(*, include_secret=False):
    return selectable_languages(exclude_secret=not include_secret)


def merge_unique_languages(*parts):
    seen = set()
    merged = []
    for part in parts:
        for lang in part or []:
            text = str(lang or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            merged.append(text)
    return sorted(merged, key=str.lower)


def collect_character_languages(data, races_db):
    """All languages the character knows from race, choices, class, and Speak Language."""
    race = str((data or {}).get("race") or "").strip()
    abilities = (data or {}).get("abilities") or {}
    int_entry = abilities.get("Intelligence") or {}
    int_score = int_entry.get("total", int_entry.get("base", 10))

    automatic = racial_automatic_languages(race, races_db)
    bonus_choices = list((data or {}).get("bonus_language_choices") or [])
    speak_choices = list((data or {}).get("speak_language_languages") or [])
    classes = (data or {}).get("classes") or []
    levels = (data or {}).get("levels") or []
    class_langs = class_granted_languages(classes, levels)

    return merge_unique_languages(automatic, bonus_choices, speak_choices, class_langs)


def format_speaks_display(data, races_db):
    """Display string for Stats page, annotating class-granted languages."""
    known = collect_character_languages(data, races_db)
    if not known:
        return "—"

    classes = (data or {}).get("classes") or []
    levels = (data or {}).get("levels") or []
    class_lang_sources = {}
    class_list = list(classes or [])
    level_list = list(levels or [])
    while len(level_list) < len(class_list):
        level_list.append(0)
    for cls_name, lvl in zip(class_list, level_list):
        if not cls_name or cls_name == "None":
            continue
        try:
            level = int(lvl or 0)
        except (TypeError, ValueError):
            level = 0
        if level <= 0:
            continue
        for lang in CLASS_LANGUAGE_GRANTS.get(cls_name, ()):
            class_lang_sources.setdefault(lang, cls_name)

    parts = []
    for lang in known:
        if lang in class_lang_sources:
            parts.append(f"{lang} ({class_lang_sources[lang]})")
        else:
            parts.append(lang)
    return ", ".join(parts)


def race_language_summary(race_name, races_db):
    """Short language blurb for race descriptions."""
    auto = racial_automatic_languages(race_name, races_db)
    lines = []
    if auto:
        lines.append("Automatic Languages: " + ", ".join(auto))
    if racial_bonus_language_pool(race_name, races_db) is None:
        lines.append(
            "Bonus Languages: Any (other than secret languages, such as Druidic).",
        )
    else:
        bonus = racial_bonus_language_pool(race_name, races_db)
        if bonus:
            lines.append("Bonus Languages: " + ", ".join(bonus))
    return lines


def speak_language_rank_value(data):
    key = f"skill_{SPEAK_LANGUAGE_SKILL}_rank"
    raw = (data or {}).get(key, 0)
    try:
        return max(0, int(float(str(raw).strip() or 0)))
    except (TypeError, ValueError):
        return 0


def required_speak_language_picks(data):
    return speak_language_rank_value(data)


def known_languages_for_picker(data, races_db):
    return set(collect_character_languages(data, races_db))


def build_language_picker(
    parent,
    *,
    title,
    subtitle,
    languages,
    known_languages,
    selected,
    max_picks,
    on_change=None,
    wraplength=900,
    height=380,
):
    """Scrollable multi-select language picker; greys out already-known languages."""
    import customtkinter as ctk

    selected = list(selected or [])
    known = set(known_languages or [])
    buttons = {}

    ctk.CTkLabel(
        parent,
        text=title,
        font=ctk.CTkFont(size=14, weight="bold"),
    ).pack(anchor="w", pady=(0, 4))
    ctk.CTkLabel(
        parent,
        text=subtitle,
        text_color="#aaaaaa",
        wraplength=wraplength,
        justify="left",
    ).pack(anchor="w", pady=(0, 8))

    status = ctk.CTkLabel(parent, text="", text_color="#28a99e")
    status.pack(anchor="w", pady=(0, 6))

    scroll = ctk.CTkScrollableFrame(parent, height=height, fg_color="#2F2F2F")
    scroll.pack(fill="both", expand=True)

    def _refresh_status():
        count = len(selected)
        status.configure(
            text=f"Selected {count} / {max_picks}",
            text_color="#d9534f" if count != max_picks else "#28a99e",
        )

    def _refresh_buttons():
        for lang, btn in buttons.items():
            is_known = lang in known and lang not in selected
            is_selected = lang in selected
            try:
                if is_known:
                    btn.configure(
                        state="disabled",
                        fg_color="#2a2a2a",
                        text_color="#666666",
                    )
                elif is_selected:
                    btn.configure(
                        state="normal",
                        fg_color="#c77626",
                        hover_color="#a56b32",
                        text_color="#ffffff",
                    )
                else:
                    btn.configure(
                        state="normal",
                        fg_color="#3a3a3a",
                        hover_color="#4a4a4a",
                        text_color="#ffffff",
                    )
            except Exception:
                pass
        _refresh_status()
        if on_change:
            on_change(list(selected))

    def _toggle(lang):
        if lang in known and lang not in selected:
            return
        if lang in selected:
            selected.remove(lang)
        elif len(selected) < max_picks:
            selected.append(lang)
        _refresh_buttons()

    cols = 3
    for idx, lang in enumerate(languages):
        row = idx // cols
        col = idx % cols
        if col == 0:
            row_frame = ctk.CTkFrame(scroll, fg_color="transparent")
            row_frame.pack(fill="x", padx=4, pady=2)
        btn = ctk.CTkButton(
            row_frame,
            text=lang,
            anchor="w",
            height=28,
            command=lambda l=lang: _toggle(l),
        )
        btn.pack(side="left", fill="x", expand=True, padx=3)
        buttons[lang] = btn

    _refresh_buttons()

    def get_selected():
        return list(selected)

    def set_selected(values):
        selected.clear()
        for lang in values or []:
            if lang in languages:
                selected.append(lang)
        _refresh_buttons()

    return {"get_selected": get_selected, "set_selected": set_selected, "refresh": _refresh_buttons}