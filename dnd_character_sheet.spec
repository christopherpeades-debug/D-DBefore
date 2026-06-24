# -*- mode: python ; coding: utf-8 -*-
import os

from PyInstaller.utils.hooks import collect_all

block_cipher = None
APP_VERSION = os.environ.get("APP_VERSION", "1.3")
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
    ('skills_srd.json', '.'),
    ('Special_Features.json', '.'),
    ('invocations.json', '.'),
    ('armor_enchants.json', '.'),
    ('shield_enchants.json', '.'),
    ('weapon_gems.json', '.'),
    ('armor_gems.json', '.'),
    ('shield_gems.json', '.'),
    ('ui_settings.json', '.'),
    ('knight_helmet.png', '.'),
    ('magic_orb_icon.png', '.'),
    ('money_coinsIcon.png', '.'),
    ('icon.png', '.'),
    ('icon.ico', '.'),
    ('assets', 'assets'),
    ('Theme BG', 'Theme BG'),
] + ctk_datas

a = Analysis(
    ['dnd_character_sheet.py'],
    pathex=[],
    binaries=ctk_binaries,
    datas=datas,
    hiddenimports=[
        'PIL', 'PIL.Image', 'PIL.ImageTk',
        'cloud_sync', 'loot_sync', 'homebrew_sync',
        'dice_roller', 'roll_log_sync', 'trade_sync', 'app_update',
        'sync_http', 'sync_intervals',
        'mounts', 'skill_detail_popup', 'magical_item_conversion_wizard',
        'character_creation_wizard', 'level_up_wizard', 'campaign_id_picker',
        'campaign_chat_sync', 'campaign_chat_window',
        'image_share_sync', 'follower_statblock_sync', 'follower_statblock_ui',
        'statblock_viewer', 'monster_statblock_icon', 'reference_tooltips',
        'dark_dialog', 'warlock_support', 'proficiency_support', 'languages',
        'augment_gems_ui', 'ui_health_icons',
    ] + ctk_hiddenimports,
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