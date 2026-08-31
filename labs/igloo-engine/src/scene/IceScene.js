import * as THREE from 'three';
import { RoundedBoxGeometry } from 'three/examples/jsm/geometries/RoundedBoxGeometry.js';
import { common, easings, noise } from '../glsl/chunks.js';
import { IceMaterial } from '../materials/IceMaterial.js';
import { ParticleSim } from '../sim/ParticleSim.js';
import { SDFText, ORDER } from '../text/SDFText.js';
import { lerpFPS } from '../core/gpu.js';

/**
 * Atmosphere constants.
 *
 * The reference is a *high-key* scene: the darkest pixel on screen is a mid
 * grey. Every material here fogs toward the same near-white, and nothing is
 * allowed to go black, because a single dark region reads as a hole punched in
 * the snow.
 */
const FOG_COLOR = new THREE.Color(0.845, 0.865, 0.895);
// Tuned so the near dunes stay crisp but the far ranges dissolve into the sky —
// aerial perspective is doing all the depth work in a scene with no shadows.
const FOG_DENSITY = 0.0062;

/** Shared fog chunk. Custom ShaderMaterials get none of three.js' fog plumbing. */
const FOG = /* glsl */ `
  uniform vec3  uFogColor;
  uniform float uFogDensity;

  // Exponential-squared fog. Matches THREE.FogExp2 so the DOM background colour
  // and the far terrain converge on exactly the same value at the horizon.
  vec3 applyFog(vec3 color, float dist) {
    float f = 1.0 - exp(-dist * dist * uFogDensity * uFogDensity);
    return mix(color, uFogColor, clamp(f, 0.0, 1.0));
  }
`;

const fogUniforms = () => ({
  uFogColor: { value: FOG_COLOR.clone() },
  uFogDensity: { value: FOG_DENSITY },
});

/* ------------------------------------------------------------------ *
 * Terrain
 * ------------------------------------------------------------------ */

/**
 * Snowfield + distant ranges.
 *
 * Displaced entirely in the vertex shader — a 400-unit plane at the tessellation
 * needed for the distant ridges is ~250k verts, and doing the fbm on the CPU
 * would stall the boot for a second and pin the geometry to one resolution.
 *
 * Normals come from finite differences of the same height function rather than
 * from `computeVertexNormals`, so lighting stays correct without a second pass.
 */
function createTerrainMaterial({ noiseTexture }) {
  return new THREE.ShaderMaterial({
    uniforms: {
      tNoise: { value: noiseTexture },
      uTime: { value: 0 },
      uSnow: { value: new THREE.Color(0.97, 0.98, 1.00) },
      // Snow shadow is strongly blue — it is lit only by sky, not sun. Pushing
      // it this far down is what gives an otherwise white frame its form.
      uShadow: { value: new THREE.Color(0.44, 0.52, 0.66) },
      uSunDir: { value: new THREE.Vector3(-0.35, 0.72, 0.60).normalize() },
      ...fogUniforms(),
    },
    vertexShader: /* glsl */ `
      varying vec3 vWorldPos;
      varying vec3 vNormal;
      varying float vHeight;

      ${common}
      ${noise}

      // Height field: a broad low-frequency base for the mountain ranges, plus
      // a flat bowl carved out around the origin so the igloo sits on level snow.
      float terrainHeight(vec2 p) {
        float ranges = fbm(vec3(p * 0.010, 0.0), 5, 2.0, 0.5);
        ranges = pow(max(ranges * 0.5 + 0.5, 0.0), 2.2) * 34.0;

        float dunes = fbm(vec3(p * 0.055, 11.3), 4, 2.0, 0.5) * 1.1;

        // Flatten toward the centre; the bowl edge is smooth so there is no
        // visible crease where the two regimes meet.
        float flat_ = smoothstep(14.0, 62.0, length(p));
        return ranges * flat_ + dunes * mix(0.18, 1.0, flat_);
      }

      void main() {
        vec3 p = position;
        vec2 xz = p.xy; // plane is authored in XY, rotated into XZ by the mesh
        float h = terrainHeight(xz);
        p.z = h;
        vHeight = h;

        vec4 world = modelMatrix * vec4(p, 1.0);
        vWorldPos = world.xyz;

        // Central-difference normal in world space.
        float e = 1.2;
        float hx = terrainHeight(xz + vec2(e, 0.0)) - terrainHeight(xz - vec2(e, 0.0));
        float hz = terrainHeight(xz + vec2(0.0, e)) - terrainHeight(xz - vec2(0.0, e));
        vNormal = normalize(vec3(-hx, 2.0 * e, -hz));

        gl_Position = projectionMatrix * viewMatrix * world;
      }
    `,
    fragmentShader: /* glsl */ `
      precision highp float;
      varying vec3 vWorldPos;
      varying vec3 vNormal;
      varying float vHeight;

      uniform sampler2D tNoise;
      uniform vec3 uSnow;
      uniform vec3 uShadow;
      uniform vec3 uSunDir;

      ${common}
      ${FOG}

      void main() {
        vec3 N = normalize(vNormal);

        // Wrapped diffuse: snow is deeply scattering, so light wraps well past
        // the terminator. Plain N.L gives it a hard, rocky shading break.
        float ndl = dot(N, uSunDir) * 0.5 + 0.5;
        float diffuse = pow(ndl, 1.4);

        // Sky occlusion approximated by slope: flats see the whole dome, steep
        // faces see less of it.
        float sky = smoothstep(0.2, 1.0, N.y);

        vec3 color = mix(uShadow, uSnow, diffuse);
        color = mix(color * 0.92, color, sky);

        // Wind-packed surface texture, faded out with distance so it never
        // aliases into noise on the far ridges.
        float grain = texture2D(tNoise, vWorldPos.xz * 0.09).r;
        float grainFade = 1.0 - smoothstep(20.0, 90.0, length(vWorldPos.xz));
        color *= mix(1.0, mix(0.95, 1.05, grain), grainFade);

        // Sparkle: only on near, sky-facing snow.
        float sparkle = pow(texture2D(tNoise, vWorldPos.xz * 2.7).a, 18.0);
        color += sparkle * sky * grainFade * 0.5;

        gl_FragColor = vec4(applyFog(color, length(vWorldPos - cameraPosition)), 1.0);
      }
    `,
  });
}

/* ------------------------------------------------------------------ *
 * Igloo construction
 * ------------------------------------------------------------------ */

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
 * Lay ice blocks in courses over a hemisphere.
 *
 * A real igloo is a stack of shrinking rings, each block cut to the local
 * curvature — so blocks are generated per ring from the arc length available,
 * not instanced from one size. Each block is oriented by `lookAt(centre)`, which
 * puts its depth axis along the dome radius and tilts it with the curvature for
 * free.
 *
 * Blocks share one geometry per ring (they only differ by transform), so the
 * whole dome is a handful of draw calls, not one per brick.
 */
function buildIgloo({ material, radius = 3.1, courses = 7, rng }) {
  const group = new THREE.Group();
  // Bricks live in their own group: the refraction pre-pass hides the ice but
  // must keep the opaque interior shell, or the blocks refract the snowfield
  // behind the dome instead of its dark inside.
  const brickGroup = new THREE.Group();
  group.add(brickGroup);
  const blocks = [];

  // Courses run from the snow line up to the crown. thetaEnd must reach the
  // equator (PI/2) or the lowest course sits above the ground and the whole
  // dome reads as floating.
  const thetaStart = 0.10; // radians from the pole, leaves room for a cap block
  const thetaEnd = Math.PI / 2;

  for (let c = 0; c < courses; c++) {
    const t0 = thetaEnd - (c / courses) * (thetaEnd - thetaStart);
    const t1 = thetaEnd - ((c + 1) / courses) * (thetaEnd - thetaStart);
    const theta = (t0 + t1) * 0.5;

    const ringRadius = radius * Math.sin(theta);
    const y = radius * Math.cos(theta);
    // Vertical extent of this course along the surface.
    const courseHeight = radius * Math.abs(t0 - t1) * 1.02;

    // Choose a block count that keeps blocks roughly brick-proportioned.
    const targetWidth = 1.15;
    const count = Math.max(5, Math.round((2 * Math.PI * ringRadius) / targetWidth));
    const arc = (2 * Math.PI) / count;
    const blockWidth = ringRadius * arc * 0.92; // mortar gap
    const depth = 0.42;

    // Generous bevel. The bright rim on the reference blocks is Fresnel on the
    // chamfer, so at a 0.045 radius it collapses to a hairline and disappears —
    // the bevel width *is* the glow width.
    const geometry = new RoundedBoxGeometry(blockWidth, courseHeight * 0.9, depth, 5, 0.12);

    // Offset every other course by half a block, the way real masonry is bonded.
    const phase = (c % 2) * arc * 0.5;

    for (let i = 0; i < count; i++) {
      const angle = i * arc + phase;

      // Entrance: leave a gap in the two lowest courses on the +Z face.
      const facingFront = Math.abs(Math.atan2(Math.sin(angle), Math.cos(angle)) - Math.PI / 2);
      if (c < 2 && facingFront < 0.42) continue;

      const mesh = new THREE.Mesh(geometry, material);
      const jitter = 1 + (rng() - 0.5) * 0.05;
      mesh.position.set(
        Math.cos(angle) * ringRadius * jitter,
        y,
        Math.sin(angle) * ringRadius * jitter
      );
      mesh.lookAt(0, 0, 0);
      // Hand-cut blocks are never quite square to the course.
      mesh.rotateZ((rng() - 0.5) * 0.05);
      mesh.rotateX((rng() - 0.5) * 0.03);
      mesh.scale.setScalar(1 + (rng() - 0.5) * 0.06);
      brickGroup.add(mesh);
      blocks.push(mesh);
    }
  }

  // Crown block, capping the hole left at the pole.
  const cap = new THREE.Mesh(new RoundedBoxGeometry(0.95, 0.95, 0.42, 5, 0.12), material);
  cap.position.set(0, radius * Math.cos(thetaStart * 0.4), 0);
  cap.rotation.y = rng() * Math.PI;
  brickGroup.add(cap);
  blocks.push(cap);

  /**
   * Entrance porch.
   *
   * A barrel vault sounds right but reads as a mess at this scale — most of the
   * arch ends up below the snow line. Real snow-house entrances are a squared
   * annex, so this is two walls plus a lintel course: unambiguous silhouette,
   * and it leaves a readable dark opening.
   */
  {
    const porchZ = radius * 0.94;
    const halfWidth = 0.82;
    const wallCourses = 3;
    const blockH = 0.46;

    for (let course = 0; course < wallCourses; course++) {
      const y = -0.02 + course * (blockH + 0.03);
      for (let depth = 0; depth < 3; depth++) {
        const z = porchZ + 0.35 + depth * 0.55;
        for (const side of [-1, 1]) {
          const g = new RoundedBoxGeometry(0.34, blockH, 0.52, 5, 0.10);
          const mesh = new THREE.Mesh(g, material);
          mesh.position.set(side * halfWidth, y, z);
          mesh.rotation.y = (rng() - 0.5) * 0.06;
          mesh.rotation.z = (rng() - 0.5) * 0.04;
          mesh.userData.anchored = true;
          brickGroup.add(mesh);
          blocks.push(mesh);
        }
      }
    }

    // Lintel: blocks spanning the opening, capping the porch.
    const lintelY = -0.02 + wallCourses * (blockH + 0.03);
    for (let depth = 0; depth < 3; depth++) {
      const g = new RoundedBoxGeometry(halfWidth * 2 + 0.34, 0.36, 0.52, 5, 0.10);
      const mesh = new THREE.Mesh(g, material);
      mesh.position.set(0, lintelY, porchZ + 0.35 + depth * 0.55);
      mesh.rotation.z = (rng() - 0.5) * 0.03;
      mesh.userData.anchored = true;
      brickGroup.add(mesh);
      blocks.push(mesh);
    }
  }

  /* foundation course: chunkier blocks half-buried at the snow line */
  {
    const r = radius * 1.02;
    const count = Math.round((2 * Math.PI * r) / 1.35);
    const arc = (2 * Math.PI) / count;
    const g = new RoundedBoxGeometry(r * arc * 0.92, 0.62, 0.62, 5, 0.12);
    for (let i = 0; i < count; i++) {
      const angle = i * arc + arc * 0.5;
      const mesh = new THREE.Mesh(g, material);
      // Sunk below y=0 so the snow shader hides the bottom edge — a foundation
      // course resting exactly on the ground plane reads as a sticker.
      mesh.position.set(Math.cos(angle) * r, -0.22 + (rng() - 0.5) * 0.05, Math.sin(angle) * r);
      mesh.lookAt(0, mesh.position.y, 0);
      mesh.rotateY((rng() - 0.5) * 0.06);
      mesh.userData.anchored = true;
      brickGroup.add(mesh);
      blocks.push(mesh);
    }
  }

  /**
   * Interior shell.
   *
   * Without it you see straight through the doorway to the bright sky, and the
   * entrance reads as a hole cut in a cardboard cutout. A back-faced dark shell
   * just inside the block courses gives the opening something to be dark
   * against, and gives every block a dim interior to refract instead of the
   * snowfield behind the dome.
   */
  const interior = new THREE.Mesh(
    new THREE.SphereGeometry(radius * 0.90, 32, 20, 0, Math.PI * 2, 0, Math.PI / 2),
    new THREE.MeshBasicMaterial({ color: new THREE.Color(0.30, 0.35, 0.43), side: THREE.BackSide })
  );
  group.add(interior);

  // Floor disc, so the interior does not open onto the sky from below.
  const floor = new THREE.Mesh(
    new THREE.CircleGeometry(radius * 0.92, 32),
    new THREE.MeshBasicMaterial({ color: new THREE.Color(0.38, 0.43, 0.51) })
  );
  floor.rotation.x = -Math.PI / 2;
  floor.position.y = 0.01;
  group.add(floor);

  /**
   * Bake per-block exploded-view state.
   *
   * This is an *exploded diagram*, not a demolition. On the reference the upper
   * dome blocks lift roughly a third of a block-width apart and hang there,
   * glowing, with annotation leaders between them — the silhouette of the igloo
   * stays completely readable the whole time. Blowing blocks across the screen
   * destroys the one thing the effect exists to show, which is how the structure
   * is assembled.
   *
   * The foundation course and the porch do not move at all: on the reference
   * they stay matte and planted while the dome above them opens up.
   */
  {
    let minY = Infinity;
    let maxY = -Infinity;
    for (const b of blocks) {
      minY = Math.min(minY, b.position.y);
      maxY = Math.max(maxY, b.position.y);
    }
    const spanY = Math.max(maxY - minY, 1e-3);

    const axis = new THREE.Vector3();
    for (const b of blocks) {
      const height = (b.position.y - minY) / spanY;

      const radial = b.position.clone();
      radial.y *= 0.35;             // flatten so blocks fan out more than up
      if (radial.lengthSq() < 1e-6) radial.set(0, 1, 0);
      radial.normalize();

      // Mostly straight out along the dome normal, with a little lift.
      const dir = radial
        .clone()
        .addScaledVector(new THREE.Vector3(0, 1, 0), 0.30 + rng() * 0.25)
        .normalize();

      axis.set(rng() * 2 - 1, rng() * 2 - 1, rng() * 2 - 1).normalize();

      b.userData.rest = {
        position: b.position.clone(),
        quaternion: b.quaternion.clone(),
      };
      b.userData.blast = {
        direction: dir,
        // Anchored blocks get 0. Everything else drifts a fraction of a block.
        distance: b.userData.anchored ? 0 : 0.10 + rng() * 0.34,
        // A few degrees of tilt, not a tumble.
        spin: new THREE.Quaternion().setFromAxisAngle(axis, (rng() * 2 - 1) * 0.20),
        // Crown blocks separate first.
        order: 1 - height,
        // Hover pushes further than the scroll exploded view — on the reference
        // the hovered cluster clearly lifts clear of its neighbours.
        hoverDistance: b.userData.anchored ? 0 : 0.55 + rng() * 0.62,
        hoverSpin: new THREE.Quaternion().setFromAxisAngle(axis, (rng() * 2 - 1) * 0.55),
      };
      b.userData.hover = 0;

      // Per-mesh uniform push. three.js fires onBeforeRender before it uploads
      // uniforms for that draw call, so a shared material can still carry
      // per-object values without cloning it 136 times.
      b.onBeforeRender = (renderer, scene, camera, geometry, mat) => {
        mat.uniforms.uHover.value = b.userData.hover;
      };
    }
  }

  group.userData.blocks = blocks;
  group.userData.brickGroup = brickGroup;
  group.userData.interior = interior;
  group.userData.floor = floor;
  return group;
}

/* ------------------------------------------------------------------ *
 * Scene
 * ------------------------------------------------------------------ */

export class IceScene {
  constructor(renderer, assets) {
    this.renderer = renderer;
    this.assets = assets;

    this.scene = new THREE.Scene();
    this.scene.background = FOG_COLOR.clone();
    this.scene.environment = assets.envMap;

    this.camera = new THREE.PerspectiveCamera(34, 1, 0.1, 600);
    this.camera.position.set(0.6, 2.2, 16.5);
    this.cameraTarget = new THREE.Vector3(0, 1.35, 0);

    /* terrain */
    const terrain = new THREE.Mesh(
      new THREE.PlaneGeometry(520, 520, 380, 380),
      createTerrainMaterial({ noiseTexture: assets.noise })
    );
    terrain.rotation.x = -Math.PI / 2;
    terrain.position.y = -1.35;
    terrain.frustumCulled = false;
    this.terrain = terrain;
    this.scene.add(terrain);

    /* ice */
    this.iceMaterial = new IceMaterial({
      envMap: assets.envMap,
      sceneTexture: null,
      frostTexture: assets.frost,
      frostNormalTexture: assets.frostNormal,
      detailTexture: assets.noise,
      blueNoise: assets.blueNoise,
      fogColor: FOG_COLOR,
      fogDensity: FOG_DENSITY,
    });
    this.iceMaterial.uniforms.uBlueSize.value.set(
      assets.blueNoise.image.width,
      assets.blueNoise.image.height
    );

    const rng = mulberry32(11);
    this.igloo = buildIgloo({ material: this.iceMaterial, radius: 3.4, courses: 8, rng });
    // Sit the equator course on the snow: terrain sits at -1.35 and the centre
    // of the map is flattened, so the dome origin goes just below that.
    this.igloo.position.y = -1.28;
    this.scene.add(this.igloo);

    /* drifting snow */
    this.particles = new ParticleSim(renderer, {
      size: 96,
      bounds: new THREE.Vector3(16, 7, 10),
      speed: 0.26,
      pointSize: 2.0,
    });
    this.particles.material.uniforms.uColor.value.setRGB(1.0, 1.0, 1.0);
    this.particles.material.uniforms.uOpacity.value = 0.5;
    this.particles.material.blending = THREE.NormalBlending;
    this.scene.add(this.particles.points);

    /* headline */
    this.headline = new SDFText(assets.font, assets.fontTexture, {
      text: 'IGLOO',
      size: 1.25,
      align: 'center',
      lineHeight: 1.0,
      letterSpacing: 0.06,
      color: 0x223140,
    });
    this.headline.position.set(0, 3.30, 5.6);
    this.headline.material.uniforms.uAnimationOrder.value = ORDER.GLYPH;
    this.headline.material.uniforms.uAnimationDirection.value.set(0, -0.5, 0.9);
    this.headline.material.uniforms.uAnimationMargin.value = 0.45;
    this.headline.material.uniforms.uWobble.value = 0.006;
    this.scene.add(this.headline);

    this.subline = new SDFText(assets.font, assets.fontTexture, {
      text: '// PROCEDURAL ICE / SCREEN-SPACE REFRACTION',
      size: 0.16,
      align: 'center',
      lineHeight: 1.4,
      letterSpacing: 0.14,
      color: 0x536171,
    });
    this.subline.position.set(0, 2.72, 5.6);
    this.subline.material.uniforms.uAnimationOrder.value = ORDER.GLYPH;
    this.subline.material.uniforms.uAnimationDirection.value.set(0.25, 0, 0);
    this.subline.material.uniforms.uAnimationMargin.value = 0.6;
    this.scene.add(this.subline);

    /**
     * Hover proxy.
     *
     * The reference raycasts the actual blocks — which is why the case study
     * lists three-mesh-bvh. A dome-shaped proxy gets the same hit point for one
     * sphere test instead of 136 mesh tests, and the difference is invisible
     * because all we need is "where on the igloo is the cursor pointing".
     *
     * Kept out of the scene graph deliberately: Raycaster skips objects with
     * visible === false, so an invisible proxy in the scene would never be hit.
     */
    this.hoverProxy = new THREE.Mesh(
      new THREE.SphereGeometry(3.55, 24, 16),
      new THREE.MeshBasicMaterial()
    );
    this.hoverProxy.position.copy(this.igloo.position);
    this.hoverProxy.updateMatrixWorld();

    this._raycaster = new THREE.Raycaster();
    this._pointerNDC = new THREE.Vector2();
    this._hoverPoint = new THREE.Vector3();
    this._hoverActive = false;

    this._parallax = { x: 0, y: 0, tx: 0, ty: 0 };
    this._mouseWorld = new THREE.Vector3();
    // Scratch quaternion for setAssembly — allocating one per block per frame
    // is 136 allocations at 60fps for no reason.
    this._blastQuat = new THREE.Quaternion();
    this._blastVec = new THREE.Vector3();
    this.assembly = 0;
  }

  setSize(width, height) {
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.iceMaterial.setSize(width, height);
  }

  setRefractionTexture(texture) {
    this.iceMaterial.uniforms.tScene.value = texture;
  }

  /**
   * The frost sim ping-pongs, so `frost.texture` points at a different render
   * target every frame. Rebind rather than caching it once at construction.
   */
  bindFrost(frost) {
    this.iceMaterial.uniforms.tFrost.value = frost.texture;
    this.iceMaterial.uniforms.tFrostNormal.value = frost.normalTexture;
  }

  /** Toggle only the ice bricks; the opaque interior stays in the refraction pass. */
  setIceVisible(visible) {
    this.igloo.userData.brickGroup.visible = visible;
  }

  /**
   * Disassemble the dome.
   *
   * @param {number} t 0 = assembled, 1 = fully blown apart.
   *
   * Each block runs its own eased sub-animation over a window of the global
   * progress, positioned by its stagger ordinal. `uAnimationMargin`-style
   * overlap (`SPREAD`) keeps the releases blended rather than sequential — the
   * same soft-front trick the text reveal uses, applied to transforms.
   */
  setAssembly(t, dt = 1 / 60) {
    const blocks = this.igloo.userData.blocks;
    const SPREAD = 0.55; // fraction of the timeline any one block occupies

    // Radius of the hover influence, in world units. Roughly two block widths —
    // enough for a cluster, not the whole dome.
    const HOVER_RADIUS = 2.6;

    for (let i = 0; i < blocks.length; i++) {
      const b = blocks[i];
      const rest = b.userData.rest;
      const blast = b.userData.blast;

      /* --- scroll-driven exploded view --- */
      const start = blast.order * (1 - SPREAD);
      const local = Math.min(1, Math.max(0, (t - start) / SPREAD));
      const scrollEased = 1 - Math.pow(1 - local, 3); // cubic out

      /* --- pointer hover --- */
      let hoverTarget = 0;
      if (this._hoverActive && !b.userData.anchored) {
        // World distance from this block's rest position to the cursor's hit
        // point on the dome. Using rest position, not current, or a block that
        // lifts away from the cursor would fall out of its own influence and
        // oscillate.
        const d = this._hoverPoint.distanceTo(
          this._blastVec.copy(rest.position).add(this.igloo.position)
        );
        const n = Math.min(1, d / HOVER_RADIUS);
        hoverTarget = 1 - n * n * (3 - 2 * n); // smoothstep falloff
      }
      // Damped so the cluster swells and settles rather than snapping.
      b.userData.hover = lerpFPS(b.userData.hover, hoverTarget, 0.12, dt);
      const hover = b.userData.hover;

      /* --- combine --- */
      const offset = blast.distance * scrollEased + blast.hoverDistance * hover;
      b.position.copy(rest.position).addScaledVector(blast.direction, offset);

      const spinAmount = Math.min(1, scrollEased + hover);
      const targetSpin = hover > scrollEased ? blast.hoverSpin : blast.spin;
      b.quaternion.copy(rest.quaternion).slerp(
        this._blastQuat.multiplyQuaternions(targetSpin, rest.quaternion),
        spinAmount
      );
    }

    // Scroll raises the floor of the glow; hover multiplies it per block in the
    // shader. The two compose so an exploded *and* hovered block is brightest.
    this.iceMaterial.uniforms.uEdgeGlow.value = 0.42 + t * 0.85;

    // The interior stays. Blocks only drift a fraction of their own width, so
    // the dome never actually opens — and the dark inside showing through the
    // widened joints is exactly what makes the separation legible.

    this.assembly = t;
  }

  update(dt, time, pointer, blueOffset) {
    this._parallax.tx = (pointer.x - 0.5) * 1.3;
    this._parallax.ty = (pointer.y - 0.5) * 0.6;
    this._parallax.x = lerpFPS(this._parallax.x, this._parallax.tx, 0.05, dt);
    this._parallax.y = lerpFPS(this._parallax.y, this._parallax.ty, 0.05, dt);

    // Slow orbital drift so the dome always has moving specular on it.
    const drift = Math.sin(time * 0.06) * 0.9;
    this.camera.position.x = this._parallax.x + drift;
    this.camera.position.y = 2.4 + this._parallax.y + this.assembly * 0.35;
    // Gentle push-in as the joints open. The reference dollies toward the dome
    // rather than cutting, which is what lets you read the individual blocks.
    this.camera.position.z = 16.5 - this.assembly * 3.2;
    this.camera.lookAt(this.cameraTarget);

    // Where on the igloo is the cursor pointing? Must run after the camera has
    // been positioned this frame, or the hover lags the parallax by a frame.
    this._pointerNDC.set(pointer.x * 2 - 1, pointer.y * 2 - 1);
    this._raycaster.setFromCamera(this._pointerNDC, this.camera);
    const hit = this._raycaster.intersectObject(this.hoverProxy, false);
    this._hoverActive = hit.length > 0;
    if (this._hoverActive) this._hoverPoint.copy(hit[0].point);

    this._mouseWorld.set(pointer.x * 2 - 1, pointer.y * 2 - 1, 0.5)
      .unproject(this.camera)
      .sub(this.camera.position)
      .normalize()
      .multiplyScalar(11)
      .add(this.camera.position);

    this.terrain.material.uniforms.uTime.value = time;
    this.iceMaterial.update(time, blueOffset);
    this.particles.update(dt, time, this._mouseWorld, pointer.active ? 0.9 : 0);
    this.headline.update(time);
    this.subline.update(time);
  }

  dispose() {
    this.particles.dispose();
    this.iceMaterial.dispose();
    this.terrain.geometry.dispose();
    this.terrain.material.dispose();
  }
}
