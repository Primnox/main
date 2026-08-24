# Security and privacy

Domains 7 (141–165) and 16 (286–290).

Scope: this is defensive testing of Primnox itself — finding weaknesses so they get
fixed. Stay inside the app under test. Don't scan hosts you don't own, and don't
build tooling whose purpose is attacking third parties.

## Existing coverage

| Area | File |
|---|---|
| CSRF / origin (151) | `test_csrf_origin.py` |
| WebSocket origin (68, 151) | `test_ws_origin.py` |
| Command injection (149) | `test_tool_escapes.py` |
| Encryption at rest (163, 164) | `test_vault.py`, `primnox2/storage/vault.py` |
| PII / privacy (286) | `test_privacy_mirror.py`, `primnox2/privacy/` |
| Prompt injection (192) | `test_sdl_inject.py` |

Run these as a gate whenever the diff touches routing, storage, tools, or privacy —
capability 165 (security regression) is just "don't let a fixed hole reopen".

## The local-app threat model

Primnox runs on the user's machine with a backend on port 4109. That shapes which
checks matter and which are theatre.

**High value here:**

- **Localhost exposure (146, 147)** — the backend must bind `127.0.0.1`, not
  `0.0.0.0`. Binding to all interfaces turns a local app into a network service
  reachable by anything on the same Wi-Fi. Assert the bind address in code, and
  confirm what's actually listening.
- **CSRF and origin checks (151)** — a local server is reachable by *any* web page the
  user visits. Origin validation is the only thing stopping a random site from
  driving the local API. This is why `test_csrf_origin.py` and `test_ws_origin.py`
  exist; keep them passing.
- **Command injection via tools (149)** — the tool layer executes things. Shell
  metacharacters, quotes, newlines, and path separators in tool arguments all need
  covering.
- **Directory traversal (158)** — `../` in any path-bearing parameter. The data root
  is a boundary; assert nothing escapes it, including via symlinks (219) and archive
  extraction (228, zip-slip).
- **Secrets at rest (141–143, 163, 164)** — API keys must come from env or the vault,
  never literals, and must not reach logs.

**Lower value here** (still check, but don't over-invest): classic web-app concerns
that assume a hostile remote user with a browser session — a local single-user app
has a different exposure profile.

## Injection testing that actually works

The pattern for 148 (SQL), 149 (command), 150 (XSS), 158 (traversal) is the same:

1. Find every place external input reaches an interpreter — SQL, shell, HTML, or the
   filesystem.
2. Send input that would change the interpreter's parse, not just odd-looking text:
   `'; DROP TABLE`, `$(cmd)`, `` `cmd` ``, `<script>`, `../../`, a null byte.
3. **Assert on the effect, not the response.** A 200 with escaped output is a pass; a
   500 might be a pass or might be a crash-on-malformed-input bug. Check what
   happened downstream.

For XSS specifically: chat and markdown rendering are the surfaces. Content flows
from a model and from tool output into rendered HTML, so both are untrusted inputs.

## Secrets (141–143)

Before any commit, scan the diff for key-shaped strings. Cheap and catches the most
common real leak:

```bash
git diff --cached -U0 | grep -nEi "(api[_-]?key|secret|token|password|bearer)[\"' ]*[:=]"
```

Also check history, not just the working tree — a secret committed and later removed
is still in the repo and still needs rotating. Finding one is not "fix the file"; it's
"rotate the credential, then fix the file", and the report should say so.

Confirm nothing sensitive lands in logs (256) or in URLs (157). Query strings end up
in browser history, proxy logs, and referrer headers.

## Dependencies (144)

```bash
npm --prefix frontend audit
```

For Python, check `backend/requirements.txt` against current advisories. Report
severity *and* whether the vulnerable path is actually reachable from this app — a
critical CVE in a code path Primnox never calls is a lower priority than a moderate
one in the request path, and saying so is more useful than forwarding a raw audit.

## Privacy (286–290)

`primnox2/privacy/` holds the PII machinery, with a local model fetched by
`fetch_pii_model.py`.

- **PII detection (286)** — the assertion is about *egress*: PII must be caught before
  data leaves the machine for a cloud provider. Test with realistic mixed content —
  names inside prose, emails in code comments, IDs in structured data — because
  detectors that pass on isolated examples routinely miss embedded ones.
- **Consent (287)** — assert no egress occurs without recorded consent. The dangerous
  default is "cloud provider configured, so send it".
- **Retention (288)** and **secure deletion (289)** — deletion must remove the row
  *and* everything derived from it: embeddings, knowledge-graph nodes, replay events,
  caches. Orphaned derivatives are how "deleted" data comes back, and a test that
  only checks the primary table will pass while the data is still there.
- **Audit logs (290)** — privacy-relevant actions logged, without logging the PII
  itself. Easy to get backwards.

## Reporting security findings

Severity is user impact, not fix difficulty. A one-line fix for a credential leak is
still Critical.

Keep exploitability separate from severity, and be explicit about preconditions —
"requires the user to visit a malicious page while Primnox runs" is a materially
different risk from "requires nothing". A finding without its preconditions gets
either over- or under-prioritised, and both waste the fix.
