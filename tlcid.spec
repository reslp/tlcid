# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=[('tlcid_database.db', '.'), ('VERSION', '.'), ('examples', 'examples'), ('icon.png', '.')],
    hiddenimports=[
        'gui',
        'gui.mainwindow',
        'gui.database_window',
        'gui.prediction_results_window',
        'gui.settings_window',
        'gui.species_prediction_window',
        'gui.substance_characteristics_window',
        'gui.substance_detail_window',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='TLCid',
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
    icon=['icon.png'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='TLCid',
)
app = BUNDLE(
    coll,
    name='TLCid.app',
    icon='icon.png',
    bundle_identifier=None,
)
