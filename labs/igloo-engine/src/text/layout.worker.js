/**
 * Text layout worker.
 *
 * Line breaking is O(characters) with backtracking, and a headline re-laid out
 * on every resize will drop frames if it runs on the main thread — so it runs
 * here and posts back transferable typed arrays.
 *
 * The interesting output is not the quads, it's the four *weight* attributes.
 * Each vertex carries its normalised position within several nested orderings:
 *
 *   textWeights.x  glyph index / total glyphs      -> sweep across the whole block
 *   textWeights.y  word index  / total words       -> sweep word by word
 *   lineWeights.x  glyph index / glyphs in line    -> sweep within each line
 *   lineWeights.y  word index  / words in line     -> ditto, per word
 *   lineWeights.z  line index  / total lines       -> sweep line by line
 *
 * A single 'uAnimationOrder' uniform then selects which ordering drives the
 * reveal, and the same geometry animates five completely different ways with no
 * CPU work. That indirection is the whole trick behind the site's text.
 */

const NEWLINE = /\n/;
const WHITESPACE = /[ \t]/;
const NBSP = String.fromCharCode(0xa0);

function kerning(font, a, b) {
  for (let i = 0; i < font.kerning.length; i++) {
    const k = font.kerning[i];
    if (k.unicode1 === a && k.unicode2 === b) return k.advance;
  }
  return 0;
}

function layout(font, options) {
  let text = options.text || '';
  const maxWidth = options.width ?? Infinity;
  const align = options.align || 'left';
  const size = options.size || 1;
  const letterSpacing = options.letterSpacing || 0;
  const lineHeight = options.lineHeight || 1.4;
  const wordSpacing = options.wordSpacing || 0;
  const wordBreak = options.wordBreak || false;
  const baseOffset = options.baseOffset || 0;

  // Scale from font units to world units.
  const scale = size / font.metrics.lineHeight;

  // Map non-breaking spaces onto ordinary spaces: the atlas has no NBSP glyph
  // and would otherwise fall back to the placeholder character.
  text = text.split(NBSP).join(String.fromCharCode(32));
  const glyphCount = text.replace(/[ \n]/g, '').length;

  const out = {
    index: new Uint16Array(glyphCount * 6),
    position: new Float32Array(glyphCount * 4 * 3),
    uv: new Float32Array(glyphCount * 4 * 2),
    centroid: new Float32Array(glyphCount * 4 * 3),
    uvBounds: new Float32Array(glyphCount * 4 * 4),
    textWeights: new Float32Array(glyphCount * 4 * 2),
    lineWeights: new Float32Array(glyphCount * 4 * 3),
    maxLineHeight: 0,
    blockWidth: 0,
    blockHeight: 0,
  };

  // Two triangles per glyph quad, wound counter-clockwise.
  for (let i = 0; i < glyphCount; i++) {
    out.index.set([i * 4, i * 4 + 2, i * 4 + 1, i * 4 + 1, i * 4 + 2, i * 4 + 3], i * 6);
  }

  /* ---------------- line breaking ---------------- */

  const lines = [];
  let cursor = 0;
  let lastBreak = 0;      // index of the last whitespace we could break at
  let sinceBreak = 0;     // width accumulated since that break opportunity

  const newLine = () => {
    const line = { width: 0, glyphs: [] };
    lines.push(line);
    lastBreak = cursor;
    sinceBreak = 0;
    return line;
  };

  let line = newLine();

  while (cursor < text.length) {
    let char = text[cursor];

    // Collapse leading whitespace on a wrapped line.
    if (!line.width && WHITESPACE.test(char)) {
      cursor++;
      lastBreak = cursor;
      sinceBreak = 0;
      continue;
    }

    if (NEWLINE.test(char)) {
      // Trailing space before an explicit break should not count toward width.
      const last = line.glyphs[line.glyphs.length - 1];
      if (last && last[0].isWhitespace) {
        line.width -= wordSpacing * size + last[0].advance * scale;
        line.glyphs.pop();
      }
      cursor++;
      line = newLine();
      continue;
    }

    let glyph = font.glyphs[char];
    if (!glyph) {
      char = font.placeholderChar;
      glyph = font.glyphs[char];
    }

    if (line.glyphs.length) {
      const prev = line.glyphs[line.glyphs.length - 1][0];
      const k = kerning(font, glyph.unicode, prev.unicode) * scale;
      line.width += k;
      sinceBreak += k;
    }

    line.glyphs.push([glyph, line.width]);

    let advance = 0;
    if (glyph.isWhitespace) {
      lastBreak = cursor;
      sinceBreak = 0;
      advance += wordSpacing * size;
    } else {
      advance += letterSpacing * size;
    }
    advance += glyph.advance * scale;

    line.width += advance;
    sinceBreak += advance;

    if (line.width > maxWidth) {
      if (wordBreak && line.glyphs.length > 1) {
        // Hard break mid-word: drop the overflowing glyph and retry it next line.
        line.width -= advance;
        line.glyphs.pop();
        line = newLine();
        continue;
      }
      if (!wordBreak && sinceBreak !== line.width) {
        // Rewind the whole trailing word back to the last break opportunity.
        const rewind = cursor - lastBreak + 1;
        line.glyphs.splice(-rewind, rewind);
        cursor = lastBreak;
        line.width -= sinceBreak;
        line = newLine();
        continue;
      }
    }
    cursor++;
  }
  if (!line.width) lines.pop();

  /* ---------------- ordering weights ---------------- */

  let totalGlyphs = -1;
  let totalWords = -1;
  const wordsPerLine = [];
  lines.forEach((l) => {
    totalGlyphs += l.glyphs.length;
    totalWords++;
    let words = 0;
    l.glyphs.forEach((g) => { if (g[0].isWhitespace) { totalWords++; words++; } });
    wordsPerLine.push(words);
  });

  const invGlyphs = totalGlyphs < 1 ? 0 : 1 / totalGlyphs;
  const invWords = totalWords < 1 ? 0 : 1 / totalWords;
  const invLines = lines.length - 1 < 1 ? 0 : 1 / (lines.length - 1);
  const invLineGlyphs = lines.map((l) => (l.glyphs.length - 1 < 1 ? 0 : 1 / (l.glyphs.length - 1)));
  const invLineWords = wordsPerLine.map((w) => (w < 1 ? 0 : 1 / w));

  /* ---------------- quad emission ---------------- */

  const aw = font.atlas.width;
  const ah = font.atlas.height;

  let penY = baseOffset * size;
  let quad = 0;
  let glyphOrdinal = -1;
  let wordOrdinal = 0;
  let widest = 0;

  for (let li = 0; li < lines.length; li++) {
    const l = lines[li];
    widest = Math.max(widest, l.width);
    const lineWeight = li * invLines;

    for (let gi = 0, wi = 0; gi < l.glyphs.length; gi++) {
      const glyph = l.glyphs[gi][0];
      let penX = l.glyphs[gi][1];
      if (align === 'center') penX -= l.width * 0.5;
      else if (align === 'right') penX -= l.width;

      glyphOrdinal++;
      if (glyph.isWhitespace) { wordOrdinal++; wi++; continue; }

      const pb = glyph.planeBounds;
      const x0 = penX + pb.left * scale;
      const x1 = penX + pb.right * scale;
      const y0 = penY + pb.bottom * scale;
      const y1 = penY + pb.top * scale;

      out.position.set([x0, y0, 0, x0, y1, 0, x1, y0, 0, x1, y1, 0], quad * 12);
      out.maxLineHeight = Math.max(out.maxLineHeight, Math.abs(y1 - y0));

      // Quad centre, so the vertex shader can rotate/scale each glyph about
      // itself without needing a per-glyph matrix.
      const cx = (x0 + x1) * 0.5;
      const cy = (y0 + y1) * 0.5;
      out.centroid.set([cx, cy, 0, cx, cy, 0, cx, cy, 0, cx, cy, 0], quad * 12);

      const ab = glyph.atlasBounds;
      const u0 = ab.left / aw;
      const u1 = ab.right / aw;
      // The atlas is a DataTexture, and WebGL's UNPACK_FLIP_Y has no effect on
      // ArrayBufferView uploads — so row 0 of the data is v = 0, which is the
      // *top* of the canvas. V therefore runs the same direction as the rows.
      const v0 = ab.bottom / ah;
      const v1 = ab.top / ah;

      out.uv.set([u0, v0, u0, v1, u1, v0, u1, v1], quad * 8);
      out.uvBounds.set([u0, u1, v0, v1, u0, u1, v0, v1, u0, u1, v0, v1, u0, u1, v0, v1], quad * 16);

      const tg = glyphOrdinal * invGlyphs;
      const tw = wordOrdinal * invWords;
      out.textWeights.set([tg, tw, tg, tw, tg, tw, tg, tw], quad * 8);

      const lg = invLineGlyphs[li] * gi;
      const lw = invLineWords[li] * wi;
      out.lineWeights.set([lg, lw, lineWeight, lg, lw, lineWeight, lg, lw, lineWeight, lg, lw, lineWeight], quad * 12);

      quad++;
    }
    wordOrdinal++;
    penY -= size * lineHeight;
  }

  out.blockWidth = widest;
  out.blockHeight = lines.length * size * lineHeight;
  return out;
}

self.onmessage = (event) => {
  const { font, options, id } = event.data;
  const buffers = layout(font, options);
  const transfer = [];
  for (const key of Object.keys(buffers)) {
    if (buffers[key] && buffers[key].buffer) transfer.push(buffers[key].buffer);
  }
  self.postMessage({ id, buffers }, transfer);
};
