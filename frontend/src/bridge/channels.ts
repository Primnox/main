/**
 * IPC channel allowlists, shared by the Tauri bridge and its tests.
 *
 * These are the single source of truth on the JS side and are kept identical to
 * `src-tauri/src/channels.rs`. `channels.test.ts` reads the Rust file and fails
 * if the two ever drift — that drift is otherwise invisible until a feature
 * silently stops working on one of the two runtimes.
 */

/** Channels the renderer may send on (renderer → main). */
export const RENDERER_TO_MAIN = [
  // Window controls
  'minimize-app',
  'maximize-app',
  'close-app',
  'restart-app',
  // Island / tray
  'show-full-window',
  // Legacy
  'set-window-mode',
  // App IPC
  'friday:proactive',
  'friday:reply',
  'friday:clear-clipboard',
  'friday:mic-state',
  'friday:state',
  'friday:mic-toggle',
  'friday:open-notes',
  'island:set-ignore-mouse',
  'island:set-enabled',
  // Tauri-only; see the matching note in src-tauri/src/channels.rs. Absent from
  // preload.js on purpose, so under Electron this send is refused as a no-op.
  'island:set-size',
  'run-smart-paste',
  'window-minimize',
  'window-maximize',
  'window-close',
] as const;

/** Channels the app may emit on (main → renderer). */
export const MAIN_TO_RENDERER = [
  'primnox:island-mode',
  'friday:proactive',
  'friday:open-notes',
  'friday:mic-state',
  'friday:state',
  'morph-island',
  'render-token-binary',
  'update-available',
  'update-downloaded',
  'smart-paste-result',
] as const;

export type RendererToMain = (typeof RENDERER_TO_MAIN)[number];
export type MainToRenderer = (typeof MAIN_TO_RENDERER)[number];

const SENDABLE = new Set<string>(RENDERER_TO_MAIN);
const RECEIVABLE = new Set<string>(MAIN_TO_RENDERER);

export const canSend = (channel: string): boolean => SENDABLE.has(channel);
export const canReceive = (channel: string): boolean => RECEIVABLE.has(channel);
