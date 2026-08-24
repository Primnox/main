"""Knowledge Service — V2.2.

The graph is built BEFORE the user asks, in the background, and the model
queries it rather than generating it. That inversion is the point: a 1.5B model
can use a rich graph it could never have built.

Extraction is Graphify's (Apache-2.0, `graphifyy` on PyPI) — deterministic
tree-sitter AST parsing, zero LLM calls. This package owns the store, the
import, and the retrieval surface; it does not own extraction, and should not
grow its own extractor.

  graph.py     the store over the knowledge_* tables
  importer.py  Graphify extraction -> those tables
  service.py   the `memory.graph_build` job
  live.py      the per-conversation ephemeral graph (ours, not Graphify's)

Submodules are NOT imported here. `chat.turns` imports `live`, and the kernel
scheduler imports `chat.turns`, so eagerly importing `service` (which registers
a job kind against the scheduler) closes a cycle: scheduler -> turns ->
knowledge -> service -> scheduler. It survives in a warm process where the
scheduler is already loaded and fails only in a cold one, which made it a crash
that appeared exclusively in the chaos test's child process.

Import the submodule you need directly, as the rest of the codebase does with
`assets` and `sandbox`.
"""
