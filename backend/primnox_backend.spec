from PyInstaller.utils.hooks import collect_data_files

block_cipher = None

a = Analysis(
  ['server.py'],
  pathex=['.'],
  binaries=[],
  datas=[
    ('settings.json', '.'),
    ('system_prompts.py', '.'),
    ('skills', 'skills'),
  ],
  hiddenimports=[
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
  ],
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
