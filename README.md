# D&D Before

Interactive D&D 3.5 character sheet — **Keen 2.01** (C# / WPF), successor to the Python app in this repository.

## Install

Download the latest release from [Releases](https://github.com/christopherpeades-debug/D-DBefore/releases):

| File | Who it's for |
|------|----------------|
| **`DnD_Before_v2.01_Setup.exe`** | New install, or **Python D&D Before** users upgrading to Keen (in-app update looks for `Setup` in the asset name) |
| **`DnD_Before_Keen_v2.01_Portable.zip`** | Already on Keen — launcher **Update** downloads this and overlays files with a progress bar |

### After install

1. Run **`D&D Before Launcher.exe`** first (shortcut / Start Menu point here).
2. Launcher can check for updates, then **Launch** starts **D&D Before Keen** (character load screen, quests, etc.).

- Default install folder: `C:\D&D Before Keen` under Local Programs (or any path you choose)
- Character data, **Character Loops**, and **Quest Loops** live **next to the install folder** (`AppDir`), not AppData
- Portable updates preserve `Characters\` and local settings

Current version: **v2.01**

## Updates

| You currently run | What the updater does |
|-------------------|------------------------|
| **Python D&D Before** | Downloads **Setup.exe** from this repo's latest GitHub Release and installs Keen |
| **Keen + Launcher** | **Update** prefers **Portable.zip**, extracts over the install with a progress bar |

Release asset keywords: `Setup` (installer), `Portable` (zip overlay)

## Version history

- **v2.01** — Quest page video loops play after install (same Source+Play path as character load screen)
- **v2.0** — Keen (WPF) full release: launcher-first, portable zip updates, Character/Quest Loops
- **v1.26** — Last Python daily-use release
