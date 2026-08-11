/* Pseudo-3D particle cloud: the visual body of "Primnox is talking".

   2D canvas, not WebGL. With alpha baked into a sprite atlas and additive
   compositing (which is order-independent, so no depth sort is needed) a few
   thousand sprites cost 2-4ms — and there is no shader compilation, no
   webglcontextlost path, and no third renderer to debug. */

import { addTick, bus, env, clamp, smoothstep } from './core.js';
import { sampleText, clearWordmarkCache } from './wordmark.js';

const AREA_PER_PARTICLE = 120;
const FOV = 620;
const BASE_SIZE = 2.6;
const SPRITE_PX = 32;
const SPRITE_SCALE = 2.5;   // sprite cell drawn larger than its visible core
const PEAK_ALPHA = 0.34;    // additive blending stacks; high peaks blow to white
const ATLAS_COLS = 4;
const ALPHA_TIERS = 4;
/* Sampled from CSS custom properties so the cloud follows the active theme
   instead of pinning the signature palette into the sprite atlas. */
const COLOR_VARS = ['--text', '--primary', '--accent'];
let COLORS = ['#f0ede6', '#c3c0ff', '#ffb695'];

let drawOp = 'lighter';

function readThemeColors() {
  const cs = getComputedStyle(document.documentElement);
  COLORS = COLOR_VARS.map((v, i) => {
    const raw = cs.getPropertyValue(v).trim();
    return raw || COLORS[i];
  });
  // On a light ground the canvas is multiplied onto the page, so accumulating
  // additively inside it would wash the dots out instead of darkening them.
  drawOp = cs.getPropertyValue('--fx-blend').trim() === 'multiply' ? 'source-over' : 'lighter';
}
const FIXED_DT = 1 / 60;
const MAX_SUBSTEPS = 3;

/* Damped harmonic oscillator per state. freq is in Hz, zeta is the damping
   ratio: <1 overshoots, 1 is critical. Expressing it this way keeps the
   integrator's units honest — acceleration in px/s², velocity in px/s. */
const STATES = {
  IDLE:     { freq: 1.10, zeta: 0.95, amp: 3, drag: 0 },
  DISPERSE: { freq: 0,    zeta: 0,    amp: 0, drag: 0.10 },
  THINKING: { freq: 1.50, zeta: 0.75, amp: 0, drag: 0 },
  REFORM:   { freq: 1.90, zeta: 0.55, amp: 2, drag: 0 },
  SPEAKING: { freq: 1.30, zeta: 0.85, amp: 5, drag: 0 },
};

/* Sine LUT — ~15k Math.sin calls per frame at full count is measurable;
   a table lookup is roughly 5x cheaper and visually identical here. */
const LUT_SIZE = 1024;
const SIN_LUT = new Float32Array(LUT_SIZE);
for (let i = 0; i < LUT_SIZE; i++) SIN_LUT[i] = Math.sin((i / LUT_SIZE) * Math.PI * 2);
const fastSin = (t) => SIN_LUT[((t * (LUT_SIZE / (Math.PI * 2))) | 0) & (LUT_SIZE - 1)];

let canvas, ctx, anchor, fallback, atlas;
let dpr = 1, w = 0, h = 0, cx = 0, cy = 0;
let N = 0;
let px, py, pz, vx, vy, vz, tx, ty, tz, seed, cidx, psize;
let state = 'IDLE';
let stateT = 0;
let accum = 0;
let yaw = 0, yawTarget = 0;
let active = false, visible = false, booted = false;
let tick, io, ro;
let speakEnv = 0;
let tier = 0;

/* ─── SPRITE ATLAS ───
   Alpha is baked per tier so the draw loop never writes globalAlpha. State
   changes, not draw calls, are what make canvas2d slow. */
function buildAtlas() {
  const c = document.createElement('canvas');
  c.width = SPRITE_PX * ATLAS_COLS;
  c.height = SPRITE_PX * COLORS.length;
  const g = c.getContext('2d');

  for (let ci = 0; ci < COLORS.length; ci++) {
    for (let ai = 0; ai < ALPHA_TIERS; ai++) {
      const a = ((ai + 1) / ALPHA_TIERS) * PEAK_ALPHA;
      const ox = ai * SPRITE_PX;
      const oy = ci * SPRITE_PX;
      const r = SPRITE_PX / 2;
      const grad = g.createRadialGradient(ox + r, oy + r, 0, ox + r, oy + r, r);
      // A gentler falloff than a plain radial ramp — the hard shoulder at the
      // midpoint is what makes stock particle sprites look like stickers.
      grad.addColorStop(0.00, hexA(COLORS[ci], a));
      grad.addColorStop(0.22, hexA(COLORS[ci], a * 0.78));
      grad.addColorStop(0.50, hexA(COLORS[ci], a * 0.28));
      grad.addColorStop(0.75, hexA(COLORS[ci], a * 0.07));
      grad.addColorStop(1.00, hexA(COLORS[ci], 0));
      g.fillStyle = grad;
      g.fillRect(ox, oy, SPRITE_PX, SPRITE_PX);
    }
  }
  return c;
}

function hexA(color, a) {
  let r = 240, g = 237, b = 230;
  if (color.startsWith('#')) {
    let h = color.slice(1);
    if (h.length === 3) h = h.split('').map((c) => c + c).join('');
    const n = parseInt(h, 16);
    r = (n >> 16) & 255; g = (n >> 8) & 255; b = n & 255;
  } else {
    const m = color.match(/(\d+(?:\.\d+)?)/g);
    if (m && m.length >= 3) [r, g, b] = m.slice(0, 3).map(Number);
  }
  return `rgba(${r},${g},${b},${a})`;
}

/* Golden-angle sphere. Procedural, so no canvas sampling needed. */
function assignSphere(radius) {
  const golden = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < N; i++) {
    const yy = 1 - (i / Math.max(1, N - 1)) * 2;
    const r = Math.sqrt(Math.max(0, 1 - yy * yy));
    const th = golden * i;
    tx[i] = Math.cos(th) * r * radius;
    ty[i] = yy * radius;
    tz[i] = Math.sin(th) * r * radius;
  }
}

function assignShape(pts) {
  const count = pts.length / 2;
  if (!count) return;
  for (let i = 0; i < N; i++) {
    const j = (i % count) * 2;
    const jitter = count < N ? 1.2 : 0;
    tx[i] = pts[j] + (rand(i) - 0.5) * jitter * 2;
    ty[i] = pts[j + 1] + (rand(i + 7) - 0.5) * jitter * 2;
    // Flat planes read as 2D no matter how good the projection is.
    tz[i] = (rand(i + 13) + rand(i + 29) + rand(i + 41) - 1.5) * 62;
  }
}

function rand(i) {
  const x = Math.sin(i * 12.9898 + 78.233) * 43758.5453;
  return x - Math.floor(x);
}

/* ─── LIFECYCLE ─── */
export function initParticles(root = document) {
  anchor = root.querySelector('.fx-anchor');
  if (!anchor) return;

  fallback = anchor.querySelector('.fx-fallback');

  if (env.reduceMotion || env.saveData) {
    showFallback();
    bus.on('env:motion', () => { if (!env.reduceMotion) initParticles(root); });
    return;
  }

  if (!canvas) {
    canvas = document.createElement('canvas');
    ctx = canvas.getContext('2d', { alpha: true, desynchronized: true });
    if (!ctx) { showFallback(); return; }
    readThemeColors();
    atlas = buildAtlas();
  }

  // Moving an existing <canvas> element preserves its bitmap and 2D context,
  // so the pool and atlas survive a page swap intact. That persistence is the
  // whole reason the router swaps <main> instead of doing a real navigation.
  anchor.appendChild(canvas);
  fallback?.classList.remove('on');

  resize();
  if (!booted) {
    booted = true;
    tick = addTick(step, 30);
    bus.on('primnox:state', setState);
    bus.on('perf:tier', onTier);
    bus.on('theme:change', () => { readThemeColors(); atlas = buildAtlas(); });
    // The wordmark must be sampled with the real face loaded, or we silently
    // capture the fallback font on a cold visit.
    document.fonts.ready.then(() => { clearWordmarkCache(); if (state === 'IDLE') applyTarget(); });
  }

  ro?.disconnect();
  ro = new ResizeObserver(debounce(resize, 150));
  ro.observe(anchor);

  io?.disconnect();
  io = new IntersectionObserver((entries) => {
    visible = entries[0].isIntersecting;
    active = visible;
    if (!visible) ctx.clearRect(0, 0, w, h);
  }, { threshold: 0, rootMargin: '200px 0px' });
  io.observe(anchor);

  anchor.addEventListener('pointermove', onAnchorMove, { passive: true });
  anchor.addEventListener('pointerleave', () => { yawTarget = 0; }, { passive: true });
}

export function destroyParticles() {
  io?.disconnect();
  ro?.disconnect();
  anchor?.removeEventListener('pointermove', onAnchorMove);
  active = false;
  // Pool and context deliberately retained — see initParticles.
  canvas?.remove();
  anchor = null;
}

function showFallback() {
  fallback?.classList.add('on');
  canvas?.remove();
  active = false;
}

function onAnchorMove(e) {
  const r = canvas.getBoundingClientRect();
  yawTarget = ((e.clientX - r.left) / r.width - 0.5) * 0.22;
}

function debounce(fn, ms) {
  let t;
  return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}

function resize() {
  if (!anchor || !canvas) return;
  const r = anchor.getBoundingClientRect();
  if (!r.width || !r.height) return;

  dpr = Math.min(devicePixelRatio || 1, 2);
  w = r.width;
  h = r.height;
  canvas.width = Math.round(w * dpr);
  canvas.height = Math.round(h * dpr);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  cx = w / 2;
  cy = h / 2;

  const want = clamp(Math.round((w * h) / AREA_PER_PARTICLE), 900, 2600);
  const capped = capFor(want);
  if (capped !== N) allocate(capped);
  clearWordmarkCache();
  applyTarget();
}

function capFor(n) {
  if (env.saveData || env.slowNet) return Math.min(n, 700);
  if (!env.finePointer) return Math.min(n, 900);
  if (env.lowEnd) return Math.min(n, 1200);
  if (tier >= 1) return Math.min(n, Math.round(n * 0.6));
  return n;
}

function allocate(n) {
  const prev = N;
  N = n;
  const f = () => new Float32Array(n);
  const oldPx = px, oldPy = py, oldPz = pz;
  px = f(); py = f(); pz = f();
  vx = f(); vy = f(); vz = f();
  tx = f(); ty = f(); tz = f();
  seed = f();
  psize = f();
  cidx = new Uint8Array(n);

  for (let i = 0; i < n; i++) {
    if (i < prev && oldPx) { px[i] = oldPx[i]; py[i] = oldPy[i]; pz[i] = oldPz[i]; }
    else {
      px[i] = (Math.random() - 0.5) * w;
      py[i] = (Math.random() - 0.5) * h;
      pz[i] = (Math.random() + Math.random() + Math.random() - 1.5) * 300;
    }
    seed[i] = Math.random() * Math.PI * 2;
    // Uniform dot sizes read as machine-made. Skew small so a few large motes
    // carry the depth cue instead of every particle competing.
    const u = Math.random();
    psize[i] = 0.55 + u * u * 1.5;
    // Mostly cream with a purple minority and a rare warm accent.
    const r = Math.random();
    cidx[i] = r < 0.62 ? 0 : r < 0.94 ? 1 : 2;
  }
}

function applyTarget() {
  if (!N) return;
  if (state === 'THINKING') assignSphere(Math.min(w, h) * 0.28);
  else assignShape(sampleText('PRIMNOX', w * 0.86, h * 0.62, 3));
}

export function setState(next) {
  if (!STATES[next] || next === state) return;
  state = next;
  stateT = 0;

  if (state === 'DISPERSE') {
    for (let i = 0; i < N; i++) {
      const dx = px[i], dy = py[i];
      const len = Math.hypot(dx, dy) || 1;
      const speed = 140 + Math.random() * 90;
      vx[i] += (dx / len) * speed;
      vy[i] += (dy / len) * speed;
      vz[i] -= 120 + Math.random() * 80;
    }
  } else {
    applyTarget();
  }
}

function onTier(t) {
  tier = t;
  if (t >= 3) { showFallback(); return; }
  const want = clamp(Math.round((w * h) / AREA_PER_PARTICLE), 900, 2600);
  allocate(capFor(want));
  applyTarget();
}

/* ─── FRAME ─── */
function step(now, dtMs) {
  if (!active || !N || !ctx) return;

  const cfg = STATES[state];
  stateT += dtMs;

  // DISPERSE is a fixed-length impulse; THINKING is held by the chat script.
  if (state === 'DISPERSE' && stateT > 620) setState('THINKING');
  if (state === 'REFORM' && stateT > 1400) setState('IDLE');

  speakEnv = state === 'SPEAKING'
    ? Math.min(1, speakEnv + dtMs / 400)
    : Math.max(0, speakEnv - dtMs / 600);

  // Fixed-step integration. A raw dt after a tab-restore stall flings every
  // particle to infinity in a single frame, which looks exactly like a crash.
  accum += dtMs / 1000;
  let steps = 0;
  while (accum >= FIXED_DT && steps < MAX_SUBSTEPS) {
    integrate(FIXED_DT, cfg, now);
    accum -= FIXED_DT;
    steps++;
  }
  if (steps === MAX_SUBSTEPS) accum = 0;

  yaw += (yawTarget - yaw) * 0.04;
  render(now);
}

function integrate(dt, cfg, now) {
  const amp = cfg.amp + speakEnv * 6;
  const tNoise = now * 0.0011;

  // Free-flight state: no target, just drag toward a stop.
  if (cfg.freq === 0) {
    const k = Math.pow(cfg.drag, dt);
    for (let i = 0; i < N; i++) {
      vx[i] *= k; vy[i] *= k; vz[i] *= k;
      px[i] += vx[i] * dt;
      py[i] += vy[i] * dt;
      pz[i] += vz[i] * dt;
    }
    return;
  }

  const omega = 2 * Math.PI * cfg.freq;
  const stiff = omega * omega;
  const damping = 2 * cfg.zeta * omega;

  for (let i = 0; i < N; i++) {
    let gx = tx[i], gy = ty[i], gz = tz[i];

    if (amp > 0) {
      const s = seed[i];
      gx += fastSin(tNoise + s) * amp;
      gy += fastSin(tNoise * 0.83 + s * 1.7) * amp;
      gz += fastSin(tNoise * 0.61 + s * 2.3) * amp * 1.5;
    }

    vx[i] += ((gx - px[i]) * stiff - vx[i] * damping) * dt;
    vy[i] += ((gy - py[i]) * stiff - vy[i] * damping) * dt;
    vz[i] += ((gz - pz[i]) * stiff - vz[i] * damping) * dt;

    px[i] += vx[i] * dt;
    py[i] += vy[i] * dt;
    pz[i] += vz[i] * dt;
  }
}

function render(now) {
  // Fade rather than clear. A hard clear each frame gives every particle a
  // crisp stroboscopic edge; a short decay leaves a faint motion trail that
  // reads as volume, and residue is gone within ~10 frames.
  ctx.globalCompositeOperation = 'destination-out';
  ctx.fillStyle = 'rgba(0,0,0,0.34)';
  ctx.fillRect(0, 0, w, h);
  ctx.globalCompositeOperation = drawOp;

  // Gentle oscillation, not continuous rotation: a wordmark that keeps turning
  // spends half its cycle edge-on and reads as a streak.
  const drift = Math.sin(now * 0.00022) * 0.13;
  const cosY = Math.cos(yaw + drift);
  const sinY = Math.sin(yaw + drift);
  const zMin = -FOV + 60;

  for (let i = 0; i < N; i++) {
    const x0 = px[i], z0 = pz[i];
    const xr = x0 * cosY + z0 * sinY;
    const zr = -x0 * sinY + z0 * cosY;

    const z = zr < zMin ? zMin : zr;
    const k = FOV / (FOV + z);
    const sx = cx + xr * k;
    const sy = cy + py[i] * k;

    if (sx < -20 || sx > w + 20 || sy < -20 || sy > h + 20) continue;

    const fog = 1 - smoothstep(140, 520, z);
    // Slow, per-particle brightness drift. Nothing in nature holds a constant
    // luminance, and the uniformity is very visible across a few thousand dots.
    const tw = 0.72 + 0.28 * fastSin(now * 0.0013 + seed[i] * 2.7);
    const a = clamp(k * 0.9, 0, 1) * fog * tw;
    if (a < 0.04) continue;

    const tierIdx = a > 0.75 ? 3 : a > 0.5 ? 2 : a > 0.25 ? 1 : 0;
    const size = BASE_SIZE * k * SPRITE_SCALE * psize[i];

    ctx.drawImage(
      atlas,
      tierIdx * SPRITE_PX, cidx[i] * SPRITE_PX, SPRITE_PX, SPRITE_PX,
      sx - size / 2, sy - size / 2, size, size,
    );
  }

  ctx.globalCompositeOperation = 'source-over';
}
