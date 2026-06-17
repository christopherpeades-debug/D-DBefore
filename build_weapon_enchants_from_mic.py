"""Build weapon_enchants.json from MIC xlsx column AI + realmshelps + Zyanya MIC table."""
import copy
import html
import json
import re
import ssl
import time
import urllib.request
from pathlib import Path

import pandas as pd

XLSX_COPY = Path(r"C:\Users\Chris\Magic_Item_Compendium_copy.xlsx")
JSON_PATH = Path(r"D:\OneDrive\DnD Beside\weapon_enchants.json")
INDEX_URL = "https://www.realmshelps.net/magic/magweapon-ability.shtml"
WIKIDOT_URL = "http://zyanya.wikidot.com/melee-weapon-properties"
USER_AGENT = "Mozilla/5.0"
SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

SKIP_NAME_PATTERNS = (
    re.compile(r"property", re.I),
    re.compile(r"^two\s", re.I),
    re.compile(r"^three\s", re.I),
    re.compile(r"^\+\d"),
)

ALIASES = {
    "ghost touch": "ghost touch",
    "ki focus": "ki focus",
    "slow burst": "slow burst",
    "mighty cleaving": "mighty cleaving",
    "mighty smiting": "mighty smiting",
    "spell storing": "spell storing",
    "quick loading": "quick-loading",
    "deadly precision": "deadly precision",
    "shocking burst": "shocking burst",
    "flaming burst": "flaming burst",
    "icy burst": "icy burst",
    "acidic burst": "acidic burst",
    "dessicating burst": "dessicating burst",
    "profane burst": "profane burst",
    "sacred burst": "sacred burst",
    "psychokinetic burst": "psychokinetic burst",
    "screaming burst": "screaming",
    "dislocator great": "dislocator, great",
    "dispelling greater": "dispelling, greater",
    "soulbound greater": "soulbound, greater",
    "anarchic": "anarchic (chaotic)",
    "axiomatic": "axiomatic (lawful)",
    "holy surge": "holy surge",
    "unholy surge": "unholy surge",
    "doom burst": "doom burst",
    "energy aura": "energy aura",
    "energy surge": "energy surge",
    "ghost strike": "ghost strike",
    "illusion bane": "illusion bane",
    "illusion theft": "illusion theft",
    "incorporeal binding": "incorporeal binding",
}

MANEUVER_KEYS = {
    "trip": "trip",
    "grapple": "grapple",
    "sunder": "sunder",
    "disarm": "disarm",
    "bull rush": "bull_rush",
    "bull-rush": "bull_rush",
    "feint": "feint",
    "overrun": "overrun",
}

COMBAT_PATTERNS = [
    {"pattern": re.compile(r"\+(\d+)\s*(?:circumstance\s+)?bonus\s+on\s+(trip|grapple|sunder|disarm|bull[\s-]?rush|feint|overrun)", re.I), "amount_group": 1, "maneuver_group": 2},
    {"pattern": re.compile(r"\+(\d+)\s*(?:circumstance\s+)?bonus\s+to\s+(trip|grapple|sunder|disarm|bull[\s-]?rush|feint|overrun)", re.I), "amount_group": 1, "maneuver_group": 2},
    {"pattern": re.compile(r"\+(\d+)\s+on\s+(trip|grapple|sunder|disarm|bull[\s-]?rush|feint|overrun)", re.I), "amount_group": 1, "maneuver_group": 2},
    {"pattern": re.compile(r"\+(\d+)\s+to\s+(trip|grapple|sunder|disarm|bull[\s-]?rush|feint|overrun)", re.I), "amount_group": 1, "maneuver_group": 2},
    {"pattern": re.compile(r"\+(\d+)\s+bonus\s+on\s+any\s+strength\s+checks?.*\btrip\b", re.I), "amount_group": 1, "maneuver": "trip"},
    {"pattern": re.compile(r"\+(\d+)\s+bonus\s+on\s+trip", re.I), "amount_group": 1, "maneuver": "trip"},
    {"pattern": re.compile(r"\+(\d+)\s+on\s+strength\s+checks?\s+to\s+trip", re.I), "amount_group": 1, "maneuver": "trip"},
    {"pattern": re.compile(r"\+(\d+)\s+on\s+strength\s+checks?\s+to\s+trip\s+an\s+opponent", re.I), "amount_group": 1, "maneuver": "trip"},
    {"pattern": re.compile(r"\+(\d+)\s+on\s+disarm\s+attempts?", re.I), "amount_group": 1, "maneuver": "disarm"},
    {"pattern": re.compile(r"\+(\d+)\s+on\s+sunder\s+attempts?", re.I), "amount_group": 1, "maneuver": "sunder"},
    {"pattern": re.compile(r"\+(\d+)\s+on\s+grapple\s+checks?", re.I), "amount_group": 1, "maneuver": "grapple"},
    {"pattern": re.compile(r"\+(\d+)\s+on\s+bull\s+rush", re.I), "amount_group": 1, "maneuver": "bull_rush"},
    {"pattern": re.compile(r"\+(\d+)\s+on\s+overrun", re.I), "amount_group": 1, "maneuver": "overrun"},
    {"pattern": re.compile(r"\+(\d+)\s+on\s+feint", re.I), "amount_group": 1, "maneuver": "feint"},
    {"pattern": re.compile(r"improved\s+sunder", re.I), "amount": 4, "maneuver": "sunder"},
]


def norm(text):
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()


def title_key(name):
    parts = re.split(r"[\s,]+", name.strip())
    out = []
    for part in parts:
        if not part:
            continue
        if part.isupper() and len(part) <= 4:
            out.append(part)
        else:
            out.append(part[:1].upper() + part[1:].lower())
    return " ".join(out)


def fetch_url(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30, context=SSL_CTX) as resp:
        return resp.read().decode("utf-8", errors="replace")


def load_mic_names():
    df = pd.read_excel(XLSX_COPY, sheet_name="Magical Items", header=None)
    names = []
    for row in range(3, df.shape[0]):
        raw = df.iloc[row, 34]
        if pd.isna(raw):
            continue
        name = str(raw).strip()
        if not name or name.lower() == "item name":
            continue
        if any(pat.search(name) for pat in SKIP_NAME_PATTERNS):
            continue
        names.append(name)
    seen = set()
    ordered = []
    for name in names:
        key = norm(name)
        if key in seen:
            continue
        seen.add(key)
        ordered.append(name)
    return ordered


def load_realmshelps_index():
    page = fetch_url(INDEX_URL)
    links = re.findall(r'href="weapon/([^"]+)"[^>]*>\s*([^<]+?)\s*</a>', page, flags=re.I)
    mapping = {}
    for slug, label in links:
        label = html.unescape(re.sub(r"\s+", " ", label).strip())
        mapping[norm(label)] = (label, slug)
    return mapping


def load_wikidot_summaries():
    page = fetch_url(WIKIDOT_URL)
    rows = re.findall(
        r"<tr>\s*<td>([^<]*)</td>\s*<td>([^<]*)</td>\s*<td>([^<]*)</td>\s*<td>([^<]*)</td>\s*<td>([^<]*)</td>\s*</tr>",
        page,
        flags=re.I | re.S,
    )
    summaries = {}
    for book, name, desc, _cost, _plus in rows:
        name = html.unescape(re.sub(r"\s+", " ", name).strip())
        desc = html.unescape(re.sub(r"\s+", " ", desc).strip())
        if not name or name.lower() in {"book", "power"}:
            continue
        if desc:
            summaries[norm(name)] = desc
    return summaries


def resolve_slug(xlsx_name, index_map):
    n = norm(xlsx_name)
    alias = ALIASES.get(n, n)
    if alias in index_map:
        return index_map[alias]
    if n in index_map:
        return index_map[n]
    compact = n.replace(" ", "")
    for key, value in index_map.items():
        if key.replace(" ", "") == compact:
            return value
    slug = title_key(xlsx_name).replace(" ", "_").replace(",", "_")
    return title_key(xlsx_name), slug


def clean_description(text):
    if not text:
        return ""
    text = html.unescape(re.sub(r"\s+", " ", text).strip())
    for marker in (
        " Caster Level",
        " Aura:",
        " Requirements:",
        " Price:",
        " About Magic Weapons",
        " Home Website design",
    ):
        idx = text.find(marker)
        if idx > 0:
            text = text[:idx].strip()
    return text


def extract_description(page):
    if "No Ability" in page or ">Ability - 404<" in page:
        return None
    match = re.search(r"<h1>[^<]+</h1>(.*?)About Magic Weapons", page, flags=re.I | re.S)
    if not match:
        match = re.search(r"<h1>[^<]+</h1>(.*)", page, flags=re.I | re.S)
    if not match:
        return None
    block = match.group(1)
    paragraphs = re.findall(r"<p>(.*?)</p>", block, flags=re.I | re.S)
    parts = []
    for para in paragraphs:
        text = re.sub(r"<[^>]+>", " ", para)
        text = html.unescape(re.sub(r"\s+", " ", text).strip())
        if not text:
            continue
        if re.match(r"^(Caster Level|Aura|Requirements|Price)\b", text, re.I):
            break
        parts.append(text)
    return clean_description(" ".join(parts))


def parse_attack_damage(desc):
    attack_bonus = 0
    damage_bonus = 0
    extra_damage = ""
    critical_extra = ""
    lower = desc.lower()
    if "threat range doubled" in lower or "threat range is doubled" in lower or "doubles the threat range" in lower:
        critical_extra = "doubled threat range"
    for match in re.finditer(r"\+(\d+) enhancement bonus", desc, re.I):
        val = int(match.group(1))
        attack_bonus = max(attack_bonus, val)
        damage_bonus = max(damage_bonus, val)
    for match in re.finditer(r"deals?\s+(?:an?\s+)?extra\s+(\d+d\d+(?:\s+\w+)?)", desc, re.I):
        extra_damage = match.group(1).strip()
    for match in re.finditer(r"\+(\d+d\d+)\s+(\w+)\s+damage", desc, re.I):
        extra_damage = f"{match.group(1)} {match.group(2).lower()}"
    for match in re.finditer(r"\+(\d+d\d+)\s+damage", desc, re.I):
        extra_damage = match.group(1)
    for match in re.finditer(r"\+(\d+)d(\d+)\s+(\w+)\s+damage", desc, re.I):
        extra_damage = f"{match.group(1)}d{match.group(2)} {match.group(3).lower()}"
    return attack_bonus, damage_bonus, extra_damage, critical_extra


def parse_combat_modifiers(desc):
    mods = {}
    if not desc:
        return mods
    for rule in COMBAT_PATTERNS:
        pattern = rule["pattern"]
        for match in pattern.finditer(desc):
            if "amount" in rule:
                amount = int(rule["amount"])
                maneuver_key = rule["maneuver"]
            else:
                amount = int(match.group(rule["amount_group"]))
                if "maneuver" in rule:
                    maneuver_key = rule["maneuver"]
                else:
                    maneuver_raw = match.group(rule["maneuver_group"])
                    maneuver_key = MANEUVER_KEYS.get(norm(maneuver_raw), maneuver_raw)
            mods[maneuver_key] = max(mods.get(maneuver_key, 0), amount)
    combo = re.search(r"\+(\d+)\s+circumstance\s+bonus\s+on\s+trip\s+and\s+disarm", desc, re.I)
    if combo:
        val = int(combo.group(1))
        mods["trip"] = max(mods.get("trip", 0), val)
        mods["disarm"] = max(mods.get("disarm", 0), val)
    return mods


def build_entry(name, desc):
    attack_bonus, damage_bonus, extra_damage, critical_extra = parse_attack_damage(desc or "")
    entry = {
        "description": desc or "",
        "attack_bonus": attack_bonus,
        "damage_bonus": damage_bonus,
        "extra_damage": extra_damage,
        "critical_extra": critical_extra,
    }
    combat_modifiers = parse_combat_modifiers(desc or "")
    if combat_modifiers:
        entry["combat_modifiers"] = combat_modifiers
    return entry


def canonicalize_existing_key(name, existing):
    target = norm(name)
    for key in existing:
        if norm(key) == target:
            return key
    return title_key(name)


def main():
    mic_names = load_mic_names()
    index_map = load_realmshelps_index()
    wikidot = load_wikidot_summaries()
    with JSON_PATH.open(encoding="utf-8") as handle:
        data = json.load(handle)

    report = {"added": 0, "updated": 0, "realmshelps": 0, "wikidot": 0, "combat_mods": []}

    for raw_name in mic_names:
        json_key = canonicalize_existing_key(raw_name, data)
        label, slug = resolve_slug(raw_name, index_map)
        desc = None
        source = None

        wd = wikidot.get(norm(raw_name)) or wikidot.get(norm(json_key))
        realms_desc = None
        if slug:
            try:
                page = fetch_url(f"https://www.realmshelps.net/magic/weapon/{slug}")
                realms_desc = extract_description(page)
                if realms_desc:
                    report["realmshelps"] += 1
            except Exception:
                pass
            time.sleep(0.08)

        if wd:
            desc = wd
            source = "wikidot"
            report["wikidot"] += 1
        elif realms_desc:
            desc = realms_desc
            source = "realmshelps"

        entry = build_entry(json_key, desc)
        if json_key in data:
            merged = copy.deepcopy(data[json_key])
            if desc:
                merged["description"] = desc
            for field in ("attack_bonus", "damage_bonus", "extra_damage", "critical_extra"):
                if field not in merged or merged[field] in ("", 0, None):
                    merged[field] = entry[field]
            if entry.get("combat_modifiers"):
                merged["combat_modifiers"] = entry["combat_modifiers"]
            data[json_key] = merged
            report["updated"] += 1
        else:
            if not desc:
                entry["description"] = ""
            data[json_key] = entry
            report["added"] += 1
        if entry.get("combat_modifiers"):
            report["combat_mods"].append({json_key: entry["combat_modifiers"]})

    with JSON_PATH.open("w", encoding="utf-8") as handle:
        json.dump(dict(sorted(data.items())), handle, indent=2, ensure_ascii=False)
        handle.write("\n")

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()