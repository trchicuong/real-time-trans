# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['translator.py'],
    pathex=[],
    binaries=[],
    datas=[
        # No additional data files needed - cache is in-memory only
    ],
    hiddenimports=[
        'tkinter',
        'tkinter.ttk',
        'tkinter.messagebox',
        'tkinter.filedialog',
        'PIL',
        'PIL.Image',
        'PIL.ImageTk',
        'PIL.Image.Resampling',  # For Image.Resampling.LANCZOS, etc.
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
        'ctypes',  # For DPI awareness on Windows
        'io',  # For StringIO in handlers and translator
        'sys',  # For sys.frozen check in handlers
        'time',  # For time operations in handlers
        'tempfile',  # For temporary directory operations in handlers and translator
        'difflib',  # For SequenceMatcher in text deduplication (built-in Python)
        # Modules package
        'modules',
        'modules.logger',
        'modules.circuit_breaker',
        'modules.ocr_postprocessing',
        'modules.batch_translation',
        'modules.deepl_context',
        'modules.text_validator',
        'modules.advanced_deduplication',
        'modules.hotkey_manager',
        # Handlers package
        'handlers',
        'handlers.tesseract_ocr_handler',
        'handlers.easyocr_handler',
        # Advanced deduplication
        'imagehash',  # Perceptual hashing library
        'difflib',    # Text similarity (built-in Python)
        # EasyOCR (optional - CPU-only mode)
        'easyocr',
        # PyTorch for EasyOCR (CPU version)
        'torch',
        'torch.nn',
        'torch.backends',
        # Encoding detection (optional)
        'chardet',
        # DeepL (optional)
        'deepl',
        # Hotkeys system (pynput)
        'pynput',
        'pynput.keyboard',
        'pynput.keyboard._win32',
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
    [],
    exclude_binaries=True,  # Don't bundle binaries into exe
    name='RealTimeScreenTranslator',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    console=False,  # No console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='RealTimeScreenTranslator',
)
