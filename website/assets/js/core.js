/* Shared primitives: event bus, environment queries, one ticker for everything. */

/* ─── EVENT BUS ─── */
const listeners = new Map();

export const bus = {
  on(evt, fn) {
    if (!listeners.has(evt)) listeners.set(evt, new Set());
    listeners.get(evt).add(fn);
    return () => bus.off(evt, fn);
  },
  off(evt, fn) {
    listeners.get(evt)?.delete(fn);
  },
  emit(evt, payload) {
    const set = listeners.get(evt);
    if (!set) return;
    for (const fn of [...set]) {
      try { fn(payload); } catch (err) { console.error(`[bus] ${evt}`, err); }
    }
  },
};

/* ─── ENVIRONMENT ─── */
const mqReduce = matchMedia('(prefers-reduced-motion: reduce)');
const mqFine = matchMedia('(hover: hover) and (pointer: fine)');

/* Query-string overrides, for reviewing the motion work on a machine that has
   "reduce motion" enabled at the OS level — otherwise none of it is visible.
     ?motion=on   force the full experience
     ?motion=off  force the reduced path
     ?intro       replay the intro on every load (implies motion=on)
   Reloads keep the query string, so ?intro alone gives a repeatable loop. */
const qs = new URLSearchParams(location.search);
const motionParam = qs.get('motion');
export const debug = {
  replayIntro: qs.has('intro'),
  forceMotion: motionParam === 'on' || qs.has('intro'),
  forceReduce: motionParam === 'off',
};

export const env = {
  get reduceMotion() {
    if (debug.forceMotion) return false;
    if (debug.forceReduce) return true;
    return mqReduce.matches;
  },
  get finePointer() { return mqFine.matches; },
  get saveData() { return navigator.connection?.saveData === true; },
  get slowNet() {
    const t = navigator.connection?.effectiveType;
    return t === 'slow-2g' || t === '2g';
  },
  get lowEnd() {
    return (navigator.hardwareConcurrency || 8) <= 4 || (navigator.deviceMemory || 8) <= 4;
  },
};

mqReduce.addEventListener('change', () => bus.emit('env:motion', mqReduce.matches));
mqFine.addEventListener('change', () => bus.emit('env:pointer', mqFine.matches));

/* ─── TICKER ───
   Everything animating rides gsap.ticker. A second rAF loop alongside GSAP's
   would interleave reads and writes across callbacks and thrash layout. */
const callbacks = [];
let running = false;
let last = 0;

function loop(time) {
  // gsap.ticker passes seconds; convert and clamp so a tab-restore stall
  // cannot deliver a multi-second dt to an integrator.
  const now = time * 1000;
  let dt = last ? now - last : 16.667;
  last = now;
  if (dt > 50) dt = 50;

  for (let i = 0; i < callbacks.length; i++) {
    const cb = callbacks[i];
    if (cb.active) cb.fn(now, dt);
  }
}

export function addTick(fn, order = 0) {
  const entry = { fn, order, active: true };
  callbacks.push(entry);
  callbacks.sort((a, b) => a.order - b.order);
  if (!running) {
    gsap.ticker.add(loop);
    gsap.ticker.lagSmoothing(500, 33);
    running = true;
  }
  return {
    pause() { entry.active = false; },
    resume() { entry.active = true; },
    destroy() {
      const i = callbacks.indexOf(entry);
      if (i > -1) callbacks.splice(i, 1);
    },
  };
}

document.addEventListener('visibilitychange', () => {
  if (!document.hidden) last = 0;
});

/* ─── MATH ─── */

/* Frame-rate-independent lerp. A raw `x += (t - x) * k` converges twice as
   fast on a 120Hz display as on 60Hz, which makes every easing constant a lie. */
export function lerpFactor(base, dt) {
  return 1 - Math.pow(1 - base, dt / 16.667);
}

export const clamp = (v, lo, hi) => (v < lo ? lo : v > hi ? hi : v);

export function smoothstep(edge0, edge1, x) {
  const t = clamp((x - edge0) / (edge1 - edge0), 0, 1);
  return t * t * (3 - 2 * t);
}

/* ─── POINTER ───
   One coalesced pointer position, read by cursor and blob. Writing transforms
   directly in a pointermove handler means 1000 style writes/sec on a gaming
   mouse; this defers all writes to the tick. */
export const pointer = { x: innerWidth / 2, y: innerHeight / 2, seen: false };

addEventListener('pointermove', (e) => {
  pointer.x = e.clientX;
  pointer.y = e.clientY;
  if (!pointer.seen) {
    pointer.seen = true;
    bus.emit('pointer:first');
  }
}, { passive: true });
