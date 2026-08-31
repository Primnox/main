import * as THREE from 'three';
import { Pass, createRT } from '../core/gpu.js';
import { common } from '../glsl/chunks.js';

/**
 * Procedural asset generation.
 *
 * igloo.inc ships its blue noise, LUT and noise tiles as KTX2/basis textures.
 * This engine has no binary assets at all — every lookup table below is
 * synthesised at boot, which keeps the repo self-contained and makes the
 * parameters of each table legible instead of baked into a file.
 */

/* ------------------------------------------------------------------ *
 * Blue noise — void-and-cluster (Ulichney 1993)
 * ------------------------------------------------------------------ */

/**
 * Generate one channel of tileable blue noise.
 *
 * White noise dithering is visible as clumps; blue noise has no low-frequency
 * energy, so the eye integrates it away. The algorithm ranks every pixel by
 * repeatedly finding the "tightest cluster" and "largest void" in a toroidal
 * Gaussian energy field, maintained incrementally so each step is O(kernel).
 *
 * @param {number} size edge length (power of two, tiles seamlessly)
 * @param {() => number} rng
 * @returns {Float32Array} ranks normalised to [0,1)
 */
function blueNoiseChannel(size, rng) {
  const N = size * size;
  const sigma = 1.9;
  const radius = Math.ceil(sigma * 2.5);
  const span = radius * 2 + 1;

  // Precompute the toroidal Gaussian kernel once.
  const kernel = new Float32Array(span * span);
  for (let y = -radius; y <= radius; y++) {
    for (let x = -radius; x <= radius; x++) {
      kernel[(y + radius) * span + (x + radius)] = Math.exp(-(x * x + y * y) / (2 * sigma * sigma));
    }
  }

  const energy = new Float32Array(N);
  const pattern = new Uint8Array(N);

  const splat = (index, sign) => {
    const px = index % size;
    const py = (index / size) | 0;
    for (let y = -radius; y <= radius; y++) {
      const wy = (py + y + size) % size;
      for (let x = -radius; x <= radius; x++) {
        const wx = (px + x + size) % size;
        energy[wy * size + wx] += sign * kernel[(y + radius) * span + (x + radius)];
      }
    }
  };

  // Tightest cluster = highest energy among set pixels.
  const tightestCluster = () => {
    let best = -1, bestVal = -Infinity;
    for (let i = 0; i < N; i++) {
      if (pattern[i] && energy[i] > bestVal) { bestVal = energy[i]; best = i; }
    }
    return best;
  };
  // Largest void = lowest energy among unset pixels.
  const largestVoid = () => {
    let best = -1, bestVal = Infinity;
    for (let i = 0; i < N; i++) {
      if (!pattern[i] && energy[i] < bestVal) { bestVal = energy[i]; best = i; }
    }
    return best;
  };

  // --- Seed: a sparse random binary pattern, relaxed until stable.
  const initialOnes = Math.max(1, Math.round(N / 10));
  let placed = 0;
  while (placed < initialOnes) {
    const i = (rng() * N) | 0;
    if (!pattern[i]) { pattern[i] = 1; splat(i, 1); placed++; }
  }
  for (let guard = 0; guard < N * 4; guard++) {
    const cluster = tightestCluster();
    pattern[cluster] = 0; splat(cluster, -1);
    const voidPos = largestVoid();
    if (voidPos === cluster) { pattern[cluster] = 1; splat(cluster, 1); break; }
    pattern[voidPos] = 1; splat(voidPos, 1);
  }

  const rank = new Int32Array(N).fill(-1);
  const seed = Uint8Array.from(pattern);

  // --- Phase 1: remove points from the seed, ranking downward from ones-1.
  for (let r = initialOnes - 1; r >= 0; r--) {
    const cluster = tightestCluster();
    pattern[cluster] = 0; splat(cluster, -1);
    rank[cluster] = r;
  }

  // --- Phases 2+3: restore the seed and insert into voids, ranking upward.
  pattern.set(seed);
  energy.fill(0);
  for (let i = 0; i < N; i++) if (pattern[i]) splat(i, 1);
  for (let r = initialOnes; r < N; r++) {
    const voidPos = largestVoid();
    if (voidPos < 0) break;
    pattern[voidPos] = 1; splat(voidPos, 1);
    rank[voidPos] = r;
  }

  const out = new Float32Array(N);
  for (let i = 0; i < N; i++) out[i] = Math.max(0, rank[i]) / N;
  return out;
}

/** Deterministic PRNG so the generated assets are identical every run. */
function mulberry32(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/**
 * RGBA blue noise texture. Each channel is an independent void-and-cluster
 * ranking so a shader can take four decorrelated dither samples per pixel.
 */
export function makeBlueNoiseTexture(size = 64) {
  const data = new Uint8Array(size * size * 4);
  for (let c = 0; c < 4; c++) {
    const channel = blueNoiseChannel(size, mulberry32(0x9e3779b9 + c * 7919));
    for (let i = 0; i < size * size; i++) {
      data[i * 4 + c] = Math.min(255, (channel[i] * 256) | 0);
    }
  }
  const tex = new THREE.DataTexture(data, size, size, THREE.RGBAFormat);
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  tex.minFilter = tex.magFilter = THREE.NearestFilter; // never interpolate a dither pattern
  tex.needsUpdate = true;
  tex.userData.size = size;
  return tex;
}

/* ------------------------------------------------------------------ *
 * 3D LUT colour grade
 * ------------------------------------------------------------------ */

/** Filmic S-curve in [0,1]. */
const contrast = (x, amount) => {
  const c = x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2;
  return x + (c - x) * amount;
};

/**
 * The "ice" grade: cool, lifted shadows with a slight cyan cast, compressed
 * highlights pulled a touch warm so specular hits read as sunlight through ice.
 * Baked into a strip LUT (size*size x size) rather than evaluated per pixel.
 */
export function makeLUTTexture(size = 32) {
  const width = size * size;
  const data = new Uint8Array(width * size * 4);

  for (let b = 0; b < size; b++) {
    for (let g = 0; g < size; g++) {
      for (let r = 0; r < size; r++) {
        let R = r / (size - 1);
        let G = g / (size - 1);
        let B = b / (size - 1);

        const l = 0.2126 * R + 0.7152 * G + 0.0722 * B;

        // Lift shadows toward blue, roll highlights toward warm white.
        const shadow = Math.pow(1 - l, 2.0);
        const highlight = Math.pow(l, 2.0);
        R += shadow * -0.020 + highlight * 0.030;
        G += shadow * 0.006 + highlight * 0.018;
        B += shadow * 0.055 + highlight * -0.010;

        // Global contrast + a small desaturation before the blue push,
        // so the cast lands on the whole frame instead of only saturated pixels.
        R = contrast(R, 0.28);
        G = contrast(G, 0.28);
        B = contrast(B, 0.28);
        const lum = 0.2126 * R + 0.7152 * G + 0.0722 * B;
        const sat = 0.88;
        R = lum + (R - lum) * sat;
        G = lum + (G - lum) * sat;
        B = lum + (B - lum) * sat * 1.12;

        // The row index is flipped to match the sampler in 'lut' chunk.
        const x = b * size + r;
        const y = size - 1 - g;
        const o = (y * width + x) * 4;
        data[o + 0] = Math.max(0, Math.min(255, Math.round(R * 255)));
        data[o + 1] = Math.max(0, Math.min(255, Math.round(G * 255)));
        data[o + 2] = Math.max(0, Math.min(255, Math.round(B * 255)));
        data[o + 3] = 255;
      }
    }
  }

  const tex = new THREE.DataTexture(data, width, size, THREE.RGBAFormat);
  tex.wrapS = tex.wrapT = THREE.ClampToEdgeWrapping;
  tex.minFilter = tex.magFilter = THREE.LinearFilter;
  tex.needsUpdate = true;
  tex.userData.size = size;
  return tex;
}

/* ------------------------------------------------------------------ *
 * GPU-baked noise tiles
 * ------------------------------------------------------------------ */

const TILEABLE = /* glsl */ `
  float vhash(vec2 p, float period) {
    p = mod(p, period);
    return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123);
  }
  float tileNoise(vec2 p, float period) {
    vec2 i = floor(p), f = fract(p);
    vec2 u = f * f * (3.0 - 2.0 * f);
    float a = vhash(i + vec2(0.0, 0.0), period);
    float b = vhash(i + vec2(1.0, 0.0), period);
    float c = vhash(i + vec2(0.0, 1.0), period);
    float d = vhash(i + vec2(1.0, 1.0), period);
    return mix(mix(a, b, u.x), mix(c, d, u.x), u.y);
  }
  float tileFbm(vec2 p, float period, int octaves) {
    float sum = 0.0, amp = 0.5, norm = 0.0, per = period;
    for (int i = 0; i < 6; i++) {
      if (i >= octaves) break;
      sum += amp * tileNoise(p, per);
      norm += amp;
      p *= 2.0; per *= 2.0; amp *= 0.5;
    }
    return sum / norm;
  }
`;

/** Bake a seamless RGBA noise tile: R = fbm, GB = a curl-ish flow field, A = ridged. */
export function bakeNoiseTile(renderer, size = 256) {
  const rt = createRT(size, size, { type: THREE.UnsignedByteType });
  rt.texture.wrapS = rt.texture.wrapT = THREE.RepeatWrapping;

  const pass = new Pass({
    uniforms: { uPeriod: { value: 8.0 } },
    fragmentShader: /* glsl */ `
      precision highp float;
      varying vec2 vUv;
      uniform float uPeriod;
      ${TILEABLE}
      void main() {
        vec2 p = vUv * uPeriod;
        float base = tileFbm(p, uPeriod, 5);
        // Finite-difference gradient of a second field -> a divergence-light flow.
        float e = 1.0 / 256.0;
        float nx = tileFbm(p + vec2(e, 0.0) * uPeriod, uPeriod, 3) - tileFbm(p - vec2(e, 0.0) * uPeriod, uPeriod, 3);
        float ny = tileFbm(p + vec2(0.0, e) * uPeriod, uPeriod, 3) - tileFbm(p - vec2(0.0, e) * uPeriod, uPeriod, 3);
        vec2 flow = normalize(vec2(ny, -nx) + 1e-5) * 0.5 + 0.5;
        float ridged = 1.0 - abs(tileFbm(p * 2.0, uPeriod * 2.0, 4) * 2.0 - 1.0);
        gl_FragColor = vec4(base, flow.x, flow.y, ridged);
      }
    `,
  });
  pass.render(renderer, rt);
  pass.dispose();
  return rt.texture;
}

/**
 * Bake a seamless caustics tile.
 *
 * Caustics are the bright envelope where refracted rays bunch up, so the cheap
 * screen-space approximation is the *inverse* of a noise field's distance to
 * zero: sharp ridges where the field crosses, dark elsewhere. Two of these
 * sampled at different scales and 'min'-ed together give the interlocking mesh.
 */
export function bakeCausticsTile(renderer, size = 512) {
  const rt = createRT(size, size, { type: THREE.UnsignedByteType });
  rt.texture.wrapS = rt.texture.wrapT = THREE.RepeatWrapping;

  const pass = new Pass({
    uniforms: { uPeriod: { value: 6.0 } },
    fragmentShader: /* glsl */ `
      precision highp float;
      varying vec2 vUv;
      uniform float uPeriod;
      ${TILEABLE}
      void main() {
        vec2 p = vUv * uPeriod;
        float a = tileFbm(p, uPeriod, 4) * 2.0 - 1.0;
        float b = tileFbm(p + vec2(3.7, 1.3), uPeriod, 4) * 2.0 - 1.0;
        float ridgeA = pow(1.0 - abs(a), 12.0);
        float ridgeB = pow(1.0 - abs(b), 12.0);
        float c = clamp(ridgeA + ridgeB * 0.7, 0.0, 1.0);
        gl_FragColor = vec4(vec3(c), 1.0);
      }
    `,
  });
  pass.render(renderer, rt);
  pass.dispose();
  return rt.texture;
}

/**
 * Bake a procedural equirectangular environment.
 *
 * Deliberately *not* PMREM'd into a CubeUV target: the ice material samples the
 * environment directly with an LOD bias derived from surface roughness, which
 * needs a plain 2D texture with a mip chain. Three.js can still consume the same
 * texture as 'scene.environment' by tagging the mapping.
 *
 * The content is a gradient sky plus three rectangular "softbox" lobes — ice
 * only reads as ice when it has long, hard-edged specular streaks to refract.
 */
export function bakeEnvironment(renderer, width = 1024) {
  const height = width / 2;
  const rt = new THREE.WebGLRenderTarget(width, height, {
    depthBuffer: false,
    stencilBuffer: false,
    type: THREE.HalfFloatType,
    minFilter: THREE.LinearMipmapLinearFilter,
    magFilter: THREE.LinearFilter,
    wrapS: THREE.RepeatWrapping,
    wrapT: THREE.ClampToEdgeWrapping,
    generateMipmaps: true,
  });
  rt.texture.colorSpace = THREE.NoColorSpace; // linear HDR-ish radiance
  rt.texture.mapping = THREE.EquirectangularReflectionMapping;

  const pass = new Pass({
    uniforms: {},
    fragmentShader: /* glsl */ `
      precision highp float;
      varying vec2 vUv;
      ${common}

      // Rectangular area light: angular distance to a box lobe, so the highlight
      // has a straight edge instead of the round blob a dot-power gives.
      float softbox(vec3 d, vec3 dir, vec2 halfAngle, float sharpness) {
        vec3 f = normalize(dir);
        vec3 r = normalize(cross(vec3(0.0, 1.0, 0.0), f) + vec3(1e-4));
        vec3 u = cross(f, r);
        float fwd = dot(d, f);
        if (fwd <= 0.0) return 0.0;
        vec2 local = vec2(dot(d, r), dot(d, u)) / fwd;
        vec2 q = abs(local) - halfAngle;
        float dist = length(max(q, 0.0)) + min(max(q.x, q.y), 0.0);
        return pow(saturate_(1.0 - dist * sharpness), 3.0) * step(0.0, fwd);
      }

      void main() {
        // Equirect: u -> azimuth, v -> elevation.
        float phi = (vUv.x - 0.5) * TAU;
        float theta = (vUv.y - 0.5) * PI;
        vec3 d = vec3(cos(theta) * sin(phi), sin(theta), cos(theta) * cos(phi));

        // Overcast polar daylight: a bright, almost uniform dome. This is the
        // whole reason the reference reads as snow — an HDRI with strong dark
        // regions would put black in every reflection and kill the high key.
        float h = d.y * 0.5 + 0.5;
        vec3 ground = vec3(0.72, 0.75, 0.80);
        vec3 horizon = vec3(0.86, 0.89, 0.93);
        vec3 zenith = vec3(1.05, 1.08, 1.14);
        vec3 col = mix(ground, horizon, smoothstep(0.30, 0.52, h));
        col = mix(col, zenith, smoothstep(0.5, 1.0, h));

        // Diffuse sun disc behind cloud: a broad, soft, barely-warm lobe. Ice
        // still needs one bright anchor or the specular streaks disappear.
        col += vec3(1.6, 1.58, 1.5) * softbox(d, vec3(-0.35, 0.72, 0.60), vec2(0.30, 0.22), 2.2);
        col += vec3(0.35, 0.38, 0.45) * softbox(d, vec3(0.9, 0.15, -0.4), vec2(0.5, 0.4), 1.6);

        gl_FragColor = vec4(col, 1.0);
      }
    `,
  });
  pass.render(renderer, rt);
  pass.dispose();
  return rt.texture;
}
