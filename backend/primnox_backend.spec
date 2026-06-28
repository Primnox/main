import os
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
hiddenimports += [
  'pyaudiowpatch',
  '_portaudiowpatch',   # top-level C extension (PortAudio) pyaudiowpatch imports
  'pycaw',
  'pycaw.pycaw',
  'comtypes',
  'sounddevice',
  'scipy',
  'scipy.signal',
]
hiddenimports += collect_submodules('comtypes')

# The _portaudiowpatch .pyd has PortAudio statically linked, so listing it in
# hiddenimports is enough to bundle it (collect_dynamic_libs finds no separate
# DLL). collect it defensively in case a future wheel ships a side-by-side DLL.
binaries = collect_dynamic_libs('pyaudiowpatch')

a = Analysis(
  ['server.py'],
  pathex=['.'],
  binaries=binaries,
  datas=datas,
  hiddenimports=hiddenimports,
  excludes=[],
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
