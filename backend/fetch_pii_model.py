"""
Pre-download + fp16-pack the Privacy Mirror PII model into backend/models/pii/
so it can be bundled into the PyInstaller build (primnox_backend.spec) — no
runtime download, no startup leak window.

Run once before building:   python fetch_pii_model.py

The weights are stored on disk as fp16 (~370 MB instead of ~760 MB). They're
upcast back to fp32 in RAM at load time (transformers' default), so CPU inference
is unaffected — this only shrinks the shipped bundle, not runtime precision.

Skips framework duplicates (TF/Flax/ONNX) to keep the bundle lean.
"""

import json
from pathlib import Path

from huggingface_hub import snapshot_download

MODEL_ID = "Isotonic/deberta-v3-base_finetuned_ai4privacy_v2"
DEST = Path(__file__).resolve().parent / "models" / "pii"

# Keep only what PyTorch inference needs.
ALLOW = ["*.json", "*.safetensors", "*.bin", "*.model", "*.spm", "*.txt"]
IGNORE = ["*.h5", "*.msgpack", "*.onnx", "*.tflite", "*.ot", "rust_model.ot"]


def _already_fp16() -> bool:
    cfg = DEST / "config.json"
    if not cfg.exists():
        return False
    try:
        return json.loads(cfg.read_text()).get("torch_dtype") == "float16"
    except Exception:
        return False


def _dir_mb() -> float:
    return sum(p.stat().st_size for p in DEST.rglob("*") if p.is_file()) / 1e6


def main() -> None:
    # Idempotent: if the on-disk copy is already fp16, don't re-pull the fp32 file.
    if _already_fp16():
        print(f"Model already fp16 at {DEST} ({_dir_mb():.0f} MB) — nothing to do.")
        return

    DEST.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {MODEL_ID} -> {DEST}")
    snapshot_download(
        repo_id=MODEL_ID,
        local_dir=str(DEST),
        allow_patterns=ALLOW,
        ignore_patterns=IGNORE,
    )
    print(f"Downloaded fp32 ({_dir_mb():.0f} MB). Packing weights to fp16…")

    # Load, halve, re-save (safetensors only). config.json gains torch_dtype=float16,
    # but privacy_mirror loads with the default dtype (None) so RAM stays fp32 → CPU ok.
    from transformers import AutoModelForTokenClassification

    model = AutoModelForTokenClassification.from_pretrained(str(DEST))
    model = model.half()
    model.save_pretrained(str(DEST), safe_serialization=True)

    files = sorted(p.name for p in DEST.glob("*") if p.is_file())
    print(f"Done. fp16 bundle: {_dir_mb():.0f} MB, {len(files)} files:")
    for f in files:
        print(f"  {f}")


if __name__ == "__main__":
    main()
