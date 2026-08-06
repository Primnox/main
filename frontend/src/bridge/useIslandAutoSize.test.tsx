import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, cleanup } from '@testing-library/react';
import { useIslandAutoSize } from './useIslandAutoSize';

// ── ResizeObserver stub ──────────────────────────────────────────────────────
// jsdom ships no ResizeObserver; this one lets a test drive observed resizes.

type ROCallback = (entries: { target: Element }[]) => void;

class StubResizeObserver {
  static instances: StubResizeObserver[] = [];
  observed: Element[] = [];
  disconnected = false;
  constructor(public cb: ROCallback) {
    StubResizeObserver.instances.push(this);
  }
  observe(el: Element) {
    this.observed.push(el);
  }
  unobserve() {}
  disconnect() {
    this.disconnected = true;
  }
  /** Pretend every observed element resized. */
  fire() {
    this.cb(this.observed.map((target) => ({ target })));
  }
}

const send = vi.fn();

// jsdom always measures 0×0, so the box is stubbed at the prototype and driven
// from `box` below.
let box = { width: 520, height: 52 };
const setSize = (width: number, height: number) => {
  box = { width, height };
};

const realGetBoundingClientRect = Element.prototype.getBoundingClientRect;

function Pill({ enabled }: { enabled: boolean }) {
  const ref = useIslandAutoSize(enabled);
  return <div ref={ref as React.RefObject<HTMLDivElement>} data-testid="pill" />;
}

/** Let the queued requestAnimationFrame callback run. */
const flushFrames = () => new Promise((r) => setTimeout(r, 20));

beforeEach(() => {
  StubResizeObserver.instances = [];
  send.mockClear();
  box = { width: 520, height: 52 };

  Element.prototype.getBoundingClientRect = function () {
    return {
      width: box.width,
      height: box.height,
      top: 0,
      left: 0,
      right: box.width,
      bottom: box.height,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    } as DOMRect;
  };

  (globalThis as any).ResizeObserver = StubResizeObserver;
  (window as any).__TAURI_INTERNALS__ = {};
  (window as any).electron = { ipcRenderer: { send, on: () => () => {} } };
});

afterEach(() => {
  cleanup();
  Element.prototype.getBoundingClientRect = realGetBoundingClientRect;
  delete (globalThis as any).ResizeObserver;
  delete (window as any).__TAURI_INTERNALS__;
  delete (window as any).electron;
});

describe('useIslandAutoSize', () => {
  it('pushes the initial size without waiting for a resize', async () => {
    // ResizeObserver only fires on change, so without an eager first push the
    // overlay keeps its configured 900x220 until the pill first animates.
    render(<Pill enabled />);
    await flushFrames();

    expect(send).toHaveBeenCalledWith('island:set-size', { width: 520, height: 52 });
  });

  it('pushes the new size when the pill grows', async () => {
    render(<Pill enabled />);
    await flushFrames();
    send.mockClear();

    setSize(760, 180);
    StubResizeObserver.instances[0].fire();
    await flushFrames();

    expect(send).toHaveBeenCalledWith('island:set-size', { width: 760, height: 180 });
  });

  it('ignores sub-pixel jitter', async () => {
    render(<Pill enabled />);
    await flushFrames();
    send.mockClear();

    // motion/react animates through fractional sizes; resizing the OS window on
    // every one of those frames is pointless and visibly janky.
    setSize(520.4, 52.2);
    StubResizeObserver.instances[0].fire();
    await flushFrames();

    expect(send).not.toHaveBeenCalled();
  });

  it('coalesces a burst of resizes into one push', async () => {
    render(<Pill enabled />);
    await flushFrames();
    send.mockClear();

    const ro = StubResizeObserver.instances[0];
    for (const w of [530, 540, 550, 560]) {
      setSize(w, 52);
      ro.fire();
    }
    await flushFrames();

    expect(send).toHaveBeenCalledTimes(1);
    expect(send).toHaveBeenCalledWith('island:set-size', { width: 560, height: 52 });
  });

  it('never pushes a zero measurement', async () => {
    // Pre-layout frames measure 0x0; sending that would collapse the overlay.
    setSize(0, 0);
    render(<Pill enabled />);
    await flushFrames();

    expect(send).not.toHaveBeenCalled();
  });

  it('does nothing when disabled', async () => {
    render(<Pill enabled={false} />);
    await flushFrames();

    expect(send).not.toHaveBeenCalled();
    expect(StubResizeObserver.instances).toHaveLength(0);
  });

  it('does nothing outside Tauri', async () => {
    // Electron keeps its fixed overlay and the click-through handshake.
    delete (window as any).__TAURI_INTERNALS__;
    render(<Pill enabled />);
    await flushFrames();

    expect(send).not.toHaveBeenCalled();
  });

  it('disconnects the observer on unmount', async () => {
    const view = render(<Pill enabled />);
    await flushFrames();

    view.unmount();
    expect(StubResizeObserver.instances[0].disconnected).toBe(true);
  });
});
