import * as THREE from 'three';
import { Pass, PingPong } from '../core/gpu.js';
import { common, easings, noise } from '../glsl/chunks.js';

/**
 * Frost trail simulation.
 *
 * This is the signature igloo.inc interaction and it is *not* a fluid solver —
 * it is a max-propagation wave on a single scalar field:
 *
 *   next = max(left, right, top, bottom)   // frost spreads outward, never recedes
 *   next += splat(mouse segment)           // capsule SDF between prev and current pointer
 *   next *= damping                        // and then slowly melts back
 *
 * Sampling coordinates are pre-advected by a noise flow field, which is what
 * turns a clean circular bloom into the crystalline, feathered edge that reads
 * as ice rather than smoke.
 *
 * Output channels:
 *   R = frost coverage [0,1]
 *   G = per-step delta (the growth "rim", bright only at the advancing front)
 *   B = temporally smoothed rim, for a softer glow
 *   A = 1
 */
export class FrostSim {
  constructor(renderer, { resolution = 512, advectTexture = null } = {}) {
    this.renderer = renderer;
    this.resolution = resolution;

    this.buffer = new PingPong(resolution, resolution, { type: THREE.HalfFloatType });
    this.buffer.clear(renderer, new THREE.Color(0, 0, 0), 1);

    this.step = new Pass({
      uniforms: {
        tBuffer: { value: null },
        tAdvect: { value: advectTexture },
        uTexel: { value: new THREE.Vector2(1 / resolution, 1 / resolution) },
        uSplatCoords: { value: new THREE.Vector2(-1, -1) },
        uSplatPrevCoords: { value: new THREE.Vector2(-1, -1) },
        uSplatRadius: { value: 0 },
        uAdvectStrength: { value: 1.6 },
        uWaveSpeed: { value: 1.0 },
        uDamping: { value: 0.985 },
        uAspect: { value: 1 },
        uTime: { value: 0 },
      },
      fragmentShader: /* glsl */ `
        precision highp float;
        varying vec2 vUv;

        uniform sampler2D tBuffer;
        uniform sampler2D tAdvect;
        uniform vec2  uTexel;
        uniform vec2  uSplatCoords;
        uniform vec2  uSplatPrevCoords;
        uniform float uSplatRadius;
        uniform float uAdvectStrength;
        uniform float uWaveSpeed;
        uniform float uDamping;
        uniform float uAspect;
        uniform float uTime;

        ${common}
        ${easings}

        // Distance from uv to the segment [a,b], aspect-corrected so the brush
        // stays circular on a non-square viewport.
        float segmentDistance(vec2 uv, vec2 a, vec2 b) {
          vec2 pa = uv - a, ba = b - a;
          pa.x *= uAspect;
          ba.x *= uAspect;
          float h = clamp(dot(pa, ba) / max(dot(ba, ba), 1e-6), 0.0, 1.0);
          return length(pa - ba * h);
        }

        void main() {
          vec2 uv = vUv;

          // Advect the sampling position along a slowly drifting noise field.
          vec2 flow = texture2D(tAdvect, uv * 3.0 + vec2(uTime * 0.01, -uTime * 0.013)).gb * 2.0 - 1.0;
          uv += flow * uTexel * uAdvectStrength;

          // Dilate: the frost front only ever advances.
          vec2 o = uTexel * uWaveSpeed;
          float l = texture2D(tBuffer, uv - vec2(o.x, 0.0)).r;
          float r = texture2D(tBuffer, uv + vec2(o.x, 0.0)).r;
          float t = texture2D(tBuffer, uv + vec2(0.0, o.y)).r;
          float b = texture2D(tBuffer, uv - vec2(0.0, o.y)).r;
          float next = max(max(l, r), max(t, b));

          // Pointer splat as a capsule, so fast mouse movement leaves an unbroken
          // stroke instead of a dotted line at low framerates.
          float radius = 0.075 * smoothstep(0.0, 0.8, uSplatRadius);
          if (radius > 0.0) {
            float d = segmentDistance(vUv, uSplatPrevCoords, uSplatCoords);
            next += power2In(clamp(1.0 - d / radius, 0.0, 1.0));
          }

          next = min(next * uDamping, 1.0);

          vec4 prev = texture2D(tBuffer, uv);
          float rim = next - prev.r;
          float rimSmooth = (prev.b + rim) * 0.9;

          gl_FragColor = vec4(next, rim, rimSmooth, 1.0);
        }
      `,
    });

    // Derives a normal map from the frost height field. Kept as a separate pass
    // because the refraction material needs it every frame but the sim may be
    // stepped at a lower rate.
    this.normalRT = new THREE.WebGLRenderTarget(resolution, resolution, {
      depthBuffer: false,
      stencilBuffer: false,
      type: THREE.HalfFloatType,
      minFilter: THREE.LinearFilter,
      magFilter: THREE.LinearFilter,
    });
    this.normalRT.texture.colorSpace = THREE.NoColorSpace;

    this.normalPass = new Pass({
      uniforms: {
        tBuffer: { value: null },
        uTexel: { value: new THREE.Vector2(1 / resolution, 1 / resolution) },
        uStrength: { value: 2.4 },
        tAdvect: { value: advectTexture },
      },
      fragmentShader: /* glsl */ `
        precision highp float;
        varying vec2 vUv;
        uniform sampler2D tBuffer;
        uniform sampler2D tAdvect;
        uniform vec2 uTexel;
        uniform float uStrength;
        ${common}

        float height(vec2 uv) {
          float h = texture2D(tBuffer, uv).r;
          // Modulate the height by high-frequency noise so the surface breaks up
          // into facets rather than reading as a smooth blob.
          float detail = texture2D(tAdvect, uv * 6.0).a;
          return h * mix(0.75, 1.0, detail);
        }

        void main() {
          float l = height(vUv - vec2(uTexel.x, 0.0));
          float r = height(vUv + vec2(uTexel.x, 0.0));
          float b = height(vUv - vec2(0.0, uTexel.y));
          float t = height(vUv + vec2(0.0, uTexel.y));
          vec3 n = normalize(vec3((l - r) * uStrength, (b - t) * uStrength, 1.0));
          gl_FragColor = vec4(n * 0.5 + 0.5, texture2D(tBuffer, vUv).r);
        }
      `,
    });
  }

  get texture() {
    return this.buffer.read.texture;
  }
  get normalTexture() {
    return this.normalRT.texture;
  }

  setAdvectTexture(texture) {
    this.step.uniforms.tAdvect.value = texture;
    this.normalPass.uniforms.tAdvect.value = texture;
  }

  setAspect(aspect) {
    this.step.uniforms.uAspect.value = aspect;
  }

  /**
   * @param {number} dt seconds
   * @param {{x:number,y:number,px:number,py:number,speed:number,down:boolean}} pointer
   *   Coordinates are normalised [0,1] with y up.
   */
  update(dt, pointer, time) {
    const u = this.step.uniforms;
    u.tBuffer.value = this.buffer.read.texture;
    u.uTime.value = time;
    u.uSplatCoords.value.set(pointer.x, pointer.y);
    u.uSplatPrevCoords.value.set(pointer.px, pointer.py);
    // Radius tracks pointer speed: a resting cursor stops painting, a fast drag
    // widens the stroke. 'active' gates it entirely when the pointer has left.
    // A resting pointer still paints a little, so the trail starts the instant
    // you move rather than needing a flick to cross a speed threshold.
    u.uSplatRadius.value = pointer.active ? Math.min(1, 0.45 + pointer.speed * 16) : 0;
    // Damping is authored per 60fps frame; correct it for the real delta.
    // 0.985 melted the trail in under a second — too fast to read as frost.
    u.uDamping.value = Math.pow(0.9905, Math.min(dt, 1 / 20) * 60);

    this.step.render(this.renderer, this.buffer.write);
    this.buffer.swap();

    this.normalPass.uniforms.tBuffer.value = this.buffer.read.texture;
    this.normalPass.render(this.renderer, this.normalRT);
  }

  setSize(width, height) {
    // The frost field stays square and low-res; it is a mask, not an image.
    this.setAspect(width / height);
  }

  dispose() {
    this.buffer.dispose();
    this.normalRT.dispose();
    this.step.dispose();
    this.normalPass.dispose();
  }
}
