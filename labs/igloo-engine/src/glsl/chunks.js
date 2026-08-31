/**
 * Shared GLSL chunk library.
 *
 * igloo.inc's bundle composes every shader out of a handful of interpolated
 * includes (minified to '${ae}', '${Ht}', '${Ue}', '${Uc}', '${Cr}', '${Lc}'...).
 * This is the same pattern, written from scratch with readable names.
 *
 * Everything targets GLSL ES 1.00 ('texture2D', 'varying', 'gl_FragColor') so it
 * drops straight into a three.js ShaderMaterial or an onBeforeCompile injection.
 */

/** Constants + remapping helpers. Included by nearly every shader. */
export const common = /* glsl */ `
  #ifndef PI
  #define PI  3.141592653589793
  #define TAU 6.283185307179586
  #endif

  float saturate_(float x) { return clamp(x, 0.0, 1.0); }
  vec3  saturate_(vec3 x)  { return clamp(x, vec3(0.0), vec3(1.0)); }

  // Remap v from [a,b] into [c,d], clamped.
  float fit(float v, float a, float b, float c, float d) {
    return c + (d - c) * saturate_((v - a) / (b - a));
  }
  float fit01(float v, float c, float d) { return fit(v, 0.0, 1.0, c, d); }
  float linearstep(float a, float b, float v) { return saturate_((v - a) / (b - a)); }

  /**
   * Soft directional wipe.
   *
   * Sweeps a threshold from below 'lo' to above 'hi' as 'progress' goes 0 -> 1,
   * with 'softness' controlling the width of the gradient edge. Returns 0 for
   * "not yet reached", 1 for "fully past". Larger softness = blurrier front.
   */
  float falloff(float v, float lo, float hi, float softness, float progress) {
    float threshold = mix(lo - softness, hi + softness, progress);
    return saturate_((threshold - v) / max(softness, 1e-4));
  }

  float luma(vec3 c) { return dot(c, vec3(0.2126, 0.7152, 0.0722)); }

  vec2 rotateUV(vec2 uv, float a, vec2 pivot) {
    float s = sin(a), c = cos(a);
    uv -= pivot;
    uv = mat2(c, -s, s, c) * uv;
    return uv + pivot;
  }
  vec2 scaleUV(vec2 uv, vec2 s, vec2 pivot) { return (uv - pivot) / s + pivot; }

  // Cover-fit a texture into a viewport of a given aspect (CSS background-size: cover).
  vec2 coverUV(vec2 uv, float viewAspect, float texAspect) {
    vec2 s = viewAspect > texAspect
      ? vec2(1.0, texAspect / viewAspect)
      : vec2(viewAspect / texAspect, 1.0);
    return (uv - 0.5) * s + 0.5;
  }
`;

/**
 * Framerate-independent smoothing.
 *
 * The one utility you cannot skip if the site must feel identical at 60/120/144Hz.
 * 'lerpFPS' converts a per-frame lerp coefficient authored at 60fps into the
 * equivalent coefficient for the actual delta time.
 */
export const damping = /* glsl */ `
  float lerpCoefFPS(float coef, float dt) {
    return 1.0 - pow(1.0 - coef, dt * 60.0);
  }
  float lerpFPS(float a, float b, float coef, float dt) {
    return mix(a, b, lerpCoefFPS(coef, dt));
  }
  vec2 lerpFPS(vec2 a, vec2 b, float coef, float dt) {
    return mix(a, b, lerpCoefFPS(coef, dt));
  }
  vec3 lerpFPS(vec3 a, vec3 b, float coef, float dt) {
    return mix(a, b, lerpCoefFPS(coef, dt));
  }
`;

/** Penner easings, GLSL form. The bundle ships all 30-odd; these are the ones actually used. */
export const easings = /* glsl */ `
  float power1In(float t)  { return t * t; }
  float power1Out(float t) { return 1.0 - (1.0 - t) * (1.0 - t); }
  float power2In(float t)  { return t * t * t; }
  float power2Out(float t) { float f = 1.0 - t; return 1.0 - f * f * f; }
  float power3In(float t)  { return t * t * t * t; }
  float power3Out(float t) { float f = 1.0 - t; return 1.0 - f * f * f * f; }
  float power4In(float t)  { return t * t * t * t * t; }
  float power4Out(float t) { float f = 1.0 - t; return 1.0 - f * f * f * f * f; }
  float sineIn(float t)    { return 1.0 - cos(t * PI * 0.5); }
  float sineOut(float t)   { return sin(t * PI * 0.5); }
  float sineInOut(float t) { return -0.5 * (cos(PI * t) - 1.0); }
  float expoOut(float t)   { return t >= 1.0 ? 1.0 : 1.0 - pow(2.0, -10.0 * t); }
  float backOut(float t)   { float f = t - 1.0; return f * f * (2.70158 * f + 1.70158) + 1.0; }
  float circularOut(float t) { return sqrt((2.0 - t) * t); }
  float cubicInOut(float t) {
    return t < 0.5 ? 4.0 * t * t * t : 0.5 * pow(2.0 * t - 2.0, 3.0) + 1.0;
  }
`;

/** Cheap hashes + value/simplex noise + fbm + curl. */
export const noise = /* glsl */ `
  float hash11(float p) {
    p = fract(p * 0.1031);
    p *= p + 33.33;
    return fract(p * (p + p));
  }
  float hash12(vec2 p) {
    vec3 p3 = fract(vec3(p.xyx) * 0.1031);
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.x + p3.y) * p3.z);
  }
  vec2 hash22(vec2 p) {
    vec3 p3 = fract(vec3(p.xyx) * vec3(0.1031, 0.1030, 0.0973));
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.xx + p3.yz) * p3.zy);
  }
  vec3 hash33(vec3 p) {
    p = fract(p * vec3(0.1031, 0.1030, 0.0973));
    p += dot(p, p.yxz + 33.33);
    return fract((p.xxy + p.yxx) * p.zyx);
  }

  // Ashima / Gustavson simplex noise (public domain).
  vec3 mod289(vec3 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
  vec4 mod289(vec4 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
  vec4 permute(vec4 x) { return mod289(((x * 34.0) + 1.0) * x); }
  vec4 taylorInvSqrt(vec4 r) { return 1.79284291400159 - 0.85373472095314 * r; }

  float snoise(vec3 v) {
    const vec2 C = vec2(1.0 / 6.0, 1.0 / 3.0);
    const vec4 D = vec4(0.0, 0.5, 1.0, 2.0);
    vec3 i  = floor(v + dot(v, C.yyy));
    vec3 x0 = v - i + dot(i, C.xxx);
    vec3 g = step(x0.yzx, x0.xyz);
    vec3 l = 1.0 - g;
    vec3 i1 = min(g.xyz, l.zxy);
    vec3 i2 = max(g.xyz, l.zxy);
    vec3 x1 = x0 - i1 + C.xxx;
    vec3 x2 = x0 - i2 + C.yyy;
    vec3 x3 = x0 - D.yyy;
    i = mod289(i);
    vec4 p = permute(permute(permute(
               i.z + vec4(0.0, i1.z, i2.z, 1.0))
             + i.y + vec4(0.0, i1.y, i2.y, 1.0))
             + i.x + vec4(0.0, i1.x, i2.x, 1.0));
    float n_ = 0.142857142857;
    vec3 ns = n_ * D.wyz - D.xzx;
    vec4 j = p - 49.0 * floor(p * ns.z * ns.z);
    vec4 x_ = floor(j * ns.z);
    vec4 y_ = floor(j - 7.0 * x_);
    vec4 x = x_ * ns.x + ns.yyyy;
    vec4 y = y_ * ns.x + ns.yyyy;
    vec4 h = 1.0 - abs(x) - abs(y);
    vec4 b0 = vec4(x.xy, y.xy);
    vec4 b1 = vec4(x.zw, y.zw);
    vec4 s0 = floor(b0) * 2.0 + 1.0;
    vec4 s1 = floor(b1) * 2.0 + 1.0;
    vec4 sh = -step(h, vec4(0.0));
    vec4 a0 = b0.xzyw + s0.xzyw * sh.xxyy;
    vec4 a1 = b1.xzyw + s1.xzyw * sh.zzww;
    vec3 p0 = vec3(a0.xy, h.x);
    vec3 p1 = vec3(a0.zw, h.y);
    vec3 p2 = vec3(a1.xy, h.z);
    vec3 p3 = vec3(a1.zw, h.w);
    vec4 norm = taylorInvSqrt(vec4(dot(p0, p0), dot(p1, p1), dot(p2, p2), dot(p3, p3)));
    p0 *= norm.x; p1 *= norm.y; p2 *= norm.z; p3 *= norm.w;
    vec4 m = max(0.6 - vec4(dot(x0, x0), dot(x1, x1), dot(x2, x2), dot(x3, x3)), 0.0);
    m = m * m;
    return 42.0 * dot(m * m, vec4(dot(p0, x0), dot(p1, x1), dot(p2, x2), dot(p3, x3)));
  }

  float fbm(vec3 p, int octaves, float lacunarity, float gain) {
    float sum = 0.0, amp = 0.5, norm = 0.0;
    for (int i = 0; i < 8; i++) {
      if (i >= octaves) break;
      sum  += amp * snoise(p);
      norm += amp;
      p    *= lacunarity;
      amp  *= gain;
    }
    return sum / max(norm, 1e-4);
  }

  // Divergence-free flow field. Used to advect the frost/particle buffers.
  vec3 curlNoise(vec3 p) {
    const float e = 0.1;
    float x1 = snoise(p + vec3(0.0, e, 0.0)) - snoise(p - vec3(0.0, e, 0.0));
    float x2 = snoise(p + vec3(0.0, 0.0, e)) - snoise(p - vec3(0.0, 0.0, e));
    float y1 = snoise(p + vec3(0.0, 0.0, e)) - snoise(p - vec3(0.0, 0.0, e));
    float y2 = snoise(p + vec3(e, 0.0, 0.0)) - snoise(p - vec3(e, 0.0, 0.0));
    float z1 = snoise(p + vec3(e, 0.0, 0.0)) - snoise(p - vec3(e, 0.0, 0.0));
    float z2 = snoise(p + vec3(0.0, e, 0.0)) - snoise(p - vec3(0.0, e, 0.0));
    return normalize(vec3(x1 - x2, y1 - y2, z1 - z2) / (2.0 * e));
  }
`;

/**
 * Blue noise sampling.
 *
 * Sampled by screen pixel and jittered per frame with a uniform offset, exactly
 * how igloo.inc hides the banding seams left by its chromatic-aberration loop.
 */
export const blueNoise = /* glsl */ `
  uniform sampler2D tBlue;
  uniform vec2 uBlueOffset;   // per-frame jitter, in tiles
  uniform vec2 uBlueSize;     // blue noise texture dimensions

  vec4 getNoise(sampler2D tex, vec2 fragCoord, vec2 offset) {
    return texture2D(tex, (fragCoord / uBlueSize) + offset);
  }
  vec4 blueNoise4(vec2 fragCoord) { return getNoise(tBlue, fragCoord, uBlueOffset); }
`;

/**
 * Chromatic aberration.
 *
 * Barrel-distorts the sample coordinate per spectral band and accumulates
 * CA_ITERATIONS taps across the visible spectrum. 'modulator' scales the effect
 * spatially (igloo vignettes it so the screen centre stays sharp) and 'jitter'
 * is a per-pixel blue-noise offset that dissolves the band boundaries.
 */
export const chromatic = /* glsl */ `
  #ifndef CA_ITERATIONS
  #define CA_ITERATIONS 5
  #endif

  vec2 ca_barrelDistortion(vec2 coord, float amt) {
    vec2 cc = coord - 0.5;
    return coord + 2.0 * cc * amt * dot(cc, cc);
  }
  // Map a normalized spectral position to an RGB weight (approx. visible spectrum).
  vec3 ca_spectrumOffset(float t) {
    float lo = step(t, 0.5);
    float hi = 1.0 - lo;
    float w = (1.0 - abs(2.0 * t - 1.0));
    return vec3(lo, 1.0, hi) * vec3(1.0 - w, w, 1.0 - w);
  }

  vec4 chromatic_aberration(sampler2D tex, vec2 uv, float modulator, float strength) {
    if (strength <= 0.0) return texture2D(tex, uv);

    vec3 sumCol = vec3(0.0);
    vec3 sumWeight = vec3(0.0);
    float alpha = 0.0;
    float amount = strength * modulator * 0.002;

    for (int i = 0; i < CA_ITERATIONS; ++i) {
      float t = (float(i) + 0.5) / float(CA_ITERATIONS);
      vec3 w = ca_spectrumOffset(t);
      sumWeight += w;
      vec4 s = texture2D(tex, ca_barrelDistortion(uv, amount * t));
      sumCol += w * s.rgb;
      alpha += s.a;
    }
    return vec4(sumCol / max(sumWeight, vec3(1e-4)), alpha / float(CA_ITERATIONS));
  }
`;

/**
 * 3D LUT colour grading from a horizontal strip texture (size*size wide, size tall).
 * Tetrahedral interpolation — noticeably cleaner than trilinear on steep grades.
 */
export const lut = /* glsl */ `
  vec3 lutLookup(sampler2D tex, vec3 rgb, float size) {
    float sliceSize = 1.0 / size;
    float slicePixelSize = sliceSize / size;
    float sliceInnerSize = slicePixelSize * (size - 1.0);
    float zSlice0 = floor(rgb.b * (size - 1.0));
    float zOffset = fract(rgb.b * (size - 1.0));

    vec2 uv0 = vec2(
      zSlice0 * sliceSize + slicePixelSize * 0.5 + rgb.r * sliceInnerSize,
      1.0 - (slicePixelSize * 0.5 + rgb.g * (1.0 - slicePixelSize))
    );
    vec2 uv1 = uv0 + vec2(sliceSize, 0.0);
    return mix(texture2D(tex, uv0).rgb, texture2D(tex, uv1).rgb, zOffset);
  }

  vec3 apply3DLUT(sampler2D tex, vec3 color, float size, float intensity) {
    return mix(color, lutLookup(tex, clamp(color, 0.0, 1.0), size), intensity);
  }
`;

/**
 * Fragment-only helpers.
 *
 * Kept out of `common` because `fwidth` is illegal in a vertex shader, and
 * `common` is included by both stages of every material in the engine.
 */
export const antialias = /* glsl */ `
  // Analytically antialiased step, one pixel wide.
  float aastep(float threshold, float v) {
    float afwidth = fwidth(v) * 0.7071;
    return smoothstep(threshold - afwidth, threshold + afwidth, v);
  }
`;

/** Signed-distance text decoding. Works for both 3-channel MSDF and 1-channel SDF atlases. */
export const sdfText = /* glsl */ `
  float median3(vec3 v) { return max(min(v.r, v.g), min(max(v.r, v.g), v.b)); }

  // 'range' is the distance field spread in texels; screen-space derivative gives
  // resolution-independent antialiasing at any scale.
  float sdfAlpha(vec3 sample_, float range, float weight) {
    float sd = median3(sample_) - 0.5 + weight;
    float w = max(fwidth(sd), 1e-5);
    return clamp(sd / w + 0.5, 0.0, 1.0);
  }
`;

/** Film grain + ordered dithering, to kill banding in the final 8-bit write. */
export const grain = /* glsl */ `
  vec3 dither8(vec3 color, vec2 fragCoord, float amount) {
    float g = hash12(fragCoord + fract(color.rg) * 13.7);
    return color + (g - 0.5) * amount;
  }
`;

/** Convenience: assemble a chunk list into a preamble. */
export const glsl = (...parts) => parts.join('\n');
