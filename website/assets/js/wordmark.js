/* Samples a word into a shuffled point cloud. Shared by the intro cube field
   and the chat particle cloud so both target an identical wordmark. */

const cache = new Map();

function rand(i) {
  const x = Math.sin(i * 12.9898 + 78.233) * 43758.5453;
  return x - Math.floor(x);
}

export function sampleText(text, boxW, boxH, step = 3, opts = {}) {
  const weight = opts.weight || 800;
  const tracking = opts.tracking || '-0.02em';
  const label = opts.upper ? text.toUpperCase() : text;
  const key = `${label}|${Math.round(boxW)}|${Math.round(boxH)}|${step}|${weight}|${tracking}|${opts.jitter ?? 0.18}`;
  if (cache.has(key)) return cache.get(key);

  const c = document.createElement('canvas');
  c.width = Math.max(2, Math.round(boxW));
  c.height = Math.max(2, Math.round(boxH));
  const g = c.getContext('2d', { willReadFrequently: true });

  g.fillStyle = '#fff';
  g.textAlign = 'center';
  g.textBaseline = 'middle';
  g.letterSpacing = tracking;

  // Measure at a reference size rather than guessing an em-per-glyph ratio.
  // Syne at 800 runs ~1.16em per character; a guessed value overflows the
  // sampling canvas and the wordmark clips into a solid bar.
  const REF = 100;
  g.font = `${weight} ${REF}px Syne, system-ui, sans-serif`;
  const emWidth = g.measureText(label).width / REF;
  const size = Math.max(12, Math.min((c.width * 0.94) / emWidth, c.height * 0.72));

  g.font = `${weight} ${Math.round(size)}px Syne, system-ui, sans-serif`;
  g.fillText(label, c.width / 2, c.height / 2);

  const data = g.getImageData(0, 0, c.width, c.height).data;
  const pts = [];
  for (let y = 0; y < c.height; y += step) {
    for (let x = 0; x < c.width; x += step) {
      if (data[(y * c.width + x) * 4 + 3] > 128) {
        // A little jitter breaks the lattice, but it has to stay small
        // relative to the glyph: at a coarse step, half-cell noise is several
        // percent of the cap height and the letterforms go ragged.
        const j = step * (opts.jitter ?? 0.18);
        pts.push(
          x - c.width / 2 + (Math.random() - 0.5) * j,
          y - c.height / 2 + (Math.random() - 0.5) * j,
        );
      }
    }
  }

  // Shuffle: sampling walks scanlines, so truncating an ordered list to the
  // particle count fills only the top rows of the glyphs.
  const n = pts.length / 2;
  const out = new Float32Array(pts.length);
  const order = new Uint32Array(n);
  for (let i = 0; i < n; i++) order[i] = i;
  for (let i = n - 1; i > 0; i--) {
    const j = (rand(i) * (i + 1)) | 0;
    const t = order[i]; order[i] = order[j]; order[j] = t;
  }
  for (let i = 0; i < n; i++) {
    out[i * 2] = pts[order[i] * 2];
    out[i * 2 + 1] = pts[order[i] * 2 + 1];
  }

  cache.set(key, out);
  return out;
}

export function clearWordmarkCache() { cache.clear(); }
