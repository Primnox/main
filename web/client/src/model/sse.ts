/* A minimal Server-Sent Events parser over a fetch response body.

   Every browser-callable provider streams as SSE (OpenAI-compatible, Anthropic,
   Gemini with ?alt=sse). This yields one {event?, data} per SSE record so each
   provider adapter only has to parse its own JSON.

   Spec note: a stream that ends mid-record without a trailing blank line has an
   incomplete final event that SSE says to discard. Provider streams always end
   with the blank line (or `[DONE]`), but this parser is lenient and flushes a
   trailing unterminated `data:` line anyway — harmless, and more robust to odd
   proxies. */

export interface SSEMessage {
  event?: string;
  data: string;
}

export async function* parseSSE(
  body: ReadableStream<Uint8Array>,
  signal?: AbortSignal,
): AsyncGenerator<SSEMessage> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buf = '';
  let event: string | undefined;
  let data: string[] = [];

  const take = (): SSEMessage | null => {
    if (data.length === 0 && event === undefined) return null;
    const msg: SSEMessage = { event, data: data.join('\n') };
    event = undefined;
    data = [];
    return msg;
  };

  // returns a completed message when the line was a blank separator
  const consumeLine = (raw: string): SSEMessage | null => {
    let line = raw.endsWith('\r') ? raw.slice(0, -1) : raw;
    if (line === '') return take();
    if (line.startsWith(':')) return null; // comment / keepalive

    const idx = line.indexOf(':');
    const field = idx === -1 ? line : line.slice(0, idx);
    let val = idx === -1 ? '' : line.slice(idx + 1);
    if (val.startsWith(' ')) val = val.slice(1);
    if (field === 'data') data.push(val);
    else if (field === 'event') event = val;
    return null;
  };

  try {
    for (;;) {
      if (signal?.aborted) throw new DOMException('aborted', 'AbortError');
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });

      let nl: number;
      while ((nl = buf.indexOf('\n')) !== -1) {
        const line = buf.slice(0, nl);
        buf = buf.slice(nl + 1);
        const m = consumeLine(line);
        if (m) yield m;
      }
    }
    if (buf.length) {
      const m = consumeLine(buf);
      if (m) yield m;
    }
    const trailing = take();
    if (trailing) yield trailing;
  } finally {
    reader.releaseLock();
  }
}

/** Test/util: a byte stream from string chunks. */
export function streamOf(chunks: string[]): ReadableStream<Uint8Array> {
  const enc = new TextEncoder();
  let i = 0;
  return new ReadableStream<Uint8Array>({
    pull(controller) {
      if (i < chunks.length) {
        controller.enqueue(enc.encode(chunks[i++]!));
      } else {
        controller.close();
      }
    },
  });
}
