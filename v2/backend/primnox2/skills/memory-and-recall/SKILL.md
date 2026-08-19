---
name: memory-and-recall
description: saving or finding what is known about the user, this chat, or the corpus
triggers: remember, remind me, don't forget, forget that, what do you know about, my notes, my preferences, knowledge graph, indexed code, last time, we discussed, earlier chat, previous conversation
---

Four stores, and picking the wrong one is the usual failure:

| The question | The tool |
|---|---|
| Something durable about *the user* | `remember` / `recall_memory` |
| What *this chat* already settled | `recall_conversation` |
| What the *indexed code and documents* say | `graph_query` |
| What an *uploaded file* says | `search_assets`, then `read_asset` |

## Writing a memory

    <tool name="remember">{"text": "Aniketh runs the backend on a Windows
      machine with no admin rights.", "category": "work",
      "asked_by_user": false}</tool>

`category` is `personal`, `work`, `project` or `session`. Set
`asked_by_user` true only when they actually asked — the Memory tab shows which
facts they chose and which you inferred, so a wrong guess can be found and
removed rather than quietly becoming true.

Write it as a standalone sentence. A memory is replayed into later chats with
none of this conversation attached, so "he prefers the second one" is worthless
six weeks from now. Name the subject, name the thing.

Save a fact when it is durable and about **them** — a preference, a constraint,
a name, how they like to work, a project they keep returning to. Do not save the
task at hand, a number you just computed, or anything you can recover by
reading the code. A store full of task residue makes the useful facts harder to
reach.

Two refusals to expect: an incognito chat saves nothing, by design, and a fact
close enough to one already held comes back as "already known" rather than
being duplicated. Both are successes. Do not retry them with reworded text.

## Reading back

Memory is already injected into every prompt, but the injection is capped —
`recall_memory` is how you reach an older fact past that cap. Call it before
saying you do not know something about the user.

    <tool name="recall_memory">{"query": "editor"}</tool>

`recall_conversation` answers a different question: what *this* conversation has
established. "The option we picked earlier", "that file from before", "what did
we decide" — those are its job, not memory's. Omitting the query returns the
whole working set of this chat.

## The knowledge graph

`graph_query` searches indexed code and documents and returns nodes with
`file:line` citations rather than file contents — far cheaper than reading a
file to find out whether it is the right one.

    <tool name="graph_query">{"question": "ingest_bytes", "depth": 2}</tool>

`depth` is 1–4 hops, default 2. `relation` narrows to one edge kind — `calls`,
`imports`, `rationale_for` — and `rationale_for` is the one that finds why a
thing was built the way it was, which is rarely in the code itself. Widen
`token_budget` past its 2,000 only when a first pass came back thin.

Read the citation, then open the file if you still need the body. And when the
graph returns nothing, say so — an unindexed corpus looks exactly like an
absent fact, and guessing at that point is how a confident wrong answer gets
written.
