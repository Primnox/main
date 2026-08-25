"""The security fabric: trust boundary, secrets, permissions and audit.

Everything else in V2 persists something about the user's work, so this
module sits under all of it. Four responsibilities:

**The trust boundary.** Content from the user and the machine is trusted
input. Content from a web page, a PDF, an external repository or a model's
own output is *data* — it can be reasoned about, but it cannot issue
instructions and it cannot become a stated fact. That rule is enforced
structurally: :func:`memory_provenance_for` will not produce `stated`
provenance for an untrusted source, whatever the content says about itself.

**Credential isolation.** The model is not the credential vault. What
reaches a prompt is `cred_groq (available)`. The value itself is fetched
through :func:`resolve_credential`, which requires an explicit purpose, goes
to an injected resolver — V1's keyring/vault path — and is audited every
time. No secret is stored in this module.

**Permission checks.** Capability, then data sensitivity, then action, then
execute, then audit. Denials and confirmations are returned as decisions
with reasons, not raised, because a caller usually needs to explain the
refusal rather than crash on it.

**Audit.** Security-relevant actions are recorded, and ordinary debug logs
are not the place for sensitive content — :func:`redact` exists so that a
value cannot reach a log or a prompt by accident.

A note on BIP-39, which the architecture is explicit about: a mnemonic is a
recovery representation for key material. It is not the encryption layer,
and nothing here treats it as one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from v2 import ids, store
from v2.world_model import Provenance, ValidationError, project_id

try:  # pragma: no cover - logging is incidental to behaviour
    from logger import get_logger

    log = get_logger("v2.policy")
except Exception:  # pragma: no cover
    import logging

    log = logging.getLogger("v2.policy")


# ── Trust ────────────────────────────────────────────────────────────────────

# Sources that originate on the user's own machine, or from the user.
TRUSTED_SOURCES: set[str] = {"user", "os", "file", "git", "tool", "conversation"}

# Everything else: fetched pages, imported documents, third-party code, and
# the model's own output — which is a proposal, not an observation.
UNTRUSTED_SOURCES: set[str] = {"web", "external", "artifact", "model", "email", "clipboard"}

DATA_OPEN = "<untrusted_content>"
DATA_CLOSE = "</untrusted_content>"

# Heuristic markers of content trying to act as an instruction. This is a
# tripwire for logging and caution, not the defence: the defence is that
# untrusted content is delivered as data and can never become authority.
_INSTRUCTION_ATTEMPT = re.compile(
    r"ignore (all |any )?(previous|prior|above|earlier) (instructions|prompts?)"
    r"|disregard (your|the) (system )?(prompt|instructions)"
    r"|you are now\b|from now on,? you\b"
    r"|(reveal|print|repeat|output) (your|the) (system )?(prompt|instructions|rules)"
    r"|send (this|it|the .{0,20}) to https?://"
    r"|exfiltrate|curl https?://.{0,60}\$\{?"
    r"|do not tell the user",
    re.I,
)

# Secret-shaped strings. Matched by *shape*, so a value is caught even when
# nobody labelled it — which is the case that leaks.
_SECRET_PATTERNS: tuple[tuple[str, re.Pattern], ...] = (
    ("openai_key", re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}\b")),
    ("anthropic_key", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{16,}\b")),
    ("groq_key", re.compile(r"\bgsk_[A-Za-z0-9]{20,}\b")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("aws_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("google_key", re.compile(r"\bAIza[0-9A-Za-z_\-]{20,}\b")),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}\b")),
    ("bearer_token", re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{20,}\b")),
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("assigned_secret", re.compile(
        r"(?i)\b(api[_-]?key|secret|password|passphrase|token)\b\s*[:=]\s*['\"]?([^\s'\"]{8,})")),
)

REDACTION = "[redacted]"


@dataclass(frozen=True)
class Classification:
    """What a piece of content is allowed to do."""

    trusted: bool
    source: str
    instruction_attempt: bool = False

    @property
    def may_instruct(self) -> bool:
        """Only trusted content can direct behaviour."""
        return self.trusted


def classify(text: str, *, source: str) -> Classification:
    """Classify content by where it came from, not by what it claims."""
    trusted = source in TRUSTED_SOURCES
    attempt = bool(_INSTRUCTION_ATTEMPT.search(text or ""))
    if attempt and not trusted:
        log.warning("untrusted %s content contained instruction-shaped text; treating as data", source)
    return Classification(trusted=trusted, source=source, instruction_attempt=attempt)


def as_data(text: str, *, source: str, label: str | None = None) -> str:
    """Wrap untrusted content so it reads as quoted material, not direction.

    Trusted content passes through unchanged; there is no reason to make a
    user's own words look foreign.
    """
    if source in TRUSTED_SOURCES:
        return text
    header = f"{DATA_OPEN} source={source}" + (f" ref={label}" if label else "")
    return f"{header}\n{text}\n{DATA_CLOSE}"


def memory_provenance_for(source: str, *, stated: bool = False) -> Provenance:
    """Provenance an observation from `source` is allowed to claim.

    This is where "external content is data, not authority" stops being a
    convention. A web page cannot produce a `stated` fact even if the caller
    asks for one: the strongest provenance an untrusted source can earn is
    an inference, which is exactly what it is.
    """
    if source in UNTRUSTED_SOURCES:
        mapped = "artifact" if source in {"artifact", "email", "clipboard"} else "model"
        return Provenance(source=mapped, origin="inferred", confidence=0.4)
    if stated:
        return Provenance(source="user", origin="stated")
    return Provenance(source=source if source in {"os", "file", "git", "tool"} else "user",
                      origin="observed")


def redact(text: str) -> tuple[str, list[str]]:
    """Remove secret-shaped values, returning the text and what was found.

    Applied before content reaches a prompt or a log. Matching by shape
    rather than by label is the point: an unlabelled key pasted into a chat
    is the one that leaks.
    """
    if not text:
        return text, []
    found: list[str] = []
    cleaned = text
    for name, pattern in _SECRET_PATTERNS:
        def _replace(match: re.Match) -> str:
            found.append(name)
            if match.lastindex and match.lastindex >= 2:
                # Keep the assignment's left-hand side so the line still reads.
                return match.group(0).replace(match.group(2), REDACTION)
            return REDACTION

        cleaned = pattern.sub(_replace, cleaned)
    return cleaned, found


def contains_secret(text: str) -> bool:
    """True if the text looks like it contains a credential."""
    return bool(redact(text)[1])


# ── Permissions ──────────────────────────────────────────────────────────────

# Default stance per capability. "confirm" means the action is legitimate but
# needs the user in the loop; "deny" means it needs an explicit grant.
DEFAULT_POLICY: dict[str, str] = {
    "read_memory": "allow",
    "write_memory": "allow",
    "read_code": "allow",
    "search": "allow",
    "read_secret": "deny",
    "write_secret": "deny",
    "delete_memory": "confirm",
    "delete_project": "confirm",
    "execute_code": "confirm",
    "external_call": "allow",
    "external_model": "allow",
    "write_file": "confirm",
    "network": "confirm",
}

# Data at or above this sensitivity may not leave the machine.
LOCAL_ONLY_SENSITIVITY = "sensitive"


@dataclass(frozen=True)
class Decision:
    """The outcome of a permission check, with a reason worth showing."""

    allowed: bool
    reason: str
    requires_confirmation: bool = False
    capability: str = ""
    audit_id: str | None = None

    def __bool__(self) -> bool:
        return self.allowed


def check(
    capability: str,
    *,
    sensitivity: str = "normal",
    project: str | None = None,
    policy: dict[str, str] | None = None,
    granted: set[str] | None = None,
    external: bool = False,
    audit_detail: str | None = None,
) -> Decision:
    """Decide whether an action may proceed, and record the decision.

    Order matters and follows the architecture: capability first, then the
    sensitivity of the data involved, then whether the action leaves the
    machine — and every outcome, including the denials, is audited.
    """
    rules = {**DEFAULT_POLICY, **(policy or {})}
    stance = rules.get(capability)

    if stance is None:
        decision = Decision(False, f"unknown capability {capability!r}", capability=capability)
    elif capability in (granted or set()):
        decision = Decision(True, "explicitly granted for this session", capability=capability)
    elif stance == "deny":
        decision = Decision(False, f"{capability} requires an explicit grant", capability=capability)
    elif external and is_local_only(project):
        decision = Decision(
            False,
            f"{project or 'this project'} is marked local-only; external calls are blocked",
            capability=capability,
        )
    elif external and _at_least(sensitivity, LOCAL_ONLY_SENSITIVITY):
        decision = Decision(
            False,
            f"{sensitivity} data may not be sent to an external service",
            capability=capability,
        )
    elif stance == "confirm":
        decision = Decision(
            True, f"{capability} needs the user to confirm", requires_confirmation=True,
            capability=capability,
        )
    else:
        decision = Decision(True, "allowed by policy", capability=capability)

    audit_id = record(
        capability,
        outcome="allowed" if decision.allowed else "denied",
        detail=audit_detail or decision.reason,
        sensitivity=sensitivity,
        project=project,
    )
    return Decision(
        allowed=decision.allowed,
        reason=decision.reason,
        requires_confirmation=decision.requires_confirmation,
        capability=capability,
        audit_id=audit_id,
    )


def _at_least(sensitivity: str, threshold: str) -> bool:
    from v2.world_model import SENSITIVITY_LEVELS

    try:
        return SENSITIVITY_LEVELS.index(sensitivity) >= SENSITIVITY_LEVELS.index(threshold)
    except ValueError:
        return False


def set_local_only(project: str, *, local_only: bool = True) -> None:
    """Mark (or unmark) a project as local-only.

    Stored as a world-model fact so the policy travels with the project and
    is inspectable and correctable like any other belief, rather than living
    in a settings file nothing else can see.
    """
    from v2 import world_model

    world_model.record_fact(
        "local-only: no external model or network calls" if local_only
        else "external model calls are permitted",
        project=project,
        slot="privacy_policy",
        prov=world_model.USER_STATED,
        on_conflict="supersede",
    )


def is_local_only(project: str | None) -> bool:
    """Is this project restricted to on-device processing?"""
    if project is None:
        return False
    from v2 import world_model

    facts = world_model.current_facts(project=project, slot="privacy_policy", limit=1)
    return bool(facts) and facts[0]["text"].startswith("local-only")


def may_use_external_model(
    *, project: str | None = None, sensitivity: str = "normal", granted: set[str] | None = None
) -> Decision:
    """Whether this request may be routed to a provider off the machine.

    Enforced by routing rather than by asking the model to behave: a policy
    the model is trusted to honour is not a policy.
    """
    return check(
        "external_model", sensitivity=sensitivity, project=project, external=True, granted=granted
    )


# ── Credentials ──────────────────────────────────────────────────────────────

_CRED_SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS credentials (
        id          TEXT PRIMARY KEY,
        name        TEXT NOT NULL,
        project_id  TEXT,
        purpose     TEXT,
        created_at  TEXT NOT NULL,
        last_used   TEXT,
        uses        INTEGER NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS audit_log (
        id          TEXT PRIMARY KEY,
        action      TEXT NOT NULL,
        outcome     TEXT NOT NULL,
        actor       TEXT NOT NULL DEFAULT 'primnox',
        subject     TEXT,
        project_id  TEXT,
        sensitivity TEXT,
        detail      TEXT,
        created_at  TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_audit_time ON audit_log(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action, outcome)",
]


def _init() -> None:
    store.ensure_schema("policy", _CRED_SCHEMA)


def register_credential(name: str, *, project: str | None = None, purpose: str | None = None) -> str:
    """Register that a credential exists. The value is never passed here.

    Returns a reference ID. This table holds names and usage records only —
    the secret itself stays in the OS keychain or the encrypted vault, which
    is the whole point of the separation.
    """
    if not name:
        raise ValidationError("a credential needs a name")
    _init()
    cred_id = ids.stable_id("credential", name, project_id(project) or "")
    with store.transaction() as conn:
        conn.execute(
            """
            INSERT INTO credentials (id, name, project_id, purpose, created_at, last_used, uses)
            VALUES (?,?,?,?,?,NULL,0)
            ON CONFLICT(id) DO UPDATE SET purpose = COALESCE(excluded.purpose, credentials.purpose)
            """,
            (cred_id, name, project_id(project), purpose, store.utc_now()),
        )
    return cred_id


def credential_reference(name: str, *, project: str | None = None) -> str | None:
    """What the model is allowed to see: a handle and an availability flag."""
    _init()
    cred_id = ids.stable_id("credential", name, project_id(project) or "")
    row = store.connect().execute("SELECT name FROM credentials WHERE id = ?", (cred_id,)).fetchone()
    return f"{cred_id} ({row['name']}: available)" if row else None


def available_credentials(*, project: str | None = None) -> list[dict]:
    """Names and handles of registered credentials — never values."""
    _init()
    rows = store.connect().execute(
        "SELECT id, name, project_id, purpose, uses, last_used FROM credentials "
        "WHERE project_id IS ? OR project_id IS NULL ORDER BY name",
        (project_id(project),),
    ).fetchall()
    return [dict(r) for r in rows]


def resolve_credential(
    cred_id: str,
    *,
    purpose: str,
    resolver,
    granted: set[str] | None = None,
    project: str | None = None,
) -> str | None:
    """Fetch a secret's value through an authorised, audited path.

    `resolver(name)` is the injected accessor — V1's keyring/vault lookup.
    Requires `read_secret` to have been granted for this session, states a
    purpose, and audits both the grant and the use. The value is returned to
    the caller for the operation that needs it; putting it into a prompt is
    a separate act this function cannot perform.
    """
    _init()
    decision = check("read_secret", sensitivity="secret", project=project, granted=granted)
    if not decision.allowed:
        log.warning("credential resolution refused: %s", decision.reason)
        return None

    row = store.connect().execute("SELECT name FROM credentials WHERE id = ?", (cred_id,)).fetchone()
    if row is None:
        record("read_secret", outcome="denied", subject=cred_id, detail="unknown credential")
        return None

    try:
        value = resolver(row["name"])
    except Exception as exc:
        record("read_secret", outcome="failed", subject=cred_id, detail=str(exc)[:200])
        log.warning("credential resolver failed for %s (%s)", row["name"], exc)
        return None

    with store.transaction() as conn:
        conn.execute(
            "UPDATE credentials SET uses = uses + 1, last_used = ? WHERE id = ?",
            (store.utc_now(), cred_id),
        )
    record("read_secret", outcome="allowed", subject=cred_id, detail=f"purpose: {purpose}",
           sensitivity="secret", project=project)
    return value


# ── Audit ────────────────────────────────────────────────────────────────────


def record(
    action: str,
    *,
    outcome: str,
    actor: str = "primnox",
    subject: str | None = None,
    project: str | None = None,
    sensitivity: str | None = None,
    detail: str | None = None,
) -> str:
    """Append a security-relevant event to the audit log.

    `detail` is redacted on the way in: an audit trail that leaks the value
    it was recording the access to would be its own vulnerability.
    """
    _init()
    audit_id = ids.new_id("audit")
    safe_detail, _ = redact(detail or "")
    with store.transaction() as conn:
        conn.execute(
            """
            INSERT INTO audit_log (id, action, outcome, actor, subject, project_id, sensitivity,
                                   detail, created_at)
            VALUES (?,?,?,?,?,?,?,?,?)
            """,
            (audit_id, action, outcome, actor, subject, project_id(project), sensitivity,
             safe_detail, store.utc_now()),
        )
    return audit_id


def audit_trail(
    *,
    action: str | None = None,
    outcome: str | None = None,
    project: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """Read the audit log, newest first."""
    _init()
    clauses, params = [], []
    if action:
        clauses.append("action = ?")
        params.append(action)
    if outcome:
        clauses.append("outcome = ?")
        params.append(outcome)
    if project is not None:
        clauses.append("project_id = ?")
        params.append(project_id(project))
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(limit)
    rows = store.connect().execute(
        f"SELECT * FROM audit_log {where} ORDER BY created_at DESC LIMIT ?", params
    ).fetchall()
    return [dict(r) for r in rows]


# ── Coordinated deletion ─────────────────────────────────────────────────────


def purge_project(project: str, *, actor: str = "user") -> dict:
    """Delete a project from every V2 subsystem, and audit that it happened.

    "Delete this project from memory" is only satisfied when the world
    model, episodes, tasks, tool results and the code index have all let go
    of it. Doing that here — rather than leaving each caller to remember six
    modules — is what stops a project surviving in whichever table was
    forgotten.

    The audit log is deliberately *not* purged: a record that a deletion
    happened contains no project content and is what makes the deletion
    verifiable.
    """
    from v2 import episodes, graphify, result_store, task_state, world_model

    report = {
        "project": project,
        "world_model": world_model.purge_project(project),
        "episodes": episodes.purge_project(project),
        "tasks": task_state.purge_project(project),
        "results": result_store.purge_project(project),
        "code_index": graphify.purge_project(project),
    }
    report["audit_id"] = record(
        "delete_project", outcome="allowed", actor=actor, subject=project,
        detail="purged world model, episodes, tasks, results and code index",
    )
    log.info("purged project %s from all V2 stores", project)
    return report
