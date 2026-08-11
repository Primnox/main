/* The website has no build step, so the persistent shell (fx layers, curtain,
   intro, nav, footer) is physically duplicated in every page. The router
   assumes those copies are identical — if one drifts, navigation swaps <main>
   into a shell that no longer matches and the failure is subtle.
   This compares the <!-- shell:start --> … <!-- shell:end --> regions and the
   asset <link>/<script> set across pages, and fails the deploy on a mismatch. */

import { readFile, readdir } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { join, relative } from 'node:path';

const ROOT = 'website';
const SHELL_RE = /<!-- shell:start -->([\s\S]*?)<!-- shell:end -->/g;

async function htmlFiles(dir) {
  const out = [];
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === 'assets') continue;
      out.push(...(await htmlFiles(path)));
    } else if (entry.name.endsWith('.html')) {
      out.push(path);
    }
  }
  return out;
}

// aria-current legitimately differs per page (and the router rewrites it on
// navigation), so it is not part of what "identical shell" means here.
const norm = (s) => s.replace(/\s*aria-current=["']page["']/g, '').replace(/\s+/g, ' ').trim();
const hash = (s) => createHash('sha256').update(s).digest('hex').slice(0, 12);

const files = (await htmlFiles(ROOT)).sort();
const shells = new Map();
const assets = new Map();
const problems = [];

for (const file of files) {
  const html = await readFile(file, 'utf8');
  const rel = relative(ROOT, file).replace(/\\/g, '/');

  const regions = [...html.matchAll(SHELL_RE)].map((m) => norm(m[1]));

  // Redirect stubs legitimately have no shell.
  if (regions.length === 0) {
    if (!/http-equiv=["']refresh/i.test(html)) {
      problems.push(`${rel}: no shell markers and not a redirect stub`);
    }
    continue;
  }

  const key = hash(regions.join('\n---\n'));
  if (!shells.has(key)) shells.set(key, []);
  shells.get(key).push(rel);

  const refs = [...html.matchAll(/(?:href|src)=["'](\/assets\/[^"']+)["']/g)]
    .map((m) => m[1])
    .sort();
  const aKey = hash(refs.join('|'));
  if (!assets.has(aKey)) assets.set(aKey, { refs, pages: [] });
  assets.get(aKey).pages.push(rel);
}

if (shells.size > 1) {
  problems.push('shell regions differ between pages:');
  for (const [key, pages] of shells) problems.push(`  ${key}  ${pages.join(', ')}`);
}

// 404.html intentionally preloads fewer fonts; only flag pages that reference
// an asset path no other page does.
const allRefs = new Set([...assets.values()].flatMap((a) => a.refs));
for (const { refs, pages } of assets.values()) {
  for (const ref of refs) {
    if (!allRefs.has(ref)) problems.push(`${pages.join(', ')}: unknown asset ${ref}`);
  }
}

const missing = [];
for (const ref of allRefs) {
  try {
    await readFile(join(ROOT, ref.replace(/^\//, '')));
  } catch {
    missing.push(ref);
  }
}
if (missing.length) problems.push(`referenced assets not found: ${missing.join(', ')}`);

if (problems.length) {
  console.error('Shell parity check FAILED\n');
  problems.forEach((p) => console.error(p));
  process.exit(1);
}

console.log(`Shell parity OK — ${files.length} html files, 1 shell variant, ${allRefs.size} assets resolved.`);
