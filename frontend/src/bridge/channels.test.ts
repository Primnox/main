import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  MAIN_TO_RENDERER,
  RENDERER_TO_MAIN,
  canReceive,
  canSend,
} from './channels';

const here = resolve(fileURLToPath(import.meta.url), '..');
const read = (rel: string) => readFileSync(resolve(here, rel), 'utf8');

/** Pull the string literals out of a `NAME: &[&str] = &[ ... ];` block. */
function rustList(source: string, name: string): string[] {
  const start = source.indexOf(`${name}: &[&str] = &[`);
  if (start === -1) throw new Error(`Rust list ${name} not found`);
  const end = source.indexOf('];', start);
  if (end === -1) throw new Error(`Rust list ${name} is unterminated`);
  const body = source.slice(start, end);
  return [...body.matchAll(/"([^"]+)"/g)].map((m) => m[1]);
}

/** Pull the `validChannels` array that follows a given key in the preload. */
function preloadChannels(source: string, after: string): string[] {
  const anchor = source.indexOf(after);
  if (anchor === -1) throw new Error(`preload anchor ${after} not found`);
  const start = source.indexOf('validChannels = [', anchor);
  const end = source.indexOf('];', start);
  const body = source.slice(start, end);
  return [...body.matchAll(/'([^']+)'/g)].map((m) => m[1]);
}

describe('channel allowlists', () => {
  it('has no duplicates', () => {
    expect(new Set(RENDERER_TO_MAIN).size).toBe(RENDERER_TO_MAIN.length);
    expect(new Set(MAIN_TO_RENDERER).size).toBe(MAIN_TO_RENDERER.length);
  });

  it('matches the Rust allowlists exactly', () => {
    const rs = read('../../src-tauri/src/channels.rs');
    expect(rustList(rs, 'RENDERER_TO_MAIN').sort()).toEqual(
      [...RENDERER_TO_MAIN].sort(),
    );
    expect(rustList(rs, 'MAIN_TO_RENDERER').sort()).toEqual(
      [...MAIN_TO_RENDERER].sort(),
    );
  });

  it('covers every channel the Electron preload allows', () => {
    // The Tauri bridge must not be more restrictive than the Electron preload,
    // or a feature that works in one build silently dies in the other.
    const preload = read('../../public/preload.js');
    for (const channel of preloadChannels(preload, 'send:')) {
      expect(canSend(channel), `preload send channel "${channel}"`).toBe(true);
    }
    for (const channel of preloadChannels(preload, 'on:')) {
      expect(canReceive(channel), `preload on channel "${channel}"`).toBe(true);
    }
  });

  it('covers every channel the island preload allows', () => {
    const preload = read('../../public/preload-island.js');
    for (const channel of preloadChannels(preload, 'send:')) {
      expect(canSend(channel), `island send channel "${channel}"`).toBe(true);
    }
    for (const channel of preloadChannels(preload, 'on:')) {
      expect(canReceive(channel), `island on channel "${channel}"`).toBe(true);
    }
  });

  it('does not let the renderer send on emit-only channels', () => {
    expect(canSend('update-available')).toBe(false);
    expect(canSend('update-downloaded')).toBe(false);
    expect(canSend('primnox:island-mode')).toBe(false);
  });

  it('rejects unknown and malformed channels', () => {
    expect(canSend('')).toBe(false);
    expect(canSend('__proto__')).toBe(false);
    expect(canReceive('nope')).toBe(false);
  });
});
