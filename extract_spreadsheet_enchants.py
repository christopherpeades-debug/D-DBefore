"""Extract full enchant spreadsheet rows from session compaction JSON."""
import ast
import json
import re
from pathlib import Path

COMPACTION = Path(
    r"C:\Users\refle\.grok\sessions\C%3A%5CUsers%5Crefle"
    r"\019ee0e3-a339-76e0-983a-72b92d989689\compaction_requests"
    r"\4dca1700-5bd6-4218-93bc-7bb7484a663d.json"
)


def parse_tuple_rows(text: str):
    rows = []
    seen = set()
    for match in re.finditer(
        r"\((?:'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\")(?:,\s*(?:'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"|None))*\)",
        text,
    ):
        snippet = match.group(0)
        if "ACIDIC" not in text[max(0, match.start() - 200):match.start() + len(snippet)]:
            if not snippet.startswith("('") or "armor" not in snippet.lower():
                if "shield" not in snippet.lower() and "Armor" not in snippet:
                    continue
        try:
            row = ast.literal_eval(snippet)
        except (SyntaxError, ValueError):
            continue
        if not isinstance(row, tuple) or len(row) < 5 or not row[0]:
            continue
        if row[0] in ("Name", "D&D 3.5 Magical Armor and Shield Enchantments"):
            continue
        if "Compiled from" in str(row[0]):
            continue
        key = str(row[0])
        if key in seen:
            continue
        seen.add(key)
        rows.append(row[:5])
    return rows


def main():
    text = COMPACTION.read_text(encoding="utf-8", errors="replace")
    rows = parse_tuple_rows(text)
    print(f"extracted {len(rows)} rows")
    for row in rows:
        print(row[0])
    out = Path(__file__).resolve().parent / "spreadsheet_enchants_rows.json"
    out.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()