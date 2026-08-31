import { describe, expect, it } from 'vitest';
import { parseSSE, streamOf } from './sse';

async function collect(chunks: string[]) {
  const out: Array<{ event?: string; data: string }> = [];
  for await (const m of parseSSE(streamOf(chunks))) out.push(m);
  return out;
}

describe('parseSSE', () => {
  it('parses single-line data records split across chunks', async () => {
    const msgs = await collect(['data: hel', 'lo\n\ndata: world\n\n']);
    expect(msgs).toEqual([
      { event: undefined, data: 'hello' },
      { event: undefined, data: 'world' },
    ]);
  });

  it('joins multi-line data and keeps the event name', async () => {
    const msgs = await collect(['event: ping\ndata: a\ndata: b\n\n']);
    expect(msgs).toEqual([{ event: 'ping', data: 'a\nb' }]);
  });

  it('ignores comments and blank leading lines', async () => {
    const msgs = await collect([': keepalive\n\ndata: x\n\n']);
    expect(msgs).toEqual([{ event: undefined, data: 'x' }]);
  });

  it('emits a trailing record with no final blank line', async () => {
    const msgs = await collect(['data: last']);
    expect(msgs).toEqual([{ event: undefined, data: 'last' }]);
  });

  it('handles CRLF line endings', async () => {
    const msgs = await collect(['data: a\r\n\r\n']);
    expect(msgs).toEqual([{ event: undefined, data: 'a' }]);
  });
});
