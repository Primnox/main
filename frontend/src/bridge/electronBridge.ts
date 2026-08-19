/**
 * The app's IPC surface, backed by Tauri.
 *
 * Electron has been removed — Tauri is the only shell now. The
 * `window.electron.ipcRenderer` SHAPE is kept deliberately: the React app and
 * `island/island.js` were written against it across ~25 call sites, and
 * renaming a working interface buys nothing but churn and regression risk.
 * Read `window.electron` as "the desktop IPC bridge"; nothing Electron
 * remains behind it.
 *
 * Install it from `main.tsx` before React mounts.
 */

import { canReceive, canSend } from './channels';

type Listener = (...args: any[]) => void;
type Unsubscribe = () => void;

interface ElectronCompat {
  ipcRenderer: {
    send: (channel: string, data?: unknown) => void;
    on: (channel: string, func: Listener) => Unsubscribe;
  };
  clipboard: {
    writeText: (text: string) => void;
  };
}

/**
 * Is this page running inside a Tauri webview?
 *
 * Tauri v2 injects `__TAURI_INTERNALS__` before any app code runs. Checked
 * directly rather than via `isTauri()` from `@tauri-apps/api` so that this
 * module stays importable (and tree-shakeable) in the Electron build, where the
 * Tauri runtime is absent.
 */
export function isTauriRuntime(): boolean {
  return typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window;
}

/**
 * Subscribe to a Tauri event, returning a synchronous unsubscribe function.
 *
 * `listen()` is async but Electron's `on()` returns its cleanup synchronously,
 * and React effects call that cleanup on unmount — which can happen before the
 * subscription resolves. The `cancelled` flag makes the late-arriving handle
 * unsubscribe itself instead of leaking a listener onto a dead component.
 */
function subscribe(channel: string, func: Listener): Unsubscribe {
  let unlisten: (() => void) | null = null;
  let cancelled = false;

  import('@tauri-apps/api/event')
    .then(({ listen }) =>
      listen(channel, (event) => {
        func(event.payload);
      }),
    )
    .then((fn) => {
      if (cancelled) fn();
      else unlisten = fn;
    })
    .catch((err) => {
      console.error(`[bridge] failed to listen on "${channel}"`, err);
    });

  return () => {
    cancelled = true;
    if (unlisten) {
      unlisten();
      unlisten = null;
    }
  };
}

function send(channel: string, data?: unknown): void {
  if (!canSend(channel)) {
    console.warn(`[bridge] blocked send on unregistered channel "${channel}"`);
    return;
  }
  import('@tauri-apps/api/core')
    .then(({ invoke }) =>
      // `payload` is Option<Value> in Rust; undefined must become null so the
      // argument is present and deserialises as None rather than being dropped.
      invoke('electron_send', { channel, payload: data ?? null }),
    )
    .catch((err) => {
      console.error(`[bridge] invoke failed for "${channel}"`, err);
    });
}

function on(channel: string, func: Listener): Unsubscribe {
  if (!canReceive(channel)) {
    console.warn(`[bridge] blocked listen on unregistered channel "${channel}"`);
    return () => {};
  }
  return subscribe(channel, func);
}

function writeText(text: string): void {
  import('@tauri-apps/plugin-clipboard-manager')
    .then(({ writeText: write }) => write(text))
    .catch((err) => {
      console.error('[bridge] clipboard write failed', err);
    });
}

/** The object installed at `window.electron`. Exported for tests. */
export function createBridge(): ElectronCompat {
  return {
    ipcRenderer: { send, on },
    clipboard: { writeText },
  };
}

/**
 * Install the compatibility layer.
 *
 * No-op outside Tauri, and no-op when a preload has already provided
 * `window.electron` — the real Electron bridge always wins.
 */
export function installElectronBridge(): boolean {
  if (!isTauriRuntime()) return false;
  if ((window as any).electron) return false;
  (window as any).electron = createBridge();
  return true;
}
