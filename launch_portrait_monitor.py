#!/usr/bin/env python3
"""
Launch D&D Beside with portrait-monitor Stats layout for this session only.

Does not write layout_profile to ui_settings.json. Window size/position is
remembered separately in window_state.json when the user closes the app.
"""
from __future__ import annotations

import os
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SHEET_SCRIPT = os.path.join(SCRIPT_DIR, "dnd_character_sheet.py")

PORTRAIT_LAYOUT_ENV = "DND_BESIDE_PORTRAIT_LAYOUT"


def main() -> int:
    env = os.environ.copy()
    env[PORTRAIT_LAYOUT_ENV] = "1"
    print("Portrait monitor layout enabled for this session (not saved to settings).")
    print("Window size/position will be remembered when you close the app.")
    return subprocess.call([sys.executable, SHEET_SCRIPT], cwd=SCRIPT_DIR, env=env)


if __name__ == "__main__":
    raise SystemExit(main())