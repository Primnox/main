# Findings — privacy mirror, Canvas routing, token efficiency

A record of what was measured, what was fixed, and what is still wrong.
Numbers here are measurements, not estimates; where something is unproven it
says so.

---

## 1. The privacy mirror is wrong in both directions

The detector is `Isotonic/deberta-v3-base_finetuned_ai4privacy_v2` — 183.9M
params, 736 MB fp32, 111 labels, 512-token window.

### It over-redacts

| input | label | score |
|---|---|---|
| `namaste` | FIRSTNAME | 0.999 |
| `shukriya` | FIRSTNAME | 0.999 |
| `dhanyavaad` | FIRSTNAME | 0.998 |
| `yaar` | FIRSTNAME | 0.995 |
| `bhai` | FIRSTNAME | 0.994 |
| `arigato` | FIRSTNAME | 0.999 |

Saying hello reported **PRIVACY MIRROR · 1 SCRUBBED** and sent the provider a
message whose entire content was `§FIRSTNAME_1§`. The reply came back "you
haven't asked a question" — because, as far as the model could see, nobody had.

### It under-redacts, which is worse

Measured against labelled data, spans the mirror is supposed to catch:

| corpus | spans | missed | recall |
|---|---|---|---|
| romanised Hindi | 658 | 193 | **70.7%** |
| English control | 252 | 48 | **81.0%** |

**125 real names leaked verbatim in 300 sentences** (99 FIRSTNAME, 26
LASTNAME), plus cities, ages and titles. Note English is not good either — it
misses roughly one PII span in five.

*Caveat: the English control reuses the same entity values in plain carrier
sentences, so it shares the dataset's European-heavy names. It shows the gap
directionally; it is not a clean like-for-like.*

### Three fixes that do not work, and why

- **A word list** does not terminate. The set is every greeting, interjection
  and loanword in every language a user might type. One afternoon in two
  languages produced twelve.
- **A score gate** cannot separate them. The false positives sit at 0.99+,
  exactly where the real names sit (`aniketh` 0.999, `priya` 0.998,
  `sundar` 1.0). The model is not uncertain, it is confidently wrong.
- **Capitalisation** cannot either. `Namaste` is clean while `namaste` is not,
  which suggests keying on case — but `my name is aniketh` scores 0.999 on a
  genuine name, and people type their own names in lowercase constantly.

### What was fixed

| fault | before | after |
|---|---|---|
| `USERAGENT` had no score gate | 33 scrubs on one technical table | **0** |
| chunker counted chars vs a token limit | 1500 chars = 1429 tokens of JSON | windows by token, 64 overlap |
| gate ran on subword pieces before merge | **`pin 4432` → redacted `44`, leaked `32`** | gate applies to the whole entity |
| tokenizer leftovers labelled as names | `bye` → `('e')`, `howdy` → `('dy')` | word-boundary rule, no vocabulary |
| inference failure logged at `warning` | silent leak | `log.error`, names the leak |

Real PII is unchanged: name, city, email, CVV, PIN, phone and genuine
user-agent strings all still caught.

### The adapter

Both directions are trainable from one corpus, and the tokenizer already
permits it — **zero `[UNK]`** on Devanagari, Japanese and Chinese. The
vocabulary can represent these words; the weights have no idea what they are.

No replacement model fits the 736 MB budget:

| model | params | RAM | licence | Hindi |
|---|---|---|---|---|
| ai4privacy ModernBERT | ~150M | ~600 MB | MIT + Llama overlay | yes |
| Piiranha | ~300M | 1.1 GB | **CC-BY-NC-ND** — cannot ship | no |
| GLiNER2-PII | 205M | **4–6 GB** | Apache 2.0 | no |
| OpenMed multilingual | 1.4B MoE | **~2.8 GB** | Apache 2.0 | yes |

> OpenMed's "50M active per token" is a **compute** figure. All 1.4B params
> stay resident. It reads as the cheapest option and is the most expensive.

`scripts/pii_adapter_data.py` builds 8,260 rows. ai4privacy's Hindi rows are
unusually well suited: the PII values are already Latin while the sentence
around them is Devanagari, so transliterating only the *context* produces
exactly the shape the model gets wrong.

`scripts/pii_adapter_train.py` — LoRA over attention projections plus the
classifier head, **527,727 trainable params (0.29%)**.

**Not trained.** A step is **70s** on this CPU — batch of 8, ~17 tokens each —
making two epochs roughly a day. That is not a slow run, it is one nobody
finishes. LoRA shrinks the weights being *updated*, not the graph being
differentiated: every step still walks all 184M params backwards.

### Running it on a GPU box

The corpus is committed (2.1 MB), so no dataset download and no
`indic-transliteration` needed. The base model is gitignored but resolves from
the hub automatically when the vendored copy is absent.

```bash
git clone <this repo> && cd Primnox
pip install torch transformers peft
python scripts/pii_adapter_train.py --epochs 2 --batch 32
```

Output is `backend/models/pii-adapter` — a few MB of adapter weights, not a
model. Then **evaluate before trusting it**:

```bash
python - <<'PY'
from peft import PeftModel
from transformers import AutoModelForTokenClassification, AutoTokenizer
base = "Isotonic/deberta-v3-base_finetuned_ai4privacy_v2"
m = PeftModel.from_pretrained(AutoModelForTokenClassification.from_pretrained(base),
                              "backend/models/pii-adapter")
PY
```

Two things to check, and they pull against each other:

- **the false positives are gone** — `namaste`, `shukriya`, `yaar`, `bhai`,
  `arigato` should stop being `FIRSTNAME`
- **short real names survive** — `Li`, `Xi`, `Wu`, `Bo`, and recall on
  romanised Hindi should climb from **70.7%**, not fall

A model that learns "greetings are never names" too well starts leaking the
short real ones. If recall drops, the corpus needs more `greeting_then_name`
rows, which `pii_adapter_data.py` already generates.

To wire it in, `mirror.py` loads the pipeline in `_load_model()`; the adapter
attaches to the model before the pipeline is built.

---

## 2. Canvas was structurally unreachable

`themed-documents/SKILL.md` opened with:

> *"Your reply must begin with `<tool name="run_python">` and contain only the code."*

Absolute — while its `triggers` included `report`, `document`, `write-up`,
`briefing`. That did not discourage `create_workspace`, it made it
**impossible**, for exactly the requests most likely to want an editable
document. Every "write me a report" came back a PDF.

The triggers were the larger half: they fired on **4 of 10** document
requests, missing `essay`, `spec`, `plan`, `proposal`, `notes`, `outline`,
`comparison`. Where the skill did not fire, the model had no instruction to
build anything at all.

| | before | after |
|---|---|---|
| triggers on document requests | 4/10 | **10/10** |
| triggers on plain questions | 0/5 | **0/5** |
| Canvases in the measured group | 0 | 3 |

Verified through the UI on two different models:

| request | result |
|---|---|
| "Write a technical spec for a caching layer" | **Canvas**, 0 files |
| "Create study notes covering the OSI model" | **Canvas** — *OSI Model Study Notes* |
| "Make me a slide deck about the water cycle" | **pptx**, 0 Canvas |

---

## 3. Token efficiency

Local measurements, unaffected by provider state.

**Context composition** — 6,144-token budget:

| block | tokens | % budget |
|---|---|---|
| system prompt | 1,012 | 16.5% |
| tool catalogue | 1,350 | 22.0% |
| memory block | 300 | 4.9% |
| skills index | 202 | 3.3% |
| **fixed overhead, every turn** | **2,864** | **46.6%** |
| left for history + the user | 3,280 | 53.4% |

**Tool loop** — overhead is re-sent every iteration:

```
1 step  →  2,372t
8 steps → 37,148t   (15.7×; the last request alone is 113% of the window)
```

**Compaction** — `eager + prefix`, **95.1% saved**, target 95% MET.

> Still a *local model of billing*, not a measurement. `bench_live_turn.py`
> has never produced a real number: it spoke only Anthropic's `/v1/messages`,
> so no OpenAI-compatible gateway could work, and a zero baseline was turned
> into a divisor that printed **"100.0% saved"** for a total outage. Both are
> fixed; the benchmark still needs one healthy provider to run against.

---

## 4. Other defects found

- **Provider 429 reported as a model bug.** A rate limit ends the gateway's
  failover on a clean empty 200, so no exception reaches `_classify` and the
  user was told *"the model replied with an unfinished tool call"*. Five turns
  in a row blamed the model for a quota problem.
- **Failed turns poisoned every later turn.** `_observe_live` ran in
  `create_turn`, before any model work. Failed turns became `DECISION` nodes
  replayed as a system directive — which is why "namaste" once produced a
  B-tree PDF.
- **The malformed-tool-call correction gave impossible advice.** Written for
  `run_python`, applied to everything; it told `create_workspace` to send no
  JSON, which cannot express `kind` + `title` + `files`.
- **OmniRoute autostart could never succeed.** Spawned with no `PORT`, so it
  landed on **4109 — Primnox's own port** — while Primnox polled 20128.

---

## 5. Measurement mistakes made here

Recorded because they shaped conclusions before they were caught.

1. **Reported "Canvas recall 4.3% — feature broken".** Wrong. Only the
   `workspaces` table was scored. Counting assets too, **7 of 8** completed
   cases had produced a real document. Canvas was not failing; it was
   unreachable, which is a different bug with a different fix.
2. **Claimed a probe "created nothing".** It had created a workspace.
   `/assets` and `/turns/{id}/executions` do not record workspaces.
3. **Blamed OmniRoute's semantic cache** for cross-conversation contamination.
   123 entries, `hit_count` sums to **0** — it never served anything.
4. **Called a delivery drop a regression from the routing change.** It was the
   trigger gap becoming visible.
5. **Burned a provider quota** running 50-case sweeps against a free tier;
   24-hour lockout.

The harness now guards the first two failure modes directly: it counts files
as well as workspaces, treats a `completed` turn with no reply as an outage
rather than a pass, and aborts after three consecutive failures.

---

## Status

**Verified:** theme contrast (0 failures, 4 themes × 99 nodes) · Escape +
focus return · mirror on technical text (33 → 0) · the `pin` span leak ·
failed-turn graph poisoning · Canvas routing on two models · **1186 tests
passing, 7 skipped** (all `test_tool_surface.py`, Computer Use absent).

**Unresolved:** `namaste` still scrubbed — the word list was removed
deliberately and the model is the real fix · adapter untrained (CPU) ·
live-billing never run · no clean 50-case sweep exists · non-English PII
recall **70.7%**.
