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


# ── A block that opened and never closed ────────────────────────────────────
#
# Measured on Qwen3.5-0.8B: asked to multiply two numbers it replied with
# exactly the form the system prompt teaches — the opening tag and a fenced
# python block — and stopped, 92 characters, no `</tool>`. Three of its ten
# answers failed that way, each naming the right tool and carrying runnable
# code. Accepting them took it from 2/10 to 3/10 on the text protocol.
#
# The line this must not cross is `test_l2_integration.py::
# test_an_unfinished_tool_block_fails_rather_than_replying_blank`, which
# exists because qwen2.5:7b produced blocks truncated MID-JSON and a turn that
# runs half a call is worse than one that fails with a Retry. The two look
# alike until you read the body, so the body is what decides.

FENCE = "`" * 3


def test_a_finished_body_runs_even_without_the_closing_tag():
    call = parse_call(f'<tool name="run_python">\n{FENCE}python\nprint(1)\n{FENCE}')
    assert call is not None
    assert call["name"] == "run_python"
    assert call["arguments"]["code"] == "print(1)"


def test_complete_json_without_the_closing_tag_also_runs():
    call = parse_call('<tool name="run_python">{"code": "print(1)"}')
    assert call is not None
    assert call["arguments"]["code"] == "print(1)"


def test_a_body_truncated_mid_json_is_still_refused():
    """The case the integration test protects: a model cut off mid-generation.
    Running the beginning of something much larger is the failure mode."""
    assert parse_call('<tool name="run_python">{"code": "print(1)"') is None


def test_an_unclosed_fence_is_still_refused():
    """Same reasoning as truncated JSON — the fence never closed, so the model
    was still writing."""
    assert parse_call(f'<tool name="run_python">\n{FENCE}python\nprint(1)') is None


def test_a_bare_fence_never_becomes_a_tool_call():
    """`format_result` promises the user that a code fence written in a reply
    is shown to them rather than run. Nothing here may weaken that."""
    assert parse_call(f"{FENCE}python\nprint(1)\n{FENCE}") is None


def test_an_unregistered_name_is_not_a_tool_call():
    """The whole safety argument for the lenient shapes is that the opener
    carries a name the runtime actually has."""
    assert parse_call('<tool name="rm_rf_slash">{"code": "x"}') is None


def test_a_properly_closed_block_never_reaches_the_fallback():
    """The fallback is last. A well-formed reply must parse by the canonical
    path, unchanged."""
    call = parse_call('<tool name="run_python">{"code": "print(1)"}</tool>')
    assert call is not None and call["arguments"]["code"] == "print(1)"
