# D&D Before

Interactive D&D 3.5 character sheet — **Keen 2.0** (C# / WPF), successor to the Python app in this repository.

## Install

Download the latest release from [Releases](https://github.com/christopherpeades-debug/D-DBefore/releases):

| File | Who it's for |
|------|----------------|
| **`D&D_Before_v2.0_Setup.exe`** | New install, or **Python D&D Before** users upgrading to Keen (in-app update looks for `Setup` in the asset name) |
| **`D&D_Before_Keen_v2.0_Portable.zip`** | Already on Keen — launcher **Update** downloads this and overlays files with a progress bar |

### After install

1. Run **`D&D Before Launcher.exe`** first (shortcut / Start Menu point here).
2. Launcher can check for updates, then **Launch** starts **D&D Before Keen** (character load screen, quests, etc.).

- Default install folder: `C:\D&D Before Keen v2.0` (or any path you choose)
- Character data, **Character Loops**, and **Quest Loops** live **next to the install folder** (`AppDir`), not AppData — works if you install under Documents or any drive
- Upgrading from Python or older Keen: Setup replaces the old app; Portable updates preserve `Characters\` and local settings

Current version: **v2.0**

## Updates

| You currently run | What the updater does |
|-------------------|------------------------|
| **Python D&D Before** | Downloads **Setup.exe** from this repo's latest GitHub Release and installs Keen 2.0 |
| **Keen + Launcher** | **Update** prefers **Portable.zip**, extracts over the install with a progress bar |

Release asset keywords used by the apps:

- Installer: `Setup`
- Portable overlay: `Portable`

## Version history

- **v2.0** — Keen (WPF) full release: launcher-first, portable zip updates, Character/Quest Loops, Spells Descriptions
- **v1.26** — Last Python daily-use release (save fix, pins, rage, sidebar portrait)
- **v1.12** — Python-era installer (numerical fix for 1.2 vs 1.11)
