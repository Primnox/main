/* Intro: a field of individually-tumbling, directionally-lit 3D cubes that
   fly at the camera and assemble into the PRIMNOX wordmark.

   This mirrors the mechanic the reference uses (per-cube rotateX about its own
   pivot, a rising zOffset, a "middle point" where the field locks to the logo
   index, and a single light direction), but renders it with a pre-baked sprite
   atlas on a 2D canvas instead of instanced WebGL. At these counts the atlas
   approach costs about the same and avoids a second renderer, a shader
   pipeline and context-loss handling for one 4-second animation. */

import { sampleText } from './wordmark.js';
import { clamp, smoothstep, env } from './core.js';

const SPINS = 16;             // baked X-rotation steps
const YAWS = 4;               // baked yaw variants, so the field isn't uniform
const ANGLES = SPINS * YAWS;
const CELL = 44;              // atlas cell size, px
const FOV = 700;
const LIGHT = (() => { const v = [0.42, 0.76, 0.5]; const m = Math.hypot(...v); return v.map(c => c / m); })();

// Unit cube, faces as vertex-index quads with outward normals.
const V = [[-.5,-.5,-.5],[.5,-.5,-.5],[.5,.5,-.5],[-.5,.5,-.5],
           [-.5,-.5,.5],[.5,-.5,.5],[.5,.5,.5],[-.5,.5,.5]];
const F = [
  { i: [4,5,6,7], n: [0,0,1] },   { i: [1,0,3,2], n: [0,0,-1] },
  { i: [5,1,2,6], n: [1,0,0] },   { i: [0,4,7,3], n: [-1,0,0] },
  { i: [3,7,6,2], n: [0,1,0] },   { i: [0,1,5,4], n: [0,-1,0] },
];

const atlases = new Map();
function getAtlas(color) {
  if (!atlases.has(color)) atlases.set(color, buildAtlas(color));
  return atlases.get(color);
}

function shade(hex, k) {
  let h = hex.replace('#', '');
  if (h.length === 3) h = h.split('').map(c => c + c).join('');
  const n = parseInt(h, 16);
  const r = Math.round(clamp(((n >> 16) & 255) * k, 0, 255));
  const g = Math.round(clamp(((n >> 8) & 255) * k, 0, 255));
  const b = Math.round(clamp((n & 255) * k, 0, 255));
  return `rgb(${r},${g},${b})`;
}

/* Bakes the cube at ANGLES rotations about X, with a fixed camera yaw so the
   form reads as a solid rather than a flat square. Doing the lighting once
   here is what keeps the draw loop to a single drawImage per cube. */
function buildAtlas(color) {
  const cols = 8;
  const rows = Math.ceil(ANGLES / cols);
  const c = document.createElement('canvas');
  c.width = CELL * cols;
  c.height = CELL * rows;
  const g = c.getContext('2d');
  const s = CELL * 0.30;

  for (let a = 0; a < ANGLES; a++) {
    // Every cube sharing one camera yaw made the whole field look stamped from
    // a single die. Baking a few yaws gives it variety for free.
    const yaw = 0.38 + ((a / SPINS) | 0) * 0.26;
    const cy = Math.cos(yaw), sy = Math.sin(yaw);
    const ang = ((a % SPINS) / SPINS) * Math.PI * 2;
    const ca = Math.cos(ang), sa = Math.sin(ang);
    const ox = (a % cols) * CELL + CELL / 2;
    const oy = ((a / cols) | 0) * CELL + CELL / 2;

    const rot = ([x, y, z]) => {
      const y1 = y * ca - z * sa, z1 = y * sa + z * ca;
      return [x * cy + z1 * sy, y1, -x * sy + z1 * cy];
    };
    const pv = V.map(rot);

    const faces = F.map(f => {
      const n = rot(f.n);
      const depth = f.i.reduce((t, k) => t + pv[k][2], 0) / 4;
      return { n, depth, pts: f.i.map(k => pv[k]) };
    }).filter(f => f.n[2] > 0.02)
      .sort((p, q) => p.depth - q.depth);

    for (const f of faces) {
      const lambert = Math.max(0, f.n[0] * LIGHT[0] + f.n[1] * LIGHT[1] + f.n[2] * LIGHT[2]);
      // Wider range than before: at this size the only thing separating one
      // face from the next is tonal contrast.
      g.fillStyle = shade(color, 0.16 + 1.05 * lambert);
      g.beginPath();
      f.pts.forEach((p, k) => {
        const X = ox + p[0] * s, Y = oy - p[1] * s;
        k ? g.lineTo(X, Y) : g.moveTo(X, Y);
      });
      g.closePath();
      g.fill();
      // A dark seam along each face keeps neighbouring cubes from fusing into
      // one mass once they are packed shoulder to shoulder.
      g.strokeStyle = shade(color, 0.06);
      g.lineWidth = 0.9;
      g.stroke();
    }
  }
  return c;
}

export function createCubeField(canvas, opts = {}) {
  const ctx = canvas.getContext('2d', { alpha: true });
  if (!ctx) return null;

  let dpr = 1, w = 0, h = 0, cx = 0, cy = 0, N = 0;
  let px, py, pz, tx, ty, tz, spin, spinRate, scale, depthSeed;
  let sx0, sy0, sz0, delay, isDot, yawBank;
  let lx, ly;              // nav-logo geometry, morphed to during the flight
  let morph = 0;
  let captured = false;
  let markBox = null;
  let cubePitch = 8;
  const view = { scale: 1, dx: 0, dy: 0, fade: 1 };
  let phase = 'fly';
  let elapsed = 0;
  let zOffset = 0;
  let assembleT = 0;
  const color = opts.color || '#f0ede6';

  function resize() {
    const r = canvas.getBoundingClientRect();
    if (!r.width || !r.height) return;
    dpr = Math.min(devicePixelRatio || 1, 2);
    w = r.width; h = r.height;
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    cx = w / 2; cy = h / 2;
    allocate();
  }

  function allocate() {
    // The intro is the heaviest thing on the site and it runs before the perf
    // governor has any frame history to react to, so it has to cap itself.
    let want = clamp(Math.round((w * h) / 620), 700, 2300);
    if (env.saveData || env.slowNet) want = Math.min(want, 520);
    else if (env.lowEnd) want = Math.min(want, 900);
    else if (!env.finePointer) want = Math.min(want, 1100);
    if (want === N && tx) { retarget(); return; }
    N = want;
    const f = () => new Float32Array(N);
    px = f(); py = f(); pz = f(); tx = f(); ty = f(); tz = f();
    spin = f(); spinRate = f(); scale = f(); depthSeed = f();
    sx0 = f(); sy0 = f(); sz0 = f(); delay = f();
    lx = f(); ly = f();
    isDot = new Uint8Array(N);
    yawBank = new Uint8Array(N);
    for (let i = 0; i < N; i++) {
      px[i] = (Math.random() - 0.5) * w * 2.4;
      py[i] = (Math.random() - 0.5) * h * 2.4;
      pz[i] = 900 + Math.random() * 1900;
      spin[i] = Math.random() * Math.PI * 2;
      spinRate[i] = (Math.random() - 0.5) * 0.0075;
      yawBank[i] = Math.floor(Math.random() * YAWS);
      scale[i] = 0.88 + Math.random() * 0.26;
      depthSeed[i] = Math.random();
    }
    retarget();
  }

  /* Two lockups, not one.

     At rest the mark wants display proportions — tight tracking, as large as
     the canvas allows, cubes big enough that the lighting on their faces
     actually reads as 3D. The nav logo wants the opposite: small, and tracked
     out to 0.18em. Matching the logo at rest is what made the intro a thin
     strip in a void, so we build both and morph between them during the
     flight, which keeps the landing exact. */
  function buildTargets(tracking, boxW, boxH, step) {
    return sampleText(opts.text || 'Primnox', boxW, boxH, step,
                      { weight: 700, tracking, upper: true });
  }

  function bboxOf(pts) {
    let x0 = 1e9, x1 = -1e9, y0 = 1e9, y1 = -1e9;
    for (let j = 0; j < pts.length; j += 2) {
      if (pts[j] < x0) x0 = pts[j];
      if (pts[j] > x1) x1 = pts[j];
      if (pts[j + 1] < y0) y0 = pts[j + 1];
      if (pts[j + 1] > y1) y1 = pts[j + 1];
    }
    return { x0, x1, y0, y1, h: y1 - y0, w: x1 - x0 };
  }

  /* Lattice-fills a disc at the same pitch as the glyphs. Scattering random
     points inside the circle leaves Poisson clumps and holes — at ~70 cubes
     that reads as a smear, not a dot. */
  function discLattice(radius, pitch) {
    const out = [];
    const r2 = radius * radius;
    for (let y = -radius; y <= radius; y += pitch)
      for (let x = -radius; x <= radius; x += pitch)
        if (x * x + y * y <= r2) out.push(x / radius, y / radius);   // normalised
    return out;
  }

  function retarget() {
    // The text box must leave room for the dot, or the dot lands off-canvas:
    // the glyphs are placed first and the dot sits to their left.
    const boxW = w * 0.76, boxH = h * 0.62;
    let step = 6;
    let disp = buildTargets('0.015em', boxW, boxH, step);
    let db = bboxOf(disp);
    const wanted = clamp(Math.round(db.h / 18), 3, 14);
    if (wanted !== step) { step = wanted; disp = buildTargets('0.015em', boxW, boxH, step); db = bboxOf(disp); }
    if (disp.length / 2 > N) {
      step = Math.max(3, Math.round(step * Math.sqrt((disp.length / 2) / N)));
      disp = buildTargets('0.015em', boxW, boxH, step);
      db = bboxOf(disp);
    }
    cubePitch = step;

    const logo = buildTargets('0.18em', boxW, boxH, step);
    const lb = bboxOf(logo);
    const glyphCount = Math.min(disp.length, logo.length) / 2;
    if (!glyphCount) return;

    // Proportions from .logo-dot beside .nav-logo.
    const dotR = db.h * 0.375, gap = db.h * 0.95;
    const lDotR = lb.h * 0.375, lGap = lb.h * 0.95;

    // Shift the glyphs right by half the dot's footprint so the whole lockup
    // (dot + wordmark) ends up centred rather than the wordmark alone.
    const shift = (gap + dotR * 2) / 2;
    const lShift = (lGap + lDotR * 2) / 2;

    const unit = discLattice(dotR, step);
    const dotCount = Math.min(unit.length / 2, Math.floor(N * 0.14));

    const dotCX = db.x0 + shift - gap - dotR;
    const dotCY = (db.y0 + db.y1) / 2;
    const lDotCX = lb.x0 + lShift - lGap - lDotR;
    const lDotCY = (lb.y0 + lb.y1) / 2;

    markBox = { x0: lDotCX - lDotR, x1: lb.x1 + lShift, y0: lb.y0, y1: lb.y1 };

    const maxDelay = 0.40;
    for (let i = 0; i < N; i++) {
      if (i < dotCount) {
        const nx = unit[i * 2], ny = unit[i * 2 + 1];
        isDot[i] = 1;
        tx[i] = dotCX + nx * dotR;   ty[i] = dotCY + ny * dotR;
        lx[i] = lDotCX + nx * lDotR; ly[i] = lDotCY + ny * lDotR;
        tz[i] = (depthSeed[i] - 0.5) * 7;
        delay[i] = maxDelay;
      } else {
        const j = ((i - dotCount) % glyphCount) * 2;
        isDot[i] = 0;
        tx[i] = disp[j] + shift;   ty[i] = disp[j + 1];
        lx[i] = logo[j] + lShift;  ly[i] = logo[j + 1];
        tz[i] = (depthSeed[i] - 0.5) * 9;
        delay[i] = ((disp[j] - db.x0) / Math.max(1, db.w)) * (maxDelay * 0.7);
      }
    }
  }

  function step(dtMs) {
    const dt = Math.min(dtMs, 50) / 1000;
    elapsed += dtMs;

    // Phase 1: the field rushes in from depth while tumbling, then locks.
    if (phase === 'fly') {
      if (elapsed >= 550) {
        phase = 'assemble';
        // Freeze the launch positions so the lock is a deterministic
        // interpolation. Exponential smoothing toward a moving target reads as
        // a drift; capturing the start lets it land on an exact beat.
        for (let i = 0; i < N; i++) { sx0[i] = px[i]; sy0[i] = py[i]; sz0[i] = pz[i]; }
        captured = true;
      }
    } else if (phase === 'assemble') {
      assembleT = Math.min(1, assembleT + dt / 1.1);
    }

    for (let i = 0; i < N; i++) {
      spin[i] += spinRate[i] * dtMs;

      if (!captured) { pz[i] -= 190 * dt; continue; }

      const span = 1 - 0.42;
      let t = clamp((assembleT - delay[i]) / span, 0, 1);
      // easeOutBack: a slight overshoot is what makes the cubes read as
      // snapping into place rather than sliding to a stop.
      const c1 = 1.24, c3 = c1 + 1;
      const u = t - 1;
      const e = t >= 1 ? 1 : 1 + c3 * u * u * u + c1 * u * u;

      // Blend the display lockup toward the nav-logo lockup as the flight runs.
      const gx = tx[i] + (lx[i] - tx[i]) * morph;
      const gy = ty[i] + (ly[i] - ty[i]) * morph;
      px[i] = sx0[i] + (gx - sx0[i]) * e;
      py[i] = sy0[i] + (gy - sy0[i]) * e;
      pz[i] = sz0[i] + (tz[i] * (1 - morph) - sz0[i]) * e;
      // Settled cubes stop tumbling — that stillness is what sells the lock.
      spinRate[i] *= (1 - 0.06 * t);
    }
  }

  function render() {
    ctx.clearRect(0, 0, w, h);
    const zMin = -FOV + 70;
    for (let i = 0; i < N; i++) {
      const z = Math.max(pz[i] + zOffset, zMin);
      const pk = clamp(FOV / (FOV + z), 0, 3.2);
      const sx = view.dx + (cx + px[i] * pk) * view.scale;
      const sy = view.dy + (cy + py[i] * pk) * view.scale;
      // The baked cube fills ~60% of its atlas cell, so the cell must be drawn
      // at ~1.9x the pitch for neighbouring cubes to actually touch.
      const size = cubePitch * 1.9 * pk * scale[i] * view.scale;
      if (size < 0.6) continue;
      if (sx < -size || sx > w + size || sy < -size || sy > h + size) continue;

      const fog = 1 - smoothstep(700, 2600, z);
      const a = clamp(pk * 0.85, 0, 1) * fog;
      if (a < 0.03) continue;

      let sp = ((spin[i] / (Math.PI * 2)) * SPINS | 0) % SPINS;
      if (sp < 0) sp += SPINS;
      const ai = yawBank[i] * SPINS + sp;
      ctx.globalAlpha = a * view.fade;
      ctx.drawImage(isDot[i] ? atlasDot : atlasMain,
                    (ai % 8) * CELL, ((ai / 8) | 0) * CELL, CELL, CELL,
                    sx - size / 2, sy - size / 2, size, size);
    }
    ctx.globalAlpha = 1;
  }

  const atlasMain = getAtlas(color);
  const atlasDot = getAtlas(opts.dotColor || color);
  resize();

  return {
    step, render, resize,
    get progress() { return phase === 'assemble' ? assembleT : 0; },
    get settled() { return phase === 'assemble' && assembleT >= 1; },
    /* Positive amount moves the field toward the camera. */
    dolly(amount) { zOffset -= amount; },
    view,
    /* 0 = display lockup, 1 = nav-logo lockup. */
    setMorph(v) { morph = clamp(v, 0, 1); },
    /* Scale/offset that maps the settled mark onto an arbitrary screen rect —
       used to fly the intro mark into the nav logo. */
    solveViewFor(rect) {
      if (!markBox) return null;
      const mw = markBox.x1 - markBox.x0;
      const mh = markBox.y1 - markBox.y0;
      if (mw <= 0) return null;
      const scale = rect.width / mw;
      const mcx = cx + (markBox.x0 + markBox.x1) / 2;
      const mcy = cy + (markBox.y0 + markBox.y1) / 2;
      return {
        scale,
        dx: (rect.left + rect.width / 2) - mcx * scale,
        dy: (rect.top + rect.height / 2) - mcy * scale,
        markH: mh,
      };
    },
  };
}
