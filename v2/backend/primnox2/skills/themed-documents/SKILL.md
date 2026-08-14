---
name: themed-documents
description: making a PDF, slide deck, Word document or styled chart
triggers: pdf, deck, slide, presentation, powerpoint, pptx, docx, word document, report, chart, graph, plot, document, write-up, briefing
---

**Run this code with `run_python`.** Saving it to a workspace does not execute
it, and a document nobody ran does not exist — measured: a deck was reported as
"created successfully" when the script had only been filed away.

Use `primnox_docs` rather than raw python-pptx, reportlab or python-docx. It is
already in the sandbox, needs no install, and produces styled output in a few
lines. Writing the colours and geometry by hand takes forty lines and usually
goes wrong.

Themes — these are the exact names to pass. `theme='light'` is not one of them;
`light` is a category, `paper` is a theme:

    dark   signature · void · carbon · midnight · ember · phosphor
    light  paper · clinical · sand · mono

Pick one that suits the subject unless the user names it.

Slide deck. Fifteen layouts, one call each — vary them, because fifteen slides
of bullets is not a deck:

    from primnox_docs import Deck
    d = Deck('rings.pptx', theme='phosphor', title='The Rings of Saturn',
             subtitle='Structure and origin', footer='Cassini review')

    d.section('Composition', 'What they are made of', number='01')
    d.bullets('Materials', ['Water ice', 'Rock and dust', 'Metres across'])
    d.kpi('At a glance', [('Width', '282,000 km', 'A to F'),
                          ('Thickness', '10 m', 'mostly'),
                          ('Age', '100 Myr', 'contested')])
    d.bento('Divisions', [('Cassini', '4,800 km', 'A/B gap'),
                          ('Encke', '325 km', 'in A')])
    d.two_column('Two theories', ['A shattered moon'], ['Captured comet'],
                 left_title='Disruption', right_title='Capture')
    d.compare('Before and after', 'Voyager', ['Coarse'], 'Cassini', ['Fine'])
    d.timeline('Missions', [('1979', 'Pioneer 11'), ('1981', 'Voyager 2'),
                            ('2004', 'Cassini')])
    d.process('How we measured', ['Occultation', 'Imaging', 'Modelling'])
    d.table('Ring densities', [['Ring', 'Optical depth'], ['A', '0.5'], ['B', '1.2']])
    d.chart('Particle size', ['1 cm', '10 cm', '1 m'], {'Share': (52, 31, 17)},
            kind='bar')
    d.matrix('Assessment', [('Strengths', ['Well imaged']),
                            ('Unknowns', ['Age'])])
    d.quote('The rings are a laboratory for accretion.', 'Cuzzi')
    d.code('Orbital period', 'T = 2 * pi * sqrt(a**3 / (G * M))', caption='Kepler')
    d.appendix('Reference', [('Ring A', '122,170 km'), ('Ring B', '92,000 km')])
    d.save()

Layouts: `hero` `section` `bullets` `two_column` `compare` `bento` `kpi`
`timeline` `process` `table` `chart` `code` `quote` `matrix` `appendix`.
(`cover` and `slide` still work — they are `hero` and `bullets`.)

Chart kinds: `bar` `hbar` `line` `area` `pie` `doughnut` `scatter`. Charts are
native and editable in PowerPoint, so never render one to PNG and paste it in.

To match a brand or a brief that names its own colours, pass a palette instead
of — or on top of — a theme:

    d = Deck('q4.pptx', palette={'bg': '#0B1220', 'text': '#F8FAFC',
                                 'primary': '#22D3EE', 'accent': '#A3E635',
                                 'muted': '#94A3B8'})

PDF:

    from primnox_docs import Report
    r = Report('heat.pdf', theme='paper', title='Urban Heat Islands',
               subtitle='A one-page briefing')
    r.heading('What causes them')
    r.text('Dense construction stores solar radiation and releases it after sunset.')
    r.bullets(['Asphalt absorbs heat', 'Fewer trees means less cooling'])
    r.table([['Surface', 'Peak temp'], ['Asphalt', '60 C'], ['Grass', '32 C']])
    r.save()

Word document:

    from primnox_docs import Doc
    w = Doc('notes.docx', theme='sand', title='Field Notes')
    w.heading('Observations')
    w.text('The canopy dropped ambient temperature by four degrees.')
    w.bullets(['Measured at noon', 'Repeated over five days'])
    w.save()

Chart, matching the document it belongs to:

    import matplotlib
    matplotlib.use('Agg')
    from primnox_docs import chart_style
    matplotlib.rcParams.update(chart_style('midnight'))
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots()
    ax.bar(['A', 'B', 'C'], [3, 7, 5])
    ax.set_title('Counts'); ax.set_xlabel('Group'); ax.set_ylabel('Count')
    fig.savefig('counts.png', dpi=150, bbox_inches='tight')

Rules that matter:

- Write to the current directory with a plain filename. Never an absolute path.
- Every method returns the object, so calls chain; `save()` returns the filename.
- An unknown theme name falls back to a default rather than failing, but check
  the spelling — a silent fallback means the user does not get what they asked
  for.
- Put real content in it. A deck of empty headings is not a deck.
- Geometry is handled for you: everything lands on an 8-point grid, headings
  shrink to fit but never below 16pt, and a table longer than 11 rows becomes a
  second slide rather than shrinking. Do not pass sizes or coordinates.
