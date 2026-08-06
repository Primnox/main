/**
 * Keep the Tauri island overlay window sized to the pill it contains.
 *
 * Under Electron the overlay is a fixed 900×220 window whose transparent margin
 * is made click-through with `setIgnoreMouseEvents(true, { forward: true })`.
 * The `forward` flag is what makes that work: the window ignores clicks but
 * still receives mouse *movement*, so the pill's `onMouseEnter` fires and can
 * turn capture back on.
 *
 * Tauri has no equivalent. `set_ignore_cursor_events(true)` makes the window
 * inert — no movement events reach the page — so the pill can never learn the
 * cursor arrived and the overlay stays permanently click-through. Sizing the
 * window to the pill deletes the transparent margin, so nothing needs ignoring
 * and hover works by ordinary means.
 */

import { useEffect, useRef } from 'react';
import { isTauriRuntime } from './electronBridge';

/** Ignore sub-pixel jitter; only report meaningful size changes. */
const EPSILON = 1;

export function useIslandAutoSize(enabled: boolean) {
  const ref = useRef<HTMLElement | null>(null);

  useEffect(() => {
    const el = ref.current;
    if (!enabled || !el || !isTauriRuntime()) return;
    if (typeof ResizeObserver === 'undefined') return;

    const electron = (window as unknown as { electron?: any }).electron;
    if (!electron?.ipcRenderer) return;

    let lastW = -1;
    let lastH = -1;
    let frame = 0;

    const push = (width: number, height: number) => {
      if (width <= 0 || height <= 0) return;
      if (Math.abs(width - lastW) < EPSILON && Math.abs(height - lastH) < EPSILON) {
        return;
      }
      lastW = width;
      lastH = height;
      electron.ipcRenderer.send('island:set-size', { width, height });
    };

    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry) return;
      // Coalesce to one push per frame: the pill is animated by motion/react,
      // which would otherwise fire a window resize on every animation tick.
      if (frame) cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        frame = 0;
        const rect = entry.target.getBoundingClientRect();
        push(rect.width, rect.height);
      });
    });

    observer.observe(el);

    // Push the initial size immediately — ResizeObserver only fires on change,
    // and without this the overlay keeps its configured 900×220 until the pill
    // first animates.
    const rect = el.getBoundingClientRect();
    push(rect.width, rect.height);

    return () => {
      if (frame) cancelAnimationFrame(frame);
      observer.disconnect();
    };
  }, [enabled]);

  return ref;
}
