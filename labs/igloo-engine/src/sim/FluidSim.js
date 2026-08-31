import * as THREE from 'three';
import { Pass, PingPong, createRT } from '../core/gpu.js';

/**
 * Stable-fluids solver (Stam 1999) on the GPU.
 *
 * Separate from FrostSim: frost is a dilation, this is real incompressible flow.
 * igloo.inc uses it for the drifting dye/vapour layers, where the motion has to
 * curl and shear rather than just spread.
 *
 * Per step:
 *   advect velocity -> curl -> vorticity confinement -> divergence
 *   -> Jacobi pressure solve (N iterations) -> subtract pressure gradient
 *   -> advect dye
 *
 * Velocity and dye run at different resolutions on purpose. Velocity is smooth
 * and can be coarse; dye carries the visible detail and needs the pixels.
 */

// Precomputes neighbour UVs in the vertex shader — one interpolator fetch beats
// four dependent texture-coordinate computations per fragment.
const STENCIL_VERT = /* glsl */ `
  varying vec2 vUv, vL, vR, vT, vB;
  uniform vec2 uTexel;
  void main() {
    vUv = uv;
    vL = uv - vec2(uTexel.x, 0.0);
    vR = uv + vec2(uTexel.x, 0.0);
    vT = uv + vec2(0.0, uTexel.y);
    vB = uv - vec2(0.0, uTexel.y);
    gl_Position = vec4(position.xy, 0.0, 1.0);
  }
`;

const STENCIL_VARYINGS = /* glsl */ `
  precision highp float;
  varying vec2 vUv, vL, vR, vT, vB;
`;

export class FluidSim {
  constructor(renderer, {
    simResolution = 128,
    dyeResolution = 512,
    pressureIterations = 20,
    curlStrength = 24,
    velocityDissipation = 0.2,
    densityDissipation = 1.0,
  } = {}) {
    this.renderer = renderer;
    this.pressureIterations = pressureIterations;

    const sr = simResolution;
    const dr = dyeResolution;
    this.simTexel = new THREE.Vector2(1 / sr, 1 / sr);
    this.dyeTexel = new THREE.Vector2(1 / dr, 1 / dr);

    const rg = { type: THREE.HalfFloatType, format: THREE.RGBAFormat };
    this.velocity = new PingPong(sr, sr, rg);
    this.pressure = new PingPong(sr, sr, rg);
    this.dye = new PingPong(dr, dr, rg);
    this.divergenceRT = createRT(sr, sr, rg);
    this.curlRT = createRT(sr, sr, rg);

    for (const pp of [this.velocity, this.pressure, this.dye]) {
      pp.clear(renderer, new THREE.Color(0, 0, 0), 1);
    }

    this.params = { curlStrength, velocityDissipation, densityDissipation };
    this._buildPasses();
  }

  _buildPasses() {
    const stencil = (uniforms, fragmentShader) =>
      new Pass({
        vertexShader: STENCIL_VERT,
        uniforms: { uTexel: { value: this.simTexel }, ...uniforms },
        fragmentShader,
      });

    this.advectPass = new Pass({
      uniforms: {
        uVelocity: { value: null },
        uSource: { value: null },
        uTexel: { value: this.simTexel },
        uDyeTexel: { value: this.dyeTexel },
        dt: { value: 0.016 },
        dissipation: { value: 1.0 },
      },
      fragmentShader: /* glsl */ `
        precision highp float;
        varying vec2 vUv;
        uniform sampler2D uVelocity;
        uniform sampler2D uSource;
        uniform vec2 uTexel;
        uniform vec2 uDyeTexel;
        uniform float dt;
        uniform float dissipation;

        // Manual bilinear fetch: the dye buffer is sampled at a different
        // resolution than the velocity field, and letting the hardware filter
        // across that mismatch smears the advection.
        vec4 bilerp(sampler2D tex, vec2 uv, vec2 texel) {
          vec2 st = uv / texel - 0.5;
          vec2 i = floor(st);
          vec2 f = fract(st);
          vec4 a = texture2D(tex, (i + vec2(0.5, 0.5)) * texel);
          vec4 b = texture2D(tex, (i + vec2(1.5, 0.5)) * texel);
          vec4 c = texture2D(tex, (i + vec2(0.5, 1.5)) * texel);
          vec4 d = texture2D(tex, (i + vec2(1.5, 1.5)) * texel);
          return mix(mix(a, b, f.x), mix(c, d, f.x), f.y);
        }

        void main() {
          // Semi-Lagrangian: trace backwards along the velocity field.
          vec2 coord = vUv - dt * bilerp(uVelocity, vUv, uTexel).xy * uTexel;
          vec4 result = bilerp(uSource, coord, uDyeTexel);
          gl_FragColor = result / (1.0 + dissipation * dt);
        }
      `,
    });

    this.curlPass = stencil({ uVelocity: { value: null } }, /* glsl */ `
      ${STENCIL_VARYINGS}
      uniform sampler2D uVelocity;
      void main() {
        float L = texture2D(uVelocity, vL).y;
        float R = texture2D(uVelocity, vR).y;
        float T = texture2D(uVelocity, vT).x;
        float B = texture2D(uVelocity, vB).x;
        gl_FragColor = vec4(0.5 * ((R - L) - (T - B)), 0.0, 0.0, 1.0);
      }
    `);

    // Vorticity confinement: re-injects the small-scale swirl that the
    // semi-Lagrangian advection step numerically dissipates away.
    this.vorticityPass = stencil({
      uVelocity: { value: null },
      uCurl: { value: null },
      curl: { value: this.params.curlStrength },
      dt: { value: 0.016 },
    }, /* glsl */ `
      ${STENCIL_VARYINGS}
      uniform sampler2D uVelocity;
      uniform sampler2D uCurl;
      uniform float curl;
      uniform float dt;
      void main() {
        float L = texture2D(uCurl, vL).x;
        float R = texture2D(uCurl, vR).x;
        float T = texture2D(uCurl, vT).x;
        float B = texture2D(uCurl, vB).x;
        float C = texture2D(uCurl, vUv).x;

        vec2 force = 0.5 * vec2(abs(T) - abs(B), abs(R) - abs(L));
        force /= length(force) + 1e-4;
        force *= curl * C;
        force.y *= -1.0;

        vec2 vel = texture2D(uVelocity, vUv).xy + force * dt;
        gl_FragColor = vec4(clamp(vel, -1000.0, 1000.0), 0.0, 1.0);
      }
    `);

    this.divergencePass = stencil({ uVelocity: { value: null } }, /* glsl */ `
      ${STENCIL_VARYINGS}
      uniform sampler2D uVelocity;
      void main() {
        float L = texture2D(uVelocity, vL).x;
        float R = texture2D(uVelocity, vR).x;
        float T = texture2D(uVelocity, vT).y;
        float B = texture2D(uVelocity, vB).y;
        // Reflective boundary: mirror the centre cell so flow cannot leak out.
        vec2 C = texture2D(uVelocity, vUv).xy;
        if (vL.x < 0.0) L = -C.x;
        if (vR.x > 1.0) R = -C.x;
        if (vT.y > 1.0) T = -C.y;
        if (vB.y < 0.0) B = -C.y;
        gl_FragColor = vec4(0.5 * ((R - L) + (T - B)), 0.0, 0.0, 1.0);
      }
    `);

    this.pressurePass = stencil({
      uPressure: { value: null },
      uDivergence: { value: null },
    }, /* glsl */ `
      ${STENCIL_VARYINGS}
      uniform sampler2D uPressure;
      uniform sampler2D uDivergence;
      void main() {
        // One Jacobi relaxation of the Poisson equation.
        float L = texture2D(uPressure, vL).x;
        float R = texture2D(uPressure, vR).x;
        float T = texture2D(uPressure, vT).x;
        float B = texture2D(uPressure, vB).x;
        float divergence = texture2D(uDivergence, vUv).x;
        gl_FragColor = vec4((L + R + B + T - divergence) * 0.25, 0.0, 0.0, 1.0);
      }
    `);

    this.gradientPass = stencil({
      uPressure: { value: null },
      uVelocity: { value: null },
    }, /* glsl */ `
      ${STENCIL_VARYINGS}
      uniform sampler2D uPressure;
      uniform sampler2D uVelocity;
      void main() {
        float L = texture2D(uPressure, vL).x;
        float R = texture2D(uPressure, vR).x;
        float T = texture2D(uPressure, vT).x;
        float B = texture2D(uPressure, vB).x;
        vec2 vel = texture2D(uVelocity, vUv).xy - vec2(R - L, T - B);
        gl_FragColor = vec4(vel, 0.0, 1.0);
      }
    `);

    this.splatPass = new Pass({
      uniforms: {
        uTarget: { value: null },
        aspectRatio: { value: 1 },
        color: { value: new THREE.Vector3() },
        point: { value: new THREE.Vector2() },
        radius: { value: 0.01 },
      },
      fragmentShader: /* glsl */ `
        precision highp float;
        varying vec2 vUv;
        uniform sampler2D uTarget;
        uniform float aspectRatio;
        uniform vec3 color;
        uniform vec2 point;
        uniform float radius;
        void main() {
          vec2 p = vUv - point;
          p.x *= aspectRatio;
          vec3 splat = exp(-dot(p, p) / radius) * color;
          gl_FragColor = vec4(texture2D(uTarget, vUv).xyz + splat, 1.0);
        }
      `,
    });
  }

  /** Inject velocity + dye at a normalised point. */
  splat(x, y, dx, dy, color, aspectRatio = 1, radius = 0.0002) {
    const u = this.splatPass.uniforms;
    u.aspectRatio.value = aspectRatio;
    u.point.value.set(x, y);
    u.radius.value = radius;

    u.uTarget.value = this.velocity.read.texture;
    u.color.value.set(dx, dy, 0);
    this.splatPass.render(this.renderer, this.velocity.write);
    this.velocity.swap();

    u.uTarget.value = this.dye.read.texture;
    u.color.value.set(color.r, color.g, color.b);
    this.splatPass.render(this.renderer, this.dye.write);
    this.dye.swap();
  }

  update(dt) {
    const r = this.renderer;
    const step = Math.min(dt, 1 / 30); // never integrate a stall

    // curl
    this.curlPass.uniforms.uVelocity.value = this.velocity.read.texture;
    this.curlPass.render(r, this.curlRT);

    // vorticity confinement
    this.vorticityPass.uniforms.uVelocity.value = this.velocity.read.texture;
    this.vorticityPass.uniforms.uCurl.value = this.curlRT.texture;
    this.vorticityPass.uniforms.dt.value = step;
    this.vorticityPass.render(r, this.velocity.write);
    this.velocity.swap();

    // divergence
    this.divergencePass.uniforms.uVelocity.value = this.velocity.read.texture;
    this.divergencePass.render(r, this.divergenceRT);

    // pressure solve
    this.pressurePass.uniforms.uDivergence.value = this.divergenceRT.texture;
    for (let i = 0; i < this.pressureIterations; i++) {
      this.pressurePass.uniforms.uPressure.value = this.pressure.read.texture;
      this.pressurePass.render(r, this.pressure.write);
      this.pressure.swap();
    }

    // project velocity to be divergence-free
    this.gradientPass.uniforms.uPressure.value = this.pressure.read.texture;
    this.gradientPass.uniforms.uVelocity.value = this.velocity.read.texture;
    this.gradientPass.render(r, this.velocity.write);
    this.velocity.swap();

    // advect velocity by itself
    const a = this.advectPass.uniforms;
    a.dt.value = step;
    a.uVelocity.value = this.velocity.read.texture;
    a.uSource.value = this.velocity.read.texture;
    a.uDyeTexel.value = this.simTexel;
    a.dissipation.value = this.params.velocityDissipation;
    this.advectPass.render(r, this.velocity.write);
    this.velocity.swap();

    // advect dye by the projected velocity
    a.uVelocity.value = this.velocity.read.texture;
    a.uSource.value = this.dye.read.texture;
    a.uDyeTexel.value = this.dyeTexel;
    a.dissipation.value = this.params.densityDissipation;
    this.advectPass.render(r, this.dye.write);
    this.dye.swap();
  }

  get texture() {
    return this.dye.read.texture;
  }

  dispose() {
    this.velocity.dispose();
    this.pressure.dispose();
    this.dye.dispose();
    this.divergenceRT.dispose();
    this.curlRT.dispose();
    for (const p of [this.advectPass, this.curlPass, this.vorticityPass,
      this.divergencePass, this.pressurePass, this.gradientPass, this.splatPass]) p.dispose();
  }
}
