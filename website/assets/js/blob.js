/* Gooey metaball trail.

   The SVG filter runs on a 520px layer that is itself translated to the
   pointer, not on a full-viewport element. Filter cost scales with the filter
   region's area, so a full-screen goo at 1440p pushes ~35x more pixels through
   the Gaussian every frame — enough on its own to blow the budget the particle
   canvas also needs. */

import { env, pointer, addTick, bus, lerpFactor, clamp } from './core.js';

/* Colours stay as var() references, so a theme switch repaints them with no
   JS involvement at all. */
const BLOBS = [
  { r: 46, lerp: 0.180, orbit: 0,  phase: 0.00,  color: 'var(--primary)' },
  { r: 34, lerp: 0.100, orbit: 14, phase: 0.00,  color: 'var(--primary)' },
  { r: 26, lerp: 0.075, orbit: 16, phase: 2.09,  color: 'var(--accent)'  },
  { r: 20, lerp: 0.055, orbit: 18, phase: 4.19,  color: 'var(--primary)' },
];

const ORBIT_SPEED = 0.0012;

let layer, nodes, tick;
let enabled = false;
let quality = 1;

const state = { scale: 1, magnet: 0, tx: 0, ty: 0 };
let hoverRect = null;

export function initBlob() {
  layer = document.querySelector('.blob-layer');
  if (!layer) return;

  if (!env.finePointer || env.reduceMotion) {
    layer.style.display = 'none';
    bus.on('env:motion', () => { if (!env.reduceMotion && env.finePointer) enable(); });
    return;
  }
  enable();
}

function enable() {
  if (enabled) return;
  enabled = true;
  layer.style.display = '';

  nodes = BLOBS.map((b) => {
    const d = document.createElement('div');
    d.className = 'blob';
    d.style.width = d.style.height = `${b.r * 2}px`;
    d.style.background = b.color;
    layer.appendChild(d);
    return { el: d, x: pointer.x, y: pointer.y, cfg: b };
  });

  state.tx = pointer.x;
  state.ty = pointer.y;

  document.addEventListener('pointerover', onOver);
  document.addEventListener('pointerout', onOut);

  tick = addTick(step, 20);
  bus.on('env:motion', () => { if (env.reduceMotion) disable(); });
  bus.on('perf:tier', onTier);
}

function disable() {
  if (!enabled) return;
  enabled = false;
  tick?.destroy();
  layer.style.display = 'none';
  layer.replaceChildren();
}

function onOver(e) {
  const t = e.target.closest?.('a, button, [data-blob="grow"]');
  if (!t) return;
  hoverRect = t.getBoundingClientRect();
  gsap.to(state, { scale: 1.55, magnet: 0.35, duration: 0.5, ease: 'expo.out' });
}

function onOut(e) {
  if (!e.target.closest?.('a, button, [data-blob="grow"]')) return;
  hoverRect = null;
  gsap.to(state, { scale: 1, magnet: 0, duration: 0.55, ease: 'power3.out' });
}

function step(now, dt) {
  // Lean toward the hovered element's centre rather than tracking the pointer
  // exactly — this is what reads as magnetism.
  let targetX = pointer.x;
  let targetY = pointer.y;
  if (hoverRect && state.magnet > 0.001) {
    const cx = hoverRect.left + hoverRect.width / 2;
    const cy = hoverRect.top + hoverRect.height / 2;
    targetX += (cx - targetX) * state.magnet;
    targetY += (cy - targetY) * state.magnet;
  }

  const lead = lerpFactor(0.22, dt);
  state.tx += (targetX - state.tx) * lead;
  state.ty += (targetY - state.ty) * lead;
  layer.style.transform = `translate3d(${state.tx}px, ${state.ty}px, 0)`;

  const count = quality === 1 ? nodes.length : 2;
  for (let i = 0; i < nodes.length; i++) {
    const n = nodes[i];
    if (i >= count) { n.el.style.opacity = '0'; continue; }
    n.el.style.opacity = '1';

    const k = lerpFactor(n.cfg.lerp, dt);
    n.x += (targetX - n.x) * k;
    n.y += (targetY - n.y) * k;

    // Orbital drift keeps the mass alive when the pointer is still.
    const a = now * ORBIT_SPEED + n.cfg.phase;
    const ox = Math.cos(a) * n.cfg.orbit;
    const oy = Math.sin(a * 1.3) * n.cfg.orbit;

    // Positions are local to the translated layer, so subtract its origin.
    const lx = n.x - state.tx + ox;
    const ly = n.y - state.ty + oy;
    const s = state.scale;
    n.el.style.transform = `translate3d(calc(-50% + ${lx}px), calc(-50% + ${ly}px), 0) scale(${s})`;
  }

  updateTint();
}

/* Drives the hero headline's clipped gradient from the blob position, so the
   colour lands inside the glyphs instead of washing out behind them. */
const heroOpacity = () =>
  parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--fx-op')) || 0.34;
let tintTarget = null;
let tintRect = null;
let heroIO = null;

/* The blob belongs to the hero. #fx sits behind <main>, which has no opaque
   background, so an always-on layer bleeds through every later section. */
/* Yamauchi-style line entrance. Returns a promise so the caller can sequence
   it after the intro curtain lifts rather than racing it. */
export function revealHero(heroEl) {
  const h1 = heroEl?.querySelector('.hero-h1');
  if (!h1) return Promise.resolve();

  // The tint overlay is a second full copy of the headline, so a plain DOM-order
  // stagger would run base lines 0-2 then tint lines 3-5 and the gradient would
  // visibly lag the text. Stagger by line index instead.
  const base = [...h1.querySelectorAll(':scope > .hl > .hl-i')];
  const tint = [...h1.querySelectorAll(':scope > .h1-tint > .hl > .hl-i')];
  const perCopy = base.length || 1;
  const lines = [...base, ...tint];
  if (!lines.length) return Promise.resolve();

  if (env.reduceMotion) {
    h1.classList.remove('reveal-armed');
    gsap.set(lines, { clearProps: 'transform' });
    return Promise.resolve();
  }

  // Drop the CSS pre-hide *before* GSAP touches these elements. If the class is
  // still applied, GSAP snapshots the computed translateY(130%), bakes it into
  // the inline transform as a fixed translate3d, and then animates its own
  // layer to zero on top of it — so the lines settle 130% low and only snap
  // into place when clearProps runs. fromTo renders its from-state
  // synchronously, so there is no flash between the two statements.
  h1.classList.remove('reveal-armed');

  return new Promise((resolve) => {
    gsap.fromTo(lines,
      { yPercent: 130 },
      {
        yPercent: 0,
        duration: 1.15,
        ease: 'expo.out',
        stagger: (i) => (i % perCopy) * 0.085,
        onComplete: () => { gsap.set(lines, { clearProps: 'transform' }); resolve(); },
      });
  });
}

export function bindHero(heroEl) {
  heroIO?.disconnect();
  heroIO = null;
  tintTarget = heroEl?.querySelector('.hero-h1') || null;
  tintRect = null;

  if (!enabled || !layer) return;

  if (!heroEl) {
    gsap.to(layer, { opacity: 0, duration: 0.3, ease: 'power2.out' });
    return;
  }

  heroIO = new IntersectionObserver(([e]) => {
    gsap.to(layer, {
      opacity: e.isIntersecting ? heroOpacity() : 0,
      duration: 0.45,
      ease: 'power2.out',
    });
  }, { threshold: 0.04 });
  heroIO.observe(heroEl);
}

function updateTint() {
  if (!tintTarget) return;
  if (!tintRect) tintRect = tintTarget.getBoundingClientRect();
  const px = clamp(((state.tx - tintRect.left) / tintRect.width) * 100, -30, 130);
  const py = clamp(((state.ty - tintRect.top) / tintRect.height) * 100, -60, 160);
  tintTarget.style.setProperty('--tint-x', `${px}%`);
  tintTarget.style.setProperty('--tint-y', `${py}%`);
}

export function refreshBlobRects() {
  tintRect = tintTarget ? tintTarget.getBoundingClientRect() : null;
  hoverRect = null;
}

function onTier(tier) {
  quality = tier >= 2 ? 0 : 1;
  if (tier >= 3) disable();
}

addEventListener('resize', refreshBlobRects, { passive: true });
addEventListener('scroll', () => { tintRect = null; }, { passive: true });
