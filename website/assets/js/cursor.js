/* The dot. Zero lag by design — it is a pointing affordance, not an effect.
   Hover feedback belongs to the blob; this stays constant so clicks feel exact. */

import { env, pointer, addTick, bus } from './core.js';

const TINT_SELECTOR = 'a, button, [data-blob="grow"]';

let el, tick;

export function initCursor() {
  el = document.getElementById('cursor');
  if (!el || !env.finePointer) return;

  bus.on('pointer:first', () => {
    el.classList.add('on');
    document.documentElement.classList.add('cursor-on');
  });

  tick = addTick(() => {
    el.style.transform = `translate3d(${pointer.x - 3.5}px, ${pointer.y - 3.5}px, 0)`;
  }, 10);

  // Delegated: the router swaps <main>, so any listener bound to a snapshot of
  // the DOM silently stops working after the first navigation.
  document.addEventListener('pointerover', (e) => {
    if (e.target.closest?.(TINT_SELECTOR)) el.classList.add('tint');
  });
  document.addEventListener('pointerout', (e) => {
    if (e.target.closest?.(TINT_SELECTOR)) el.classList.remove('tint');
  });

  addEventListener('blur', () => el.classList.remove('on'));
  addEventListener('focus', () => { if (pointer.seen) el.classList.add('on'); });

  bus.on('env:pointer', (fine) => {
    if (fine) {
      tick.resume();
    } else {
      tick.pause();
      el.classList.remove('on');
      document.documentElement.classList.remove('cursor-on');
    }
  });
}
