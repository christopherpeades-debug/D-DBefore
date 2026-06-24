"""One-off builder: fetch d20 SRD skill pages into skills_srd.json."""

from __future__ import annotations

import json
import os
import re
import urllib.request
from html.parser import HTMLParser

SKILLS = {
    "Appraise": "appraise",
    "Balance": "balance",
    "Bluff": "bluff",
    "Climb": "climb",
    "Concentration": "concentration",
    "Craft": "craft",
    "Decipher Script": "decipherScript",
    "Diplomacy": "diplomacy",
    "Disable Device": "disableDevice",
    "Disguise": "disguise",
    "Escape Artist": "escapeArtist",
    "Forgery": "forgery",
    "Gather Information": "gatherInformation",
    "Handle Animal": "handleAnimal",
    "Heal": "heal",
    "Hide": "hide",
    "Intimidate": "intimidate",
    "Jump": "jump",
    "Knowledge": "knowledge",
    "Listen": "listen",
    "Move Silently": "moveSilently",
    "Open Lock": "openLock",
    "Perform": "perform",
    "Profession": "profession",
    "Ride": "ride",
    "Search": "search",
    "Sense Motive": "senseMotive",
    "Sleight of Hand": "sleightOfHand",
    "Spellcraft": "spellcraft",
    "Spot": "spot",
    "Survival": "survival",
    "Swim": "swim",
    "Tumble": "tumble",
    "Use Magic Device": "useMagicDevice",
    "Use Rope": "useRope",
    "Speak Language": "speakLanguage",
}

BASE = "https://www.d20srd.org/srd/skills/"
OUTPUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "skills_srd.json")


class SkillPageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_body = False
        self.skip = False
        self.in_h5 = False
        self.in_table = False
        self.in_cell = False
        self.current = ""
        self.parts = []
        self.table_rows = []
        self.current_row = []

    def handle_starttag(self, tag, attrs):
        if tag == "body":
            self.in_body = True
            return
        if not self.in_body:
            return
        if tag in ("script", "style"):
            self.skip = True
            return
        if tag == "h5":
            self.in_h5 = True
            self.current = ""
        elif tag == "table":
            self.in_table = True
            self.table_rows = []
        elif tag == "tr" and self.in_table:
            self.current_row = []
        elif tag in ("td", "th") and self.in_table:
            self.in_cell = True
            self.current = ""
        elif tag == "p" and not self.in_table:
            self.current = ""
        elif tag == "br" and not self.in_table:
            self.current += "\n"

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = False
            return
        if not self.in_body:
            return
        if tag == "body":
            self.in_body = False
        elif tag == "h5" and self.in_h5:
            title = re.sub(r"\s+", " ", self.current).strip()
            if title:
                self.parts.append({"type": "section", "title": title, "blocks": []})
            self.in_h5 = False
        elif tag in ("td", "th") and self.in_cell:
            self.current_row.append(re.sub(r"\s+", " ", self.current).strip())
            self.in_cell = False
        elif tag == "tr" and self.in_table:
            if any(cell.strip() for cell in self.current_row):
                self.table_rows.append(self.current_row)
        elif tag == "table" and self.in_table:
            if self.table_rows:
                self.parts.append({"type": "table", "rows": self.table_rows})
            self.in_table = False
        elif tag == "p" and not self.in_table:
            text = re.sub(r"\s+", " ", self.current).strip()
            if text:
                if self.parts and self.parts[-1]["type"] == "section":
                    self.parts[-1]["blocks"].append({"type": "paragraph", "text": text})
                else:
                    self.parts.append({"type": "paragraph", "text": text})

    def handle_data(self, data):
        if self.skip or not self.in_body:
            return
        if self.in_h5 or self.in_cell or (not self.in_table):
            self.current += data


def clean_text(text: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def parse_skill_html(html: str, fallback_name: str) -> dict:
    match = re.search(r"<h1[^>]*>(.*?)</h1>(.*?)<div class=\"footer\">", html, re.S | re.I)
    if not match:
        match = re.search(r"<h1[^>]*>(.*?)</h1>(.*)", html, re.S | re.I)
    title = clean_text(re.sub("<[^<]+?>", "", match.group(1))) if match else fallback_name
    body = match.group(2) if match else html

    parser = SkillPageParser()
    parser.in_body = True
    parser.feed(body)

    sections = []
    for part in parser.parts:
        if part["type"] == "section":
            sections.append({
                "title": clean_text(part["title"]),
                "blocks": [
                    {"type": "paragraph", "text": clean_text(block["text"])}
                    for block in part.get("blocks", [])
                    if block.get("type") == "paragraph" and block.get("text")
                ],
            })
        elif part["type"] == "paragraph":
            text = clean_text(part["text"])
            if sections:
                sections[-1]["blocks"].append({"type": "paragraph", "text": text})
            else:
                sections.append({"title": "", "blocks": [{"type": "paragraph", "text": text}]})
        elif part["type"] == "table":
            rows = [[clean_text(cell) for cell in row] for row in part["rows"]]
            if sections:
                sections[-1]["blocks"].append({"type": "table", "rows": rows})
            else:
                sections.append({"title": "", "blocks": [{"type": "table", "rows": rows}]})

    ability = ""
    ability_match = re.search(r"\(([^)]+)\)\s*$", title)
    if ability_match:
        ability = ability_match.group(1).strip()

    return {"title": title, "ability": ability, "sections": sections}


def main():
    output = {}
    for name, slug in SKILLS.items():
        url = f"{BASE}{slug}.htm"
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; DDBeforeSkillBuilder/1.0)"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            html = response.read().decode("utf-8", errors="replace")
        record = parse_skill_html(html, name)
        record["srd_url"] = url
        output[name] = record
        print(f"OK {name}: {len(record['sections'])} sections")

    with open(OUTPUT, "w", encoding="utf-8") as handle:
        json.dump(output, handle, indent=2, ensure_ascii=False)
    print(f"Wrote {OUTPUT} ({len(output)} skills)")


if __name__ == "__main__":
    main()