# Orchestrator

Fans work out to N headless `opencode` processes, each running the configured
worker model, each in its own sandbox outside this repository.

The worker is treated as a stranger. It never sees this repo, this product, or
this conversation — only a self-contained work order.

## Commands

```
node scripts/orchestrator/orchestrator.mjs doctor
node scripts/orchestrator/orchestrator.mjs list
node scripts/orchestrator/orchestrator.mjs dispatch --dry-run
node scripts/orchestrator/orchestrator.mjs dispatch --task a --task b
node scripts/orchestrator/orchestrator.mjs status
node scripts/orchestrator/orchestrator.mjs collect --run-id <id>
node scripts/orchestrator/orchestrator.mjs sweep <file>...
```

`doctor` is the gate. It refuses to report ready if the sandbox root sits inside
the repo, if an `AGENTS.md` / `CLAUDE.md` / `.opencode` exists anywhere above the
sandbox root, if the denylist is empty, or if the configured model is not in
`worker.allowedModels`.

## Containment

Four independent barriers, in the order they apply:

1. **Sandbox location.** Every worker runs in `paths.sandboxRoot/<runId>/<taskId>`,
   which must resolve outside the repo. `opencode` walks up from its cwd looking
   for context files; outside the repo there is nothing to find.
2. **Config pinning.** Each sandbox gets its own `opencode.json`, pointed at via
   `OPENCODE_CONFIG`, so the ambient user config never selects the model. Workers
   run `--pure` (no external plugins).
3. **Env scrubbing.** Only `isolation.env.passthrough` variables reach the child.
   Everything else is dropped.
4. **Leak guard.** The rendered brief, the standards file, and every seeded input
   are swept against `denylist.txt` before the process is spawned. A hit blocks
   that task, writes `leaks.json`, and leaves the rest of the run alone.

## Configuration

Everything lives in `orchestrator.config.json`. No model id, path, limit, or flag
is baked into `orchestrator.mjs`. Strings support `${env:NAME}`,
`${env:NAME:-fallback}`, `${configDir}`, `${repoRoot}`, and `${tmpdir}`.

Override without editing the file:

| Variable | Controls |
| --- | --- |
| `ORCH_CONFIG` | path to an alternate config file |
| `ORCH_OPENCODE_BIN` | runner executable name |
| `ORCH_WORKER_MODEL` | worker model id |
| `ORCH_WORKER_VARIANT` | reasoning variant |
| `ORCH_CONCURRENCY` | parallel workers |
| `ORCH_TASK_TIMEOUT_MS` | per-task wall clock |
| `ORCH_SANDBOX_ROOT` | sandbox location |
| `ORCH_RUNS_DIR` | where results land |

## Writing a task

Copy `tasks/_template.task.json` to `tasks/<id>.task.json` and set
`"enabled": true`. The brief is the whole world the worker gets: state inputs,
outputs, invariants, language, and what must be configurable — and nothing about
where the code will live or what it is for.
