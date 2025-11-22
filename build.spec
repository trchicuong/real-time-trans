# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['translator.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('preset_cache.txt', '.'),  # Bundle preset_cache.txt vào exe
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
        'collections',  # For OrderedDict in cache_manager
        'io',  # For StringIO in handlers and translator
        'sys',  # For sys.frozen check in handlers
        'time',  # For time operations in handlers
        'tempfile',  # For temporary directory operations in handlers and translator
        # Modules package
        'modules',
        'modules.logger',
        'modules.circuit_breaker',
        'modules.ocr_postprocessing',
        'modules.unified_translation_cache',
        'modules.batch_translation',
        'modules.deepl_context',
        # Handlers package
        'handlers',
        'handlers.tesseract_ocr_handler',
        'handlers.easyocr_handler',
        'handlers.cache_manager',
        # EasyOCR (optional - requires PyTorch)
        'easyocr',
        # PyTorch for EasyOCR GPU support
        'torch',
        'torch.cuda',
        'torch.nn',
        'torch.backends',
        'torch.backends.cudnn',
        'torchvision',
        'torchaudio',  # Part of PyTorch CUDA installation
        # Encoding detection (optional)
        'chardet',
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
