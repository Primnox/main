/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

// Voice-Activity-Detection level updates arrive over the websocket at 10Hz+.
// Previously this was stored via useState in usePrimnox(), which lives in
// App.tsx's fiber — every tick triggered a full re-render of the entire
// application tree (chat, notes, sidebars, everything).
//
// This module is a tiny pub-sub bus: the websocket handler calls vadBus.set()
// directly (no setState, no App re-render). Only the one component that
// actually renders the VAD visualization (DynamicIsland) subscribes via
// useSyncExternalStore, so only it re-renders on each tick.

type Listener = () => void;

const listeners = new Set<Listener>();
let current = 0;

export const vadBus = {
  set(v: number) {
    current = v;
    listeners.forEach((l) => l());
  },
  get() {
    return current;
  },
  subscribe(listener: Listener) {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
};
