---
name: interactive-apps
description: building a small app, page or diagram the user keeps
triggers: build an app, web app, small app, single-file, calculator, dashboard, simulator, prototype, mockup, widget, tool that, game, workspace, react component, html page, javascript app, write a script, script that, flowchart, diagram, mermaid
---

Code the user keeps goes in a workspace. It is versioned, it survives the chat,
and it shows in the rail beside the conversation:

    <tool name="create_workspace">{"kind": "html", "title": "Tip calculator",
      "files": {"index.html": "<!doctype html>…"}}</tool>

`kind` is one of `react` `python` `markdown` `html` `notebook` `doc` `shell`.
Editing later takes `update_workspace` with the `workspace_id` and **only the
files that changed** — the rest carry forward on their own.

## A workspace is storage, not a computer

Nothing in it runs. Creating one holds text and returns a version number, which
is easy to mistake for having built something — measured: asked for a deck, the
model wrote correct code, filed it in a workspace, and reported the deck as
created. No file existed.

So decide which of these you were actually asked for:

- **Source the user will run themselves** — a script, a component, a page.
  A workspace is right, and the job is done when it is stored.
- **Something to look at or open now** — a document, a table, a chart, a
  diagram. A workspace cannot deliver it. Produce a real file with `run_python`
  instead; files a script writes become assets with a download, and `.pptx`,
  `.xlsx`, `.pdf`, `.docx` and images all open in the app's own viewer.
- **A picture of how something works** — put a ```mermaid fence in your reply.
  It renders as a live, explorable flowchart, no workspace involved.

Never store `.pdf`, `.pptx`, `.xlsx` or `.png` in a workspace. Those are
binaries; text saved under that name is a broken file, not a document.

## What the code has to survive

There is no build step, no package manager, and no network — not when you write
it, and not when the user opens it. `npm install`, a CDN `<script src>` and an
`import` from node_modules all fail.

Write one self-contained file. Inline the CSS and the JavaScript, keep the
whole thing under a single `index.html`, and use no dependency the browser does
not already have. A React `kind` means the file is JSX the user can drop into
their own build — not something this app will compile.

A whole one, as the tool actually takes it — one JSON object, the file content
as one string:

    <tool name="create_workspace">
    {"kind": "html", "title": "Tip calculator", "files": {"index.html":
     "<!doctype html><meta charset=utf-8><title>Tip</title><style>body{font:16px system-ui;margin:2rem}</style><input id=bill type=number><output id=out></output><script>bill.oninput=()=>out.value=(bill.value*0.15).toFixed(2)</script>"}}
    </tool>

## Before you hand it over

If the logic can be checked, check it. A pure function is worth ten lines of
`run_python` proving it returns what you claim; a rounding rule you asserted and
never ran is the one that is wrong.

Say where it went and what it is: the title, the version, and the one sentence
of what it does. "Created a workspace" tells the user nothing they can act on.
