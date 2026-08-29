"""Train a LoRA adapter that teaches the PII model romanised non-English text.

A PLUGIN, NOT A REPLACEMENT. The alternative was swapping the detector, and
nothing on offer fits: measured against the shipped model's 736 MB (183.9M
params, fp32),

    ai4privacy ModernBERT   ~150M   ~600 MB   MIT, but a Llama licence overlay
    Piiranha                ~300M   1.1 GB    CC-BY-NC-ND — cannot ship at all
    GLiNER2-PII             ~205M   4-6 GB    Apache, no Hindi
    OpenMed multilingual     1.4B   ~2.8 GB   "50M active" is compute, not RAM

and none of them is trained on romanised Hindi either, because no public
dataset declares `hi-Latn`. An adapter costs a few MB of weights on top of a
model that already tokenizes these scripts with zero [UNK], and leaves the base
detector untouched for everything it already gets right.

WHAT IS FROZEN AND WHAT IS NOT. LoRA on the encoder's attention projections,
plus the classifier head — the head has to move because the decision being
corrected IS the head's, and rank-8 updates to attention alone would be asking
the model to re-weight evidence it is not allowed to relabel.

THIS NEEDS A GPU. Measured on torch 2.12.0+cpu with 6 threads: 70 SECONDS per
step, on a batch of 8 sequences averaging 17 tokens. Two epochs over this
corpus is roughly 2,000 steps, so a real run is about a day — which is not a
slow run, it is a run nobody will ever finish. The base model is 184M params
and every step still walks the whole encoder backwards; LoRA shrinks the
weights being updated, not the graph being differentiated.

On any CUDA device the same run is minutes. Nothing else about the script
changes: it resolves the base model from the hub when the vendored copy is
absent, so a fresh clone is enough.

Usage:
    python scripts/pii_adapter_data.py --rows 8000        # only if data/ is empty
    python scripts/pii_adapter_train.py --epochs 2 --batch 32

Then evaluate against the failure set before trusting it — the corpus is
synthetic-adjacent and a model that has learned "greetings are never names"
too well will start leaking the short real ones (Li, Xi, Wu, Bo).
"""
from __future__ import annotations

import argparse
import json
import pathlib
import random
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

# The vendored copy when it is there, the hub id when it is not. `backend/models/`
# is gitignored, so a fresh clone — which is what a GPU box is — has no local
# weights and would otherwise fail on a path that only exists on the machine
# the corpus happened to be built on.
_LOCAL_MODEL = ROOT / "backend" / "models" / "pii"
HUB_MODEL = "Isotonic/deberta-v3-base_finetuned_ai4privacy_v2"
BASE_MODEL = str(_LOCAL_MODEL) if (_LOCAL_MODEL / "config.json").exists() else HUB_MODEL
MAX_LEN = 256


def load_rows(path: pathlib.Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def encode(rows: list[dict], tokenizer, label2id: dict[str, int]) -> list[dict]:
    """Character spans -> BIO token labels, via the tokenizer's own offsets.

    Offset mapping rather than word splitting: the model is SentencePiece, so
    "Aniketh" is three pieces and any word-level alignment would have to guess
    where they start. The offsets are the ground truth the tokenizer itself
    used, so a span lands on exactly the pieces it covers.
    """
    out: list[dict] = []
    dropped = 0
    for row in rows:
        text = row["text"]
        enc = tokenizer(text, truncation=True, max_length=MAX_LEN,
                        return_offsets_mapping=True)
        offsets = enc["offset_mapping"]
        labels = [0] * len(offsets)          # 0 == "O"
        ok = True
        for span in row["spans"]:
            begin, finish, label = span["start"], span["end"], span["label"]
            b_id = label2id.get(f"B-{label}")
            i_id = label2id.get(f"I-{label}")
            if b_id is None or i_id is None:
                ok = False
                break
            first = True
            for idx, (start, end) in enumerate(offsets):
                if end <= start:             # special token
                    continue
                if start >= finish or end <= begin:
                    continue
                labels[idx] = b_id if first else i_id
                first = False
            if first:                        # span fell outside the window
                ok = False
                break
        if not ok:
            dropped += 1
            continue
        for idx, (start, end) in enumerate(offsets):
            if end <= start:
                labels[idx] = -100           # ignored by the loss
        out.append({"input_ids": enc["input_ids"],
                    "attention_mask": enc["attention_mask"],
                    "labels": labels})
    if dropped:
        print(f"  dropped {dropped} rows whose spans did not survive tokenization")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/pii_adapter.jsonl")
    ap.add_argument("--out", default="backend/models/pii-adapter")
    ap.add_argument("--epochs", type=float, default=2.0)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--rank", type=int, default=8)
    ap.add_argument("--seed", type=int, default=17)
    args = ap.parse_args()

    import torch
    from torch.utils.data import DataLoader
    from transformers import (AutoConfig, AutoTokenizer,
                              AutoModelForTokenClassification,
                              DataCollatorForTokenClassification)
    from peft import LoraConfig, get_peft_model, TaskType

    random.seed(args.seed)
    torch.manual_seed(args.seed)

    rows = load_rows(ROOT / args.data)
    print("corpus rows:", len(rows))

    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
    config = AutoConfig.from_pretrained(BASE_MODEL)
    label2id = {name: int(idx) for idx, name in config.id2label.items()}

    encoded = encode(rows, tokenizer, label2id)
    random.shuffle(encoded)
    split = max(1, int(len(encoded) * 0.05))
    holdout, train_rows = encoded[:split], encoded[split:]
    print("train %d | holdout %d" % (len(train_rows), len(holdout)))

    model = AutoModelForTokenClassification.from_pretrained(BASE_MODEL)
    lora = LoraConfig(
        task_type=TaskType.TOKEN_CLS,
        r=args.rank,
        lora_alpha=args.rank * 2,
        lora_dropout=0.05,
        bias="none",
        # DeBERTa-v2 names its projections query_proj/key_proj/value_proj.
        target_modules=["query_proj", "key_proj", "value_proj"],
        # The head moves too — see the module docstring.
        modules_to_save=["classifier"],
    )
    model = get_peft_model(model, lora)
    model.print_trainable_parameters()

    collate = DataCollatorForTokenClassification(tokenizer)
    loader = DataLoader(train_rows, batch_size=args.batch, shuffle=True,
                        collate_fn=collate)
    optimiser = torch.optim.AdamW(
        [p for p in model.parameters() if p.requires_grad], lr=args.lr)
    steps = int(len(loader) * args.epochs)
    schedule = torch.optim.lr_scheduler.OneCycleLR(
        optimiser, max_lr=args.lr, total_steps=max(steps, 1), pct_start=0.1)

    model.train()
    step = 0
    done = False
    for epoch in range(int(args.epochs) + 1):
        if done:
            break
        for batch in loader:
            loss = model(**batch).loss
            loss.backward()
            torch.nn.utils.clip_grad_norm_(
                [p for p in model.parameters() if p.requires_grad], 1.0)
            optimiser.step()
            schedule.step()
            optimiser.zero_grad()
            step += 1
            if step % 25 == 0:
                print("  step %4d/%d  loss %.4f" % (step, steps, loss.item()), flush=True)
            if step >= steps:
                done = True
                break

    model.eval()
    correct = total = 0
    with torch.no_grad():
        for batch in DataLoader(holdout, batch_size=args.batch, collate_fn=collate):
            logits = model(**batch).logits.argmax(-1)
            mask = batch["labels"] != -100
            correct += (logits[mask] == batch["labels"][mask]).sum().item()
            total += mask.sum().item()
    print("holdout token accuracy: %.4f (%d tokens)" % (correct / max(total, 1), total))

    out_dir = ROOT / args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(out_dir))
    tokenizer.save_pretrained(str(out_dir))
    size = sum(f.stat().st_size for f in out_dir.rglob("*") if f.is_file())
    print("saved adapter -> %s  (%.1f MB)" % (out_dir, size / 1e6))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
