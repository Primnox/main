"""Tests for the code-aware error detection in screen_reader.py.

`_is_code_error` replaced a bare 5-keyword substring match that fired on any
UI text containing "failed" or "expected" — including browser 404s and
deprecation notices. `fingerprint` collapses "the same error, different line
number" down to one identity so error-streak tracking doesn't re-fire on
every superficial variation.
"""

from screen_reader import _is_code_error, fingerprint, _find_errors, _error_records


class TestIsCodeError:
    def test_typescript_diagnostic(self):
        assert _is_code_error("TS2304: Cannot find name 'foo'.") is True

    def test_python_traceback_header(self):
        assert _is_code_error("Traceback (most recent call last):") is True

    def test_python_traceback_frame(self):
        assert _is_code_error('  File "server.py", line 42, in run') is True

    def test_named_exception(self):
        assert _is_code_error("NameError: name x is not defined") is True

    def test_test_runner_summary(self):
        assert _is_code_error("3 failed, 12 passed") is True

    def test_browser_404_is_not_a_code_error(self):
        assert _is_code_error("Failed to load page (404)") is False

    def test_deprecation_warning_is_not_a_code_error(self):
        assert _is_code_error("DeprecationWarning: something old") is False

    def test_network_noise_is_not_a_code_error(self):
        assert _is_code_error("ERR_INTERNET_DISCONNECTED") is False

    def test_bare_keyword_too_short(self):
        assert _is_code_error("failed") is False

    def test_find_errors_filters_a_mixed_batch(self):
        texts = [
            "Traceback (most recent call last):",
            "Failed to load page (404)",
            "NameError: name x is not defined",
            "click here to continue",
        ]
        assert _find_errors(texts) == [
            "Traceback (most recent call last):",
            "NameError: name x is not defined",
        ]


class TestFingerprint:
    def test_stable_across_line_numbers(self):
        f1 = fingerprint("TS2304: Cannot find name at file.ts:42:10")
        f2 = fingerprint("TS2304: Cannot find name at file.ts:99:3")
        assert f1 == f2

    def test_stable_across_absolute_paths(self):
        f1 = fingerprint(r"Error in C:\Users\alice\proj\server.py:12")
        f2 = fingerprint(r"Error in /home/bob/proj/server.py:99")
        assert f1 == f2

    def test_different_errors_differ(self):
        f1 = fingerprint("NameError: name x is not defined")
        f2 = fingerprint("TypeError: cannot read property of undefined")
        assert f1 != f2

    def test_error_records_carry_fingerprint(self):
        records = _error_records(["NameError: name x is not defined"])
        assert records == [{
            "text": "NameError: name x is not defined",
            "fingerprint": fingerprint("NameError: name x is not defined"),
        }]
