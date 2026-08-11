/* Scroll reveal. One observer per page, torn down on navigation. */

import { env } from './core.js';

let io;
let marqueeIO;

export function initReveal(root = document) {
  gateMarquees(root);
  const items = root.querySelectorAll('.ri');

  if (env.reduceMotion) {
    items.forEach((el) => el.classList.add('vis'));
    return;
  }

  io = new IntersectionObserver((entries) => {
    for (const e of entries) {
      if (!e.isIntersecting) continue;
      e.target.classList.add('vis');
      io.unobserve(e.target);
    }
  }, { threshold: 0.07, rootMargin: '0px 0px -24px 0px' });

  items.forEach((el) => io.observe(el));
}

export function destroyReveal() {
  io?.disconnect();
  io = null;
  marqueeIO?.disconnect();
  marqueeIO = null;
}

/* An infinite marquee ticking away below the fold is pure wasted compositing.
   Browsers do not reliably throttle offscreen CSS animations. */
function gateMarquees(root) {
  const wraps = root.querySelectorAll('.mq-wrap');
  if (!wraps.length) return;

  if (env.reduceMotion) { wraps.forEach((el) => el.classList.remove('on')); return; }

  marqueeIO = new IntersectionObserver((entries) => {
    for (const e of entries) e.target.classList.toggle('on', e.isIntersecting);
  }, { rootMargin: '120px 0px' });
  wraps.forEach((el) => marqueeIO.observe(el));
}
