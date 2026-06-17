# -*- mode: python ; coding: utf-8 -*-
import os

from PyInstaller.utils.hooks import collect_all

block_cipher = None
APP_VERSION = os.environ.get("APP_VERSION", "1.22")
APP_DIST_NAME = f"D&D Before v{APP_VERSION}"

ctk_datas, ctk_binaries, ctk_hiddenimports = collect_all('customtkinter')

datas = [
    ('spells.json', '.'),
    ('classes.json', '.'),
    ('feats.json', '.'),
    ('epic_feats.json', '.'),
    ('magical_items.json', '.'),
    ('weapon_enchants.json', '.'),
    ('armor_shields.json', '.'),
    ('wild_shapes.json', '.'),
    ('animal_companions.json', '.'),
    ('familiars.json', '.'),
    ('mounts.json', '.'),
    ('PHB2_Spells.json', '.'),
    ('sync_config.example.json', '.'),
    ('version.json', '.'),
    ('Mundane_Weapons.json', '.'),
    ('Mundane_Armors_Shields.json', '.'),
    ('Adventuring_Gear.json', '.'),
    ('buffs.json', '.'),
    ('Special_Features.json', '.'),
    ('icon.png', '.'),
    ('icon.ico', '.'),
    ('Theme BG', 'Theme BG'),
] + ctk_datas

a = Analysis(
    ['dnd_character_sheet.py'],
    pathex=[],
    binaries=ctk_binaries,
    datas=datas,
    hiddenimports=['PIL', 'PIL.Image', 'PIL.ImageTk', 'cloud_sync', 'loot_sync', 'roll_log_sync', 'trade_sync', 'app_update', 'mounts'] + ctk_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_DIST_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=APP_DIST_NAME,
)