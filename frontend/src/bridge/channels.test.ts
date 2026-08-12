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
