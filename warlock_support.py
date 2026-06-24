"""Warlock invocations, eldritch blast, DR, and fast healing helpers for D&D Beside."""

from __future__ import annotations

import json
import os
import re

WARLOCK_CLASS = "Warlock"
ELDRITCH_BLAST_NAME = "Eldritch Blast"

_FALLBACK_INVOCATIONS_KNOWN_BY_LEVEL = {
    1: 1, 2: 2, 3: 2, 4: 3, 5: 3, 6: 4, 7: 4, 8: 5, 9: 5, 10: 6,
    11: 7, 12: 7, 13: 8, 14: 8, 15: 9, 16: 10, 17: 10, 18: 11, 19: 11, 20: 12,
}

_BUNDLE_DIR = None
_INVOCATIONS_KNOWN_TABLE = None

GRADE_MIN_LEVEL = {"least": 2, "lesser": 6, "greater": 11, "dark": 16}

WARLOCK_DR_BY_LEVEL = {
    3: "1/cold iron", 7: "2/cold iron", 11: "3/cold iron",
    15: "4/cold iron", 19: "5/cold iron",
}

FIENDISH_RESILIENCE_BY_LEVEL = {8: 1, 13: 2, 18: 5}

ENERGY_RESISTANCE_BY_LEVEL = {10: 5, 20: 10}

WARLOCK_ENERGY_TYPES = ("acid", "cold", "electricity", "fire", "sonic")

TRADITIONAL_CASTER_CLASSES = {
    "Wizard", "Sorcerer", "Bard", "Cleric", "Druid", "Paladin", "Ranger",
}


def load_invocations_db(bundle_dir):
    path = os.path.join(bundle_dir, "invocations.json")
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def set_bundle_dir(bundle_dir):
    """Remember the app bundle path so invocation tables can load classes.json."""
    global _BUNDLE_DIR, _INVOCATIONS_KNOWN_TABLE
    bundle_dir = str(bundle_dir or "").strip()
    if bundle_dir != _BUNDLE_DIR:
        _BUNDLE_DIR = bundle_dir or None
        _INVOCATIONS_KNOWN_TABLE = None


def _parse_invocations_known_table(raw):
    if not isinstance(raw, dict):
        return None
    table = {}
    for key, value in raw.items():
        try:
            level = int(key)
            count = int(value)
        except (TypeError, ValueError):
            continue
        if level > 0:
            table[level] = max(0, count)
    return table or None


def _load_invocations_known_table_from_classes_json(bundle_dir):
    path = os.path.join(str(bundle_dir or "").strip(), "classes.json")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    warlock = (data or {}).get(WARLOCK_CLASS) or {}
    spellcasting = warlock.get("spellcasting") or {}
    return _parse_invocations_known_table(spellcasting.get("invocations_known"))


def get_invocations_known_table(*, classes_db=None, bundle_dir=None):
    """Return the warlock invocations-known table keyed by class level."""
    if classes_db is not None:
        warlock = (classes_db or {}).get(WARLOCK_CLASS) or {}
        spellcasting = warlock.get("spellcasting") or {}
        parsed = _parse_invocations_known_table(spellcasting.get("invocations_known"))
        if parsed:
            return parsed

    global _INVOCATIONS_KNOWN_TABLE
    resolved_bundle = str(bundle_dir or _BUNDLE_DIR or "").strip()
    if resolved_bundle:
        if _INVOCATIONS_KNOWN_TABLE is None or resolved_bundle != _BUNDLE_DIR:
            set_bundle_dir(resolved_bundle)
        if _INVOCATIONS_KNOWN_TABLE is None:
            _INVOCATIONS_KNOWN_TABLE = (
                _load_invocations_known_table_from_classes_json(resolved_bundle)
                or dict(_FALLBACK_INVOCATIONS_KNOWN_BY_LEVEL)
            )
        return dict(_INVOCATIONS_KNOWN_TABLE)

    return dict(_FALLBACK_INVOCATIONS_KNOWN_BY_LEVEL)


def get_warlock_level(sheet):
    return int(sheet._get_class_level(WARLOCK_CLASS) or 0)


def invocations_known_count(warlock_level, *, classes_db=None, bundle_dir=None):
    level = max(0, int(warlock_level or 0))
    if level <= 0:
        return 0
    table = get_invocations_known_table(classes_db=classes_db, bundle_dir=bundle_dir)
    if level in table:
        return int(table[level])
    known_levels = [lvl for lvl in table if lvl <= level]
    if known_levels:
        return int(table[max(known_levels)])
    return 0


def get_known_invocations(data):
    known = data.get("known_invocations")
    if isinstance(known, list):
        return [str(name).strip() for name in known if str(name).strip()]
    return []


def set_known_invocations(data, names):
    data["known_invocations"] = sorted(
        {str(name).strip() for name in (names or []) if str(name).strip()},
        key=str.lower,
    )


def get_warlock_blast_modifiers(data):
    mods = data.get("warlock_blast_modifiers")
    if isinstance(mods, dict):
        return {
            "essence": str(mods.get("essence") or "").strip(),
            "shape": str(mods.get("shape") or "").strip(),
        }
    return {"essence": "", "shape": ""}


def set_warlock_blast_modifier(data, role, invocation_name):
    mods = get_warlock_blast_modifiers(data)
    mods[str(role or "").strip()] = str(invocation_name or "").strip()
    data["warlock_blast_modifiers"] = mods


def _has_least_blast_shape(known_invocations, invocations_db):
    for name in known_invocations:
        info = invocations_db.get(name) or {}
        if info.get("blast_role") == "shape" and info.get("grade") == "least":
            return True
    return False


def _prerequisites_met(name, info, warlock_level, known_invocations, invocations_db):
    for prereq in info.get("prerequisites") or []:
        token = str(prereq).strip()
        if token == "least_blast":
            if not _has_least_blast_shape(known_invocations, invocations_db):
                return False
            continue
        if token not in known_invocations:
            return False
    return int(warlock_level or 0) >= int(info.get("min_warlock_level") or 0)


def list_available_invocations(
    invocations_db,
    warlock_level,
    known_invocations,
    *,
    exclude_known=True,
):
    available = []
    known_set = set(known_invocations or [])
    for name, info in invocations_db.items():
        if exclude_known and name in known_set:
            continue
        if not _prerequisites_met(name, info, warlock_level, known_invocations, invocations_db):
            continue
        available.append(name)
    return sorted(available, key=str.lower)


def list_all_selectable_invocations(invocations_db, warlock_level, known_invocations):
    """Invocations the character may know (already known + newly selectable)."""
    known = list(known_invocations or [])
    available = list_available_invocations(
        invocations_db, warlock_level, known, exclude_known=True,
    )
    return sorted(set(known) | set(available), key=str.lower)


def invocation_pick_quota(warlock_level, known_invocations, *, classes_db=None, bundle_dir=None):
    allowed = invocations_known_count(
        warlock_level, classes_db=classes_db, bundle_dir=bundle_dir,
    )
    known = get_known_invocations({"known_invocations": known_invocations})
    remaining = max(0, allowed - len(known))
    return allowed, remaining


def get_warlock_damage_reduction(warlock_level):
    dr_value = ""
    for level, value in sorted(WARLOCK_DR_BY_LEVEL.items()):
        if warlock_level >= level:
            dr_value = value
    return dr_value


def get_fiendish_resilience_fast_healing(warlock_level):
    amount = 0
    for level, value in sorted(FIENDISH_RESILIENCE_BY_LEVEL.items()):
        if warlock_level >= level:
            amount = value
    return amount


def get_warlock_energy_resistance_amount(warlock_level):
    amount = 0
    for level, value in sorted(ENERGY_RESISTANCE_BY_LEVEL.items()):
        if warlock_level >= level:
            amount = value
    return amount


def get_warlock_energy_resistance_types(data):
    stored = (data or {}).get("warlock_energy_resistance")
    if not isinstance(stored, list):
        return []
    types = []
    for token in stored:
        text = str(token or "").strip().lower()
        if text in WARLOCK_ENERGY_TYPES and text not in types:
            types.append(text)
    return types


def set_warlock_energy_resistance_types(data, types):
    cleaned = []
    for token in types or []:
        text = str(token or "").strip().lower()
        if text in WARLOCK_ENERGY_TYPES and text not in cleaned:
            cleaned.append(text)
    data["warlock_energy_resistance"] = cleaned[:2]


def is_fiendish_resilience_active(data):
    state = data.get("class_feature_state") or {}
    return bool(state.get("Warlock_Fiendish_Resilience_active"))


def get_active_fast_healing(sheet):
    warlock_level = get_warlock_level(sheet)
    if warlock_level <= 0:
        return 0
    if not is_fiendish_resilience_active(sheet.data):
        return 0
    return get_fiendish_resilience_fast_healing(warlock_level)


def character_has_traditional_spellcasting(sheet):
    for cls_name, level in sheet._get_class_level_slots():
        if not cls_name or cls_name == "None" or int(level or 0) <= 0:
            continue
        if cls_name == WARLOCK_CLASS:
            continue
        sc = (sheet.classes_db.get(cls_name) or {}).get("spellcasting")
        if sc and (sc.get("spells_per_day") or sc.get("spells_known") or sc.get("advancement")):
            return True
        if cls_name in TRADITIONAL_CASTER_CLASSES:
            return True
    return False


def warlock_uses_invocation_sheet(sheet):
    return get_warlock_level(sheet) > 0 and not character_has_traditional_spellcasting(sheet)


def eldritch_blast_damage_die(warlock_level):
    level = max(1, int(warlock_level or 1))
    return f"{level}d6"


def get_eldritch_blast_definition(invocations_db):
    """Return the Eldritch Blast invocation record (not a prepared-caster spell)."""
    invocations_db = invocations_db or {}
    return invocations_db.get(ELDRITCH_BLAST_NAME) or {
        "description": (
            "Supernatural ray. Ranged touch attack vs AC, 60 ft. range "
            "(longer with Eldritch Spear). Deals 1d6 damage per warlock level. "
            "Not a spell, but affected by spell resistance. One eldritch essence "
            "and one blast shape invocation may modify each blast."
        ),
        "attack_type": "Ranged Touch",
        "vs": "AC",
        "blast_role": "base",
        "modifies_eldritch_blast": False,
    }


def build_eldritch_blast_attack_entry(sheet):
    warlock_level = max(1, get_warlock_level(sheet))
    mods = get_warlock_blast_modifiers(sheet.data)
    invocations_db = getattr(sheet, "invocations_db", {}) or {}

    die = eldritch_blast_damage_die(warlock_level)
    attack_type = "Ranged Touch"
    vs = "AC"
    essence_save = None
    range_ft = 60
    label_parts = []

    shape = mods.get("shape") or ""
    essence = mods.get("essence") or ""
    if shape and shape in invocations_db:
        shape_info = invocations_db[shape]
        if shape == "Eldritch Spear":
            range_ft = 250
        elif shape == "Hideous Blow":
            attack_type = "Melee Touch"
        label_parts.append(shape)
    if essence and essence in invocations_db:
        essence_info = invocations_db[essence]
        dmg_type = essence_info.get("damage_type")
        save = essence_info.get("save")
        if save:
            essence_save = str(save).strip()
        if essence_save:
            label_parts.append(f"{essence}, DC {{dc}} vs {essence_save}")
        else:
            extra = [essence]
            if dmg_type:
                extra.append(str(dmg_type).capitalize())
            label_parts.append(", ".join(extra))

    try:
        warlock_dc = sheet.get_spell_dc(WARLOCK_CLASS, min(9, warlock_level))
    except Exception:
        cha_mod = sheet._effective_ability_mod("Charisma")
        warlock_dc = 10 + min(9, warlock_level) + cha_mod

    label = ELDRITCH_BLAST_NAME
    if label_parts:
        joined = ", ".join(label_parts)
        joined = joined.replace("{dc}", str(warlock_dc))
        label = f"{ELDRITCH_BLAST_NAME} ({joined})"

    return {
        "spell": ELDRITCH_BLAST_NAME,
        "label": label,
        "slot_level": 0,
        "dc_level": min(9, warlock_level),
        "prep_id": "warlock_eldritch_blast",
        "attack_type": attack_type,
        "vs": vs,
        "essence_save": essence_save,
        "die": die,
        "dc": warlock_dc if essence_save else None,
        "range_ft": range_ft,
        "warlock_level": warlock_level,
        "shape": shape,
        "essence": essence,
    }


def sync_warlock_prepared_invocations(sheet):
    """Ensure eldritch blast + known invocations appear in prepared_spells."""
    import uuid

    warlock_level = get_warlock_level(sheet)
    if warlock_level <= 0:
        return False

    known = get_known_invocations(sheet.data)
    invocations_db = getattr(sheet, "invocations_db", {}) or {}
    target_specs = []

    target_specs.append({
        "spell": ELDRITCH_BLAST_NAME,
        "source": "invocation",
        "feature_name": ELDRITCH_BLAST_NAME,
        "feature_key": "Warlock_Eldritch_Blast",
        "at_will": True,
    })

    for name in known:
        info = invocations_db.get(name) or {}
        if info.get("modifies_eldritch_blast"):
            continue
        target_specs.append({
            "spell": name,
            "source": "invocation",
            "feature_name": name,
            "feature_key": f"Warlock_{name}",
            "at_will": True,
            "invocation_grade": info.get("grade"),
        })

    prepared = sheet.data.setdefault("prepared_spells", [])
    kept = [e for e in prepared if not _is_invocation_prepared_entry(e)]
    existing = {}
    for entry in prepared:
        if not _is_invocation_prepared_entry(entry):
            continue
        key = entry.get("feature_key") or entry.get("spell")
        existing[key] = entry

    for spec in target_specs:
        key = spec["feature_key"]
        if key in existing:
            kept.append(existing[key])
            continue
        new_entry = {
            "spell": spec["spell"],
            "metamagic": [],
            "slot_level": 0,
            "base_level": 0,
            "prep_id": uuid.uuid4().hex[:8],
            "source": "invocation",
            "feature_name": spec["feature_name"],
            "feature_key": key,
            "at_will": True,
        }
        kept.append(new_entry)
        sheet.data.setdefault("spell_states", {})[
            sheet._prepared_entry_key(new_entry)
        ] = "Ready"

    sheet.data["prepared_spells"] = kept
    return True


def find_eldritch_blast_combat_attack_index(attacks):
    for index, attack in enumerate(attacks or []):
        if attack.get("prep_id") == "warlock_eldritch_blast":
            return index
        if str(attack.get("spell") or "").strip() == ELDRITCH_BLAST_NAME:
            return index
    return None


def is_eldritch_blast_in_combat_summary(sheet):
    return find_eldritch_blast_combat_attack_index(
        sheet.data.get("combat_spell_attacks", []),
    ) is not None


def sync_warlock_combat_spell_attacks(sheet):
    """Refresh an existing Eldritch Blast summary entry; do not auto-add it."""
    warlock_level = get_warlock_level(sheet)
    attacks = sheet.data.setdefault("combat_spell_attacks", [])
    index = find_eldritch_blast_combat_attack_index(attacks)
    if warlock_level <= 0:
        if index is not None:
            del attacks[index]
        return
    if index is None:
        return
    attacks[index] = build_eldritch_blast_attack_entry(sheet)


def _is_invocation_prepared_entry(entry):
    return isinstance(entry, dict) and entry.get("source") == "invocation"


def compute_level_up_invocation_gain(old_level, new_level, *, classes_db=None, bundle_dir=None):
    old_count = invocations_known_count(
        old_level, classes_db=classes_db, bundle_dir=bundle_dir,
    )
    new_count = invocations_known_count(
        new_level, classes_db=classes_db, bundle_dir=bundle_dir,
    )
    return max(0, new_count - old_count)