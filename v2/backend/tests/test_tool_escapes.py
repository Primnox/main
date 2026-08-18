"""Escape decoding in the tool-call salvage path.

`_salvage_single_value` recovers the payload from a `{"code": "…"}` whose
quoting the model broke. Its escape decoding used sequential `str.replace`
calls, which cannot be correct: each pass reads the output of the one before,
so `\\n` was decoded before `\\\\`, and any backslash pair whose second half
happened to be `n`, `t` or `r` was torn apart mid-sequence.

The victim is Windows paths, which is the most likely thing in this app's
generated code to carry backslashes at all.
"""
from __future__ import annotations

from primnox2.tools.runtime import _decode_escapes, parse_call

BS = "\\"          # one literal backslash, spelled out so the tests are readable


def test_escaped_backslash_before_t_is_not_a_tab():
    """`C:\\\\temp` is a path, not `C:<TAB>emp`.

    The old order decoded the `\\t` inside an escaped backslash first, so this
    reached the sandbox with a tab where a separator belonged.
    """
    encoded = f'open("C:{BS}{BS}temp{BS}{BS}x.txt")'
    assert _decode_escapes(encoded) == f'open("C:{BS}temp{BS}x.txt")'
    assert "\t" not in _decode_escapes(encoded)


def test_escaped_backslash_before_n_is_not_a_newline():
    encoded = f'p = "C:{BS}{BS}new{BS}{BS}dir"'
    decoded = _decode_escapes(encoded)
    assert decoded == f'p = "C:{BS}new{BS}dir"'
    assert "\n" not in decoded


def test_a_real_newline_escape_still_decodes():
    """The case the sequential version got right must stay right — two
    statements separated by `\\n` have to arrive on separate lines, or Python
    sees `a = 1b = 2` and raises SyntaxError."""
    assert _decode_escapes(f"a = 1{BS}nb = 2") == "a = 1\nb = 2"


def test_an_unknown_escape_keeps_its_backslash():
    """`\\d` is a regex class. Dropping the backslash would silently turn a
    working pattern into one that matches the letter d."""
    assert _decode_escapes(f're.compile("{BS}d+")') == f're.compile("{BS}d+")'


def test_a_trailing_backslash_is_not_dropped():
    """A line-continuation at the end of the payload must survive rather than
    fall off the end of the scan."""
    assert _decode_escapes(f"x = 1 + {BS}") == f"x = 1 + {BS}"


def test_salvage_recovers_code_from_broken_json():
    """End to end: the shape this path exists for. A model closes the JSON
    badly, and the code still has to arrive intact and runnable."""
    body = f'{{"code": "import os{BS}nprint(os.sep)"'      # no closing brace
    call = parse_call(f'<tool name="run_python">{body}</tool>')
    assert call is not None
    assert call["arguments"]["code"] == "import os\nprint(os.sep)"


def test_salvage_keeps_a_windows_path_runnable():
    body = f'{{"code": "open(r{BS}"C:{BS}{BS}tmp{BS}{BS}a.txt{BS}")"'
    call = parse_call(f'<tool name="run_python">{body}</tool>')
    assert call is not None
    code = call["arguments"]["code"]
    assert "\t" not in code, f"a tab was fabricated inside a path: {code!r}"
    assert f"C:{BS}tmp{BS}a.txt" in code
