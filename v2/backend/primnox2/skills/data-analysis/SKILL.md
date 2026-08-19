---
name: data-analysis
description: computing numbers from a CSV, table or spreadsheet
triggers: csv, spreadsheet, excel, xlsx, dataset, data set, dataframe, pandas, statistics, correlation, median, tabular data, trend, these numbers, each column, per row
---

Compute it with `run_python`. Do not do arithmetic in your head and report the
answer — measured on a 7B: asked for `137 * 449` it replied 61,013 for a value
that is 61,513, having run nothing.

The smallest version that works:

    rows = [('Jan', 120), ('Feb', 145), ('Mar', 98)]
    total = sum(v for _, v in rows)
    print('total', total)
    print('mean', total / len(rows))
    print('best', max(rows, key=lambda r: r[1]))

Plain Python is enough for a few dozen rows and cannot go wrong the way a
dataframe can. Reach for pandas when there are columns to join, group or pivot:

    import pandas as pd
    df = pd.DataFrame(rows, columns=['month', 'sales'])
    print(df.describe())
    print(df.groupby('month')['sales'].sum().head(20))

## Getting the data into the script

The sandbox is offline and sees only its own directory. It cannot download a
file, cannot `pip install`, and cannot open anything on the user's machine — so
`pd.read_csv('/Users/…/sales.csv')` fails every time.

There are exactly three ways data arrives:

1. The user pasted it into the chat. Put it in the script as a literal.
2. It was uploaded as a document. `search_assets` finds the text, `read_asset`
   returns it in full; paste what you need into the script.
3. You generated it in an earlier step of the same script.

For a CSV that reached you as text, parse the text you already have:

    import csv, io
    text = """month,sales\nJan,120\nFeb,145"""
    rows = list(csv.DictReader(io.StringIO(text)))
    print(len(rows), 'rows', rows[0])

## Printing

Only what you `print()` comes back — a bare expression on the last line shows
nothing, and a clean exit with no output reads as success to everyone reading
it. Roughly 2,000 characters come back inline and the rest is stored as an
asset, so print the answer, not the whole table: `df.head(10)`,
`df.describe()`, a total, a count. Never state a number you have not seen in
the output.

Check your own result before reporting it. An empty dataframe, a column of
`NaN` and a group-by that silently dropped rows all print without complaint —
`print(len(df), df.isna().sum().sum())` costs one line and catches all three.

## Giving the numbers back as a file

Files the script writes become openable in the app. An `.xlsx` renders as a
browsable table there, so it is the better deliverable when the answer is a
table rather than one number:

    df.to_excel('sales.xlsx', index=False)

For a chart, or a deck or PDF built from the numbers, ask for the
`themed-documents` skill — it has the builders and the matching palettes.

Which libraries are actually installed is listed in your system prompt; pandas,
numpy, matplotlib, openpyxl and xlsxwriter are normally among them. Do not
import anything that is not on that list — there is no network to install it
from.
