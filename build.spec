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
        'sqlite3',  # For SQLite cache backend (built-in Python)
        'difflib',  # For SequenceMatcher in text deduplication (built-in Python)
        # Modules package
        'modules',
        'modules.logger',
        'modules.circuit_breaker',
        'modules.ocr_postprocessing',
        'modules.unified_translation_cache',
        'modules.batch_translation',
        'modules.deepl_context',
        'modules.text_validator',
        'modules.text_normalizer',
        'modules.text_deduplication',
        'modules.sentence_buffer',
        'modules.smart_queue',
        'modules.rate_limiter',
        'modules.translation_continuity',
        'modules.advanced_deduplication',  # NEW: Advanced deduplication module
        'modules.hotkey_manager',  # NEW: Global hotkeys system
        # Handlers package
        'handlers',
        'handlers.tesseract_ocr_handler',
        'handlers.easyocr_handler',
        'handlers.cache_manager',
        'handlers.sqlite_cache_backend',
        'handlers.marianmt_handler',  # NEW: MarianMT local translation
        # Advanced deduplication
        'imagehash',  # Perceptual hashing library
        'difflib',    # Text similarity (built-in Python)
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
        # MarianMT dependencies
        'transformers',
        'transformers.models',
        'transformers.models.marian',
        'transformers.models.marian.modeling_marian',
        'transformers.models.marian.tokenization_marian',
        'transformers.configuration_utils',
        'transformers.modeling_utils',
        'transformers.tokenization_utils',
        'transformers.tokenization_utils_base',
        'transformers.utils',
        'transformers.utils.hub',
        'transformers.utils.import_utils',
        'transformers.file_utils',
        'transformers.generation',
        'transformers.generation.utils',
        'sentencepiece',
        # Tokenizers library (used by transformers)
        'tokenizers',
        'tokenizers.implementations',
        'tokenizers.models',
        'tokenizers.pre_tokenizers',
        'tokenizers.processors',
        # Hugging Face Hub (for model download)
        'huggingface_hub',
        'huggingface_hub.file_download',
        'huggingface_hub.hf_api',
        'huggingface_hub.utils',
        'huggingface_hub._snapshot_download',
        # Networking (for model download)
        'requests',
        'requests.adapters',
        'requests.sessions',
        'urllib3',
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
