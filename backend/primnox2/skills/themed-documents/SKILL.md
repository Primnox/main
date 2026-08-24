---
name: themed-documents
description: making a PDF, slide deck, Word document or styled chart
triggers: pdf, deck, slide, presentation, powerpoint, pptx, docx, word document, report, chart, graph, plot, document, write-up, briefing
---

Your reply must begin with `<tool name="run_python">` and contain only the code.

Copy this, change the words, send it:

    from primnox_docs import Deck
    d = Deck('water.pptx', theme='midnight', title='The Water Cycle')
    d.bullets('Evaporation', ['The sun heats the sea', 'Water becomes vapour'])
    d.bullets('Condensation', ['Vapour cools', 'Cloud forms'])
    d.bullets('Precipitation', ['It rains', 'The water returns'])
    print(d.save())

`title=` opens the deck. Each `bullets()` is one slide. `print(d.save())` writes
the file — nothing is created unless printed.

Themes: `midnight` `signature` `void` `carbon` `ember` `phosphor` (dark),
`paper` `clinical` `sand` `mono` (light). `'light'` and `'dark'` also work.

A plain filename, never an absolute path. For more layouts, themes, custom
palettes, PDF, Word, or matplotlib charts, `read_skill` fetches this skill's
own files: `layouts.md` (kpi, table, chart, timeline, compare, quote, bento,
matrix) and `pdf-and-word.md` (Report, Doc, chart_style).
