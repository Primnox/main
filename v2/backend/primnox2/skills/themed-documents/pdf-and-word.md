# PDF, Word, and a matching chart

Same rules as a deck: run it with `run_python`, write to the current directory
with a plain filename, and `print()` the result of `save()` so you can see the
file was actually written.

## PDF

    from primnox_docs import Report
    r = Report('heat.pdf', theme='paper', title='Urban Heat Islands',
               subtitle='A one-page briefing')
    r.heading('What causes them')
    r.text('Dense construction stores solar radiation and releases it after sunset.')
    r.bullets(['Asphalt absorbs heat', 'Fewer trees means less cooling'])
    r.table([['Surface', 'Peak temp'], ['Asphalt', '60 C'], ['Grass', '32 C']])
    print(r.save())

`title` `heading` `text` `bullets` `table` — and `table` takes a list of rows,
each row a list, the first row being the header.

## Word

    from primnox_docs import Doc
    w = Doc('notes.docx', theme='sand', title='Field Notes')
    w.heading('Observations')
    w.text('The canopy dropped ambient temperature by four degrees.')
    w.bullets(['Measured at noon', 'Repeated over five days'])
    print(w.save())

`title` `heading` `text` `bullets`. A Word document has no table method — if the
content is tabular, either build a deck with `Deck.table` or a PDF with
`Report.table`.

## A chart that matches the document

`chart_style` returns matplotlib rcParams for any of the themes, so a figure
dropped into a `paper` report is not a default-blue matplotlib chart on a cream
page.

    import matplotlib
    matplotlib.use('Agg')
    from primnox_docs import chart_style
    matplotlib.rcParams.update(chart_style('midnight'))
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots()
    ax.bar(['A', 'B', 'C'], [3, 7, 5])
    ax.set_title('Counts'); ax.set_xlabel('Group'); ax.set_ylabel('Count')
    fig.savefig('counts.png', dpi=150, bbox_inches='tight')

`matplotlib.use('Agg')` comes before the pyplot import. There is no display in
the sandbox, and the default backend will fail looking for one.

For a chart *inside* a deck, do not do this at all — `Deck.chart` produces a
native, editable PowerPoint chart, which a picture can never be.
