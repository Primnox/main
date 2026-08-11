/* Curtain wipe + the first-load PRIMNOX intro. */

import { env, debug, bus } from './core.js';
import { createCubeField } from './introcubes.js';

const PANELS = 5;
const INTRO_KEY = 'primnox:intro-seen';

let el, panelEls, labelEl, wordEl, waitTimer;
let ready = false;

export function initCurtain() {
  el = document.getElementById('curtain');
  if (!el) return;

  panelEls = [...el.querySelectorAll('.curtain-panel')];
  labelEl = el.querySelector('.curtain-label');
  wordEl = el.querySelector('.curtain-word');
  ready = true;

  gsap.set(panelEls, { scaleY: 0, transformOrigin: 'bottom' });
  gsap.set(labelEl, { opacity: 0 });

  // Back/forward into bfcache restores the document exactly as it was left —
  // including a curtain that was down for an outgoing navigation. Without this
  // the user lands on a permanently black screen.
  addEventListener('pageshow', (e) => { if (e.persisted) resetCurtain(); });
}

export function resetCurtain() {
  if (!ready) return;
  clearTimeout(waitTimer);
  el.classList.remove('busy', 'waiting');
  gsap.killTweensOf([panelEls, labelEl]);
  gsap.set(panelEls, { scaleY: 0, transformOrigin: 'bottom' });
  gsap.set(labelEl, { opacity: 0 });
}

/* Covers the viewport. Resolves once the screen is fully hidden — the caller
   swaps content only after this settles. */
export function curtainIn(label) {
  if (!ready) return Promise.resolve();
  clearTimeout(waitTimer);
  el.classList.add('busy');

  if (label && wordEl) wordEl.textContent = label;

  // A stalled fetch behind an opaque panel is indistinguishable from a crash,
  // so surface a waiting hint if we are still covered after 400ms.
  waitTimer = setTimeout(() => el.classList.add('waiting'), 400);

  if (env.reduceMotion) {
    gsap.set(panelEls, { scaleY: 1, transformOrigin: 'bottom' });
    return new Promise((r) => setTimeout(r, 120));
  }

  return new Promise((resolve) => {
    gsap.timeline({ onComplete: resolve })
      .set(panelEls, { transformOrigin: 'bottom' })
      .to(panelEls, {
        scaleY: 1,
        duration: 0.52,
        ease: 'power3.inOut',
        stagger: { each: 0.045, from: 'start' },
      })
      .to(labelEl, { opacity: 1, duration: 0.22, ease: 'power2.out' }, '-=0.2');
  });
}

/* Uncovers. Sweeps the opposite way on a Back navigation so history direction
   is legible without any UI. */
export function curtainOut(direction = 'forward') {
  if (!ready) return Promise.resolve();
  clearTimeout(waitTimer);
  el.classList.remove('waiting');

  const done = () => el.classList.remove('busy');

  if (env.reduceMotion) {
    gsap.set(panelEls, { scaleY: 0 });
    gsap.set(labelEl, { opacity: 0 });
    done();
    return Promise.resolve();
  }

  return new Promise((resolve) => {
    gsap.timeline({
      onComplete: () => { done(); resolve(); },
    })
      .to(labelEl, { opacity: 0, duration: 0.18, ease: 'power2.in' })
      .set(panelEls, { transformOrigin: 'top' })
      .to(panelEls, {
        scaleY: 0,
        duration: 0.62,
        ease: 'expo.inOut',
        stagger: { each: 0.05, from: direction === 'back' ? 'end' : 'start' },
      }, '-=0.05');
  });
}

/* ─── INTRO ─── */

export function shouldPlayIntro() {
  if (debug.replayIntro) return true;   // testing loop: ignore the once-per-session gate
  if (env.reduceMotion) return false;
  if (location.pathname !== '/' && location.pathname !== '/index.html') return false;
  try {
    return sessionStorage.getItem(INTRO_KEY) !== '1';
  } catch {
    return false; // private mode / storage blocked — never trap the user
  }
}

export function markIntroSeen() {
  if (debug.replayIntro) return;        // never latch the flag while replaying
  try { sessionStorage.setItem(INTRO_KEY, '1'); } catch { /* non-fatal */ }
}

export function playIntro() {
  const intro = document.getElementById('intro');
  const canvas = document.getElementById('introCanvas');
  if (!intro || !canvas) return Promise.resolve();

  const sub = intro.querySelector('.intro-sub');

  intro.classList.add('on');
  markIntroSeen();

  const cs = getComputedStyle(document.documentElement);
  const color = cs.getPropertyValue('--text').trim() || '#f0ede6';
  const dotColor = cs.getPropertyValue('--primary').trim() || '#c3c0ff';
  const field = createCubeField(canvas, { text: 'Primnox', color, dotColor });
  if (!field) { intro.classList.remove('on'); return Promise.resolve(); }

  const onResize = () => field.resize();
  addEventListener('resize', onResize, { passive: true });

  return new Promise((resolve) => {
    let last = 0;
    // Driven off gsap.ticker so the cube field shares the one clock the rest of
    // the site uses, rather than opening a competing rAF loop.
    const drive = (time) => {
      const now = time * 1000;
      const dt = last ? now - last : 16.7;
      last = now;
      field.step(dt);
      field.render();
    };
    gsap.ticker.add(drive);

    const finish = () => {
      gsap.ticker.remove(drive);
      removeEventListener('resize', onResize);
      intro.classList.remove('on');
      document.documentElement.classList.remove('intro-pending');
      document.documentElement.classList.remove('logo-handoff');
      // Leave no state behind, or a replay starts with the logo already shown.
      document.documentElement.style.removeProperty('--logo-op');
      gsap.set(intro, { clearProps: 'opacity', background: '' });
      resolve();
    };

    const tl = gsap.timeline({ onComplete: finish });

    // Lock completes ~1.65s in. The caption rides the tail of it rather than
    // waiting, and the finished mark then gets a real beat on screen before it
    // leaves — that hold is the payoff shot. No progress bar: nothing is
    // actually loading, and a timer dressed up as progress is a lie.
    tl.to(sub, { opacity: 1, duration: 0.55, ease: 'power2.out' }, 1.15)
      .to(sub, { opacity: 0, duration: 0.35, ease: 'power2.in' }, 2.30);

    tl.add(() => {
      const logo = document.querySelector('.nav-logo');
      const target = logo && field.solveViewFor(logo.getBoundingClientRect());
      if (!target) { gsap.to(field.view, { fade: 0, duration: 0.4 }); return; }

      document.documentElement.classList.remove('intro-pending');
      document.documentElement.classList.add('logo-handoff');
      gsap.set(intro, { background: 'transparent' });

      // The hero entrance starts while the cubes are still travelling, so the
      // eye follows them up-left and finds the headline already arriving.
      bus.emit('intro:handoff');

      // Geometry morph and view transform run on the same curve, so the mark
      // re-tracks into logo proportions exactly as it shrinks into the corner.
      const m = { v: 0 };
      gsap.to(m, {
        v: 1, duration: 1.0, ease: 'power3.inOut',
        onUpdate: () => field.setMorph(m.v),
      });
      gsap.to(field.view, {
        scale: target.scale, dx: target.dx, dy: target.dy,
        duration: 1.0, ease: 'power3.inOut',
      });
      gsap.to(field.view, { fade: 0, duration: 0.26, ease: 'power2.in', delay: 0.80 });
      gsap.set(document.documentElement, { '--logo-op': 1, delay: 0.90 });
    }, 2.20);

    tl.to(intro, { opacity: 0, duration: 0.28, ease: 'power2.inOut' }, 3.10);
  });
}
