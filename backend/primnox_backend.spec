# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller packaging source for the Primnox backend.

Hand-authored, and tracked in git despite the root `.gitignore`'s `*.spec`
rule — see the exception there. This file encodes decisions (what to collect,
what to exclude, which data files the frozen app resolves through
`sys._MEIPASS`) that nothing regenerates.

Run from `backend/`:

    pyinstaller primnox_backend.spec --clean -y

Output is `backend/dist/primnox_backend/`, which
`frontend/src-tauri/tauri.bundle.conf.json` copies into the installer as the
`primnox_backend` resource and `src-tauri/src/backend.rs` spawns at startup.
Those three names must agree; changing one means changing all of them.

ONEDIR, not onefile. A onefile build unpacks ~1.5 GB of torch to a temp
directory on every launch before the first line of Python runs, which reads as
a hang. Onedir also lets the NSIS installer's own compression do the work
once, at install time, instead of on every start.
"""
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

# The spec runs with CWD = the directory it lives in (backend/), but SPECPATH
# is the reliable anchor — `--clean` and CI both invoke it from elsewhere.
BACKEND = Path(SPECPATH).resolve()          # noqa: F821 — PyInstaller injects it
REPO = BACKEND.parent

# ── Data the frozen app resolves at runtime ────────────────────────────────
# Both of these are looked up under sys._MEIPASS first (see
# primnox2/privacy/mirror.py:_resolve_model_source and
# primnox2/storage/vault.py:_wordlist_path), so the destination names here are
# load-bearing, not cosmetic.
datas = []

# The DeBERTa PII model behind Privacy Mirror. Not in git (373 MB) — CI runs
# `python fetch_pii_model.py` before this spec. A missing model is NOT fatal:
# mirror.py falls back to the HF hub id, and below that to regex-only
# scrubbing. So warn rather than fail, or a developer without the model
# cannot build at all.
pii_model = BACKEND / "models" / "pii"
if (pii_model / "config.json").is_file():
    datas.append((str(pii_model), "models/pii"))
else:
    print(f"WARNING: no PII model at {pii_model} — "
          "run `python fetch_pii_model.py` first. Privacy Mirror will fall "
          "back to downloading it at runtime.")

# BIP-39 wordlist for the vault's recovery phrase. Unlike the model there is
# no fallback — vault.py raises FileNotFoundError — so this one is fatal.
wordlist = REPO / "website" / "wordlist.txt"
if not wordlist.is_file():
    raise SystemExit(f"BIP-39 wordlist missing at {wordlist}; cannot build.")
datas.append((str(wordlist), "."))

# Everything non-.py inside the package: guides/*.md, settings/providers.json,
# skills/** (SKILL.md, template packs, selection-index.json). These are read
# package-relative rather than through _MEIPASS, so they must keep their
# position under `primnox2/`.
datas += collect_data_files("primnox2", include_py_files=False)

# ── Third-party collection ─────────────────────────────────────────────────
hiddenimports = []
binaries = []

# transformers and tokenizers ship data files and resolve a lot dynamically;
# sentencepiece carries a native extension. collect_all is the blunt but
# correct tool for all three.
for pkg in ("transformers", "tokenizers", "sentencepiece", "safetensors"):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

# uvicorn/fastapi resolve their loop, protocol and lifespan implementations by
# string at runtime — `uvicorn[standard]` in requirements.txt is what makes
# these importable, and static analysis cannot see any of them.
hiddenimports += collect_submodules("uvicorn")
hiddenimports += [
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
    "websockets.legacy",
    "anyio._backends._asyncio",
]

# keyring picks its backend at runtime by walking entry points; on Windows the
# credential-locker backend is the one the vault actually uses.
hiddenimports += collect_submodules("keyring.backends")

# The app's own package — app.py mounts routers that import laterally, and
# skills are discovered by directory walk rather than by import.
hiddenimports += collect_submodules("primnox2")

# graphifyy installs as the module `graphify` (see requirements.txt).
hiddenimports += ["graphify"]

# Document generation. reportlab and matplotlib both load fonts/backends
# through data files rather than imports.
for pkg in ("reportlab", "matplotlib", "pptx", "docx", "openpyxl"):
    try:
        hiddenimports += collect_submodules(pkg)
        datas += collect_data_files(pkg)
    except Exception as exc:  # a missing optional package must not kill the build
        print(f"WARNING: could not collect {pkg}: {exc}")

# ── Exclusions ─────────────────────────────────────────────────────────────
# Weight ~= install size ~= download size. None of these are imported by the
# backend; torch pulls several in transitively and they cost hundreds of MB.
excludes = [
    "tkinter",
    "PyQt5", "PyQt6", "PySide2", "PySide6",
    "IPython", "jupyter", "notebook", "ipykernel",
    "pytest", "_pytest",
    # torch.distributed / TensorBoard are dead weight for single-process CPU
    # inference, which is all Privacy Mirror does.
    "tensorboard", "torch.distributed",
    # transformers imports these lazily behind `is_tf_available()` /
    # `is_flax_available()` guards that are False here.
    "tensorflow", "jax", "flax",
]

a = Analysis(                                            # noqa: F821
    ["pyinstaller_entry.py"],
    pathex=[str(BACKEND)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)                                        # noqa: F821

exe = EXE(                                               # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="primnox_backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # UPX corrupts some torch DLLs and saves little on an already-compressed
    # installer. Off deliberately, not by omission.
    upx=False,
    # No console window: Tauri spawns this as a child of a GUI app, and a
    # flashing terminal on launch reads as malware.
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(                                          # noqa: F821
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="primnox_backend",
)
