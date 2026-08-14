import os, sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, collect_dynamic_libs

block_cipher = None

datas = [
  ('settings.json', '.'),
  ('system_prompts.py', '.'),
  ('skills', 'skills'),
]

# Bundle the Privacy Mirror PII model so it ships inside the build — no runtime
# HF download, no startup leak window. Populate it first: `python fetch_pii_model.py`.
if os.path.isdir('models/pii'):
  datas.append(('models', 'models'))
else:
  print("WARNING: models/pii not found — run `python fetch_pii_model.py` to bundle "
        "the PII model, otherwise Privacy Mirror falls back to a runtime download.")

# transformers/tokenizers ship data files and load model classes dynamically; pull
# them in so the DeBERTa token-classification pipeline runs inside the frozen app.
datas += collect_data_files('transformers')
datas += collect_data_files('tokenizers')

# ── Packages that resolve assets at runtime ────────────────────────────────────
# The module graph pulls in the *code* for these, so a frozen build imports them
# fine and only fails later, when they go looking for data that never shipped.
# That is why they survive a launch smoke test and break in the wild instead.

# botocore keeps every AWS service definition as JSON and reads it when a client
# is constructed, not when it is imported. Without this, backup_providers/s3.py
# raises DataNotFoundError the first time an S3/B2/R2/Wasabi backup runs.
datas += collect_data_files('botocore')

# google-api-python-client resolves discovery documents the same way, for
# backup_providers/gdrive.py and skills/calendar_providers/google_provider.py.
datas += collect_data_files('googleapiclient')

# ultralytics and easyocr both read packaged YAML/character configs from their
# own install dir (spatial_engine.py). Model *weights* stay a first-run download
# by design; these are the config files needed before that download can start.
datas += collect_data_files('ultralytics')
datas += collect_data_files('easyocr')

hiddenimports = [
  'uvicorn',
  'uvicorn.logging',
  'uvicorn.loops',
  'uvicorn.loops.auto',
  'uvicorn.protocols',
  'uvicorn.protocols.http',
  'uvicorn.protocols.http.auto',
  'fastapi',
  'pypdf',
  'pptx',
  'groq',
  'sqlite3',
  'websockets',
  'dotenv',
  'PIL',
  'cv2',
  'reminder_manager',
  'emotion_agent',
  'profiler',
  # Privacy Mirror PII model runtime
  'torch',
  'transformers',
  'tokenizers',
  'safetensors',
  'sentencepiece',
  'huggingface_hub',
  'numpy',
  'regex',
] + collect_submodules('transformers.models.deberta_v2')

# ── Meeting audio capture ──────────────────────────────────────────────────────
# These are imported lazily INSIDE functions (meeting_recorder.py), so PyInstaller
# can't discover them statically. Without listing them here they silently don't
# ship — the packaged backend then fails `import pyaudiowpatch` at runtime and
# records meetings with NO AUDIO (which also aborts the summary, so recordings
# look "unnamed"). pyaudiowpatch = WASAPI loopback + mic capture; pycaw/comtypes
# = in-call detection; scipy.signal = the mic+speaker mixdown.
# scipy.signal powers the mic+speaker mixdown on every platform.
hiddenimports += ['scipy', 'scipy.signal']

# keyring selects its OS backend through package entry points, which a frozen
# app cannot enumerate — the import succeeds and then no backend is found, so
# every secret read returns nothing. Name the backends explicitly. Used by
# local_vault, settings_manager, sandbox_account, brain, code_exec and
# backup_manager, i.e. the whole credential path.
hiddenimports += collect_submodules('keyring.backends')

# Per-platform capture backends — keep them platform-scoped so neither build
# carries the other's unused PortAudio DLLs, and a mac build doesn't warn about
# Windows-only modules.
binaries = []
if sys.platform == 'win32':
  # Windows: WASAPI loopback + mic via pyaudiowpatch (C ext `_portaudiowpatch`,
  # PortAudio statically linked), in-call detection via pycaw/comtypes.
  hiddenimports += [
    'pyaudiowpatch',
    '_portaudiowpatch',
    'pycaw',
    'pycaw.pycaw',
    'comtypes',
  ]
  hiddenimports += collect_submodules('comtypes')
  binaries += collect_dynamic_libs('pyaudiowpatch')  # defensive; usually empty
else:
  # macOS / Linux: capture via sounddevice (bundles its own PortAudio binary).
  hiddenimports += ['sounddevice']
  binaries += collect_dynamic_libs('sounddevice')

a = Analysis(
  ['server.py'],
  pathex=['.'],
  binaries=binaries,
  datas=datas,
  hiddenimports=hiddenimports,
  # On Windows the sounddevice path is never taken (we use pyaudiowpatch), but
  # its lazy `import sounddevice` in meeting_recorder is auto-discovered by
  # PyInstaller and drags in PortAudio DLLs. Exclude it so the Windows build
  # doesn't carry them; the win capture path doesn't need it.
  excludes=(['sounddevice'] if sys.platform == 'win32' else []),
  cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
  pyz,
  a.scripts,
  [],
  exclude_binaries=True,
  name='primnox_backend',
  debug=False,
  bootloader_ignore_signals=False,
  strip=True,
  upx=True,
  console=True,
  cipher=block_cipher,
)

coll = COLLECT(
  exe,
  a.binaries,
  a.zipfiles,
  a.datas,
  strip=True,
  upx=True,
  upx_exclude=[],
  name='primnox_backend',
)
