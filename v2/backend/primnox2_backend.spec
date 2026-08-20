import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

datas = [
  ('primnox2/settings/providers.json', 'primnox2/settings'),
  ('primnox2/skills', 'primnox2/skills'),
  # storage/db.py reads this as Path(__file__).with_name("schema.sql") — a
  # sibling of the .py file, so it has to land in the same subdirectory
  # inside the bundle that db.py itself does.
  ('primnox2/storage/schema.sql', 'primnox2/storage'),
  # storage/vault.py's _wordlist_path() looks for this at the bundle ROOT
  # (sys._MEIPASS / "wordlist.txt") when frozen — see that function for why
  # dev's four-parents-up path can't resolve inside a frozen build at all.
  ('../../website/wordlist.txt', '.'),
]

# Bundle the Privacy Mirror PII model so it ships inside the build — no
# runtime HF download, no startup leak window. Populate it first:
# `python fetch_pii_model.py`.
if os.path.isdir('models/pii'):
  datas.append(('models', 'models'))
else:
  print("WARNING: models/pii not found — run `python fetch_pii_model.py` to bundle "
        "the PII model, otherwise Privacy Mirror falls back to a runtime download.")

# transformers/tokenizers ship data files and load model classes dynamically; pull
# them in so the DeBERTa token-classification pipeline runs inside the frozen app.
datas += collect_data_files('transformers')
datas += collect_data_files('tokenizers')

# Packages that resolve assets at runtime, not at import time — the module
# graph pulls in their *code* fine and only fails later, when they go looking
# for data that never shipped, which is why this class of bug survives a
# launch smoke test and breaks in the wild.
#
# python-pptx and python-docx each ship a "default" template (a blank .pptx /
# .docx) inside their own package dir and open it on first Presentation()/
# Document() call — without this, creating either kind of file from scratch
# fails the moment a skill tries to.
datas += collect_data_files('pptx')
datas += collect_data_files('docx')
# matplotlib resolves its font list and default style from data files under
# its own install dir (used by the chart-rendering paths in ppt_design).
datas += collect_data_files('matplotlib')
# graphify ships its BIP-39-unrelated internal resources (community-detection
# defaults, label heuristics) the same way; collected defensively since its
# packaging is less familiar than the others here.
datas += collect_data_files('graphify')

hiddenimports = [
  'uvicorn',
  'uvicorn.logging',
  'uvicorn.loops',
  'uvicorn.loops.auto',
  'uvicorn.protocols',
  'uvicorn.protocols.http',
  'uvicorn.protocols.http.auto',
  'uvicorn.protocols.websockets',
  'uvicorn.protocols.websockets.auto',
  'uvicorn.lifespan',
  'uvicorn.lifespan.on',
  'websockets',
  'fastapi',
  'multipart',
  'pypdf',
  'PyPDF2',
  'pptx',
  'docx',
  'openpyxl',
  'reportlab',
  'matplotlib',
  'sqlite3',
  # Local vault (storage/vault.py)
  'cryptography',
  'keyring',
  # Knowledge graph (knowledge/service.py, knowledge/importer.py)
  'graphify',
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

# keyring selects its OS backend through package entry points, which a frozen
# app cannot enumerate — the import succeeds and then no backend is found, so
# the vault's OS-keychain read/write silently does nothing. Name the backends
# explicitly, same fix V1 needed for the same reason.
hiddenimports += collect_submodules('keyring.backends')

# Belt-and-suspenders alongside pyinstaller_entry.py's direct `from
# primnox2.app import app`: that import already puts the whole package graph
# in front of PyInstaller's static analysis, but the runtime tool-routing and
# skill-loading code (tools/runtime.py, skills/loader.py) resolves some of
# its own submodules dynamically by name — the same class of "works until it
# doesn't" gap the entry-script rewrite exists to close for the top level.
hiddenimports += collect_submodules('primnox2')

a = Analysis(
  ['pyinstaller_entry.py'],
  pathex=['.'],
  binaries=[],
  datas=datas,
  hiddenimports=hiddenimports,
  cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
  pyz,
  a.scripts,
  [],
  exclude_binaries=True,
  name='primnox2_backend',
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
  name='primnox2_backend',
)
