#!/usr/bin/env node
/**
 * Fan-out orchestrator for headless opencode workers.
 *
 * The worker is treated as a stranger: it runs in a sandbox outside the
 * repository, sees only a self-contained brief plus explicitly seeded inputs,
 * and every byte of that is swept against a denylist before the process starts.
 *
 * All behaviour is driven by orchestrator.config.json. This file contains no
 * model ids, no paths, no limits, and no product knowledge.
 */

import { spawn } from 'node:child_process';
import fs from 'node:fs';
import fsp from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const CONFIG_DIR = path.dirname(fileURLToPath(import.meta.url));
const CONFIG_ENV = 'ORCH_CONFIG';
const CONFIG_DEFAULT = 'orchestrator.config.json';
const TASK_SUFFIX = '.task.json';
const INTERPOLATION_PASSES = 8;

/* ------------------------------------------------------------------ config */

/** Resolve ${...} tokens in a string, innermost first, until stable. */
function interpolate(value, scope) {
  if (typeof value !== 'string') return value;
  let out = value;
  for (let pass = 0; pass < INTERPOLATION_PASSES; pass += 1) {
    const next = out.replace(/\$\{([^{}]+)\}/g, (whole, token) => {
      const sep = token.indexOf(':-');
      const name = sep === -1 ? token : token.slice(0, sep);
      const fallback = sep === -1 ? undefined : token.slice(sep + 2);
      let resolved;
      if (name.startsWith('env:')) resolved = process.env[name.slice(4)];
      else if (Object.prototype.hasOwnProperty.call(scope, name)) resolved = scope[name];
      else return whole;
      if (resolved === undefined || resolved === '') {
        return fallback === undefined ? '' : fallback;
      }
      return String(resolved);
    });
    if (next === out) break;
    out = next;
  }
  return out;
}

function interpolateTree(node, scope) {
  if (Array.isArray(node)) return node.map((n) => interpolateTree(n, scope));
  if (node && typeof node === 'object') {
    const out = {};
    for (const [k, v] of Object.entries(node)) out[k] = interpolateTree(v, scope);
    return out;
  }
  return interpolate(node, scope);
}

function readJson(file) {
  return JSON.parse(fs.readFileSync(file, 'utf8'));
}

function repoRootOf(dir) {
  let cur = dir;
  for (;;) {
    if (fs.existsSync(path.join(cur, '.git'))) return cur;
    const up = path.dirname(cur);
    if (up === cur) return dir;
    cur = up;
  }
}

function loadConfig(extraScope = {}) {
  const file = process.env[CONFIG_ENV]
    ? path.resolve(process.env[CONFIG_ENV])
    : path.join(CONFIG_DIR, CONFIG_DEFAULT);
  if (!fs.existsSync(file)) throw new Error(`config not found: ${file}`);
  const configDir = path.dirname(file);
  const scope = {
    configDir,
    repoRoot: repoRootOf(configDir),
    tmpdir: os.tmpdir(),
    ...extraScope,
  };
  const cfg = interpolateTree(readJson(file), scope);
  cfg.__file = file;
  cfg.__scope = scope;
  return cfg;
}

const num = (value, fallback) => {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
};

/* -------------------------------------------------------------- leak guard */

function loadDenylist(file) {
  if (!fs.existsSync(file)) return [];
  const rules = [];
  for (const raw of fs.readFileSync(file, 'utf8').split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith('#')) continue;
    if (line.startsWith('re:')) {
      const source = line.slice(3);
      try {
        rules.push({ kind: 'regex', source: line, test: new RegExp(source, 'i') });
      } catch (err) {
        throw new Error(`bad regex in denylist: ${source} (${err.message})`);
      }
    } else {
      rules.push({ kind: 'literal', source: line, needle: line.toLowerCase() });
    }
  }
  return rules;
}

function excerpt(text, at, len) {
  const pad = 24;
  const start = Math.max(0, at - pad);
  const end = Math.min(text.length, at + len + pad);
  const head = start > 0 ? '…' : '';
  const tail = end < text.length ? '…' : '';
  return `${head}${text.slice(start, end).replace(/\s+/g, ' ')}${tail}`;
}

/** @returns {{where: string, rule: string, sample: string}[]} */
function sweepText(text, rules, label) {
  const hits = [];
  const lower = text.toLowerCase();
  for (const rule of rules) {
    if (rule.kind === 'literal') {
      const at = lower.indexOf(rule.needle);
      if (at !== -1) hits.push({ where: label, rule: rule.source, sample: excerpt(text, at, rule.needle.length) });
    } else {
      const m = rule.test.exec(text);
      if (m) hits.push({ where: label, rule: rule.source, sample: excerpt(text, m.index, m[0].length) });
    }
  }
  return hits;
}

async function sweepFile(file, rules, iso, label) {
  const ext = path.extname(file).toLowerCase();
  if ((iso.sweepBinaryExtensions ?? []).includes(ext)) return [];
  const stat = await fsp.stat(file);
  const max = num(iso.maxSweepFileBytes, 2 * 1024 * 1024);
  if (stat.size > max) {
    return [{ where: label, rule: '<unsweepable>', sample: `file exceeds maxSweepFileBytes (${stat.size} > ${max})` }];
  }
  return sweepText(await fsp.readFile(file, 'utf8'), rules, label);
}

/* ----------------------------------------------------------------- sandbox */

async function walk(dir, base = dir, ignore = []) {
  const out = [];
  for (const entry of await fsp.readdir(dir, { withFileTypes: true })) {
    if (ignore.includes(entry.name)) continue;
    const abs = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...(await walk(abs, base, ignore)));
    else if (entry.isFile()) out.push(path.relative(base, abs));
  }
  return out;
}

function renderBrief(task, briefBody) {
  const lines = [`# ${task.title || task.id}`, '', briefBody.trim(), ''];
  if (task.deliverables?.length) {
    lines.push('## Deliverables', '');
    for (const d of task.deliverables) lines.push(`- \`${d}\``);
    lines.push('');
  }
  if (task.acceptance?.length) {
    lines.push('## Acceptance criteria', '');
    for (const a of task.acceptance) lines.push(`- ${a}`);
    lines.push('');
  }
  return lines.join('\n');
}

async function buildSandbox(cfg, task, runId, rules) {
  const iso = cfg.isolation;
  const sandbox = path.join(cfg.paths.sandboxRoot, runId, task.id);
  const hits = [];

  const briefBody = task.briefFile
    ? await fsp.readFile(path.resolve(cfg.paths.tasksDir, task.briefFile), 'utf8')
    : String(task.brief ?? '');
  if (!briefBody.trim()) throw new Error(`task ${task.id}: empty brief`);
  const brief = renderBrief(task, briefBody);
  if (iso.sweepBrief) hits.push(...sweepText(brief, rules, `${task.id}:brief`));

  const standardsFile = path.resolve(cfg.paths.standardsDir, task.standards || cfg.worker.standardsFilename);
  const standards = await fsp.readFile(standardsFile, 'utf8');
  hits.push(...sweepText(standards, rules, `${task.id}:standards`));

  const seeds = [];
  for (const seed of task.seed ?? []) {
    const from = path.resolve(cfg.__scope.repoRoot, seed.from);
    const to = seed.to || path.basename(from);
    if (iso.sweepSeededInputs) hits.push(...(await sweepFile(from, rules, iso, `${task.id}:seed:${seed.from}`)));
    seeds.push({ from, to });
  }

  if (hits.length) return { sandbox, hits, built: false };

  await fsp.rm(sandbox, { recursive: true, force: true });
  await fsp.mkdir(sandbox, { recursive: true });
  await fsp.writeFile(path.join(sandbox, cfg.worker.briefFilename), brief, 'utf8');
  await fsp.writeFile(path.join(sandbox, cfg.worker.standardsFilename), standards, 'utf8');
  for (const { from, to } of seeds) {
    const dest = path.join(sandbox, to);
    await fsp.mkdir(path.dirname(dest), { recursive: true });
    await fsp.copyFile(from, dest);
  }
  if (iso.writeSandboxConfig) {
    const sandboxCfg = { $schema: 'https://opencode.ai/config.json', model: cfg.worker.model };
    await fsp.writeFile(
      path.join(sandbox, iso.sandboxConfigFilename),
      `${JSON.stringify(sandboxCfg, null, 2)}\n`,
      'utf8',
    );
  }
  return { sandbox, hits, built: true };
}

function buildEnv(cfg, sandbox) {
  const iso = cfg.isolation;
  const env = {};
  for (const key of iso.env.passthrough ?? []) {
    if (process.env[key] !== undefined) env[key] = process.env[key];
  }
  Object.assign(env, iso.env.inject ?? {});
  if (iso.writeSandboxConfig && iso.sandboxConfigEnvVar) {
    env[iso.sandboxConfigEnvVar] = path.join(sandbox, iso.sandboxConfigFilename);
  }
  return env;
}

/* ------------------------------------------------------------------ runner */

const isBatch = (file, win) => (win.batchExtensions ?? []).includes(path.extname(file).toLowerCase());

/**
 * Package-manager shims on Windows are .cmd files that forward to a real
 * executable on a single quoted line. Node 24 refuses to spawn .cmd without a
 * shell, so where the shim names a real binary we follow it and spawn that
 * directly, which sidesteps shell quoting entirely.
 * @returns {string|null} absolute path to the forwarded executable
 */
function followWindowsShim(shimPath, win) {
  let text;
  try {
    text = fs.readFileSync(shimPath, 'utf8');
  } catch {
    return null;
  }
  const shimDir = path.dirname(shimPath);
  const forwarded = /"([^"\n]+)"[^\n"]*%\*/g;
  for (const m of text.matchAll(forwarded)) {
    const expanded = m[1].replace(/%~?dp0%\\?/gi, `${shimDir}${path.sep}`);
    if (!path.isAbsolute(expanded)) continue;
    const target = path.normalize(expanded);
    if (target === path.normalize(shimPath) || isBatch(target, win)) continue;
    if (fs.existsSync(target) && fs.statSync(target).isFile()) return target;
  }
  return null;
}

function resolveExecutable(cfg) {
  const cmd = cfg.runner.command;
  const win = cfg.runner.windows ?? {};
  const settle = (file) => {
    if (process.platform !== 'win32' || !win.followShims || !isBatch(file, win)) return file;
    return followWindowsShim(file, win) ?? file;
  };

  if (cmd.includes(path.sep) || cmd.includes('/')) return settle(path.resolve(cmd));

  const dirs = (process.env.PATH || process.env.Path || '').split(path.delimiter).filter(Boolean);
  const exts = process.platform === 'win32'
    ? (process.env.PATHEXT || '.COM;.EXE;.BAT;.CMD').split(';').filter(Boolean)
    : [''];
  for (const dir of dirs) {
    for (const ext of exts) {
      const candidate = path.join(dir, cmd + ext);
      if (fs.existsSync(candidate) && fs.statSync(candidate).isFile()) return settle(candidate);
    }
  }
  return null;
}

/** Quote one argument for a `cmd.exe /s /c "..."` command line. */
const quoteForComspec = (arg) => `"${String(arg).replace(/(\\*)"/g, '$1$1\\"').replace(/(\\+)$/, '$1$1')}"`;

/**
 * Spawn that tolerates a Windows batch target. Real executables spawn normally;
 * a .cmd/.bat that could not be followed goes through the comspec with verbatim
 * arguments, so we control the quoting rather than letting a shell re-parse it.
 */
function spawnRunner(cfg, exe, args, options) {
  const win = cfg.runner.windows ?? {};
  if (process.platform !== 'win32' || !isBatch(exe, win)) return spawn(exe, args, options);
  const comspec = win.comspec || process.env.COMSPEC || 'cmd.exe';
  const line = [exe, ...args].map(quoteForComspec).join(' ');
  return spawn(comspec, [...(win.comspecArgs ?? ['/d', '/s', '/c']), `"${line}"`], {
    ...options,
    windowsVerbatimArguments: true,
  });
}

function buildArgs(cfg, task) {
  const r = cfg.runner;
  const w = cfg.worker;
  const args = [r.subcommand, ...(r.baseArgs ?? [])];
  args.push(r.modelFlag, w.model);
  if (w.variant) args.push(r.variantFlag, w.variant);
  if (w.agent) args.push(r.agentFlag, w.agent);
  if (r.attachFlag) args.push(r.attachFlag, w.briefFilename);
  if (r.titleFlag) args.push(r.titleFlag, task.id);
  args.push(w.kickoff);
  return args;
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/**
 * Run one task, retrying on failure with exponential backoff. A provider's
 * per-day quota is the case this exists for: the worker cannot succeed now but
 * will succeed later, and the operator should not have to sit and re-dispatch.
 */
async function runWithRetry(cfg, task, sandbox, outDir, onAttempt) {
  const attempts = Math.max(0, num(cfg.execution.retries, 0)) + 1;
  const base = num(cfg.execution.retryBackoffMs, 60_000);
  const cap = num(cfg.execution.retryBackoffMaxMs, 900_000);
  let res;
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    res = await runWorker(cfg, task, sandbox, outDir, attempt);
    res.attempt = attempt;
    if (res.status === 'ok') return res;
    if (attempt >= attempts) return res;
    const delay = Math.min(base * 2 ** (attempt - 1), cap);
    onAttempt?.(attempt, attempts - 1, res, delay);
    await sleep(delay);
  }
  return res;
}

function runWorker(cfg, task, sandbox, outDir, attempt = 1) {
  const exe = resolveExecutable(cfg);
  if (!exe) throw new Error(`runner not found on PATH: ${cfg.runner.command}`);
  const args = buildArgs(cfg, task);
  const timeoutMs = num(cfg.execution.taskTimeoutMs, 45 * 60 * 1000);
  const graceMs = num(cfg.execution.killGraceMs, 10_000);

  return new Promise((resolve) => {
    const started = Date.now();
    const tag = attempt > 1 ? `.${attempt}` : '';
    const stdout = fs.createWriteStream(path.join(outDir, `stdout${tag}.jsonl`));
    const stderr = fs.createWriteStream(path.join(outDir, `stderr${tag}.log`));
    // stdin must be closed, not an idle pipe. The runner checks for piped input
    // on startup; an open pipe that never sees data or EOF blocks it forever,
    // before it ever reaches the model.
    const child = spawnRunner(cfg, exe, args, {
      cwd: sandbox,
      env: buildEnv(cfg, sandbox),
      windowsHide: true,
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    let timedOut = false;

    const softKill = setTimeout(() => {
      timedOut = true;
      child.kill('SIGTERM');
      setTimeout(() => child.kill('SIGKILL'), graceMs).unref();
    }, timeoutMs);

    child.stdout.pipe(stdout);
    child.stderr.pipe(stderr);
    child.on('error', (err) => {
      clearTimeout(softKill);
      resolve({ status: 'error', code: null, timedOut, ms: Date.now() - started, error: err.message });
    });
    child.on('close', (code) => {
      clearTimeout(softKill);
      resolve({
        status: timedOut ? 'timeout' : code === 0 ? 'ok' : 'failed',
        code,
        timedOut,
        ms: Date.now() - started,
      });
    });
  });
}

async function pool(items, limit, worker) {
  const results = new Array(items.length);
  let cursor = 0;
  const laneCount = Math.max(1, Math.min(limit, items.length));
  const lanes = Array.from({ length: laneCount }, async () => {
    for (;;) {
      const i = cursor;
      cursor += 1;
      if (i >= items.length) return;
      results[i] = await worker(items[i], i);
    }
  });
  await Promise.all(lanes);
  return results;
}

/* ------------------------------------------------------------------- tasks */

function loadTasks(cfg) {
  const dir = cfg.paths.tasksDir;
  if (!fs.existsSync(dir)) return [];
  return fs
    .readdirSync(dir)
    .filter((f) => f.endsWith(TASK_SUFFIX) && !f.startsWith('_'))
    .map((f) => {
      const task = readJson(path.join(dir, f));
      task.__file = path.join(dir, f);
      task.id ||= f.slice(0, -TASK_SUFFIX.length);
      return task;
    });
}

function selectTasks(cfg, wanted) {
  const all = loadTasks(cfg);
  if (!wanted.length) return all.filter((t) => t.enabled !== false);
  const byId = new Map(all.map((t) => [t.id, t]));
  return wanted.map((id) => {
    const t = byId.get(id);
    if (!t) throw new Error(`unknown task: ${id} (have: ${[...byId.keys()].join(', ') || 'none'})`);
    return t;
  });
}

/* ---------------------------------------------------------------- commands */

function parseArgv(argv) {
  const out = { _: [], flags: {}, list: {} };
  for (let i = 0; i < argv.length; i += 1) {
    const a = argv[i];
    if (!a.startsWith('--')) {
      out._.push(a);
      continue;
    }
    const eq = a.indexOf('=');
    let key;
    let val;
    if (eq === -1) {
      key = a.slice(2);
      const peek = argv[i + 1];
      if (peek === undefined || peek.startsWith('--')) val = true;
      else {
        i += 1;
        val = peek;
      }
    } else {
      key = a.slice(2, eq);
      val = a.slice(eq + 1);
    }
    if (val === true) out.flags[key] = true;
    else (out.list[key] ||= []).push(val);
  }
  return out;
}

function newRunId() {
  return new Date().toISOString().replace(/[-:]/g, '').replace(/\.\d+Z$/, 'Z');
}

async function cmdDoctor(cfg) {
  const problems = [];
  const notes = [];

  const exe = resolveExecutable(cfg);
  notes.push(`runner       ${exe || `NOT FOUND (${cfg.runner.command})`}`);
  if (exe && isBatch(exe, cfg.runner.windows ?? {})) {
    notes.push('             (batch shim - spawning through comspec)');
  }
  if (!exe) problems.push(`runner "${cfg.runner.command}" is not on PATH`);

  const variantNote = cfg.worker.variant ? ` (variant: ${cfg.worker.variant})` : '';
  notes.push(`worker       ${cfg.worker.label} -> ${cfg.worker.model}${variantNote}`);
  const allow = cfg.worker.allowedModels ?? [];
  if (allow.length && !allow.includes(cfg.worker.model)) {
    problems.push(`worker.model "${cfg.worker.model}" is not in worker.allowedModels`);
  }

  const sandboxRoot = path.resolve(cfg.paths.sandboxRoot);
  const repoRoot = path.resolve(cfg.__scope.repoRoot);
  const inside = sandboxRoot === repoRoot || sandboxRoot.startsWith(repoRoot + path.sep);
  notes.push(`sandboxRoot  ${sandboxRoot}`);
  notes.push(`repoRoot     ${repoRoot}`);
  if (cfg.isolation.requireSandboxOutsideRepo && inside) {
    problems.push('sandboxRoot is inside repoRoot - the worker would inherit repository context files');
  }

  // opencode walks up from cwd collecting AGENTS.md / CLAUDE.md. Anything found
  // above the sandbox root would be handed to the worker without us choosing it.
  const contextNames = ['AGENTS.md', 'CLAUDE.md', '.opencode'];
  let cur = sandboxRoot;
  for (;;) {
    for (const name of contextNames) {
      const candidate = path.join(cur, name);
      if (cur !== sandboxRoot && fs.existsSync(candidate)) {
        problems.push(`ambient context above sandbox: ${candidate}`);
      }
    }
    const up = path.dirname(cur);
    if (up === cur) break;
    cur = up;
  }

  const rules = loadDenylist(cfg.paths.denylistFile);
  notes.push(`denylist     ${rules.length} rule(s) from ${cfg.paths.denylistFile}`);
  if (!rules.length) problems.push('denylist is empty - the leak guard would pass everything');

  const tasks = loadTasks(cfg);
  const enabled = tasks.filter((t) => t.enabled !== false).length;
  notes.push(`tasks        ${tasks.length} defined, ${enabled} enabled`);
  notes.push(`concurrency  ${num(cfg.execution.concurrency, 1)}`);
  notes.push(`timeout      ${num(cfg.execution.taskTimeoutMs, 0)} ms/task`);

  console.log(notes.map((n) => `  ${n}`).join('\n'));
  if (problems.length) {
    console.log(`\n  ${problems.length} problem(s):`);
    for (const p of problems) console.log(`  x ${p}`);
    process.exitCode = 1;
  } else {
    console.log('\n  ok - ready to dispatch');
  }
}

async function cmdList(cfg) {
  const tasks = loadTasks(cfg);
  if (!tasks.length) {
    console.log(`  no tasks in ${cfg.paths.tasksDir}`);
    return;
  }
  for (const t of tasks) {
    const state = t.enabled === false ? 'disabled' : 'enabled';
    console.log(`  ${t.id.padEnd(28)} ${state.padEnd(9)} ${t.title || ''}`);
  }
}

async function cmdDispatch(cfg, argv) {
  const wanted = argv.list.task ?? [];
  const tasks = selectTasks(cfg, wanted);
  if (!tasks.length) {
    console.log('  nothing to dispatch');
    return;
  }

  const runId = argv.list['run-id']?.[0] ?? newRunId();
  const dryRun = Boolean(argv.flags['dry-run']);
  const rules = loadDenylist(cfg.paths.denylistFile);
  const concurrency = num(cfg.execution.concurrency, 1);
  const runDir = path.join(cfg.paths.runsDir, runId);
  await fsp.mkdir(runDir, { recursive: true });

  console.log(
    `  run ${runId} | ${tasks.length} task(s) | concurrency ${concurrency} | ${cfg.worker.label}${dryRun ? ' | DRY RUN' : ''}\n`,
  );

  const results = await pool(tasks, concurrency, async (task) => {
    const outDir = path.join(runDir, task.id);
    await fsp.mkdir(outDir, { recursive: true });

    let prepared;
    try {
      prepared = await buildSandbox(cfg, task, runId, rules);
    } catch (err) {
      console.log(`  x ${task.id} | prepare failed | ${err.message}`);
      return { id: task.id, status: 'prepare-error', error: err.message };
    }

    if (prepared.hits.length) {
      console.log(`  x ${task.id} | LEAK GUARD blocked ${prepared.hits.length} hit(s)`);
      for (const h of prepared.hits) console.log(`      ${h.where}  rule=${h.rule}  ${h.sample}`);
      await fsp.writeFile(path.join(outDir, 'leaks.json'), JSON.stringify(prepared.hits, null, 2));
      return { id: task.id, status: 'blocked', hits: prepared.hits };
    }

    if (dryRun) {
      console.log(`  . ${task.id} | sandbox ready | ${prepared.sandbox}`);
      return { id: task.id, status: 'dry-run', sandbox: prepared.sandbox };
    }

    console.log(`  > ${task.id} | dispatched`);
    const res = await runWithRetry(cfg, task, prepared.sandbox, outDir, (n, of, last, delay) => {
      console.log(`  ~ ${task.id} | ${last.status} (attempt ${n}/${of + 1}) | retrying in ${Math.round(delay / 1000)}s`);
    });
    const missing = (task.deliverables ?? []).filter((d) => !fs.existsSync(path.join(prepared.sandbox, d)));
    const record = { id: task.id, sandbox: prepared.sandbox, ...res, missingDeliverables: missing };
    await fsp.writeFile(path.join(outDir, 'result.json'), JSON.stringify(record, null, 2));
    const mark = res.status === 'ok' && !missing.length ? 'v' : 'x';
    const tail = missing.length ? ` | missing ${missing.length}: ${missing.join(', ')}` : '';
    console.log(`  ${mark} ${task.id} | ${res.status} | ${Math.round(res.ms / 1000)}s${tail}`);
    return record;
  });

  await fsp.writeFile(
    path.join(runDir, 'run.json'),
    JSON.stringify({ runId, worker: cfg.worker, dryRun, results }, null, 2),
  );
  console.log(`\n  results -> ${runDir}`);
  if (results.some((r) => r.status !== 'ok' && r.status !== 'dry-run')) process.exitCode = 1;
}

async function cmdStatus(cfg, argv) {
  const runsDir = cfg.paths.runsDir;
  if (!fs.existsSync(runsDir)) {
    console.log('  no runs yet');
    return;
  }
  const runs = fs.readdirSync(runsDir).sort();
  const target = argv.list['run-id']?.[0] ?? runs[runs.length - 1];
  if (!target) {
    console.log('  no runs yet');
    return;
  }
  const file = path.join(runsDir, target, 'run.json');
  if (!fs.existsSync(file)) {
    console.log(`  run ${target} has no run.json (still in flight?)`);
    return;
  }
  const run = readJson(file);
  console.log(`  run ${run.runId} | ${run.worker.label} | ${run.results.length} task(s)\n`);
  for (const r of run.results) {
    const extra = r.missingDeliverables?.length ? ` missing: ${r.missingDeliverables.join(', ')}` : '';
    console.log(`  ${r.status === 'ok' ? 'v' : 'x'} ${r.id.padEnd(28)} ${String(r.status).padEnd(14)}${extra}`);
  }
}

async function cmdCollect(cfg, argv) {
  const runId = argv.list['run-id']?.[0];
  if (!runId) throw new Error('collect requires --run-id');
  const run = readJson(path.join(cfg.paths.runsDir, runId, 'run.json'));
  const ignore = cfg.collect.ignore ?? [];
  for (const r of run.results) {
    if (!r.sandbox || !fs.existsSync(r.sandbox)) continue;
    const dest = path.join(cfg.paths.runsDir, runId, r.id, cfg.collect.outputDirname);
    await fsp.rm(dest, { recursive: true, force: true });
    const files = await walk(r.sandbox, r.sandbox, ignore);
    for (const rel of files) {
      const to = path.join(dest, rel);
      await fsp.mkdir(path.dirname(to), { recursive: true });
      await fsp.copyFile(path.join(r.sandbox, rel), to);
    }
    console.log(`  ${r.id} | ${files.length} file(s) -> ${dest}`);
  }
}

async function cmdSweep(cfg, argv) {
  const rules = loadDenylist(cfg.paths.denylistFile);
  const targets = argv._.slice(1);
  if (!targets.length) throw new Error('sweep requires one or more file paths');
  let total = 0;
  for (const t of targets) {
    const hits = await sweepFile(path.resolve(t), rules, cfg.isolation, t);
    total += hits.length;
    if (!hits.length) console.log(`  v ${t}`);
    else for (const h of hits) console.log(`  x ${t}  rule=${h.rule}  ${h.sample}`);
  }
  if (total) process.exitCode = 1;
}

const COMMANDS = {
  doctor: cmdDoctor,
  list: cmdList,
  dispatch: cmdDispatch,
  status: cmdStatus,
  collect: cmdCollect,
  sweep: cmdSweep,
};

async function main() {
  const argv = parseArgv(process.argv.slice(2));
  const command = argv._[0] ?? 'doctor';
  const handler = COMMANDS[command];
  if (!handler) {
    console.error(`unknown command: ${command}`);
    console.error(`usage: orchestrator.mjs <${Object.keys(COMMANDS).join('|')}> [--task id] [--run-id id] [--dry-run]`);
    process.exit(2);
  }
  await handler(loadConfig(), argv);
}

main().catch((err) => {
  console.error(`orchestrator: ${err.message}`);
  process.exit(1);
});
