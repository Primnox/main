/* Entry point. Wires the persistent shell, registers per-page lifecycles,
   and runs the intro. */

import { bus, env, addTick } from './core.js';
import { initCurtain, curtainOut, playIntro, shouldPlayIntro, markIntroSeen } from './curtain.js';
import { initCursor } from './cursor.js';
import { initBlob, bindHero, revealHero, refreshBlobRects } from './blob.js';
import { initParticles, destroyParticles } from './particles.js';
import { initReveal, destroyReveal } from './reveal.js';
import { initChat, destroyChat } from './chat.js';
import { initRouter, registerPage } from './router.js';
import { initTheme } from './theme.js';

/* ─── PER-PAGE LIFECYCLE ───
   One definition drives both the first load and every router navigation, so
   the two paths cannot drift apart. */
const PAGES = {
  home:     { showcase: true,  seed: false },
  product:  { showcase: true,  seed: false },
  privacy:  { showcase: false, seed: false },
  download: { showcase: false, seed: false },
  seed:     { showcase: false, seed: true },
  404:      { showcase: false, seed: false },
};

function setupPage(name) {
  const cfg = PAGES[name] || PAGES['404'];
  initReveal();
  if (cfg.showcase) { initChat(); initParticles(); }
  // The 2048-word BIP-39 list is ~7KB gzipped and only /seed/ needs it.
  if (cfg.seed) import('./seed.js').then((m) => m.initSeed());
  const hero = document.querySelector('.hero');
  bindHero(hero);
  refreshBlobRects();
  return hero;
}

function teardownPage(name) {
  const cfg = PAGES[name] || PAGES['404'];
  destroyReveal();
  if (cfg.showcase) { destroyChat(); destroyParticles(); }
  bindHero(null);
}

for (const name of Object.keys(PAGES)) {
  registerPage(name, {
    setup: () => setupPage(name),
    teardown: () => teardownPage(name),
  });
}

/* ─── PERF GOVERNOR ───
   One-way ratchet. Stepping quality back up on recovery causes oscillation,
   which is more distracting than staying at the lower tier. */
function initGovernor() {
  if (env.reduceMotion) return;

  let tier = 0;
  let frames = 0;
  let total = 0;
  let strikes = 0;

  addTick((now, dt) => {
    total += dt;
    if (++frames < 60) return;

    const mean = total / frames;
    frames = 0;
    total = 0;

    if (mean > 20) {
      if (++strikes >= 2 && tier < 3) {
        tier += 1;
        strikes = 0;
        bus.emit('perf:tier', tier);
        console.info(`[perf] tier ${tier} (mean frame ${mean.toFixed(1)}ms)`);
      }
    } else {
      strikes = 0;
    }
  }, 99);
}

function initNavDrawer() {
  const toggle = document.getElementById('navToggle');
  const drawer = document.getElementById('navDrawer');
  if (!toggle || !drawer) return;

  const setOpen = (open) => {
    toggle.setAttribute('aria-expanded', String(open));
    toggle.setAttribute('aria-label', open ? 'Close menu' : 'Open menu');
    drawer.classList.toggle('open', open);
    if (open) drawer.removeAttribute('inert');
    else drawer.setAttribute('inert', '');
    document.body.style.overflow = open ? 'hidden' : '';
  };

  toggle.addEventListener('click', () => {
    setOpen(toggle.getAttribute('aria-expanded') !== 'true');
  });

  // The router intercepts these links, so close on any navigation rather than
  // wiring per-link handlers.
  bus.on('page:setup', () => setOpen(false));
  drawer.addEventListener('click', (e) => { if (e.target.closest('a')) setOpen(false); });
  addEventListener('keydown', (e) => { if (e.key === 'Escape') setOpen(false); });
}

function initNavScroll() {
  const nav = document.getElementById('nav');
  if (!nav) return;
  let last = false;
  addEventListener('scroll', () => {
    const slim = scrollY > 50;
    if (slim !== last) { nav.classList.toggle('slim', slim); last = slim; }
  }, { passive: true });
}

/* ─── BOOT ─── */
function start() {
  initTheme();
  initCurtain();
  initCursor();
  initBlob();
  initNavScroll();
  initNavDrawer();
  initRouter();
  initGovernor();

  const hero = setupPage(document.body.dataset.page);

  if (shouldPlayIntro()) {
    // Arm before the intro so the lines are already hidden when it lifts.
    document.querySelector('.hero-h1')?.classList.add('reveal-armed');
    // Fired mid-flight, not on completion — the two motions overlap.
    bus.on('intro:handoff', () => revealHero(hero));
    playIntro();
  } else {
    markIntroSeen();
    document.documentElement.classList.remove('intro-pending');
    curtainOut();
    revealHero(hero);
  }

  // The entrance is a one-off. Replaying it on every router return to Home
  // turns a flourish into a tic.
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', start, { once: true });
} else {
  start();
}
