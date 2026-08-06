/**
 * Headless smoke test against the production build.
 *
 * Replaces the ad-hoc `test_browser.cjs` / `test_notes.cjs` scripts, which
 * needed a live dev server plus a live backend and only printed results without
 * ever failing. This one serves the built `dist/`, drives it with no backend
 * running — the realistic worst case, and the state that surfaced both bugs
 * below — and exits non-zero on regression.
 *
 * Guards:
 *   - no uncaught exceptions in either window mode
 *   - the app actually renders rather than blanking
 *   - no request storms (a runaway effect once hit /api/dashboard ~500x/sec)
 *   - no calls to any external host (webfonts are vendored; the app is
 *     supposed to be able to run entirely offline)
 *   - no horizontal overflow at common window sizes
 *
 * Usage:  npm run build && npm run test:e2e
 */

import { spawn } from 'node:child_process';
import { chromium } from 'playwright';

const PORT = Number(process.env.E2E_PORT ?? 4183);
const ORIGIN = `http://localhost:${PORT}`;
const LOCAL_HOSTS = new Set(['localhost', '127.0.0.1', '[::1]']);

// The backend is deliberately not started: this exercises the offline path.
const BACKEND_ORIGIN = 'localhost:4009';

/** Requests to any single endpoint above this in the observation window is a storm. */
const REQUEST_STORM_THRESHOLD = 10;
const OBSERVE_MS = 8000;

const failures = [];
const fail = (msg) => {
  failures.push(msg);
  console.error(`  FAIL  ${msg}`);
};
const pass = (msg) => console.log(`  ok    ${msg}`);

function startPreview() {
  const proc = spawn(
    process.platform === 'win32' ? 'npx.cmd' : 'npx',
    ['vite', 'preview', '--port', String(PORT), '--strictPort'],
    { stdio: 'ignore' },
  );
  return proc;
}

async function waitForServer(timeoutMs = 30000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const res = await fetch(ORIGIN);
      if (res.ok) return;
    } catch {
      /* not up yet */
    }
    await new Promise((r) => setTimeout(r, 400));
  }
  throw new Error(`preview server never became ready on ${ORIGIN}`);
}

async function checkWindow(browser, path, label, { expectMinHtml }) {
  console.log(`\n${label}`);
  const page = await browser.newPage({ viewport: { width: 1200, height: 800 } });

  const uncaught = [];
  const external = new Set();
  const requestCounts = new Map();

  page.on('pageerror', (e) => uncaught.push(e.message));
  page.on('request', (r) => {
    let host;
    try {
      host = new URL(r.url()).host.split(':')[0];
    } catch {
      return;
    }
    if (!LOCAL_HOSTS.has(host)) external.add(new URL(r.url()).origin);
    const key = r.url().split('?')[0];
    requestCounts.set(key, (requestCounts.get(key) ?? 0) + 1);
  });

  await page.goto(ORIGIN + path, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(OBSERVE_MS);

  // ── renders at all ────────────────────────────────────────────────────
  const htmlLength = await page.evaluate(
    () => document.getElementById('root')?.innerHTML.length ?? -1,
  );
  if (htmlLength < expectMinHtml) {
    fail(`${label}: root rendered ${htmlLength} chars, expected >= ${expectMinHtml}`);
  } else {
    pass(`renders (${htmlLength} chars)`);
  }

  // ── no uncaught exceptions ────────────────────────────────────────────
  if (uncaught.length) {
    fail(`${label}: ${uncaught.length} uncaught exception(s): ${uncaught[0]}`);
  } else {
    pass('no uncaught exceptions');
  }

  // ── no request storms ─────────────────────────────────────────────────
  const storms = [...requestCounts.entries()].filter(
    ([, count]) => count > REQUEST_STORM_THRESHOLD,
  );
  if (storms.length) {
    for (const [url, count] of storms) {
      fail(`${label}: ${count} requests to ${url} in ${OBSERVE_MS}ms`);
    }
  } else {
    const worst = Math.max(0, ...requestCounts.values());
    pass(`no request storms (busiest endpoint: ${worst})`);
  }

  // ── backend is polled, but politely ───────────────────────────────────
  const backendHits = [...requestCounts.entries()]
    .filter(([url]) => url.includes(BACKEND_ORIGIN))
    .reduce((n, [, c]) => n + c, 0);
  pass(`backend requests while unreachable: ${backendHits}`);

  // ── nothing leaves the machine ────────────────────────────────────────
  if (external.size) {
    fail(`${label}: contacted external host(s): ${[...external].join(', ')}`);
  } else {
    pass('no external hosts contacted');
  }

  // ── layout ────────────────────────────────────────────────────────────
  for (const [w, h] of [
    [1200, 800],
    [1024, 768],
    [1440, 900],
  ]) {
    await page.setViewportSize({ width: w, height: h });
    await page.waitForTimeout(250);
    const overflows = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth,
    );
    if (overflows) fail(`${label}: horizontal overflow at ${w}x${h}`);
  }
  if (!failures.some((f) => f.includes('horizontal overflow'))) {
    pass('no horizontal overflow at 1024/1200/1440 wide');
  }

  await page.close();
}

async function main() {
  const preview = startPreview();
  let browser;
  try {
    await waitForServer();

    // Prefer the image's preinstalled Chromium when present; Playwright's own
    // download location varies between environments.
    const executablePath = process.env.E2E_CHROMIUM || undefined;
    browser = await chromium.launch({
      executablePath,
      args: ['--no-sandbox'],
    });

    await checkWindow(browser, '/', 'main window', { expectMinHtml: 5000 });
    await checkWindow(browser, '/?primnox_island=1', 'island overlay', {
      expectMinHtml: 500,
    });
  } finally {
    await browser?.close();
    preview.kill();
  }

  console.log('');
  if (failures.length) {
    console.error(`${failures.length} check(s) failed`);
    process.exit(1);
  }
  console.log('all smoke checks passed');
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
