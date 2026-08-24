"""Which tools are worth showing this model. Built, measured, NOT enabled.

Read the note at the bottom of this file before reaching for it. The short
version: the retriever is good and the idea does not work, for a reason that
is specific and worth knowing.

The problem it was built for: a small model asked to pick one of fourteen
tools gets it right about half the time, and its mistakes are confusions
between near-synonyms — `recall_memory` against `recall_conversation`,
`create_workspace` against `update_workspace`. Rewriting the descriptions to
lead with the distinguishing condition moved that from 3/10 to 5/10 and then
stopped. Discrete-ID menus made it worse (1/10). So did a disambiguation
table, and so did the provider's own native tool calling on that model.

What none of those changed is the SIZE of the decision, and this narrows it:
an encoder ranks the tools against the request and only the top few are shown.
The ranking works — recall@3 of 10/10, recall@1 of 8/10 over ten tasks, no
language model involved (`scripts/bench_tool_retrieval.py`). End to end it
still lost, 4/10 against 5/10.

Retrieval never chooses the tool, only the shortlist; the model still decides.
That was deliberate — a retriever that picked outright would put a silent
8/10 classifier in front of every turn with nothing able to overrule it.

Everything here degrades to "show everything": the encoder loads lazily on a
background thread, as the privacy scrubber's NER model does, and every failure
path returns None. Losing it costs prompt size, never a turn.

`memory/service.py` deliberately declined embeddings, and that reasoning
stands where it was made — it runs on every write, and a model in the path of
"remember this" is a model in the path of something that must not stall. This
would run once per turn.
"""
from __future__ import annotations

import threading

# Small, and small on purpose: 22M parameters, CPU-only, roughly 80 MB on
# disk. Tool retrieval competes with the model it is helping for the same
# machine, so an encoder that needed a GPU would defeat the point.
ENCODER = "sentence-transformers/all-MiniLM-L6-v2"

# Never narrow below this. Retrieval is a ranking, not a verdict, and the
# measured recall@3 is what this is set from — three is where the right tool
# was present in every case, so anything tighter trades the whole benefit for
# a token saving.
MIN_CANDIDATES = 3

# What a tool is FOR, phrased as things a person would say.
#
# Descriptions retrieve badly and the reason is worth keeping: measured,
# `run_python` ranked NINTH for "work out 137 * 449", because its description
# says "execute Python code in an isolated sandbox" and no encoder bridges
# that to arithmetic from surface text. Swapping descriptions for examples
# took recall@3 from 6/10 to 10/10.
#
# They live here rather than on `ToolSpec` because they are not part of a
# tool's contract — nothing calls a tool differently on account of them. They
# are training data for the retriever, and putting them in the registry would
# invite writing them for the model to read, which is what descriptions are
# for and what made them retrieve poorly in the first place.
EXAMPLES: dict[str, list[str]] = {
    "run_python": ["calculate 17 times 3", "what is 2 to the power of 30",
                   "parse this csv and total the third column",
                   "work out the average of these numbers"],
    "run_node": ["run this javascript snippet", "execute some js for me"],
    "run_shell": ["what version of git do I have", "is docker installed",
                  "check what is on my PATH", "list the running processes"],
    "search_assets": ["which of my files mentions the refund policy",
                      "look through my pdfs for the contract",
                      "find the document about pricing"],
    "read_asset": ["open the file you just found", "show me that pdf's text",
                   "read it back to me"],
    "remember": ["keep in mind that I use vim", "note that my name is Sam",
                 "from now on, always use metric",
                 "remember that I prefer this"],
    "recall_memory": ["what are my preferences", "do you know my setup",
                      "what have I told you about myself",
                      "what do you know about me"],
    "recall_conversation": ["what did we settle on before",
                            "which approach did we agree earlier",
                            "what file were we looking at",
                            "what did we decide"],
    "graph_query": ["how is authentication implemented here",
                    "where does this project handle retries",
                    "explain how the indexer works in this repo",
                    "how does this codebase do that"],
    "create_workspace": ["make me a landing page",
                         "write a small script I can edit",
                         "start a new project for this",
                         "build me an app"],
    "update_workspace": ["change the colour in that file",
                         "add a function to the thing you built",
                         "edit the page you just made",
                         "add a feature to that app"],
    "ask_user": ["I am not sure which one you mean",
                 "which of these did you want"],
    "read_skill": ["what does that skill do",
                   "show me the instructions for it"],
    "render_slide_json": ["turn this into a deck", "make me some slides"],
}

_lock = threading.Lock()
_encoder = None                 # callable(list[str]) -> tensor, once ready
_loading = False
_failed = False
_vectors = None                 # cached tool matrix
_owner: list[int] = []          # row -> index into the spec list it came from
_vector_names: list[str] = []   # the registry the cache was built against


def _load() -> None:
    """Bring the encoder up on a background thread. Never raises."""
    global _encoder, _loading, _failed
    with _lock:
        if _encoder is not None or _loading or _failed:
            return
        _loading = True

    def work() -> None:
        global _encoder, _loading, _failed
        try:
            import torch
            from transformers import AutoModel, AutoTokenizer

            tokenizer = AutoTokenizer.from_pretrained(ENCODER)
            model = AutoModel.from_pretrained(ENCODER)
            model.eval()

            def embed(texts: list[str]):
                batch = tokenizer(texts, padding=True, truncation=True,
                                  max_length=256, return_tensors="pt")
                with torch.no_grad():
                    hidden = model(**batch).last_hidden_state
                # Mean pooling over real tokens only. Counting padding drags
                # every vector toward the pad embedding and compresses the
                # distances this depends on.
                mask = batch["attention_mask"].unsqueeze(-1).float()
                pooled = (hidden * mask).sum(1) / mask.sum(1).clamp(min=1e-9)
                return torch.nn.functional.normalize(pooled, dim=1)

            with _lock:
                _encoder, _loading = embed, False
        except Exception:
            # No encoder means no narrowing, which is the behaviour that
            # existed before this module. Marked failed so a machine without
            # the model pays one attempt rather than one per turn.
            with _lock:
                _loading, _failed = False, True

    threading.Thread(target=work, name="tool-retrieval", daemon=True).start()


def _tool_matrix(specs):
    """Vectors for every tool, rebuilt when the registry changes.

    Each tool contributes SEVERAL rows — its description and each example —
    and scores by its best match rather than an average. A tool reached for in
    two unrelated situations has no single centre, and averaging puts it
    between them, close to neither.
    """
    global _vectors, _owner, _vector_names

    names = [spec.name for spec in specs]
    if _vectors is not None and names == _vector_names:
        return _vectors

    corpus, owner = [], []
    for index, spec in enumerate(specs):
        corpus.append(f"{spec.name.replace('_', ' ')}. {spec.description}")
        owner.append(index)
        for example in EXAMPLES.get(spec.name, []):
            corpus.append(example)
            owner.append(index)

    _vectors = _encoder(corpus)
    _owner = owner
    _vector_names = names
    return _vectors


def ready() -> bool:
    return _encoder is not None


def candidates(request: str, k: int = 5) -> "list[str] | None":
    """The k tool names most likely to be wanted, or None to show everything.

    None is the honest answer whenever anything is missing — the encoder still
    loading, a machine that cannot load it, an empty request. The caller shows
    the full catalogue, which is what it did before this existed.
    """
    if not (request or "").strip():
        return None
    if _encoder is None:
        _load()                     # warm for next time; this turn is unnarrowed
        return None

    try:
        from .registry import all_specs

        specs = all_specs()
        if len(specs) <= MIN_CANDIDATES:
            return None

        vectors = _tool_matrix(specs)
        query = _encoder([request])[0]
        scores = (vectors @ query).tolist()

        best = [-2.0] * len(specs)
        for row, score in enumerate(scores):
            slot = _owner[row]
            if score > best[slot]:
                best[slot] = score

        ranked = sorted(range(len(specs)), key=lambda i: -best[i])
        keep = max(MIN_CANDIDATES, min(k, len(specs)))
        return [specs[i].name for i in ranked[:keep]]
    except Exception:
        return None


def warm() -> None:
    """Start loading without asking for anything. Called at startup."""
    _load()


# ── Measured, and NOT enabled ───────────────────────────────────────────────
#
# This module works and is not wired in. `kernel/scheduler.py` deliberately
# does not pass `request=` to `system_prompt`, so `_shortlist` never runs.
# Turning it on is that one argument.
#
# The retriever itself is good: recall@3 of 10/10 and recall@1 of 8/10 over
# ten tasks, with no language model involved. End to end it made the answer
# WORSE — qwen2.5:0.5b scored 4/10 with narrowing against 5/10 without.
#
# The reason is worth keeping, because it is not obvious and it invalidates
# the argument that motivated the work:
#
#   SEMANTIC RETRIEVAL CONCENTRATES THE CONFUSABLE TOOLS.
#
# The model's failures were never spread evenly. They were confusions between
# near-synonyms — `recall_memory` against `recall_conversation`,
# `create_workspace` against `update_workspace`. Those pairs are near
# neighbours in embedding space BY CONSTRUCTION, so any request that retrieves
# one retrieves the other. Narrowing fourteen tools to five removes the easy
# distractors and keeps exactly the hard ones, and the model is left making
# the same discrimination it was already failing, with fewer obvious wrong
# answers to reject on the way.
#
# That also settles a result that looked contradictory. An entropy sweep with
# RANDOM distractors did improve at three candidates; semantic retrieval at
# five did not. Both are true: fewer options help when the options removed are
# ones the model could already rule out. Semantic similarity removes the
# opposite ones.
#
# What would actually be worth trying, if this is picked up again: rank by
# similarity, then apply a DIVERSITY penalty so a shortlist cannot be filled
# with mutual near-neighbours (maximal marginal relevance is the standard
# form). That attacks the mechanism above rather than working around it.
