import * as THREE from 'three';

/**
 * Runtime SDF font atlas generation.
 *
 * igloo.inc ships a pre-baked MSDF atlas produced by msdfgen. Generating a true
 * *multi*-channel field needs the glyph outlines, which the browser will not
 * hand over — so this rasterises each glyph and computes a single-channel signed
 * distance field with 8SSEDT (Danielsson's 8-point sequential Euclidean
 * distance transform, two passes, O(n)).
 *
 * The tradeoff versus real MSDF is sharp corners: a single channel rounds them
 * at large scales. Everything downstream is identical — the shader's 'median3'
 * degrades to identity on a greyscale sample, so the same material handles a
 * real MSDF atlas if you ever drop one in.
 */

const INF = 1e20;

/**
 * 8SSEDT over a boolean grid.
 * @param {Uint8Array} inside 1 where the glyph covers the pixel
 * @returns {Float32Array} signed distance in pixels, positive inside
 */
function signedDistanceField(inside, w, h) {
  // Two vector grids: one measuring distance to the nearest inside pixel,
  // one to the nearest outside pixel. Subtracting them gives the sign.
  const make = (seedInside) => {
    const dx = new Float32Array(w * h);
    const dy = new Float32Array(w * h);
    for (let i = 0; i < w * h; i++) {
      const on = seedInside ? inside[i] : !inside[i];
      if (on) { dx[i] = 0; dy[i] = 0; }
      else { dx[i] = INF; dy[i] = INF; }
    }
    return { dx, dy };
  };

  const propagate = ({ dx, dy }) => {
    const d2 = (i) => (dx[i] === INF ? INF : dx[i] * dx[i] + dy[i] * dy[i]);
    const compare = (i, ox, oy, x, y) => {
      const nx = x + ox, ny = y + oy;
      if (nx < 0 || ny < 0 || nx >= w || ny >= h) return;
      const j = ny * w + nx;
      if (dx[j] === INF) return;
      // Offset the neighbour's vector by the step we took to reach it.
      const vx = dx[j] - ox;
      const vy = dy[j] - oy;
      if (vx * vx + vy * vy < d2(i)) { dx[i] = vx; dy[i] = vy; }
    };

    // Forward pass: N, W, NW, NE
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        const i = y * w + x;
        compare(i, 0, -1, x, y);
        compare(i, -1, 0, x, y);
        compare(i, -1, -1, x, y);
        compare(i, 1, -1, x, y);
      }
      for (let x = w - 2; x >= 0; x--) compare(y * w + x, 1, 0, x, y);
    }
    // Backward pass: S, E, SE, SW
    for (let y = h - 1; y >= 0; y--) {
      for (let x = w - 1; x >= 0; x--) {
        const i = y * w + x;
        compare(i, 0, 1, x, y);
        compare(i, 1, 0, x, y);
        compare(i, 1, 1, x, y);
        compare(i, -1, 1, x, y);
      }
      for (let x = 1; x < w; x++) compare(y * w + x, -1, 0, x, y);
    }
  };

  const outer = make(true);   // distance from outside pixels to the glyph
  const inner = make(false);  // distance from inside pixels to the background
  propagate(outer);
  propagate(inner);

  const out = new Float32Array(w * h);
  for (let i = 0; i < w * h; i++) {
    const dOut = outer.dx[i] === INF ? INF : Math.hypot(outer.dx[i], outer.dy[i]);
    const dIn = inner.dx[i] === INF ? INF : Math.hypot(inner.dx[i], inner.dy[i]);
    out[i] = (dIn === INF ? 0 : dIn) - (dOut === INF ? 0 : dOut);
  }
  return out;
}

const DEFAULT_CHARSET =
  ' !"#$%&\'()*+,-./0123456789:;<=>?@' +
  'ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`' +
  'abcdefghijklmnopqrstuvwxyz{|}~';

/**
 * Build an SDF atlas + metrics for a CSS font.
 *
 * @returns {{texture: THREE.Texture, font: object}} 'font' matches the shape the
 *   layout worker expects (an msdf-bmfont-style descriptor, em-normalised).
 */
export function createSDFFont({
  family = 'system-ui, sans-serif',
  weight = 600,
  charset = DEFAULT_CHARSET,
  em = 48,
  padding = 10,
  distanceRange = 8,
  columns = 16,
} = {}) {
  const cell = Math.ceil(em * 1.7) + padding * 2;
  const rows = Math.ceil(charset.length / columns);
  const width = columns * cell;
  const height = rows * cell;

  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext('2d', { willReadFrequently: true });
  ctx.font = `${weight} ${em}px ${family}`;
  ctx.textBaseline = 'alphabetic';
  ctx.fillStyle = '#fff';

  const glyphs = {};
  const atlas = new Uint8Array(width * height * 4);

  charset.split('').forEach((char, index) => {
    const col = index % columns;
    const row = Math.floor(index / columns);
    const ox = col * cell;
    const oy = row * cell;

    const m = ctx.measureText(char);
    const advance = m.width / em;
    const isWhitespace = char.trim().length === 0;

    if (isWhitespace) {
      glyphs[char] = {
        unicode: char.codePointAt(0), advance, isWhitespace: true,
        planeBounds: { left: 0, right: 0, top: 0, bottom: 0 },
        atlasBounds: { left: 0, right: 0, top: 0, bottom: 0 },
      };
      return;
    }

    const left = m.actualBoundingBoxLeft ?? 0;
    const right = m.actualBoundingBoxRight ?? m.width;
    const ascent = m.actualBoundingBoxAscent ?? em * 0.8;
    const descent = m.actualBoundingBoxDescent ?? em * 0.2;

    // Draw the glyph into its own cell, offset by padding so the distance field
    // has room to fall off before it hits the cell boundary.
    ctx.clearRect(ox, oy, cell, cell);
    ctx.fillText(char, ox + padding + left, oy + padding + ascent);

    const img = ctx.getImageData(ox, oy, cell, cell).data;
    const bin = new Uint8Array(cell * cell);
    for (let i = 0; i < cell * cell; i++) bin[i] = img[i * 4 + 3] > 127 ? 1 : 0;

    const sdf = signedDistanceField(bin, cell, cell);
    for (let y = 0; y < cell; y++) {
      for (let x = 0; x < cell; x++) {
        // Map signed pixels into [0,1] with 0.5 at the outline.
        const v = Math.max(0, Math.min(255, Math.round((sdf[y * cell + x] / distanceRange + 0.5) * 255)));
        const o = ((oy + y) * width + (ox + x)) * 4;
        atlas[o] = atlas[o + 1] = atlas[o + 2] = v;
        atlas[o + 3] = 255;
      }
    }

    const glyphW = left + right;
    const glyphH = ascent + descent;
    glyphs[char] = {
      unicode: char.codePointAt(0),
      advance,
      isWhitespace: false,
      // Quad corners in em units, relative to the pen position on the baseline.
      planeBounds: {
        left: (-left - padding) / em,
        right: (right + padding) / em,
        top: (ascent + padding) / em,
        bottom: (-descent - padding) / em,
      },
      // Pixel rect in the atlas. 'top' is the visually upper edge.
      atlasBounds: {
        left: ox,
        right: ox + glyphW + padding * 2,
        top: oy,
        bottom: oy + glyphH + padding * 2,
      },
    };
  });

  const texture = new THREE.DataTexture(atlas, width, height, THREE.RGBAFormat);
  texture.minFilter = THREE.LinearFilter;
  texture.magFilter = THREE.LinearFilter;
  texture.generateMipmaps = false;
  texture.flipY = false;
  texture.colorSpace = THREE.NoColorSpace;
  texture.needsUpdate = true;

  const font = {
    metrics: { lineHeight: 1 }, // planeBounds are already em-normalised
    atlas: { width, height, distanceRange },
    glyphs,
    kerning: [], // canvas gives no kerning pairs; layout falls back to advances
    placeholderChar: '?',
  };

  return { texture, font };
}
