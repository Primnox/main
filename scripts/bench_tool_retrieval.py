"""Can an encoder put the right tool in front of the model?

This measures the RETRIEVER ALONE, with no language model anywhere in the
loop. That separation is the whole point: an earlier attempt at retrieval
scored 1/10 end-to-end and told us nothing, because a bad retriever and a bad
chooser produce the same number. Recall@k answers the retriever's half by
itself — if the right tool is not in the top three, no amount of prompt work
downstream can recover it, and if it always is, then narrowing is a real
mechanism rather than a hope.

The encoder is a small sentence-similarity model loaded through plain
`transformers` with mean pooling, because `sentence_transformers` is not
installed and one 80 MB download is cheaper than a new dependency.

Tool selection is a text-classification problem, and a discriminative encoder
is built for exactly that. A 0.5B generative model is not: measured over ten
tasks it picked the right tool 5 times, and its failures were almost entirely
semantic confusions between near-synonymous pairs — the thing an embedding
space is supposed to separate.

Usage:
    python scripts/bench_tool_retrieval.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

ENCODER = "sentence-transformers/all-MiniLM-L6-v2"


# Two or three things a person might actually say, per tool.
#
# Embedding the DESCRIPTION was tried first and put `run_python` ninth for
# "work out 137 * 449" — the description says "execute Python code in a
# sandbox", the request says "work out a sum", and no encoder bridges that
# from surface text alone. What retrieves well is not what a tool IS but when
# you would reach for it, so these are phrased as requests rather than as
# capabilities.
#
# Deliberately NOT the benchmark's own wordings. Reusing those would make
# recall@k measure whether I can copy a string, which is not a property that
# survives contact with a real user.
EXAMPLES = {
    "run_python": ["calculate 17 times 3", "what is 2 to the power of 30",
                   "parse this csv and total the third column"],
    "run_node": ["run this javascript snippet", "execute some js for me"],
    "run_shell": ["what version of git do I have", "is docker installed",
                  "check what is on my PATH"],
    "search_assets": ["which of my files mentions the refund policy",
                      "look through my pdfs for the contract"],
    "read_asset": ["open the file you just found", "show me that pdf's text"],
    "remember": ["keep in mind that I use vim", "note that my name is Sam",
                 "from now on, always use metric"],
    "recall_memory": ["what are my preferences", "do you know my setup",
                      "what have I told you about myself"],
    "recall_conversation": ["what did we settle on before",
                            "which approach did we agree earlier",
                            "what file were we looking at"],
    "graph_query": ["how is authentication implemented here",
                    "where does this project handle retries",
                    "explain how the indexer works in this repo"],
    "create_workspace": ["make me a landing page", "write a small script I can edit",
                         "start a new project for this"],
    "update_workspace": ["change the colour in that file",
                         "add a function to the thing you built",
                         "edit the page you just made"],
    "ask_user": ["I am not sure which one you mean",
                 "which of these did you want"],
    "read_skill": ["what does that skill do", "show me the instructions for it"],
    "render_slide_json": ["turn this into a deck", "make me some slides"],
}


def load_encoder():
    import torch
    from transformers import AutoModel, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(ENCODER)
    model = AutoModel.from_pretrained(ENCODER)
    model.eval()

    def embed(texts: list[str]):
        batch = tokenizer(texts, padding=True, truncation=True,
                          max_length=256, return_tensors="pt")
        with torch.no_grad():
            output = model(**batch).last_hidden_state
        # Mean pooling over real tokens only. Including padding drags every
        # vector toward whatever the pad embedding happens to be, which
        # compresses the distances this whole measurement depends on.
        mask = batch["attention_mask"].unsqueeze(-1).float()
        pooled = (output * mask).sum(1) / mask.sum(1).clamp(min=1e-9)
        return torch.nn.functional.normalize(pooled, dim=1)

    return embed


def main() -> int:
    from primnox2.tools import runtime                     # noqa: F401
    from primnox2.tools.registry import all_specs
    from bench_tool_surface import TASKS

    print(f"loading {ENCODER} …")
    embed = load_encoder()

    specs = all_specs()
    # Name AND description. The name carries real signal — `search_assets`
    # and `read_asset` differ by a verb that says what each one is for — and
    # dropping it would throw that away for the sake of tidiness.
    # Each tool is represented by SEVERAL vectors — its description and each
    # example — and scores by its best match. A tool used for two unrelated
    # things does not have one centre, and averaging its examples into one
    # point puts it between them, close to neither.
    corpus, owner = [], []
    for index, spec in enumerate(specs):
        corpus.append(f"{spec.name.replace('_', ' ')}. {spec.description}")
        owner.append(index)
        for example in EXAMPLES.get(spec.name, []):
            corpus.append(example)
            owner.append(index)
    vectors = embed(corpus)
    request_vectors = embed([user for user, _, _ in TASKS])

    hits = {1: 0, 3: 0, 5: 0}
    print(f"\n  {'request':44s} {'rank':>5s}  top-3")
    for index, (user, _, accepted) in enumerate(TASKS):
        raw = (vectors @ request_vectors[index]).tolist()
        best = [-2.0] * len(specs)
        for row, score in enumerate(raw):
            slot = owner[row]
            if score > best[slot]:
                best[slot] = score
        ranked = sorted(range(len(specs)), key=lambda i: -best[i])
        names = [specs[i].name for i in ranked]
        position = next((r + 1 for r, name in enumerate(names)
                         if name in accepted), None)
        for k in hits:
            if position is not None and position <= k:
                hits[k] += 1
        shown = ", ".join(names[:3])
        print(f"  {user[:44]:44s} {str(position or '-'):>5s}  {shown}")

    total = len(TASKS)
    print()
    for k in sorted(hits):
        print(f"  recall@{k}: {hits[k]}/{total}")
    print("\n  recall@3 is the number that matters: it is the ceiling on any "
          "design\n  that shows a small model three candidates.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
