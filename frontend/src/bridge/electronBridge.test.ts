import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  createBridge,
  installElectronBridge,
  isTauriRuntime,
} from './electronBridge';

// ── Tauri module mocks ───────────────────────────────────────────────────────
// The bridge reaches the Tauri API through dynamic `import()` so the Electron
// build never pulls it in; these mocks intercept those imports.

const invoke = vi.fn(() => Promise.resolve());

type PendingListen = {
  channel: string;
  handler: (event: { payload: unknown }) => void;
  resolve: (unlisten: () => void) => void;
};
let pending: PendingListen[] = [];

vi.mock('@tauri-apps/api/core', () => ({
  invoke: (...args: unknown[]) => invoke(...(args as [])),
}));

vi.mock('@tauri-apps/api/event', () => ({
  listen: (channel: string, handler: (e: { payload: unknown }) => void) =>
    new Promise<() => void>((resolve) => {
      pending.push({ channel, handler, resolve });
    }),
}));

const writeText = vi.fn((_text: string) => Promise.resolve());
vi.mock('@tauri-apps/plugin-clipboard-manager', () => ({
  writeText: (text: string) => writeText(text),
}));

/** Resolve the oldest pending `listen()` with a stub unlisten fn. */
function settleListen(): { unlisten: ReturnType<typeof vi.fn>; entry: PendingListen } {
  const entry = pending.shift();
  if (!entry) throw new Error('no pending listen() call');
  const unlisten = vi.fn();
  entry.resolve(unlisten);
  return { unlisten, entry };
}

/** Let queued microtasks (the dynamic imports) run. */
const flush = () => new Promise((r) => setTimeout(r, 0));

const enterTauri = () => {
  (window as any).__TAURI_INTERNALS__ = {};
};

beforeEach(() => {
  pending = [];
  invoke.mockClear();
  writeText.mockClear();
  delete (window as any).__TAURI_INTERNALS__;
  delete (window as any).electron;
});

afterEach(() => {
  delete (window as any).__TAURI_INTERNALS__;
  delete (window as any).electron;
});

describe('runtime detection', () => {
  it('is false in a plain browser', () => {
    expect(isTauriRuntime()).toBe(false);
  });

  it('is true once Tauri injects its internals', () => {
    enterTauri();
    expect(isTauriRuntime()).toBe(true);
  });
});

describe('installElectronBridge', () => {
  it('does nothing outside Tauri', () => {
    expect(installElectronBridge()).toBe(false);
    expect((window as any).electron).toBeUndefined();
  });

  it('installs the compat surface under Tauri', () => {
    enterTauri();
    expect(installElectronBridge()).toBe(true);
    const api = (window as any).electron;
    expect(typeof api.ipcRenderer.send).toBe('function');
    expect(typeof api.ipcRenderer.on).toBe('function');
    expect(typeof api.clipboard.writeText).toBe('function');
  });

  it('never overwrites a real Electron preload', () => {
    enterTauri();
    const preload = { ipcRenderer: { send: vi.fn(), on: vi.fn() } };
    (window as any).electron = preload;
    expect(installElectronBridge()).toBe(false);
    expect((window as any).electron).toBe(preload);
  });

  it('is idempotent', () => {
    enterTauri();
    expect(installElectronBridge()).toBe(true);
    const first = (window as any).electron;
    expect(installElectronBridge()).toBe(false);
    expect((window as any).electron).toBe(first);
  });
});

describe('ipcRenderer.send', () => {
  it('forwards an allowed channel to the electron_send command', async () => {
    const { ipcRenderer } = createBridge();
    ipcRenderer.send('minimize-app');
    await flush();
    expect(invoke).toHaveBeenCalledWith('electron_send', {
      channel: 'minimize-app',
      payload: null,
    });
  });

  it('passes payloads through untouched', async () => {
    const { ipcRenderer } = createBridge();
    ipcRenderer.send('island:set-enabled', false);
    await flush();
    expect(invoke).toHaveBeenCalledWith('electron_send', {
      channel: 'island:set-enabled',
      payload: false,
    });
  });

  it('turns undefined into null so Rust sees Option::None', async () => {
    // `{ payload: undefined }` is dropped by JSON serialisation, which makes
    // the Rust argument missing rather than None and fails deserialisation.
    const { ipcRenderer } = createBridge();
    ipcRenderer.send('run-smart-paste', undefined);
    await flush();
    expect(invoke).toHaveBeenCalledWith('electron_send', {
      channel: 'run-smart-paste',
      payload: null,
    });
  });

  it('preserves `false` rather than coercing it to null', async () => {
    // Guard against `data || null`: island:set-ignore-mouse(false) is the
    // "capture clicks" signal and must survive.
    const { ipcRenderer } = createBridge();
    ipcRenderer.send('island:set-ignore-mouse', false);
    await flush();
    expect(invoke).toHaveBeenCalledWith('electron_send', {
      channel: 'island:set-ignore-mouse',
      payload: false,
    });
  });

  it('blocks channels outside the allowlist', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const { ipcRenderer } = createBridge();
    ipcRenderer.send('rm-rf-everything');
    await flush();
    expect(invoke).not.toHaveBeenCalled();
    expect(warn).toHaveBeenCalled();
  });

  it('blocks emit-only channels', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    const { ipcRenderer } = createBridge();
    ipcRenderer.send('update-downloaded');
    await flush();
    expect(invoke).not.toHaveBeenCalled();
  });
});

describe('ipcRenderer.on', () => {
  it('delivers the event payload as a single argument', async () => {
    const { ipcRenderer } = createBridge();
    const handler = vi.fn();
    ipcRenderer.on('smart-paste-result', handler);
    await flush();

    const { entry } = settleListen();
    expect(entry.channel).toBe('smart-paste-result');
    entry.handler({ payload: { ok: true, changed: true } });
    expect(handler).toHaveBeenCalledWith({ ok: true, changed: true });
  });

  it('returns a working unsubscribe function', async () => {
    const { ipcRenderer } = createBridge();
    const off = ipcRenderer.on('update-available', vi.fn());
    await flush();
    const { unlisten } = settleListen();
    await flush();

    off();
    expect(unlisten).toHaveBeenCalledTimes(1);
  });

  it('unsubscribes even when the component unmounts before listen() resolves', async () => {
    // React effects can run their cleanup before the dynamic import settles;
    // without the cancelled flag this leaks a listener for the page's lifetime.
    const { ipcRenderer } = createBridge();
    const off = ipcRenderer.on('friday:proactive', vi.fn());
    await flush();

    off(); // unmount first
    const { unlisten } = settleListen();
    await flush();

    expect(unlisten).toHaveBeenCalledTimes(1);
  });

  it('is safe to call the unsubscribe twice', async () => {
    const { ipcRenderer } = createBridge();
    const off = ipcRenderer.on('update-downloaded', vi.fn());
    await flush();
    const { unlisten } = settleListen();
    await flush();

    off();
    off();
    expect(unlisten).toHaveBeenCalledTimes(1);
  });

  it('returns a no-op for channels outside the allowlist', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const { ipcRenderer } = createBridge();
    const off = ipcRenderer.on('not-a-channel', vi.fn());
    await flush();

    expect(pending).toHaveLength(0);
    expect(warn).toHaveBeenCalled();
    expect(() => off()).not.toThrow();
  });
});

describe('clipboard', () => {
  it('writes through the clipboard plugin', async () => {
    const { clipboard } = createBridge();
    clipboard.writeText('hello');
    await flush();
    expect(writeText).toHaveBeenCalledWith('hello');
  });
});
