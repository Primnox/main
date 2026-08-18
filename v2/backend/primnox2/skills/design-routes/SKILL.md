---
name: design-routes
description: composing slides by routing through a design system, not writing code
triggers: design a presentation, create a slideshow, build a slide deck, make slides, compose slides, slide layout, presentation layout, slide composition
---

Reply with a JSON object only. Do not write the slides out.

Fill in this shape and send it:

```json
{
  "slide_type": "content",
  "title": "Water Cycle",
  "bullets": [
    "Evaporation: heat turns water to vapour",
    "Condensation: cold air cools the vapour",
    "Precipitation: water falls as rain"
  ],
  "density": "medium",
  "theme": "light",
  "notes": ""
}
```

That creates one slide. Repeat in a loop for each slide you want.

`slide_type` choices (pick one per slide):
- `hero` — opening slide, just title and subtitle
- `content` — title + bullets (default)
- `two_column` — split left/right
- `kpi` — key metrics as cards
- `chart` — a chart with title
- `process` — numbered steps
- `timeline` — events with dates
- `comparison` — before/after
- `end` — closing slide

Fill in the fields that match your `slide_type`:
- `hero` needs `title`, `subtitle`
- `content` needs `title`, `bullets` (list of strings)
- `two_column` needs `title`, `left_column`, `right_column`
- `kpi` needs `title`, `metrics` (list of {"label": "...", "value": "..."})
- `chart` needs `title`, `chart_type` (bar/line/pie), `chart_data`
- `process` needs `title`, `items` (list of strings)
- `timeline` needs `title`, `items` (list of strings)
- `comparison` needs `title`, `left_column`, `right_column`

`density` ("light", "medium", "heavy") sets whitespace.
`theme` ("light", "dark", "brand") sets colors.
Leave unused fields empty or omit them.
