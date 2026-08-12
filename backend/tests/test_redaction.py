"""Tests for redaction.py — masking secrets out of commands before the
activity panel shows them to the user.

Two failure modes matter and they pull against each other:
  - under-redaction leaks a real credential over the websocket
  - over-redaction turns the log into dots and defeats the transparency
    the panel exists for

So there are as many "leave this alone" tests here as "mask this" ones.
"""
from redaction import MASK, redact_command, redact_text


class TestFlagValues:
    def test_masks_space_separated_api_key_flag(self):
        out = redact_command("python upload.py --api-key sk-live-abcdefghijklmnop")
        assert "sk-live-abcdefghijklmnop" not in out
        assert MASK in out
        assert out.startswith("python upload.py --api-key ")

    def test_masks_equals_form(self):
        out = redact_command("node build.js --token=abc123xyz789")
        assert "abc123xyz789" not in out

    def test_masks_quoted_value(self):
        out = redact_command('curl --secret "hunter2 with spaces"')
        assert "hunter2" not in out

    def test_masks_password_and_credential_variants(self):
        for flag in ("--password", "--passwd", "--credential", "--apikey"):
            out = redact_command(f"tool {flag} supersecretvalue")
            assert "supersecretvalue" not in out, flag

    def test_leaves_innocuous_flags_alone(self):
        # --keyword / --keyfile-ish flags share a prefix with --key but are
        # not credentials; masking them would be pure noise.
        cmd = "python analyze.py --keyword revenue --output report.json"
        assert redact_command(cmd) == cmd


class TestHeaders:
    def test_masks_bearer_token(self):
        out = redact_command('curl -H "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9"')
        assert "eyJhbGciOiJIUzI1NiJ9" not in out

    def test_masks_x_api_key_header(self):
        out = redact_command('curl -H "x-api-key: abcdef123456789"')
        assert "abcdef123456789" not in out


class TestEnvAssignments:
    def test_masks_env_style_assignment(self):
        out = redact_command("OPENAI_API_KEY=sk-abc123def456ghi789 python run.py")
        assert "sk-abc123def456ghi789" not in out

    def test_leaves_ordinary_assignment_alone(self):
        cmd = "python train.py --epochs=30 --batch_size=64"
        assert redact_command(cmd) == cmd


class TestKeyShapes:
    def test_masks_bare_provider_keys_with_no_flag(self):
        # A key pasted straight into a command is still a leaked key.
        for key in (
            "sk-ant-api03-abcdefghijklmnop",
            "gsk_abcdefghijklmnopqrstuvwx",
            "AIzaSyA1234567890abcdefghijklmnopqrs",
            "ghp_abcdefghijklmnopqrstuvwxyz",
            "xoxb-1234567890-abcdefghij",
        ):
            out = redact_command(f"echo {key}")
            assert key not in out, key
            assert MASK in out

    def test_does_not_mask_ordinary_words(self):
        cmd = "python skills/analyze.py --input notes.txt"
        assert redact_command(cmd) == cmd


class TestIdempotenceAndEdges:
    def test_running_twice_is_stable(self):
        once = redact_command("run --api-key sk-abcdefghijklmnopqrst")
        assert redact_command(once) == once

    def test_empty_and_none_safe(self):
        assert redact_command("") == ""
        assert redact_text("") == ""

    def test_plain_command_is_untouched(self):
        cmd = "node build.js"
        assert redact_command(cmd) == cmd


class TestRedactText:
    def test_masks_known_secret_values_echoed_in_output(self):
        # A program that prints the key back in a shape no pattern
        # anticipates is still caught, because we know the literal value.
        out = redact_text("connecting with key MyC0nfiguredKey123", ("MyC0nfiguredKey123",))
        assert "MyC0nfiguredKey123" not in out

    def test_ignores_short_extra_secrets(self):
        # Masking a 3-char "secret" would shred unrelated text.
        text = "the cat sat on the mat"
        assert redact_text(text, ("cat",)) == text

    def test_still_applies_pattern_rules(self):
        out = redact_text("failed: sk-ant-api03-abcdefghijklmnop rejected")
        assert "sk-ant-api03-abcdefghijklmnop" not in out
