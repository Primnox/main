import { lerpFPS } from './gpu.js';

/**
 * Pointer state in normalised [0,1] coordinates with y up.
 *
 * Keeps the *previous* position around because the frost splat draws a capsule
 * between frames — without it a fast flick leaves a dotted trail on any machine
 * that drops below the mouse's report rate.
 */
export class Pointer {
  constructor(element, { smoothing = 0.35 } = {}) {
    this.element = element;
    this.smoothing = smoothing;

    this.x = 0.5;
    this.y = 0.5;
    this.px = 0.5;
    this.py = 0.5;
    this.speed = 0;
    this.active = false;
    this.down = false;

    // Raw target, before smoothing.
    this._tx = 0.5;
    this._ty = 0.5;
    this._idle = 0;

    this._onMove = (e) => {
      const rect = this.element.getBoundingClientRect();
      this._tx = (e.clientX - rect.left) / rect.width;
      this._ty = 1 - (e.clientY - rect.top) / rect.height;
      this.active = true;
      this._idle = 0;
    };
    this._onLeave = () => { this.active = false; };
    this._onDown = () => { this.down = true; };
    this._onUp = () => { this.down = false; };

    window.addEventListener('pointermove', this._onMove, { passive: true });
    window.addEventListener('pointerdown', this._onDown, { passive: true });
    window.addEventListener('pointerup', this._onUp, { passive: true });
    window.addEventListener('pointerleave', this._onLeave, { passive: true });
  }

  update(dt) {
    this.px = this.x;
    this.py = this.y;
    this.x = lerpFPS(this.x, this._tx, this.smoothing, dt);
    this.y = lerpFPS(this.y, this._ty, this.smoothing, dt);

    const dx = this.x - this.px;
    const dy = this.y - this.py;
    this.speed = Math.hypot(dx, dy);

    // Stop painting once the pointer has been still for a moment, otherwise a
    // parked cursor slowly burns a hole in the frost buffer.
    this._idle += dt;
    if (this.speed < 1e-4 && this._idle > 0.4) this.active = false;
    else if (this.speed >= 1e-4) { this.active = true; this._idle = 0; }
  }

  dispose() {
    window.removeEventListener('pointermove', this._onMove);
    window.removeEventListener('pointerdown', this._onDown);
    window.removeEventListener('pointerup', this._onUp);
    window.removeEventListener('pointerleave', this._onLeave);
  }
}
