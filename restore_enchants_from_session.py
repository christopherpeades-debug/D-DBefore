"""Restore armor/shield enchant JSON from session terminal log + build script."""
import ast
import json
import re
from pathlib import Path

import build_armor_shield_enchants as builder

LOG = Path(
    r"C:\Users\refle\.grok\sessions\C%3A%5CUsers%5Crefle"
    r"\019ee0e3-a339-76e0-983a-72b92d989689\terminal"
    r"\call-60b5c809-7bf2-423c-b183-7c6c42618718-composer_call_kLDxP.log"
)
COMPACTION = Path(
    r"C:\Users\refle\.grok\sessions\C%3A%5CUsers%5Crefle"
    r"\019ee0e3-a339-76e0-983a-72b92d989689\compaction_requests"
    r"\4dca1700-5bd6-4218-93bc-7bb7484a663d.json"
)
OUT_DIR = Path(__file__).resolve().parent


def parse_tuple_rows(text: str):
    rows = []
    for match in re.finditer(r"\((?:'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\")(?:,\s*(?:'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"|None))*\)", text):
        snippet = match.group(0)
        if "ACIDIC" in snippet or snippet.startswith("('") and "Armor" in snippet or "Shield" in snippet or "shield" in snippet or "armor" in snippet:
            try:
                row = ast.literal_eval(snippet)
            except (SyntaxError, ValueError):
                continue
            if isinstance(row, tuple) and len(row) >= 5 and row[0] and row[0] not in ("Name", "D&D 3.5 Magical Armor and Shield Enchantments"):
                rows.append(row[:5])
    return rows


def collect_rows():
    chunks = []
    if LOG.exists():
        chunks.append(LOG.read_text(encoding="utf-8", errors="replace"))
    if COMPACTION.exists():
        chunks.append(COMPACTION.read_text(encoding="utf-8", errors="replace"))
    seen = set()
    rows = []
    for chunk in chunks:
        for row in parse_tuple_rows(chunk):
            key = row[0]
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)
    return rows


def main():
    rows = collect_rows()
    if not rows:
        raise SystemExit("No enchant rows recovered from session logs.")

    old_armor = {}
    old_shield = {}
    armor_path = OUT_DIR / "armor_enchants.json"
    shield_path = OUT_DIR / "shield_enchants.json"

    armor_db = {}
    shield_db = {}
    for raw_name, applies_raw, cost_raw, desc, notes in rows:
        name = builder.title_name(raw_name)
        applies_to, restrictions = builder.classify_applies(applies_raw)
        entry = {
            "description": str(desc or "").strip(),
            "applies_to": applies_to,
        }
        if restrictions:
            entry["restrictions"] = restrictions
        if notes:
            entry["notes"] = str(notes).strip()
        entry.update(builder.parse_cost(cost_raw))

        if applies_to in ("armor", "both"):
            merged = dict(entry)
            merged.update(builder.merge_old_effects(name, old_armor))
            armor_db[name] = merged
        if applies_to in ("shield", "both"):
            merged = dict(entry)
            merged.update(builder.merge_old_effects(name, old_shield))
            shield_db[name] = merged

    armor_path.write_text(json.dumps(armor_db, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    shield_path.write_text(json.dumps(shield_db, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Recovered {len(rows)} spreadsheet rows")
    print(f"Wrote {len(armor_db)} armor entries, {len(shield_db)} shield entries")


if __name__ == "__main__":
    main()