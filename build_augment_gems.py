"""Build weapon/armor/shield augment crystal JSON and merge into magical_items.json."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MAGICAL_ITEMS = ROOT / "magical_items.json"


def _entry(description: str, *, rank: str, cost: str, uses_per_day: int = 0, max_charges: int = 0, granted_spells: list | None = None):
    return {
        "description": description.strip(),
        "rank": rank,
        "cost": cost,
        "uses_per_day": uses_per_day,
        "max_charges": max_charges,
        "granted_spells": granted_spells or [],
    }


def _ranked(base: str, least: str, lesser: str, greater: str, *, costs: tuple[str, str, str]):
    return {
        f"{base} (least)": _entry(least, rank="least", cost=costs[0]),
        f"{base} (lesser)": _entry(lesser, rank="lesser", cost=costs[1]),
        f"{base} (greater)": _entry(greater, rank="greater", cost=costs[2]),
    }


def build_weapon_gems() -> dict:
    gems: dict = {}
    gems.update(_ranked(
        "Crystal of Adamant Weaponry",
        "Improves weapon hardness by 2.",
        "Improves weapon hardness by 5.",
        "Improves weapon hardness by 10.",
        costs=("300 gp", "1,400 gp", "3,400 gp"),
    ))
    gems.update(_ranked(
        "Crystal of Arcane Steel",
        "+1 insight bonus on weapon damage when delivering a spell through a melee attack.",
        "As least, and +1 insight bonus on the attack roll.",
        "As lesser, and increases the spell save DC by 1.",
        costs=("500 gp", "2,000 gp", "6,000 gp"),
    ))
    for energy in ("Acid", "Cold", "Electricity", "Fire"):
        gems.update(_ranked(
            f"Crystal of Energy Assault, {energy}",
            f"Adds 1 point of {energy.lower()} damage to the weapon's damage.",
            f"Adds an extra 1d6 points of {energy.lower()} damage.",
            f"Adds 1d6 {energy.lower()} damage plus a secondary rider effect on hit.",
            costs=("600 gp", "3,000 gp", "6,000 gp"),
        ))
    gems.update(_ranked(
        "Crystal of Illumination",
        "Swift (command): weapon sheds bright light 5 ft. and shadowy light 5 ft. beyond.",
        "Bright light 20 ft. and shadowy light 20 ft. beyond.",
        "Bright light 60 ft. and shadowy light 60 ft. beyond.",
        costs=("100 gp", "400 gp", "1,000 gp"),
    ))
    gems.update(_ranked(
        "Crystal of Life Drinking",
        "Heal 1 hp per hit on a living creature (max 10 hp/day, then inert until next day).",
        "Heal 3 hp per hit (max 30 hp/day).",
        "Heal 5 hp per hit (max 50 hp/day).",
        costs=("400 gp", "1,500 gp", "6,000 gp"),
    ))
    gems.update(_ranked(
        "Crystal of Return",
        "Draw the weapon as a free action.",
        "As least, and call the weapon from up to 30 ft. away as a move action.",
        "As lesser, and thrown weapons also gain the returning property.",
        costs=("300 gp", "1,000 gp", "4,000 gp"),
    ))
    gems.update(_ranked(
        "Crystal of Security",
        "+2 bonus on checks to draw the weapon or keep it in your hand.",
        "Bonus is +5.",
        "Bonus is +10.",
        costs=("300 gp", "1,000 gp", "3,000 gp"),
    ))
    gems.update(_ranked(
        "Demolition Crystal",
        "+1d6 damage to constructs.",
        "As least, and weapon counts as adamantine vs. construct DR.",
        "As lesser, and weapon can sneak attack and critically hit constructs.",
        costs=("1,000 gp", "3,000 gp", "6,000 gp"),
    ))
    gems.update(_ranked(
        "Fiendslayer Crystal",
        "+1d6 damage to evil outsiders.",
        "As least, and weapon counts as good-aligned for overcoming DR.",
        "As lesser, and a critical hit prevents teleportation for 1 round.",
        costs=("1,000 gp", "3,000 gp", "5,000 gp"),
    ))
    gems.update(_ranked(
        "Phoenix Ash Threat",
        "Target hit last round takes 1 fire damage at the start of your turn.",
        "Target takes 3 fire damage.",
        "Target takes 5 fire damage.",
        costs=("500 gp", "2,000 gp", "6,000 gp"),
    ))
    gems.update(_ranked(
        "Revelation Crystal",
        "Invisible creature you damage glows for 1 round (reveals its square).",
        "Also suppresses invisibility effects for 1 round.",
        "Also suppresses blur/displacement-like concealment for 1 round.",
        costs=("400 gp", "1,000 gp", "5,000 gp"),
    ))
    gems.update(_ranked(
        "Truedeath Crystal",
        "+1d6 damage to undead.",
        "As least, and weapon functions as ghost touch.",
        "As lesser, and weapon can sneak attack and critically hit undead.",
        costs=("1,000 gp", "5,000 gp", "10,000 gp"),
    ))
    gems["Witchlight Reservoir"] = _entry(
        "Greater crystal. Swift (mental): imbue next melee hit with sunlight (+2d6 fire, +4d6 vs undead), "
        "moonlight (+2d6 electricity, +4d6 vs lycanthropes), blood (+2d6 vs living), or wine (–2 Will saves 1 round) "
        "depending on 8-hour exposure. Functions 5 times before re-imbuing.",
        rank="greater",
        cost="5,000 gp",
        uses_per_day=5,
    )
    return gems


def build_armor_gems() -> dict:
    gems: dict = {}
    gems.update(_ranked(
        "Crystal of Adamant Armor",
        "Improves armor hardness by 2.",
        "Improves armor hardness by 5.",
        "Improves armor hardness by 10.",
        costs=("300 gp", "1,400 gp", "3,400 gp"),
    ))
    gems.update(_ranked(
        "Crystal of Adaptation",
        "Protects from temperature extremes as endure elements.",
        "As least, and protects from alignment traits of planes.",
        "As lesser, and protects from positive/negative dominant traits.",
        costs=("500 gp", "1,500 gp", "3,000 gp"),
    ))
    gems.update(_ranked(
        "Crystal of Aquatic Action",
        "Armor imposes no armor check penalty on Swim checks.",
        "As least, and grants Swim speed equal to half land speed.",
        "As lesser, and freedom of movement underwater plus breathe water.",
        costs=("250 gp", "1,000 gp", "3,000 gp"),
    ))
    gems.update(_ranked(
        "Crystal of Glancing Blows",
        "+2 competence bonus on grapple checks to prevent a grapple being initiated.",
        "Bonus is +5.",
        "Bonus is +10.",
        costs=("500 gp", "3,000 gp", "5,000 gp"),
    ))
    gems.update(_ranked(
        "Crystal of Lifekeeping",
        "+1 competence bonus on saves vs energy drain, inflict, death spells, and death effects.",
        "Bonus is +3.",
        "Bonus is +5; once per day reroll a failed save against those effects (immediate).",
        costs=("200 gp", "1,000 gp", "5,000 gp"),
    ))
    gems["Crystal of Lifekeeping (greater)"]["uses_per_day"] = 1
    gems.update(_ranked(
        "Crystal of Mind Cloaking",
        "+1 competence bonus on saves vs mind-affecting spells and abilities.",
        "Bonus is +3.",
        "Bonus is +5; once per day reroll a failed save (immediate).",
        costs=("500 gp", "4,000 gp", "10,000 gp"),
    ))
    gems["Crystal of Mind Cloaking (greater)"]["uses_per_day"] = 1
    gems.update(_ranked(
        "Crystal of Screening",
        "–2 penalty on incorporeal touch attacks against you.",
        "Penalty is –5.",
        "Penalty is –10.",
        costs=("400 gp", "1,000 gp", "3,000 gp"),
    ))
    gems.update(_ranked(
        "Crystal of Stamina",
        "+1 competence bonus on saves vs disease and poison.",
        "Bonus is +3.",
        "Bonus is +5; once per day reroll a failed save (immediate).",
        costs=("300 gp", "900 gp", "2,700 gp"),
    ))
    gems["Crystal of Stamina (greater)"]["uses_per_day"] = 1
    gems.update(_ranked(
        "Iron Ward Diamond",
        "DR 1/— until 10 damage prevented (then inert until next day).",
        "DR 3/— until 30 damage prevented (medium or heavy armor only).",
        "DR 5/— until 50 damage prevented (heavy armor only).",
        costs=("500 gp", "2,000 gp", "8,000 gp"),
    ))
    gems["Restful Crystal"] = _entry(
        "Sleeping in armor with this crystal attached does not make you fatigued.",
        rank="least",
        cost="500 gp",
    )
    gems.update(_ranked(
        "Rubicund Frenzy",
        "While at half hp or below: +1 morale bonus on weapon damage and saves vs fear.",
        "Bonus is +3.",
        "Bonus is +5.",
        costs=("500 gp", "2,000 gp", "6,000 gp"),
    ))
    return gems


def build_shield_gems() -> dict:
    gems: dict = {}
    for energy in ("Acid", "Cold", "Electricity", "Fire", "Sonic"):
        gems.update(_ranked(
            f"Clasp of Energy Protection, {energy}",
            f"Resistance 5 to {energy.lower()} (max 25 prevented/day, then inert).",
            f"Resistance 10 (max 50/day).",
            f"Resistance 15 (max 75/day).",
            costs=("500 gp", "1,500 gp", "3,000 gp"),
        ))
    gems.update(_ranked(
        "Crystal of Adamant Armor",
        "Improves shield hardness by 2.",
        "Improves shield hardness by 5.",
        "Improves shield hardness by 10.",
        costs=("300 gp", "1,400 gp", "3,400 gp"),
    ))
    gems.update(_ranked(
        "Crystal of Arrow Deflection",
        "+2 bonus to AC against ranged attacks.",
        "Bonus is +5.",
        "As least, and deflect one ranged attack per round (Deflect Arrows).",
        costs=("500 gp", "2,500 gp", "5,000 gp"),
    ))
    gems["Crystal of Bent Sight"] = _entry(
        "Avert your eyes from gaze attackers without suffering a miss chance against them.",
        rank="least",
        cost="500 gp",
    )
    return gems


def merge_into_magical_items(weapon_gems: dict, armor_gems: dict, shield_gems: dict) -> None:
    with open(MAGICAL_ITEMS, "r", encoding="utf-8") as handle:
        data = json.load(handle)
    misc = data.setdefault("Misc", {})

    def add_gems(gems: dict, augment_type: str) -> None:
        for name, info in gems.items():
            misc[name] = {
                "description": info["description"],
                "weight": "—",
                "cost": info.get("cost", "—"),
                "augment_gem": True,
                "augment_type": augment_type,
            }

    add_gems(weapon_gems, "weapon")
    add_gems(armor_gems, "armor")
    add_gems(shield_gems, "shield")

    with open(MAGICAL_ITEMS, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def main() -> None:
    weapon_gems = build_weapon_gems()
    armor_gems = build_armor_gems()
    shield_gems = build_shield_gems()
    for path, payload in (
        ("weapon_gems.json", weapon_gems),
        ("armor_gems.json", armor_gems),
        ("shield_gems.json", shield_gems),
    ):
        out = ROOT / path
        with open(out, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        print(f"Wrote {len(payload)} entries to {out.name}")
    merge_into_magical_items(weapon_gems, armor_gems, shield_gems)
    print("Merged gems into magical_items.json (Misc)")


if __name__ == "__main__":
    main()