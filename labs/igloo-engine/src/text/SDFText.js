import * as THREE from 'three';
import { common, easings, noise, sdfText } from '../glsl/chunks.js';

/** Which of the worker's orderings drives the stagger. */
export const ORDER = {
  GLYPH: 0,      // one continuous sweep across the whole block
  WORD: 1,       // word by word
  LINE_GLYPH: 2, // each line sweeps its own glyphs, all lines at once
  LINE_WORD: 3,
  LINE: 4,       // whole lines, one after another
  RANDOM: 5,
};

let worker = null;
let requestId = 0;
const pending = new Map();

function getWorker() {
  if (!worker) {
    worker = new Worker(new URL('./layout.worker.js', import.meta.url), { type: 'module' });
    worker.onmessage = (e) => {
      const resolve = pending.get(e.data.id);
      if (resolve) {
        pending.delete(e.data.id);
        resolve(e.data.buffers);
      }
    };
  }
  return worker;
}

/** Lay out a string off-thread. Resolves with the transferable attribute set. */
export function layoutText(font, options) {
  const id = ++requestId;
  return new Promise((resolve) => {
    pending.set(id, resolve);
    getWorker().postMessage({ id, font, options });
  });
}

/**
 * Animated SDF text material.
 *
 * The reveal is driven entirely on the GPU: each vertex knows its own ordinal
 * (see layout.worker.js), so 'uAnimationProgress' sweeping 0 -> 1 walks a soft
 * front across the block. 'uAnimationMargin' is the width of that front — at 1.0
 * every glyph moves together, at 0.05 they fire almost one at a time.
 */
export class SDFTextMaterial extends THREE.ShaderMaterial {
  constructor({ map, distanceRange = 8, color = new THREE.Color(0x0d1b2a) } = {}) {
    super({
      transparent: true,
      depthWrite: false,
      side: THREE.DoubleSide,
      uniforms: {
        tMap: { value: map },
        uColor: { value: color },
        uAlpha: { value: 1 },
        uRange: { value: distanceRange },
        uOutlineWidth: { value: 0 },
        uOutlineColor: { value: new THREE.Color(0xffffff) },
        uWeight: { value: 0 },

        uAnimationProgress: { value: 0 },
        uAnimationOrder: { value: ORDER.GLYPH },
        uAnimationDirection: { value: new THREE.Vector3(0, -1, 0) },
        uAnimationAmount: { value: 0.6 },
        uAnimationMargin: { value: 0.35 },
        uAnimationRotation: { value: 0.5 },
        uAnimationScale: { value: 0.4 },

        uTime: { value: 0 },
        uWobble: { value: 0 },
      },

      vertexShader: /* glsl */ `
        attribute vec3 aCenter;
        attribute vec2 textWeights;
        attribute vec3 lineWeights;
        attribute vec4 uvBounds;

        uniform float uAnimationProgress;
        uniform float uAnimationOrder;
        uniform vec3  uAnimationDirection;
        uniform float uAnimationAmount;
        uniform float uAnimationMargin;
        uniform float uAnimationRotation;
        uniform float uAnimationScale;
        uniform float uTime;
        uniform float uWobble;

        varying vec2 vUv;
        varying float vReveal;

        ${common}
        ${easings}
        ${noise}

        // Select the ordinal this glyph animates on. Branchless: five mixes cost
        // less than a dynamic branch on most mobile GPUs and the compiler folds
        // the whole thing once uAnimationOrder is a constant per draw.
        float pickOrdinal() {
          float o = uAnimationOrder;
          float v = textWeights.x;
          v = mix(v, textWeights.y,  step(0.5, o) * step(o, 1.5));
          v = mix(v, lineWeights.x,  step(1.5, o) * step(o, 2.5));
          v = mix(v, lineWeights.y,  step(2.5, o) * step(o, 3.5));
          v = mix(v, lineWeights.z,  step(3.5, o) * step(o, 4.5));
          v = mix(v, hash12(aCenter.xy * 17.3), step(4.5, o));
          return v;
        }

        void main() {
          vUv = uv;

          float ordinal = pickOrdinal();
          // Soft front sweeping across the ordering.
          float reveal = falloff(ordinal, 0.0, 1.0, uAnimationMargin, uAnimationProgress);
          reveal = power2Out(reveal);
          vReveal = reveal;

          vec3 local = position - aCenter;

          // Scale and rotate about the glyph's own centre while it flies in.
          float s = mix(1.0 - uAnimationScale, 1.0, reveal);
          float a = (1.0 - reveal) * uAnimationRotation * (hash12(aCenter.xy) * 2.0 - 1.0);
          float c = cos(a), sn = sin(a);
          local.xy = mat2(c, -sn, sn, c) * local.xy * s;

          vec3 offset = uAnimationDirection * uAnimationAmount * (1.0 - reveal);

          // Idle wobble, decorrelated per glyph so the block breathes.
          offset += vec3(
            snoise(vec3(aCenter.xy * 0.6, uTime * 0.25)),
            snoise(vec3(aCenter.xy * 0.6 + 31.7, uTime * 0.25)),
            0.0
          ) * uWobble;

          vec3 world = aCenter + local + offset;
          gl_Position = projectionMatrix * modelViewMatrix * vec4(world, 1.0);
        }
      `,

      fragmentShader: /* glsl */ `
        precision highp float;
        varying vec2 vUv;
        varying float vReveal;

        uniform sampler2D tMap;
        uniform vec3  uColor;
        uniform vec3  uOutlineColor;
        uniform float uAlpha;
        uniform float uRange;
        uniform float uOutlineWidth;
        uniform float uWeight;

        ${common}
        ${sdfText}

        void main() {
          vec3 s = texture2D(tMap, vUv).rgb;
          float fill = sdfAlpha(s, uRange, uWeight);

          vec3 color = uColor;
          float alpha = fill;

          if (uOutlineWidth > 0.0) {
            // A second threshold further out gives a stroke; subtracting the
            // fill leaves a ring rather than a filled halo.
            float outer = sdfAlpha(s, uRange, uWeight + uOutlineWidth);
            color = mix(uOutlineColor, uColor, fill);
            alpha = outer;
          }

          alpha *= uAlpha * vReveal;
          if (alpha < 0.003) discard;
          gl_FragColor = vec4(color, alpha);
        }
      `,
    });
  }
}

/**
 * A laid-out block of SDF text.
 *
 * Geometry is rebuilt from the worker on every 'setText' / 'setWidth'; the
 * material and its uniforms survive, so an in-flight reveal is not interrupted
 * by a resize.
 */
export class SDFText extends THREE.Mesh {
  constructor(font, texture, options = {}) {
    const material = new SDFTextMaterial({
      map: texture,
      distanceRange: font.atlas.distanceRange,
      color: options.color ? new THREE.Color(options.color) : new THREE.Color(0x0d1b2a),
    });
    super(new THREE.BufferGeometry(), material);

    this.font = font;
    this.options = {
      text: '',
      size: 1,
      align: 'center',
      width: Infinity,
      lineHeight: 1.15,
      letterSpacing: 0,
      wordSpacing: 0,
      ...options,
    };
    this.frustumCulled = false;
    this.ready = this.rebuild();
  }

  async rebuild() {
    const b = await layoutText(this.font, this.options);
    const g = new THREE.BufferGeometry();
    g.setIndex(new THREE.BufferAttribute(b.index, 1));
    g.setAttribute('position', new THREE.BufferAttribute(b.position, 3));
    g.setAttribute('uv', new THREE.BufferAttribute(b.uv, 2));
    g.setAttribute('aCenter', new THREE.BufferAttribute(b.centroid, 3));
    g.setAttribute('uvBounds', new THREE.BufferAttribute(b.uvBounds, 4));
    g.setAttribute('textWeights', new THREE.BufferAttribute(b.textWeights, 2));
    g.setAttribute('lineWeights', new THREE.BufferAttribute(b.lineWeights, 3));
    g.computeBoundingSphere();

    this.geometry.dispose();
    this.geometry = g;
    this.blockWidth = b.blockWidth;
    this.blockHeight = b.blockHeight;
    return this;
  }

  setText(text) {
    this.options.text = text;
    return this.rebuild();
  }

  set progress(v) {
    this.material.uniforms.uAnimationProgress.value = v;
  }
  get progress() {
    return this.material.uniforms.uAnimationProgress.value;
  }

  update(time) {
    this.material.uniforms.uTime.value = time;
  }
}
