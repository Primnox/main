import * as THREE from 'three';

/**
 * Fullscreen triangle pass.
 *
 * A single oversized triangle instead of a quad: no diagonal seam, one less
 * vertex, and the GPU never rasterizes a helper-invocation strip down the middle.
 * Position and UV are computed in the vertex shader from gl_VertexID-equivalent
 * attributes, so the geometry is shared across every pass in the app.
 */
const TRI = new THREE.BufferGeometry();
TRI.setAttribute('position', new THREE.BufferAttribute(new Float32Array([-1, -1, 0, 3, -1, 0, -1, 3, 0]), 3));
TRI.setAttribute('uv', new THREE.BufferAttribute(new Float32Array([0, 0, 2, 0, 0, 2]), 2));

export const TRI_VERT = /* glsl */ `
  varying vec2 vUv;
  void main() {
    vUv = uv;
    gl_Position = vec4(position.xy, 0.0, 1.0);
  }
`;

const ORTHO_CAM = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);

export class Pass {
  /**
   * @param {object} spec - three.js ShaderMaterial spec. 'vertexShader' defaults
   *   to the fullscreen triangle vertex shader.
   */
  constructor(spec) {
    this.material = new THREE.ShaderMaterial({
      vertexShader: TRI_VERT,
      depthTest: false,
      depthWrite: false,
      ...spec,
    });
    this.mesh = new THREE.Mesh(TRI, this.material);
    this.mesh.frustumCulled = false;
    this.scene = new THREE.Scene();
    this.scene.add(this.mesh);
  }

  get uniforms() {
    return this.material.uniforms;
  }

  /** Render into 'target' (or the canvas when target is null). */
  render(renderer, target = null) {
    const prev = renderer.getRenderTarget();
    renderer.setRenderTarget(target);
    renderer.render(this.scene, ORTHO_CAM);
    renderer.setRenderTarget(prev);
    return target;
  }

  dispose() {
    this.material.dispose();
  }
}

const DEFAULT_RT = {
  depthBuffer: false,
  stencilBuffer: false,
  type: THREE.HalfFloatType,
  format: THREE.RGBAFormat,
  minFilter: THREE.LinearFilter,
  magFilter: THREE.LinearFilter,
  wrapS: THREE.ClampToEdgeWrapping,
  wrapT: THREE.ClampToEdgeWrapping,
  generateMipmaps: false,
};

export function createRT(width, height, options = {}) {
  const rt = new THREE.WebGLRenderTarget(Math.max(1, width | 0), Math.max(1, height | 0), {
    ...DEFAULT_RT,
    ...options,
  });
  rt.texture.colorSpace = THREE.NoColorSpace; // simulation data, never sRGB
  return rt;
}

/**
 * Double-buffered render target.
 *
 * Every iterative simulation in the engine (frost propagation, fluid pressure
 * solve, particle integration) reads '.read' and writes '.write', then swaps.
 */
export class PingPong {
  constructor(width, height, options = {}) {
    this.a = createRT(width, height, options);
    this.b = createRT(width, height, options);
    this.options = options;
    this.width = width;
    this.height = height;
  }

  get read() {
    return this.a;
  }
  get write() {
    return this.b;
  }

  swap() {
    const t = this.a;
    this.a = this.b;
    this.b = t;
  }

  setSize(width, height) {
    if (width === this.width && height === this.height) return;
    this.width = width;
    this.height = height;
    this.a.setSize(width, height);
    this.b.setSize(width, height);
  }

  /** Clear both buffers to a known state — required before the first sim step. */
  clear(renderer, color = new THREE.Color(0, 0, 0), alpha = 1) {
    const prevTarget = renderer.getRenderTarget();
    const prevColor = new THREE.Color();
    const prevAlpha = renderer.getClearAlpha();
    renderer.getClearColor(prevColor);
    renderer.setClearColor(color, alpha);
    for (const rt of [this.a, this.b]) {
      renderer.setRenderTarget(rt);
      renderer.clear(true, false, false);
    }
    renderer.setRenderTarget(prevTarget);
    renderer.setClearColor(prevColor, prevAlpha);
  }

  dispose() {
    this.a.dispose();
    this.b.dispose();
  }
}

/**
 * Framerate-independent smoothing, JS side.
 *
 * 'coef' is authored as "fraction to close per frame at 60fps". Without this
 * correction every eased value on the site moves at a different speed on a
 * 144Hz display — the single most common bug in scroll-driven WebGL sites.
 */
export function lerpFPS(current, target, coef, dt) {
  return current + (target - current) * (1 - Math.pow(1 - coef, dt * 60));
}

export class Damped {
  constructor(value = 0, coef = 0.1) {
    this.value = value;
    this.target = value;
    this.coef = coef;
    this.velocity = 0;
  }
  set(v) {
    this.value = this.target = v;
    this.velocity = 0;
    return this;
  }
  update(dt) {
    const prev = this.value;
    this.value = lerpFPS(this.value, this.target, this.coef, dt);
    this.velocity = dt > 0 ? (this.value - prev) / dt : 0;
    return this.value;
  }
}
