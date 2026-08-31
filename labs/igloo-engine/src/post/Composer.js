import * as THREE from 'three';
import { Pass, createRT } from '../core/gpu.js';
import { common, easings, noise, chromatic, blueNoise, lut, grain } from '../glsl/chunks.js';

/**
 * Post pipeline.
 *
 * Two passes, in the order igloo.inc runs them:
 *
 *   1. TRANSITION — blends two fully-rendered scene buffers along a noise-warped
 *      diagonal front, with chromatic aberration concentrated at the front and
 *      opposing parallax on either side. This is why their section changes read
 *      as ice cracking rather than a crossfade: the *cut line itself* is a
 *      displacement map, not a straight edge.
 *
 *   2. GRADE — 3D LUT, vignette, blue-noise dither. Always last, always in one
 *      pass, so the 8-bit quantisation happens exactly once.
 *
 * Both render at full resolution into half-float targets; only the final write
 * to the default framebuffer is 8-bit.
 */
export class Composer {
  constructor(renderer, { blueNoiseTexture, lutTexture, noiseTexture }) {
    this.renderer = renderer;

    const size = renderer.getDrawingBufferSize(new THREE.Vector2());
    // The scene buffers hold real geometry and need depth. createRT defaults to
    // depthBuffer:false because most targets in this engine are 2D simulation
    // state — without this override, occlusion silently falls back to draw order.
    this.sceneA = createRT(size.x, size.y, { depthBuffer: true });
    this.sceneB = createRT(size.x, size.y, { depthBuffer: true });
    this.transitionRT = createRT(size.x, size.y);

    const blueSize = new THREE.Vector2(
      blueNoiseTexture.image.width,
      blueNoiseTexture.image.height
    );

    this.transition = new Pass({
      uniforms: {
        tScene1: { value: this.sceneA.texture },
        tScene2: { value: this.sceneB.texture },
        tScroll: { value: noiseTexture },
        tBlue: { value: blueNoiseTexture },
        uBlueOffset: { value: new THREE.Vector2() },
        uBlueSize: { value: blueSize },
        uProgress: { value: 0 },
        uProgressVel: { value: 0 },
        uAspect: { value: size.x / size.y },
        uSlope: { value: -0.2 },
        uParallax: { value: 0.35 },
      },
      fragmentShader: /* glsl */ `
        precision highp float;
        varying vec2 vUv;

        uniform sampler2D tScene1;
        uniform sampler2D tScene2;
        uniform sampler2D tScroll;
        uniform float uProgress;
        uniform float uProgressVel;
        uniform float uAspect;
        uniform float uSlope;
        uniform float uParallax;

        #define CA_ITERATIONS 5

        ${common}
        ${easings}
        ${noise}
        ${blueNoise}
        ${chromatic}

        void main() {
          // Early out on the common case: no transition in flight.
          if (uProgress <= 0.0) {
            gl_FragColor = vec4(texture2D(tScene1, vUv).rgb, 1.0);
            return;
          }
          if (uProgress >= 1.0) {
            gl_FragColor = vec4(texture2D(tScene2, vUv).rgb, 1.0);
            return;
          }

          // Aspect-corrected lookup so the warp texture isn't stretched.
          vec2 uvTex = vec2((vUv.x - 0.5) * uAspect + 0.5, vUv.y);
          vec3 scroll = texture2D(tScroll, uvTex).rgb;

          // The cut is a diagonal whose slope tracks scroll velocity, displaced
          // per-pixel by the noise so the front is ragged.
          float slope = uSlope * uAspect;
          float slopeDisp = (scroll.b * 2.0 - 1.0) * 0.4;
          float inclination = mix(1.0 - vUv.x + slopeDisp, vUv.x + slopeDisp, step(slope, 0.0));
          float axis = vUv.y + inclination * abs(slope);
          float front = fit(uProgress, 0.0, 1.0, 0.0, 1.0 + abs(slope));

          // Three fronts at different softness, from the same axis: a wide one
          // for CA, a medium one for UV displacement, a tight one for the cut.
          float caFront   = falloff(axis, 0.0, 1.0, 2.0, front);
          float dispFront = falloff(axis, 0.0, 1.0, 0.9, front);
          float cutFront  = falloff(axis, 0.0, 1.0, 0.2, front);

          float disp = falloff(scroll.g, 0.0, 1.0, 1.0, dispFront);
          float cut  = falloff(scroll.r, 0.0, 1.0, 2.0, cutFront);

          // Vignette the aberration so the centre of frame stays clean.
          float modulator = 12.0
            * smoothstep(1.0, 0.7, abs(vUv.x * 2.0 - 1.0))
            * smoothstep(1.0, 0.7, abs(vUv.y * 2.0 - 1.0));
          modulator *= 1.0 + abs(uProgressVel) * 4.0;

          vec4 n = blueNoise4(gl_FragCoord.xy);

          const float displacement = 0.025;
          vec3 a = vec3(0.0);
          vec3 b = vec3(0.0);

          // Skip the 5-tap CA loop entirely on pixels that are fully one side.
          if (cut < 1.0) {
            vec2 uvA = vUv - vec2(0.0, uParallax * power2In(uProgress) + displacement * disp);
            a = chromatic_aberration(tScene1, uvA, modulator, caFront * n.r).rgb;
          }
          if (cut > 0.0) {
            vec2 uvB = vUv + vec2(0.0, uParallax * power2In(1.0 - uProgress) + displacement * (1.0 - disp));
            b = chromatic_aberration(tScene2, uvB, modulator, (1.0 - caFront) * n.g).rgb;
          }

          gl_FragColor = vec4(clamp(mix(a, b, cut), 0.0, 1.0), 1.0);
        }
      `,
    });

    this.grade = new Pass({
      uniforms: {
        tDiffuse: { value: this.transitionRT.texture },
        tLUT: { value: lutTexture },
        tBlue: { value: blueNoiseTexture },
        tFrost: { value: null },
        tFrostNormal: { value: null },
        uBlueOffset: { value: new THREE.Vector2() },
        uBlueSize: { value: blueSize },
        uFrostAmount: { value: 1.0 },
        uFrostColor: { value: new THREE.Color(0.90, 0.95, 1.0) },
        uFrostDisplace: { value: 0.028 },
        uLUTSize: { value: lutTexture.userData.size },
        // A high-key scene has almost no shadow range for a LUT to work on, so
        // the grade is applied at partial strength — at 1.0 it crushes the snow
        // into the same value everywhere.
        uLUTIntensity: { value: 0.45 },
        uVignette: { value: 0.14 },
        uGrain: { value: 0.022 },
        uExposure: { value: 1.15 },
        uTime: { value: 0 },
      },
      fragmentShader: /* glsl */ `
        precision highp float;
        varying vec2 vUv;

        uniform sampler2D tDiffuse;
        uniform sampler2D tLUT;
        uniform sampler2D tFrost;
        uniform sampler2D tFrostNormal;
        uniform float uFrostAmount;
        uniform vec3  uFrostColor;
        uniform float uFrostDisplace;
        uniform float uLUTSize;
        uniform float uLUTIntensity;
        uniform float uVignette;
        uniform float uGrain;
        uniform float uExposure;
        uniform float uTime;

        ${common}
        ${noise}
        ${blueNoise}
        ${lut}
        ${grain}

        // AgX-flavoured tonemap: rolls highlights without the saturation crush
        // Reinhard gives you, and keeps the specular streaks on ice from clipping.
        vec3 tonemap(vec3 x) {
          x = max(vec3(0.0), x);
          return (x * (2.51 * x + 0.03)) / (x * (2.43 * x + 0.59) + 0.14);
        }

        void main() {
          // --- frost -----------------------------------------------------
          // The case study lists frost alongside chromatic aberration and tech
          // displacement as a *scene* effect. Applying it only to the ice
          // material made it invisible: the ice covers a small fraction of the
          // frame, so most of the pointer trail landed on snow and did nothing.
          // Here it refracts and freezes the whole composited image.
          vec4 frost = texture2D(tFrost, vUv);
          vec3 frostN = texture2D(tFrostNormal, vUv).rgb * 2.0 - 1.0;
          float mask = clamp(frost.r * uFrostAmount, 0.0, 1.0);

          vec2 uv = vUv + frostN.xy * mask * uFrostDisplace;
          vec3 color = texture2D(tDiffuse, uv).rgb * uExposure;

          if (mask > 0.001) {
            // Frost scatters: crush toward luminance, tint cold, lift.
            float l = luma(color);
            vec3 frozen = mix(color, vec3(l), 0.38) * uFrostColor + 0.03 * uFrostColor;
            color = mix(color, frozen, mask);
            // The advancing growth front is the bright part of real frost.
            color += uFrostColor * clamp(frost.b, 0.0, 1.0) * 1.1;
          }

          color = tonemap(color);
          color = apply3DLUT(tLUT, color, uLUTSize, uLUTIntensity);

          float d = length((vUv - 0.5) * vec2(1.0, 0.85));
          color *= 1.0 - uVignette * smoothstep(0.35, 0.95, d);

          // Animated grain, then a blue-noise dither below it. The dither is what
          // actually removes banding; the grain is taste.
          float g = hash12(vUv * 1024.0 + fract(uTime) * 91.7) - 0.5;
          color += g * uGrain;
          color += (blueNoise4(gl_FragCoord.xy).a - 0.5) / 255.0;

          gl_FragColor = vec4(color, 1.0);
        }
      `,
    });
  }

  /** Rebind the frost sim's ping-pong textures. Must be called every frame. */
  bindFrost(frost) {
    this.grade.uniforms.tFrost.value = frost.texture;
    this.grade.uniforms.tFrostNormal.value = frost.normalTexture;
  }

  /** Jitter the blue-noise lookup each frame so the dither pattern animates. */
  setFrame(frame, time) {
    const ox = ((frame * 0.7548776662) % 1);
    const oy = ((frame * 0.5698402909) % 1);
    this.transition.uniforms.uBlueOffset.value.set(ox, oy);
    this.grade.uniforms.uBlueOffset.value.set(oy, ox);
    this.grade.uniforms.uTime.value = time;
  }

  setSize(width, height) {
    this.sceneA.setSize(width, height);
    this.sceneB.setSize(width, height);
    this.transitionRT.setSize(width, height);
    this.transition.uniforms.uAspect.value = width / height;
  }

  /** @param {number} progress 0 = scene A only, 1 = scene B only. */
  render(progress, progressVelocity) {
    this.transition.uniforms.uProgress.value = progress;
    this.transition.uniforms.uProgressVel.value = progressVelocity;
    this.transition.render(this.renderer, this.transitionRT);
    this.grade.render(this.renderer, null);
  }

  dispose() {
    this.sceneA.dispose();
    this.sceneB.dispose();
    this.transitionRT.dispose();
    this.transition.dispose();
    this.grade.dispose();
  }
}
