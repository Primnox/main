"""Strip secrets out of commands before they're shown to the user.

The activity panel shows the actual commands a skill runs — that
transparency is the point, it's what makes "the AI is executing things on
my machine" understandable instead of mysterious. But a command line is
exactly where credentials end up (`--api-key sk-...`, `-H "Authorization:
Bearer ..."`), and the sandbox is handed the user's real keys.

So redaction happens here, on the way OUT to the display layer only. The
executed command keeps its real values; the broadcast copy never carries
them. Doing it the other way round — redacting at render time in the
frontend — would mean the secret had already crossed the websocket.

Deliberately conservative about what counts as a secret: over-redaction
turns a useful log into a wall of dots, so patterns are anchored to
recognised credential flags, headers, env-assignments and key prefixes
rather than "anything that looks random".
"""
import re

MASK = "•" * 8

# Value shapes distinctive enough to redact wherever they appear, since a
# bare key in a command is still a leaked key even with no flag in front.
_KEY_SHAPES = re.compile(
    r"""(
        sk-ant-[A-Za-z0-9_\-]{8,}
      | sk-[A-Za-z0-9_\-]{16,}
      | gsk_[A-Za-z0-9_\-]{16,}
      | AIza[A-Za-z0-9_\-]{20,}
      | ghp_[A-Za-z0-9]{16,}
      | xox[baprs]-[A-Za-z0-9\-]{10,}
    )""",
    re.VERBOSE,
)

_SENSITIVE_WORD = r"(?:api[_-]?key|apikey|secret|token|password|passwd|pwd|auth|credential)"

# `--api-key VALUE` / `--api-key=VALUE` / `-k VALUE` is not included: a
# single-letter flag is too ambiguous to guess at.
_FLAG_VALUE = re.compile(
    rf"(--{_SENSITIVE_WORD}[a-z\-]*[=\s]+)(\"[^\"]*\"|'[^']*'|\S+)",
    re.IGNORECASE,
)

# `Authorization: Bearer VALUE`, `x-api-key: VALUE` — inside quotes or not.
_HEADER_VALUE = re.compile(
    rf"((?:authorization|x-{_SENSITIVE_WORD})\s*:\s*(?:bearer\s+|basic\s+)?)([^\"'\s][^\"']*)",
    re.IGNORECASE,
)

# `API_KEY=VALUE` as an env assignment. Requires the name to be
# assignment-shaped so ordinary prose with an `=` isn't caught.
_ENV_ASSIGNMENT = re.compile(
    rf"\b([A-Z0-9_]*{_SENSITIVE_WORD}[A-Z0-9_]*\s*=\s*)(\"[^\"]*\"|'[^']*'|\S+)",
    re.IGNORECASE,
)


def redact_command(command: str) -> str:
    """`command` with any credential-looking value replaced by a fixed mask.

    Idempotent — running it over already-redacted text leaves the mask
    alone, so a command can pass through more than one layer safely.
    """
    if not command:
        return command

    def _mask_value(match: re.Match) -> str:
        return f"{match.group(1)}{MASK}"

    redacted = _FLAG_VALUE.sub(_mask_value, command)
    redacted = _HEADER_VALUE.sub(_mask_value, redacted)
    redacted = _ENV_ASSIGNMENT.sub(_mask_value, redacted)
    redacted = _KEY_SHAPES.sub(MASK, redacted)
    return redacted


def redact_text(text: str, extra_secrets: tuple = ()) -> str:
    """Same masking for free-form output (stdout/stderr shown in the log).

    `extra_secrets` lets a caller pass the literal values it knows are
    sensitive — the user's configured API keys — so a key echoed back by a
    program that formats it in a shape none of the patterns anticipate is
    still caught. Short values are ignored: masking a 3-character "secret"
    would shred unrelated text.
    """
    if not text:
        return text
    redacted = redact_command(text)
    for secret in extra_secrets:
        if secret and len(str(secret)) >= 8:
            redacted = redacted.replace(str(secret), MASK)
    return redacted
