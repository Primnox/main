import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

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

a = Analysis(
  ['server.py'],
  pathex=['.'],
  binaries=[],
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
