"""Weapon and armor proficiency resolution for D&D Beside."""

from __future__ import annotations

import re

WEAPON_NONPROFICIENCY_PENALTY = -6

WEAPON_CATEGORY_ORDER = ("simple", "martial", "exotic")

RACIAL_WEAPON_PROFICIENCIES = {
    "Elf": [
        "Longsword", "Rapier", "Longbow", "Composite Longbow", "Shortbow", "Composite Shortbow",
    ],
    "Half-Elf": [
        "Longsword", "Rapier", "Longbow", "Composite Longbow", "Shortbow", "Composite Shortbow",
    ],
    "Dwarf": ["Dwarven Waraxe", "Battleaxe", "Heavy Pick", "Light Pick"],
    "Gnome": ["Gnome Hooked Hammer"],
    "Half-Orc": ["Orc Double Axe"],
}

CLASS_DEFAULT_PROFICIENCIES = {
    "Barbarian": {
        "weapon_categories": ["simple", "martial"],
        "weapons": [],
        "armor": ["light", "medium"],
        "shield": True,
        "tower_shield": False,
    },
    "Bard": {
        "weapon_categories": ["simple"],
        "weapons": ["Longsword", "Rapier", "Sap", "Short Sword", "Shortbow", "Whip"],
        "armor": ["light"],
        "shield": True,
        "tower_shield": False,
    },
    "Cleric": {
        "weapon_categories": ["simple", "martial"],
        "weapons": [],
        "armor": ["light", "medium", "heavy"],
        "shield": True,
        "tower_shield": False,
    },
    "Druid": {
        "weapon_categories": [],
        "weapons": [
            "Club", "Dagger", "Dart", "Quarterstaff", "Scimitar", "Sickle",
            "Shortspear", "Sling", "Spear",
        ],
        "armor": ["light", "medium"],
        "shield": True,
        "tower_shield": False,
    },
    "Fighter": {
        "weapon_categories": ["simple", "martial"],
        "weapons": [],
        "armor": ["light", "medium", "heavy"],
        "shield": True,
        "tower_shield": True,
    },
    "Monk": {
        "weapon_categories": [],
        "weapons": [
            "Club", "Crossbow, Heavy", "Crossbow, Light", "Dagger", "Handaxe", "Javelin",
            "Kama", "Nunchaku", "Quarterstaff", "Sai", "Shuriken", "Siangham", "Sling",
        ],
        "armor": [],
        "shield": False,
        "tower_shield": False,
    },
    "Paladin": {
        "weapon_categories": ["simple", "martial"],
        "weapons": [],
        "armor": ["light", "medium", "heavy"],
        "shield": True,
        "tower_shield": False,
    },
    "Ranger": {
        "weapon_categories": ["simple", "martial"],
        "weapons": [],
        "armor": ["light"],
        "shield": True,
        "tower_shield": False,
    },
    "Rogue": {
        "weapon_categories": ["simple"],
        "weapons": ["Hand Crossbow", "Rapier", "Sap", "Shortbow", "Short Sword"],
        "armor": ["light"],
        "shield": False,
        "tower_shield": False,
    },
    "Sorcerer": {
        "weapon_categories": ["simple"],
        "weapons": [],
        "armor": [],
        "shield": False,
        "tower_shield": False,
    },
    "Wizard": {
        "weapon_categories": ["simple"],
        "weapons": [],
        "armor": [],
        "shield": False,
        "tower_shield": False,
    },
    "Warlock": {
        "weapon_categories": ["simple"],
        "weapons": [],
        "armor": [],
        "shield": False,
        "tower_shield": False,
    },
    "Radiant Servant of Pelor": {
        "weapon_categories": ["simple", "martial"],
        "weapons": [],
        "armor": ["light", "medium", "heavy"],
        "shield": True,
        "tower_shield": False,
    },
}

FEAT_ARMOR_PROFICIENCY = {
    "armor proficiency (light)": "light",
    "armor proficiency (medium)": "medium",
    "armor proficiency (heavy)": "heavy",
}

FEAT_WEAPON_CATEGORY = {
    "simple weapon proficiency": "simple",
    "martial weapon proficiency": "martial",
}


def _normalize_token(text):
    return re.sub(r"\s+", " ", str(text or "").strip())


def _folded(text):
    return _normalize_token(text).lower()


def _merge_proficiency_dict(target, source):
    if not isinstance(source, dict):
        return
    for category in WEAPON_CATEGORY_ORDER:
        values = source.get("weapon_categories") or source.get("weapons_categories") or []
        if category in {_folded(v) for v in values}:
            if category not in target["weapon_categories"]:
                target["weapon_categories"].append(category)
    for weapon in source.get("weapons") or []:
        weapon = _normalize_token(weapon)
        if weapon and weapon not in target["weapons"]:
            target["weapons"].append(weapon)
    for armor in source.get("armor") or []:
        armor = _folded(armor)
        if armor and armor not in target["armor"]:
            target["armor"].append(armor)
    if source.get("shield"):
        target["shield"] = True
    if source.get("tower_shield"):
        target["tower_shield"] = True
        target["shield"] = True


def _empty_proficiency_state():
    return {
        "weapon_categories": [],
        "weapons": [],
        "armor": [],
        "shield": False,
        "tower_shield": False,
    }


def _class_proficiency_block(sheet, class_name):
    class_name = _normalize_token(class_name)
    if not class_name or class_name == "None":
        return {}
    level = int(sheet._get_class_level(class_name) or 0)
    if level <= 0:
        return {}
    class_info = (getattr(sheet, "classes_db", None) or {}).get(class_name, {})
    prof = class_info.get("proficiencies")
    if isinstance(prof, dict):
        return prof
    return CLASS_DEFAULT_PROFICIENCIES.get(class_name, {})


def _iter_selected_feats(sheet):
    seen = set()
    if hasattr(sheet, "_get_all_selected_feats"):
        for feat in sheet._get_all_selected_feats():
            feat = _normalize_token(feat)
            if feat and feat not in seen:
                seen.add(feat)
                yield feat
    for feat in sheet.data.get("general_feats") or []:
        feat = _normalize_token(feat)
        if feat and feat not in seen:
            seen.add(feat)
            yield feat
    for feat in (sheet.data.get("bonus_feats") or {}).values():
        feat = _normalize_token(feat)
        if feat and feat not in seen:
            seen.add(feat)
            yield feat
    human_feat = str(sheet.data.get("human_bonus_feat") or "").strip()
    if human_feat and human_feat not in seen:
        yield human_feat


def _feat_spec_for_entry(sheet, feat_text, index_hint=None):
    base, legacy_spec = sheet._split_feat_spec_from_name(feat_text)
    if index_hint is not None:
        slot_key = f"general_feat_{index_hint}"
        live_spec = sheet._get_feat_spec_live(slot_key)
        if live_spec:
            return base, live_spec
    for slot_key, feat in (sheet.data.get("bonus_feats") or {}).items():
        if _normalize_token(feat) == _normalize_token(feat_text):
            live_spec = sheet._get_feat_spec_live(slot_key)
            if live_spec:
                return base, live_spec
    return base, legacy_spec


def _apply_feat_proficiencies(state, sheet):
    for index, feat_text in enumerate(sheet.data.get("general_feats") or []):
        feat_text = _normalize_token(feat_text)
        if not feat_text:
            continue
        base, spec = _feat_spec_for_entry(sheet, feat_text, index_hint=index)
        _apply_single_feat(state, base, spec)

    for feat_text in (sheet.data.get("bonus_feats") or {}).values():
        feat_text = _normalize_token(feat_text)
        if not feat_text:
            continue
        base, spec = _feat_spec_for_entry(sheet, feat_text)
        _apply_single_feat(state, base, spec)

    human_feat = _normalize_token(sheet.data.get("human_bonus_feat") or "")
    if human_feat:
        base, spec = _feat_spec_for_entry(sheet, human_feat)
        _apply_single_feat(state, base, spec)


def _apply_single_feat(state, base, spec):
    folded_base = _folded(base)
    if folded_base in FEAT_ARMOR_PROFICIENCY:
        armor = FEAT_ARMOR_PROFICIENCY[folded_base]
        if armor not in state["armor"]:
            state["armor"].append(armor)
        return
    if folded_base == "shield proficiency":
        state["shield"] = True
        return
    if folded_base == "tower shield proficiency":
        state["tower_shield"] = True
        state["shield"] = True
        return
    if folded_base in FEAT_WEAPON_CATEGORY:
        category = FEAT_WEAPON_CATEGORY[folded_base]
        if category not in state["weapon_categories"]:
            state["weapon_categories"].append(category)
        if spec:
            weapon = _normalize_token(spec)
            if weapon and weapon not in state["weapons"]:
                state["weapons"].append(weapon)
        return
    if folded_base == "exotic weapon proficiency":
        weapon = _normalize_token(spec)
        if weapon and weapon not in state["weapons"]:
            state["weapons"].append(weapon)


def get_character_proficiencies(sheet):
    state = _empty_proficiency_state()
    for class_name, _level in sheet._get_class_level_slots():
        _merge_proficiency_dict(state, _class_proficiency_block(sheet, class_name))
    race = str(sheet.data.get("race") or "").strip()
    for weapon in RACIAL_WEAPON_PROFICIENCIES.get(race, []):
        weapon = _normalize_token(weapon)
        if weapon and weapon not in state["weapons"]:
            state["weapons"].append(weapon)
    _apply_feat_proficiencies(state, sheet)
    return state


def _resolve_weapon_name_token(sheet, weapon_name):
    weapon_name = _normalize_token(weapon_name)
    if not weapon_name:
        return None
    lookup = sheet._lookup_mundane_weapon_info(weapon_name)
    if lookup:
        return weapon_name
    db = getattr(sheet, "mundane_weapons_db", None) or {}
    folded = weapon_name.lower()
    for key in db:
        if key.lower() == folded:
            return key
    return weapon_name


def _weapon_proficiency_category(sheet, weapon_name):
    resolved = _resolve_weapon_name_token(sheet, weapon_name)
    info = sheet._lookup_mundane_weapon_info(resolved or weapon_name)
    category = _folded(info.get("proficiency") or "")
    if category in WEAPON_CATEGORY_ORDER:
        return category
    lowered = _folded(weapon_name)
    if "unarmed" in lowered:
        return "simple"
    return "martial"


def _weapon_name_matches(spec, weapon_name):
    spec_folded = _folded(spec)
    weapon_folded = _folded(weapon_name)
    if spec_folded == weapon_folded:
        return True
    return spec_folded in weapon_folded or weapon_folded in spec_folded


def is_weapon_proficient(sheet, weapon_name):
    weapon_name = _normalize_token(weapon_name)
    if not weapon_name:
        return True
    state = get_character_proficiencies(sheet)
    resolved = _resolve_weapon_name_token(sheet, weapon_name) or weapon_name
    for weapon in state["weapons"]:
        if _weapon_name_matches(weapon, resolved) or _weapon_name_matches(weapon, weapon_name):
            return True
    category = _weapon_proficiency_category(sheet, weapon_name)
    categories = {_folded(v) for v in state["weapon_categories"]}
    if category == "simple" and "simple" in categories:
        return True
    if category == "martial" and ("martial" in categories or "simple" in categories):
        return "martial" in categories
    if category == "exotic":
        return False
    if category == "martial":
        return "martial" in categories
    return "simple" in categories


def get_weapon_nonproficiency_penalty(sheet, weapon_name):
    if is_weapon_proficient(sheet, weapon_name):
        return 0
    return WEAPON_NONPROFICIENCY_PENALTY


def _armor_category_proficient(state, category):
    category = _folded(category)
    if not category:
        return True
    armor = {_folded(v) for v in state["armor"]}
    if category == "light":
        return bool(armor & {"light", "medium", "heavy"})
    if category == "medium":
        return bool(armor & {"medium", "heavy"})
    if category == "heavy":
        return "heavy" in armor
    return True


def _is_wearing_armor(sheet):
    armor = sheet.data.get("armor") or {}
    return (
        str(armor.get("status") or "").strip().lower() == "worn"
        and bool(str(armor.get("name") or "").strip())
    )


def _is_wearing_shield(sheet):
    shield = sheet.data.get("shield") or {}
    return (
        str(shield.get("status") or "").strip().lower() == "worn"
        and bool(str(shield.get("name") or "").strip())
    )


def _is_tower_shield(sheet):
    shield = sheet.data.get("shield") or {}
    name = str(shield.get("name") or "").strip().lower()
    if "tower" in name:
        return True
    info = sheet._lookup_shield_info(shield.get("name", ""))
    haystack = " ".join([
        name,
        str(info.get("category", "") or "").lower(),
        str(info.get("special_description", "") or "").lower(),
    ])
    return "tower" in haystack


def is_armor_proficient(sheet):
    if not _is_wearing_armor(sheet):
        return True
    state = get_character_proficiencies(sheet)
    category = sheet._armor_category_from_data()
    return _armor_category_proficient(state, category)


def is_shield_proficient(sheet):
    if not _is_wearing_shield(sheet):
        return True
    state = get_character_proficiencies(sheet)
    if _is_tower_shield(sheet):
        return bool(state.get("tower_shield"))
    return bool(state.get("shield"))


def get_armor_nonproficiency_check_penalty(sheet):
    """ACP from worn armor/shield the character is not proficient with (attacks & ability checks)."""
    penalty = 0
    if _is_wearing_armor(sheet) and not is_armor_proficient(sheet):
        armor = sheet.data.get("armor") or {}
        penalty += int(sheet._resolve_armor_acp(armor) or 0)
    if _is_wearing_shield(sheet) and not is_shield_proficient(sheet):
        shield = sheet.data.get("shield") or {}
        penalty += int(sheet._resolve_shield_acp(shield) or 0)
    return penalty