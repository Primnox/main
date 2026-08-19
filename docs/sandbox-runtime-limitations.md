# Sandbox runtime limitations

**RESOLVED (2026-08-12): Node.js and Pillow now work in the sandbox.** Not
via the `PrimnoxSandbox` Windows account this whole document investigates —
that account genuinely cannot run them, for the reasons documented below,
and no fix exists for it. The fix is a **second, preferred backend**:
`appcontainer_sandbox.py` + the AppContainer path in `code_exec.py`. See
"Resolution" near the bottom for what it is and why it works. Keep reading
from the top if you want the investigation that ruled out every alternative
first — it's still accurate, and it's why AppContainer was worth trying.

Some native code will not initialise under the `PrimnoxSandbox` account
specifically. It is written down because the symptom is baffling on first
contact and costs hours to re-derive, and because the investigation itself
(what was ruled out, and how) is what led to the actual fix.

## Symptom

Exactly one class of thing fails, and it fails identically everywhere:

| Fails in sandbox | Error |
|---|---|
| `_ctypes` (via `libffi-8.dll`) | `DLL load failed ... initialization routine failed` |
| `_ssl`, `_hashlib` (via `libcrypto-3.dll`) | same |
| `PIL._imaging` | same |
| `node.exe` (V8) | exit `0xC0000142` — `STATUS_DLL_INIT_FAILED` |

Everything else is fine: `_socket`, `_sqlite3`, `zlib`, `_lzma`, `_bz2`,
`pyexpat`, `_decimal`, `_multiprocessing`, `select`, `lxml`, `xlsxwriter`,
plain Python, `cmd.exe`, and file/registry access all work as the sandbox
account.

Because `PIL._imaging` fails, **`python-pptx` and `reportlab` also fail** in
the sandbox — they are victims, not separate bugs. One root cause explains
every document-generation limitation Primnox currently has.

## Ruled out (tested, not assumed)

Each of these was tried against the live sandbox account and made no
difference:

- **File permissions** — the sandbox reads `libffi-8.dll`, `_ctypes.pyd` and
  `node.exe` fine; `os.access` and a real `open().read()` both succeed.
- **Program Files ACLs** — `node.exe` copied into a fully sandbox-writable
  directory fails identically.
- **Group membership** — the account originally had *no* groups at all.
  Adding it to `Users` changed nothing. (A fresh `LogonUser` per execution
  means the new membership is genuinely in the token.)
- **Job Object memory cap** — fails with `JOB_OBJECT_LIMIT_JOB_MEMORY`
  removed, and with no Job Object at all.
- **Environment** — fails with the minimal allowlist, with the caller's full
  `os.environ`, and with `TEMP`/`TMP`/`USERPROFILE` redirected to a directory
  the account owns.
- **Window station / desktop** — fails with `winsta0\default` access
  explicitly granted to the account. Creating a *private* window station
  instead is not possible: `CreateWindowStation` returns `ACCESS_DENIED` from
  a non-elevated process at every access mask.
- **User profile / registry** — `LoadUserProfile` does fail (needs
  `SeRestorePrivilege`), but `HKCU` and `HKLM` are both readable from inside
  the sandbox, so the missing profile is not the cause.
- **Logon type** — `BATCH` and `NETWORK_CLEARTEXT` both fail identically.
  `INTERACTIVE` and `SERVICE` are refused by design (only `SeBatchLogonRight`
  is granted).

## Ruled out: process mitigation policies (ACG/CIG/CFG/CET)

The "executable memory is blocked" theory — libffi builds closure
trampolines, V8 JITs, so maybe Arbitrary Code Guard is on — is **dead**.

`GetProcessMitigationPolicy` was queried for all 17 policy classes against
two processes spawned from the same parent with the same command line, one
as the normal user and one as `PrimnoxSandbox`. **Every value is identical:**

| Policy | Normal user | PrimnoxSandbox |
|---|---|---|
| DEP | `0x100000003` | `0x100000003` |
| ASLR | `0x00000005` | `0x00000005` |
| **DynamicCode (ACG)** | `0x00000000` | `0x00000000` |
| ControlFlowGuard | `0x00000001` | `0x00000001` |
| Signature (CIG) | `0x00000000` | `0x00000000` |
| ImageLoad | `0x00000000` | `0x00000000` |
| ExtensionPointDisable | `0x00000000` | `0x00000000` |
| UserShadowStack (CET) | `0x00000100` | `0x00000100` |
| SEHOP | `0x00000001` | `0x00000001` |

(The remaining classes — StrictHandleCheck, SystemCallDisable,
SystemCallFilter, PayloadRestriction, ChildProcess, SideChannelIsolation,
FontDisable, RedirectionTrust — are `0x00000000` on both.)

ACG is **off** in both. `Get-ProcessMitigation -System` reports every setting
as `NOTSET`, and there are no per-executable overrides for `node.exe` or
`python.exe`. No mitigation is involved.

Reproduce with `GetProcessMitigationPolicy(hProcess, class, buf, size)` —
note `size` is **4** bytes for every class except `ProcessDEPPolicy`, which
is 8. Passing 8 for all of them returns `ERROR_INVALID_PARAMETER` (87) and
looks like the query failed.

## Minimal reproduction (no Primnox code involved)

The failure reproduces with stock Windows binaries, which makes this
diagnosable without any of Primnox's machinery:

| Binary | As normal user | As `PrimnoxSandbox` |
|---|---|---|
| `reg.exe` | works | **works** |
| `cmd.exe`, `whoami.exe`, `ping.exe` | works | **works** |
| `python.exe` | works | **works** |
| `certutil.exe` | works | **`0xC0000142`** |
| `tasklist.exe` | works | **`0xC0000142`** |
| `notepad.exe` | works | **`0xC0000142`** |
| `powershell.exe` | works | **`0xC0000142`** |

PowerShell failing is significant on its own: the .NET CLR JITs everything it
runs, so this is also the executable-memory test — and it fails while the
mitigation policies say dynamic code is permitted.

> Careful with `mspaint.exe` as a test case — it does not exist in System32 on
> this machine, so it returns "command not found" (rc=1), which reads as a
> pass. Verify a test binary exists before drawing conclusions from it.

## Also ruled out: window station / desktop access

The failing set correlates with `user32.dll` — everything that works
(`reg`, `cmd`, `ping`, `whoami`, `python`) is console-only, everything that
fails links user32 or something that does. user32's initialiser attaches the
process to a window station, and failing there produces exactly
`STATUS_DLL_INIT_FAILED`. Granting the account access to the window station
and desktop is also *the* documented fix for `CreateProcessAsUser` +
`0xC0000142`, so this looked highly probable.

**It is not the cause.** The grant was applied and then *verified by reading
the DACL back* — the sandbox SID is present on both objects with full
access, as two ACEs each (inherit-only + direct):

```
winsta0            ... mask=0x0000037f  DESKTOP-...\PrimnoxSandbox   (flags 0x0b, 0x00)
desktop 'default'  ... mask=0x000001ff  DESKTOP-...\PrimnoxSandbox   (flags 0x0b, 0x00)
```

With those ACEs confirmed in place, `node`, `powershell.exe` and
`certutil.exe` all still exit `0xC0000142`, while `reg.exe` still succeeds.

**Verify the DACL by reading it back before trusting a negative result here** —
`SetUserObjectSecurity` can silently no-op on a malformed ACE, which is
indistinguishable from a genuine "the fix didn't work".

The ACEs were removed afterwards: they bought nothing and would have let the
sandbox reach the interactive desktop.

## Where this leaves it

Every cheap Win32-level explanation is now eliminated: file ACLs, group
membership, Job Object limits, environment, logon type, user profile,
process mitigation policies, and window station/desktop access. The cause is
something less obvious, and further progress needs real tracing rather than
hypothesis-and-test.

Next steps if picked up:

1. Get the actual loader error instead of the summary status — enable Loader
   Snaps (`gflags /i certutil.exe +sls`) and run under a debugger to see
   which DLL's initialiser returns FALSE. This is the highest-value step by
   far; everything above was guessing at what the loader already knows.
2. Process Monitor on a `certutil.exe` launch as the sandbox account — the
   last operations before exit usually name the resource being denied.
3. Test a private window station from an **elevated** process
   (`CreateWindowStation` returns `ACCESS_DENIED` non-elevated, so this
   specific variant was never actually tested — distinct from the winsta0
   grant above, which was).

## Root cause, confirmed

Windows Loader Snaps (`ShowSnaps` via IFEO `GlobalFlag=0x2`) were enabled for
`node.exe`, and the sandboxed process's own loader was captured live by
attaching as its debugger (`CreateProcessAsUser` with `DEBUG_PROCESS`,
reading `OUTPUT_DEBUG_STRING_EVENT`s via `ReadProcessMemory`). The loader
names the failure directly — no more inference from which binaries pass or
fail:

```
LdrpInitializeNode - ERROR: Init routine ... for DLL "C:\WINDOWS\System32\USER32.dll"
                            failed during DLL_PROCESS_ATTACH
LdrpInitializeProcess - ERROR: Running the init routines of the executable's
                                static imports failed with status 0xc0000142
```

`USER32.dll`'s own startup code fails, not something it depends on.

Session ID was checked and ruled out — the sandbox token's `TokenSessionId`
is `1`, identical to the interactive session, so this is not Session 0
service isolation.

What actually gates it: `winsta0`'s real security descriptor contains a
**logon-session SID** (`S-1-5-5-0-<logon-id>`, confirmed present in the live
DACL) — a one-time identifier minted by winlogon for the specific
interactive logon, distinct from and stronger than any account-level ACE.
Full interactive window-station/desktop access (which `USER32.dll`'s
`DllMain` requires to complete initialization) is gated on holding that
exact SID. The sandbox account authenticates through an unrelated logon
event and structurally cannot carry it — there is no API to request it, and
granting the *account* SID access to `winsta0` (verified applied earlier)
sits alongside this mechanism without satisfying it.

**This is not a misconfiguration.** It is the specific Windows control that
stops one logon session from reaching into another's desktop — precisely
the class of attack (shatter attacks, cross-session input/message
injection) that this sandbox exists to prevent. There is no supported way
for a non-elevated, or even elevated-but-non-SYSTEM, process to grant
another logon session that SID. Obtaining it would mean defeating the same
category of OS security boundary this project has already ruled out
weakening in the sandbox account itself.

**Conclusion: no further Win32-level fix should be attempted.** Every
avenue that doesn't involve subverting this boundary has been tried and
ruled out. See "Strategic note" below.

## Strategic note (superseded — kept for the reasoning trail)

A local Windows user account is a mediocre isolation primitive: it is
ACL-based only (no memory, CPU or kernel-surface isolation), and — as this
document shows — a large fraction of Windows will not initialise inside one.

**WSL2 was scoped as a replacement** (a real VM boundary; Node, Pillow,
LibreOffice and pandoc all work normally there) — full architecture,
provisioning module, and backend-selection design were written and unit
tested (2026-08-11). **The user explicitly declined it** ("i dont want
wsl") and the WSL2 code was removed at their request. Do not re-propose
WSL2 for this — it was a considered, deliberate rejection, not an oversight,
and it's moot now regardless: AppContainer resolved the same problem
without leaving Windows. See "Resolution" below.

## Resolution: AppContainer (2026-08-12)

`appcontainer_sandbox.py` + the AppContainer branch of `code_exec.py`
(`_active_backend()`, `_build_appcontainer_command()`,
`_create_appcontainer_process()`) — a **second backend**, preferred when
available, with the `PrimnoxSandbox` account kept permanently as fallback.

**Why it works where a separate Windows account can't:** every failure
above traces to one thing — a separate `LogonUser()` session lacks the
winlogon-minted logon-session SID that `USER32.dll`'s own init requires.
AppContainer doesn't create a separate logon session at all.
`CreateAppContainerProfile` mints an isolated SID; the process launches via
plain `CreateProcess` carrying that SID in a security-capabilities
attribute, **in Primnox's own session** — so it inherits the session's
already-legitimate window station. Confirmed live: `node.exe` and
`import PIL._imaging` both succeed under it.

Isolation still holds, confirmed live against the same checks used
throughout this document: `settings.json`/`memory.db`/`chat.db`/source all
`PermissionError` with zero capabilities granted; network `URLError` (zero
capabilities means no network capability at all — a first-class Windows
Filtering Platform deny, not a bolted-on firewall rule). File access is
explicit icacls allow-listing on the AppContainer SID, same pattern as
`sandbox_account.py`'s grants, reused via a SID-object bridge rather than
duplicated.

Three non-obvious things it took to get working, in case this needs
revisiting:
1. `STARTF_USESTDHANDLES` (the normal way to capture output) makes the
   AppContainer process die with `STATUS_DLL_INIT_FAILED` — regardless of
   handle type. Fix: Python/Node launch directly (no shell wrapper) and
   redirect their *own* stdout/stderr internally.
2. A custom environment block passed alongside the security-capabilities
   attribute fails outright (`ERROR_ENVVAR_NOT_FOUND`) unless
   `LOCALAPPDATA` is present — AppContainer's own per-container storage
   redirection needs it. Distinct from `APPDATA`/Roaming, where secrets
   live; adding it exposes nothing new.
3. Node's own module resolution walks up the directory tree and hits the
   drive root, which the AppContainer was never granted — fixed with
   `--preserve-symlinks --preserve-symlinks-main`, not a permission grant.

`runtime_capabilities.py` needed zero changes — it now reports Node/Pillow
as available automatically, exactly as the "kept in the codebase" note
below anticipated.

## Design response

Do **not** fix this by widening the `PrimnoxSandbox` account's privileges.
The point of the architecture is that model-generated code runs somewhere
restricted; trading that away for nicer PowerPoints was always the wrong
trade — which is exactly why the fix ended up being a different isolation
primitive instead, not a weaker version of the old one.

- `runtime_capabilities.detect()` probes the sandbox at first use and caches
  the result. It probes *inside* the sandbox, and probes the module that
  actually breaks (`PIL._imaging`, not `PIL` — the shallow name imports fine
  and proves nothing).
- `skills/adapted_skill.py` puts the capability list in the prompt, so a
  skill picks a working implementation up front rather than discovering the
  gap mid-workflow.
- `skills/sandboxed_render.py` takes a `requires=` tuple and renders
  in-process when a needed library is missing, instead of paying for a
  sandboxed execution that is certain to fail.

This machinery stays even though Node/Pillow now work through AppContainer —
it's what makes ANY future gap (a different missing library, a machine
where AppContainer provisioning fails) survivable rather than a hard
failure, and the Windows-account backend still needs it as long as it
exists as a fallback.

The JavaScript path was **kept in the codebase** through the whole
investigation on exactly this bet — that the gap was one isolation
primitive away from closing, not a dead end. If this limitation is ever
resolved, `detect()` starts reporting Node as available and the
higher-fidelity `pptxgenjs`/`docx-js` path lights up with no code
change.
