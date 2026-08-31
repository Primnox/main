import * as THREE from 'three';
import { Pass, PingPong } from '../core/gpu.js';
import { common, noise, easings } from '../glsl/chunks.js';

/**
 * GPGPU particle field — the drifting ice motes.
 *
 * State lives in two float textures (position.xyz + life, velocity.xyz + seed)
 * of size N x N. The draw call is a single BufferGeometry of N*N points whose
 * only real attribute is the lookup UV into that state; every particle's
 * position is fetched in the vertex shader.
 *
 * Integration is curl noise, not gravity: a divergence-free field means the
 * particles never bunch up or thin out, so the field stays evenly dense forever
 * without any respawn balancing.
 */
export class ParticleSim {
  constructor(renderer, {
    size = 128,
    bounds = new THREE.Vector3(9, 6, 6),
    noiseScale = 0.16,
    speed = 0.35,
    pointSize = 2.2,
  } = {}) {
    this.renderer = renderer;
    this.size = size;
    this.count = size * size;
    this.bounds = bounds;

    this.positions = new PingPong(size, size, { type: THREE.FloatType });
    this.velocities = new PingPong(size, size, { type: THREE.FloatType });

    this._seed(renderer);

    this.simPass = new Pass({
      uniforms: {
        tPosition: { value: null },
        tVelocity: { value: null },
        tOrigin: { value: this.originTexture },
        uTime: { value: 0 },
        uDelta: { value: 0.016 },
        uNoiseScale: { value: noiseScale },
        uSpeed: { value: speed },
        uBounds: { value: bounds },
        uMouse: { value: new THREE.Vector3(0, 0, 0) },
        uInteractForce: { value: 0 },
      },
      fragmentShader: /* glsl */ `
        precision highp float;
        varying vec2 vUv;
        uniform sampler2D tPosition;
        uniform sampler2D tVelocity;
        uniform sampler2D tOrigin;
        uniform float uTime;
        uniform float uDelta;
        uniform float uNoiseScale;
        uniform float uSpeed;
        uniform vec3  uBounds;
        uniform vec3  uMouse;
        uniform float uInteractForce;

        ${common}
        ${noise}

        void main() {
          vec4 pos = texture2D(tPosition, vUv);
          vec4 vel = texture2D(tVelocity, vUv);
          float seed = vel.w;

          // Divergence-free advection. Offsetting the sample point per particle
          // by its seed decorrelates neighbours that would otherwise move as one.
          vec3 flow = curlNoise(pos.xyz * uNoiseScale + vec3(0.0, uTime * 0.05, seed * 3.1));
          vec3 target = flow * uSpeed;

          // Pointer repulsion, falling off over a fixed world radius.
          vec3 toMouse = pos.xyz - uMouse;
          float d = length(toMouse);
          target += normalize(toMouse + 1e-5) * uInteractForce * exp(-d * d * 0.35);

          // Critically damped approach so bursts settle instead of ringing.
          vel.xyz = mix(vel.xyz, target, 1.0 - pow(0.001, uDelta));
          pos.xyz += vel.xyz * uDelta;

          // Toroidal wrap keeps density uniform and costs no respawn logic.
          pos.xyz = mod(pos.xyz + uBounds, uBounds * 2.0) - uBounds;

          // Life drives per-particle twinkle, offset by seed so they never sync.
          pos.w = fract(pos.w + uDelta * mix(0.05, 0.22, seed));

          gl_FragColor = pos;
          #ifdef WRITE_VELOCITY
            gl_FragColor = vec4(vel.xyz, seed);
          #endif
        }
      `,
    });

    // A second material instance writing the velocity target. Sharing one shader
    // with a define beats maintaining two near-identical integrators.
    this.velPass = new Pass({
      uniforms: this.simPass.uniforms,
      defines: { WRITE_VELOCITY: '' },
      fragmentShader: this.simPass.material.fragmentShader,
    });

    this._buildPoints(pointSize);
  }

  _seed(renderer) {
    const { size, count, bounds } = this;
    const pos = new Float32Array(count * 4);
    const vel = new Float32Array(count * 4);
    for (let i = 0; i < count; i++) {
      pos[i * 4 + 0] = (Math.random() * 2 - 1) * bounds.x;
      pos[i * 4 + 1] = (Math.random() * 2 - 1) * bounds.y;
      pos[i * 4 + 2] = (Math.random() * 2 - 1) * bounds.z;
      pos[i * 4 + 3] = Math.random();       // life phase
      vel[i * 4 + 3] = Math.random();       // per-particle seed
    }

    const upload = (data) => {
      const tex = new THREE.DataTexture(data, size, size, THREE.RGBAFormat, THREE.FloatType);
      tex.needsUpdate = true;
      tex.minFilter = tex.magFilter = THREE.NearestFilter;
      tex.colorSpace = THREE.NoColorSpace;
      return tex;
    };
    this.originTexture = upload(pos);
    const velTexture = upload(vel);

    // Blit the seed data into both halves of each ping-pong buffer.
    const blit = new Pass({
      uniforms: { tSrc: { value: null } },
      fragmentShader: `
        precision highp float;
        varying vec2 vUv;
        uniform sampler2D tSrc;
        void main() { gl_FragColor = texture2D(tSrc, vUv); }
      `,
    });
    for (const [pp, tex] of [[this.positions, this.originTexture], [this.velocities, velTexture]]) {
      blit.uniforms.tSrc.value = tex;
      blit.render(renderer, pp.a);
      blit.render(renderer, pp.b);
    }
    blit.dispose();
  }

  _buildPoints(pointSize) {
    const { size, count } = this;
    const lookup = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      lookup[i * 3 + 0] = ((i % size) + 0.5) / size;
      lookup[i * 3 + 1] = (Math.floor(i / size) + 0.5) / size;
      lookup[i * 3 + 2] = 0;
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(lookup, 3));
    geometry.boundingSphere = new THREE.Sphere(new THREE.Vector3(), 32);

    this.material = new THREE.ShaderMaterial({
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      uniforms: {
        tPosition: { value: null },
        uSize: { value: pointSize },
        uPixelRatio: { value: 1 },
        uColor: { value: new THREE.Color(0.72, 0.85, 1.0) },
        uOpacity: { value: 0.9 },
      },
      vertexShader: /* glsl */ `
        uniform sampler2D tPosition;
        uniform float uSize;
        uniform float uPixelRatio;
        varying float vLife;
        varying float vDepth;
        void main() {
          // 'position' here is a lookup coordinate, not a location.
          vec4 state = texture2D(tPosition, position.xy);
          vLife = state.w;
          vec4 mv = modelViewMatrix * vec4(state.xyz, 1.0);
          vDepth = -mv.z;
          gl_Position = projectionMatrix * mv;
          // Perspective-correct sizing, clamped so near particles don't blow up.
          gl_PointSize = min(uSize * uPixelRatio * (8.0 / max(vDepth, 0.1)), 24.0);
        }
      `,
      fragmentShader: /* glsl */ `
        precision highp float;
        varying float vLife;
        varying float vDepth;
        uniform vec3 uColor;
        uniform float uOpacity;
        ${common}
        void main() {
          // Round sprite from point coords; no texture needed.
          vec2 c = gl_PointCoord * 2.0 - 1.0;
          float d = dot(c, c);
          if (d > 1.0) discard;
          float alpha = pow(1.0 - d, 2.0);
          // Twinkle, then fade with distance so the field has depth.
          float twinkle = 0.35 + 0.65 * pow(abs(sin(vLife * PI)), 3.0);
          alpha *= twinkle * uOpacity * fit(vDepth, 24.0, 3.0, 0.0, 1.0);
          gl_FragColor = vec4(uColor * alpha, alpha);
        }
      `,
    });

    this.points = new THREE.Points(geometry, this.material);
    this.points.frustumCulled = false;
  }

  update(dt, time, mouseWorld, interactForce = 0) {
    const u = this.simPass.uniforms;
    u.uTime.value = time;
    u.uDelta.value = Math.min(dt, 1 / 30);
    u.uInteractForce.value = interactForce;
    if (mouseWorld) u.uMouse.value.copy(mouseWorld);

    u.tPosition.value = this.positions.read.texture;
    u.tVelocity.value = this.velocities.read.texture;

    // Velocity first: both passes read the same previous state, so the order
    // only matters in that neither may consume the other's new output.
    this.velPass.render(this.renderer, this.velocities.write);
    this.simPass.render(this.renderer, this.positions.write);
    this.velocities.swap();
    this.positions.swap();

    this.material.uniforms.tPosition.value = this.positions.read.texture;
  }

  setPixelRatio(dpr) {
    this.material.uniforms.uPixelRatio.value = dpr;
  }

  dispose() {
    this.positions.dispose();
    this.velocities.dispose();
    this.simPass.dispose();
    this.velPass.dispose();
    this.points.geometry.dispose();
    this.material.dispose();
  }
}
