/* Client-side router.

   This is an enhancement layer, never the only way to navigate. Every anchor
   points at a real, complete, standalone document; if anything here throws,
   fails, or is slow, we fall through to a plain browser navigation. The reason
   it exists at all is state persistence: a real page load destroys the particle
   canvas and resets the blob's easing, which is exactly the seam the design is
   meant to remove. */

import { curtainIn, curtainOut } from './curtain.js';
import { bus } from './core.js';

const FETCH_TIMEOUT = 4000;
const CACHE_MAX = 6;

const lifecycles = new Map();
const cache = new Map();

let enabled = true;
let navigating = null;
let abortCtl = null;
let historyIdx = 0;
let liveRegion, mainEl;

export function registerPage(name, hooks) {
  lifecycles.set(name, hooks);
}

export function initRouter() {
  mainEl = document.getElementById('app');
  liveRegion = document.getElementById('a11y-live');
  if (!mainEl) return;

  if ('scrollRestoration' in history) history.scrollRestoration = 'manual';

  historyIdx = 0;
  history.replaceState({ idx: 0, page: document.body.dataset.page, scroll: 0 }, '');

  document.addEventListener('click', onClick);
  addEventListener('popstate', onPopState);
  addEventListener('pagehide', saveScroll);

  document.addEventListener('pointerenter', onHover, true);
  document.addEventListener('focusin', onHover);

  if (!navigator.connection?.saveData) {
    const idle = window.requestIdleCallback || ((fn) => setTimeout(fn, 800));
    idle(prefetchAll);
  }
}

/* ─── INTERCEPTION ─── */
function shouldIntercept(a, ev) {
  if (!enabled || !a) return false;
  if (ev.defaultPrevented || ev.button !== 0) return false;
  if (ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.altKey) return false;
  if (a.target && a.target !== '_self') return false;
  if (a.hasAttribute('download') || a.dataset.noRouter !== undefined) return false;
  if (a.getAttribute('rel')?.includes('external')) return false;

  const href = a.getAttribute('href');
  if (!href || href.startsWith('#') || /^(mailto|tel|javascript):/i.test(href)) return false;

  const url = new URL(a.href);
  if (url.origin !== location.origin) return false;

  // Same page, hash only — native scrolling already does the right thing.
  if (url.pathname === location.pathname && url.hash) return false;

  // Anything that is not a document route is an asset link.
  if (!url.pathname.endsWith('/') && !url.pathname.endsWith('.html')) return false;

  return true;
}

function onClick(ev) {
  const a = ev.target.closest?.('a[href]');
  if (!shouldIntercept(a, ev)) return;
  ev.preventDefault();
  navigate(a.href, { label: a.dataset.label || a.textContent.trim() });
}

function onHover(ev) {
  const a = ev.target.closest?.('a[href]');
  if (!a || !enabled) return;
  try {
    const url = new URL(a.href);
    if (url.origin === location.origin) prefetch(url.href);
  } catch { /* malformed href, ignore */ }
}

/* ─── NAVIGATION ─── */
export async function navigate(href, opts = {}) {
  if (!enabled) return hardNavigate(href);

  const url = new URL(href, location.href);
  if (url.href === location.href && !opts.force) return;

  // Users double-click nav links. Dropping the second click feels broken, so
  // abandon the in-flight navigation and honour the newer one.
  if (navigating) abortCtl?.abort();

  const token = {};
  navigating = token;
  abortCtl = new AbortController();

  saveScroll();

  try {
    // Fetch and curtain run together. Serialising them is the classic
    // hand-rolled-router mistake and doubles perceived latency.
    const docPromise = fetchDocument(url.href, abortCtl.signal);
    const curtainPromise = curtainIn(labelFor(url, opts.label));

    const doc = await Promise.race([
      docPromise,
      new Promise((_, rej) => setTimeout(() => rej(new Error('timeout')), FETCH_TIMEOUT)),
    ]);
    await curtainPromise;

    if (navigating !== token) return;

    teardown();
    commit(doc, url);

    if (opts.push !== false) {
      historyIdx += 1;
      history.pushState({ idx: historyIdx, page: document.body.dataset.page, scroll: 0 }, '', url.href);
    }

    applyScroll(url, opts.restoreScroll);
    setup();

    // Two frames: one guarantees style is resolved, two guarantees the new DOM
    // has actually painted. Lifting after one shows a blank flash.
    await nextFrame();
    await nextFrame();

    if (navigating !== token) return;
    navigating = null;

    announce();
    await curtainOut(opts.direction || 'forward');
    focusHeading();
  } catch (err) {
    if (err?.name === 'AbortError') return;
    console.warn('[router] falling back to hard navigation:', err.message);
    enabled = false;  // one strike: degrade for the rest of the session
    hardNavigate(url.href);
  }
}

function labelFor(url, fallback) {
  const seg = url.pathname.replace(/\/index\.html$/, '/').split('/').filter(Boolean).pop();
  return (seg || 'Primnox').replace(/\.html$/, '');
}

async function fetchDocument(href, signal) {
  if (cache.has(href)) return cache.get(href).cloneNode(true);

  const res = await fetch(href, { signal, headers: { 'X-Requested-With': 'router' } });
  // Never render a 404 body at a URL the browser thinks returned 200 — let the
  // real page load with the real status code.
  if (!res.ok) throw new Error(`status ${res.status}`);
  if (!res.headers.get('content-type')?.includes('text/html')) throw new Error('not html');

  const doc = new DOMParser().parseFromString(await res.text(), 'text/html');
  if (!doc.getElementById('app')) throw new Error('no #app in response');

  store(href, doc);
  return doc.cloneNode(true);
}

function store(href, doc) {
  cache.set(href, doc);
  if (cache.size > CACHE_MAX) cache.delete(cache.keys().next().value);
}

function commit(doc, url) {
  const incoming = doc.getElementById('app');
  mainEl.replaceChildren(...incoming.childNodes);
  mainEl.className = incoming.className;

  document.title = doc.title;
  document.body.dataset.page = doc.body.dataset.page || '';

  const desc = doc.querySelector('meta[name="description"]')?.content;
  if (desc) {
    const meta = document.querySelector('meta[name="description"]');
    if (meta) meta.content = desc;
  }

  const canonical = document.querySelector('link[rel="canonical"]');
  if (canonical) canonical.href = url.href;

  const here = url.pathname;
  document.querySelectorAll('.nav-links a, .f-links a').forEach((a) => {
    const match = new URL(a.href).pathname === here;
    if (match) a.setAttribute('aria-current', 'page');
    else a.removeAttribute('aria-current');
  });
}

function applyScroll(url, restore) {
  if (url.hash) {
    const target = document.getElementById(url.hash.slice(1));
    if (target) { target.scrollIntoView({ behavior: 'instant', block: 'start' }); return; }
  }
  scrollTo({ top: restore || 0, behavior: 'instant' });
}

function teardown() {
  mainEl.setAttribute('inert', '');
  const page = document.body.dataset.page;
  try { lifecycles.get(page)?.teardown?.(); } catch (e) { console.error('[router] teardown', e); }
  bus.emit('page:teardown', page);
}

function setup() {
  mainEl.removeAttribute('inert');
  const page = document.body.dataset.page;
  try { lifecycles.get(page)?.setup?.(); } catch (e) { console.error('[router] setup', e); }
  bus.emit('page:setup', page);
}

function announce() {
  if (!liveRegion) return;
  // Setting textContent in the same task as the DOM swap is missed by several
  // screen readers; a short delay makes the announcement reliable.
  setTimeout(() => { liveRegion.textContent = `${document.title} — page loaded`; }, 150);
}

function focusHeading() {
  const h = mainEl.querySelector('h1');
  if (!h) return;
  h.setAttribute('tabindex', '-1');
  h.focus({ preventScroll: true });
}

/* ─── HISTORY ─── */
function saveScroll() {
  try {
    history.replaceState({ ...history.state, scroll: scrollY }, '');
  } catch { /* state not cloneable, non-fatal */ }
}

function onPopState(ev) {
  if (!enabled) return;
  // No state means the entry predates the router (or is a bare hash change).
  if (!ev.state) {
    if (location.hash) return;
    return hardNavigate(location.href);
  }
  const direction = ev.state.idx < historyIdx ? 'back' : 'forward';
  historyIdx = ev.state.idx;
  navigate(location.href, {
    push: false,
    restoreScroll: ev.state.scroll || 0,
    direction,
    force: true,
  });
}

/* ─── PREFETCH ─── */
function prefetch(href) {
  if (cache.has(href) || href === location.href) return;
  const t = navigator.connection?.effectiveType;
  if (t === 'slow-2g' || t === '2g') return;

  fetch(href, { headers: { 'X-Requested-With': 'router-prefetch' } })
    .then((r) => (r.ok && r.headers.get('content-type')?.includes('text/html') ? r.text() : null))
    .then((html) => {
      if (!html || cache.has(href)) return;
      store(href, new DOMParser().parseFromString(html, 'text/html'));
    })
    .catch(() => { /* prefetch is best-effort */ });
}

function prefetchAll() {
  document.querySelectorAll('.nav-links a, .f-links a').forEach((a) => {
    try {
      const url = new URL(a.href);
      if (url.origin === location.origin) prefetch(url.href);
    } catch { /* ignore */ }
  });
}

/* ─── FALLBACK ─── */
function hardNavigate(href) {
  navigating = null;
  // Deliberately does NOT lift the curtain: the real navigation paints behind
  // it, so a fallback reads as a slightly longer transition, not an error.
  setTimeout(() => curtainOut(), 8000);  // deadman, in case the load hangs
  location.href = href;
}

const nextFrame = () => new Promise((r) => requestAnimationFrame(r));

addEventListener('error', () => { if (navigating) enabled = false; });
addEventListener('unhandledrejection', () => { if (navigating) enabled = false; });
