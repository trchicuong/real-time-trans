# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['translator.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'tkinter',
        'tkinter.ttk',
        'tkinter.messagebox',
        'tkinter.filedialog',
        'PIL',
        'PIL.Image',
        'PIL.ImageTk',
        'mss',
        'numpy',
        'pytesseract',
        'deep_translator',
        'deep_translator.google',
        'cv2',
        'threading',
        'json',
        'os',
        'shutil',
        're',
        'traceback',
        'datetime',
        'hashlib',
        'random',
        'queue',
        'concurrent.futures',
        'warnings',
        # EasyOCR (optional - requires PyTorch)
        'easyocr',
        'torch',
        'torchvision',
        'torch.nn',
        'torch.backends',
        # DeepL (optional)
        'deepl',
    ],
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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='RealTimeScreenTranslator',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # No console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

