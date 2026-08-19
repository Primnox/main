# The other slide layouts

Fifteen in total, one call each. Vary them — fifteen slides of bullets is not a
deck. Every method returns the deck, so calls chain if you prefer.

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
    print(d.save())

Layouts: `hero` `section` `bullets` `two_column` `compare` `bento` `kpi`
`timeline` `process` `table` `chart` `code` `quote` `matrix` `appendix`.
(`cover` and `slide` still work — they are `hero` and `bullets`.)

## The shape each one expects

`bullets` and `process` take plain strings. Everything else takes tuples (pairs),
and this is the one mistake that produces a broken deck without producing an error:

    d.kpi('Metrics', ['Revenue', 'Users'])                         # silent garbage
    d.kpi('Metrics', [('Revenue', '£4.2m'), ('Users', '18,000')])   # correct

Measured: the first line made two cards reading `e | R | v` and `s | U | e` —
Python unpacked each string into its characters — and the deck saved with no
error anywhere. `kpi`, `bento`, `timeline` and `appendix` take `(label, value)`
or `(label, value, note)`. `matrix` takes `(heading, [lines])`. `table` takes a
list of rows, each row itself a list, the first being the header.

Limits are handled for you: `kpi` shows up to 8 cards, `bento` and `timeline`
and `process` up to 6, and a table longer than 11 rows becomes a second slide
rather than shrinking below 16pt. Do not pass sizes or coordinates.

## Charts

    d.chart('Revenue', ['Q1', 'Q2', 'Q3'], {'2024': (31, 40, 52),
                                            '2025': (44, 49, 61)}, kind='line')

Kinds: `bar` `hbar` `line` `area` `pie` `doughnut` `scatter`. These are native,
editable PowerPoint charts — never render one to PNG and paste the picture in.
More than one series adds a legend automatically.

## A brand's own colours

To match a brief that names its colours, pass a palette instead of — or on top
of — a theme. Keys given override the theme; the rest carry over.

    d = Deck('q4.pptx', palette={'bg': '#0B1220', 'text': '#F8FAFC',
                                 'primary': '#22D3EE', 'accent': '#A3E635',
                                 'muted': '#94A3B8'})
