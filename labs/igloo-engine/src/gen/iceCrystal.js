import * as THREE from 'three';

/**
 * Procedural ice crystal growth.
 *
 * The case study describes their workflow directly: "we wrote a custom algorithm
 * that mimicked the growth of ice crystals inside a container. This way we could
 * pick a base shape, such as a cube or cylinder, and then 'grow' a detailed ice
 * structure inside of it." They ran it in Houdini and exported meshes; this runs
 * the equivalent at load time in the browser.
 *
 * The model:
 *
 *   1. Nucleate N crystals at random points inside a container shape.
 *   2. Give each one a hexagonal habit — 6 prism faces, 2 basal faces, 12
 *      pyramidal faces — in its own random orientation.
 *   3. Grow each facet outward along its normal, one step at a time. A facet
 *      freezes when it would leave the container or push into a neighbouring
 *      crystal.
 *   4. Union the crystals, intersect with the container, perturb with noise.
 *   5. Mesh the result with surface nets, flat-shaded so the facets read.
 *
 * Step 3 is what makes it look grown rather than modelled. Crystals that
 * nucleate early claim space and stay chunky; late ones get boxed in by their
 * neighbours and end up as thin wedges. That competition produces the interlock
 * you can see in the reference block, and you cannot get it by unioning random
 * polyhedra.
 */

/* ------------------------------------------------------------------ *
 * Noise
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

function hash3(x, y, z) {
  let h = Math.imul(x | 0, 374761393) ^ Math.imul(y | 0, 668265263) ^ Math.imul(z | 0, 2147483647);
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
}

const smootherstep = (t) => t * t * t * (t * (t * 6 - 15) + 10);

function valueNoise3(x, y, z) {
  const ix = Math.floor(x), iy = Math.floor(y), iz = Math.floor(z);
  const fx = smootherstep(x - ix), fy = smootherstep(y - iy), fz = smootherstep(z - iz);
  let n = 0;
  for (let dz = 0; dz < 2; dz++) {
    const wz = dz ? fz : 1 - fz;
    for (let dy = 0; dy < 2; dy++) {
      const wy = dy ? fy : 1 - fy;
      for (let dx = 0; dx < 2; dx++) {
        const wx = dx ? fx : 1 - fx;
        n += hash3(ix + dx, iy + dy, iz + dz) * wx * wy * wz;
      }
    }
  }
  return n * 2 - 1;
}

function fbm3(x, y, z, octaves = 3) {
  let sum = 0, amp = 0.5, norm = 0, f = 1;
  for (let i = 0; i < octaves; i++) {
    sum += amp * valueNoise3(x * f, y * f, z * f);
    norm += amp;
    f *= 2.07;
    amp *= 0.5;
  }
  return sum / norm;
}

/* ------------------------------------------------------------------ *
 * Containers
 * ------------------------------------------------------------------ */

/** Signed distance to the container. Negative inside. */
function makeContainer(kind, extents) {
  const [ex, ey, ez] = extents;
  if (kind === 'cylinder') {
    const r = Math.min(ex, ez);
    return (x, y, z) => {
      const dr = Math.hypot(x, z) - r;
      const dy = Math.abs(y) - ey;
      const outside = Math.hypot(Math.max(dr, 0), Math.max(dy, 0));
      return outside + Math.min(Math.max(dr, dy), 0);
    };
  }
  // box
  return (x, y, z) => {
    const qx = Math.abs(x) - ex;
    const qy = Math.abs(y) - ey;
    const qz = Math.abs(z) - ez;
    const outside = Math.hypot(Math.max(qx, 0), Math.max(qy, 0), Math.max(qz, 0));
    return outside + Math.min(Math.max(qx, Math.max(qy, qz)), 0);
  };
}

/* ------------------------------------------------------------------ *
 * Crystal habit
 * ------------------------------------------------------------------ */

/**
 * Hexagonal ice habit (Ih), in the crystal's local frame.
 *
 * Real ice is hexagonal, and the ratio between basal and prism growth rates is
 * what decides whether you get a flat plate or a long needle. Randomising that
 * ratio per crystal is most of the visual variety in a cluster.
 */
function hexHabitNormals() {
  const normals = [];
  // 6 prism faces around the c-axis (y).
  for (let i = 0; i < 6; i++) {
    const a = (i / 6) * Math.PI * 2;
    normals.push([Math.cos(a), 0, Math.sin(a)]);
  }
  // 2 basal faces.
  normals.push([0, 1, 0], [0, -1, 0]);
  // 12 pyramidal faces, capping the prism ends.
  for (let i = 0; i < 6; i++) {
    const a = (i / 6) * Math.PI * 2 + Math.PI / 6;
    for (const sy of [1, -1]) {
      const n = [Math.cos(a) * 0.75, sy * 0.66, Math.sin(a) * 0.75];
      const len = Math.hypot(n[0], n[1], n[2]);
      normals.push([n[0] / len, n[1] / len, n[2] / len]);
    }
  }
  return normals;
}

/** Random rotation matrix (3x3, row-major) from a quaternion. */
function randomBasis(rng) {
  const u1 = rng(), u2 = rng(), u3 = rng();
  const s1 = Math.sqrt(1 - u1), s2 = Math.sqrt(u1);
  const q = [
    s1 * Math.sin(2 * Math.PI * u2),
    s1 * Math.cos(2 * Math.PI * u2),
    s2 * Math.sin(2 * Math.PI * u3),
    s2 * Math.cos(2 * Math.PI * u3),
  ];
  const [x, y, z, w] = q;
  return [
    1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w),
    2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w),
    2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y),
  ];
}

/* ------------------------------------------------------------------ *
 * Growth
 * ------------------------------------------------------------------ */

function growCluster({ rng, container, extents, count, steps }) {
  const habit = hexHabitNormals();
  const crystals = [];

  for (let c = 0; c < count; c++) {
    // Nucleate somewhere inside, biased toward the middle so crystals have room.
    let origin;
    for (let tries = 0; tries < 40; tries++) {
      const p = [
        (rng() * 2 - 1) * extents[0] * 0.75,
        (rng() * 2 - 1) * extents[1] * 0.8,
        (rng() * 2 - 1) * extents[2] * 0.75,
      ];
      if (container(p[0], p[1], p[2]) < -0.05) { origin = p; break; }
    }
    if (!origin) continue;

    const basis = randomBasis(rng);

    // Habit ratio: <1 favours prism growth (plates), >1 favours basal (needles).
    const habitRatio = 0.35 + rng() * 1.9;
    const rates = habit.map((n) => {
      const basalness = Math.abs(n[1]);
      const base = 1 - basalness + basalness * habitRatio;
      return base * (0.7 + rng() * 0.6); // per-facet jitter breaks the symmetry
    });

    crystals.push({
      origin,
      basis,
      normals: habit,
      rates,
      offsets: new Float32Array(habit.length).fill(0.02),
      frozen: new Uint8Array(habit.length),
    });
  }

  // Convex polyhedron SDF for one crystal, evaluated in world space.
  const crystalSDF = (cr, x, y, z) => {
    const px = x - cr.origin[0], py = y - cr.origin[1], pz = z - cr.origin[2];
    const b = cr.basis;
    // World -> local is the transpose of the (orthonormal) local -> world basis.
    const lx = b[0] * px + b[3] * py + b[6] * pz;
    const ly = b[1] * px + b[4] * py + b[7] * pz;
    const lz = b[2] * px + b[5] * py + b[8] * pz;

    let d = -Infinity;
    for (let i = 0; i < cr.normals.length; i++) {
      const n = cr.normals[i];
      const dist = n[0] * lx + n[1] * ly + n[2] * lz - cr.offsets[i];
      if (dist > d) d = dist;
    }
    return d;
  };

  const stepSize = Math.max(...extents) / steps * 1.6;

  for (let s = 0; s < steps; s++) {
    for (let ci = 0; ci < crystals.length; ci++) {
      const cr = crystals[ci];
      const b = cr.basis;

      for (let i = 0; i < cr.normals.length; i++) {
        if (cr.frozen[i]) continue;
        const n = cr.normals[i];
        const next = cr.offsets[i] + cr.rates[i] * stepSize;

        // Probe the point this facet would advance to, in world space.
        const lx = n[0] * next, ly = n[1] * next, lz = n[2] * next;
        const wx = cr.origin[0] + b[0] * lx + b[1] * ly + b[2] * lz;
        const wy = cr.origin[1] + b[3] * lx + b[4] * ly + b[5] * lz;
        const wz = cr.origin[2] + b[6] * lx + b[7] * ly + b[8] * lz;

        if (container(wx, wy, wz) > -0.01) { cr.frozen[i] = 1; continue; }

        // Competition: stop where another crystal already occupies the space.
        let blocked = false;
        for (let cj = 0; cj < crystals.length; cj++) {
          if (cj === ci) continue;
          if (crystalSDF(crystals[cj], wx, wy, wz) < 0) { blocked = true; break; }
        }
        if (blocked) { cr.frozen[i] = 1; continue; }

        cr.offsets[i] = next;
      }
    }
  }

  return { crystals, crystalSDF };
}

/* ------------------------------------------------------------------ *
 * Surface nets
 * ------------------------------------------------------------------ */

const CUBE_EDGES = [
  0, 1, 0, 2, 0, 4, 1, 3, 1, 5, 2, 3, 2, 6, 3, 7, 4, 5, 4, 6, 5, 7, 6, 7,
];

/**
 * Naive surface nets (Gibson 1998, after Lysenko's formulation).
 *
 * Chosen over marching cubes because it needs no 256-entry triangle table and
 * places one vertex per cell instead of up to five, which keeps the mesh small
 * enough to flat-shade without exploding the vertex count.
 */
function surfaceNets(field, dims, scale, origin) {
  const [nx, ny, nz] = dims;
  const positions = [];
  const buffer = new Int32Array(nx * ny * nz).fill(-1);
  const cornerValues = new Float32Array(8);

  const idx = (x, y, z) => x + nx * (y + ny * z);

  for (let z = 0; z < nz - 1; z++) {
    for (let y = 0; y < ny - 1; y++) {
      for (let x = 0; x < nx - 1; x++) {
        let mask = 0;
        for (let i = 0; i < 8; i++) {
          const cx = x + (i & 1);
          const cy = y + ((i >> 1) & 1);
          const cz = z + ((i >> 2) & 1);
          const v = field[idx(cx, cy, cz)];
          cornerValues[i] = v;
          if (v < 0) mask |= 1 << i;
        }
        if (mask === 0 || mask === 255) continue;

        // Average the zero crossings on all 12 edges.
        let vx = 0, vy = 0, vz = 0, crossings = 0;
        for (let e = 0; e < 12; e++) {
          const a = CUBE_EDGES[e * 2];
          const b = CUBE_EDGES[e * 2 + 1];
          const va = cornerValues[a];
          const vb = cornerValues[b];
          if ((va < 0) === (vb < 0)) continue;
          const t = va / (va - vb);
          const ax = a & 1, ay = (a >> 1) & 1, az = (a >> 2) & 1;
          const bx = b & 1, by = (b >> 1) & 1, bz = (b >> 2) & 1;
          vx += ax + (bx - ax) * t;
          vy += ay + (by - ay) * t;
          vz += az + (bz - az) * t;
          crossings++;
        }
        const inv = 1 / crossings;
        buffer[idx(x, y, z)] = positions.length / 3;
        positions.push(
          origin[0] + (x + vx * inv) * scale[0],
          origin[1] + (y + vy * inv) * scale[1],
          origin[2] + (z + vz * inv) * scale[2]
        );
      }
    }
  }

  // Emit a quad per sign-changing axis edge, from the four cells around it.
  const indices = [];
  for (let z = 1; z < nz - 1; z++) {
    for (let y = 1; y < ny - 1; y++) {
      for (let x = 1; x < nx - 1; x++) {
        const v0 = buffer[idx(x, y, z)];
        if (v0 < 0) continue;
        const solid = field[idx(x, y, z)] < 0;

        // +X edge -> quad in the YZ plane
        if ((field[idx(x + 1, y, z)] < 0) !== solid) {
          const a = buffer[idx(x, y - 1, z)];
          const b = buffer[idx(x, y - 1, z - 1)];
          const c = buffer[idx(x, y, z - 1)];
          if (a >= 0 && b >= 0 && c >= 0) {
            if (solid) indices.push(v0, a, b, v0, b, c);
            else indices.push(v0, b, a, v0, c, b);
          }
        }
        // +Y edge
        if ((field[idx(x, y + 1, z)] < 0) !== solid) {
          const a = buffer[idx(x - 1, y, z)];
          const b = buffer[idx(x - 1, y, z - 1)];
          const c = buffer[idx(x, y, z - 1)];
          if (a >= 0 && b >= 0 && c >= 0) {
            if (solid) indices.push(v0, b, a, v0, c, b);
            else indices.push(v0, a, b, v0, b, c);
          }
        }
        // +Z edge
        if ((field[idx(x, y, z + 1)] < 0) !== solid) {
          const a = buffer[idx(x - 1, y, z)];
          const b = buffer[idx(x - 1, y - 1, z)];
          const c = buffer[idx(x, y - 1, z)];
          if (a >= 0 && b >= 0 && c >= 0) {
            if (solid) indices.push(v0, a, b, v0, b, c);
            else indices.push(v0, b, a, v0, c, b);
          }
        }
      }
    }
  }

  return { positions, indices };
}

/* ------------------------------------------------------------------ *
 * Public API
 * ------------------------------------------------------------------ */

/**
 * Grow and mesh one ice block.
 *
 * @param {object} opts
 * @param {number} opts.seed          deterministic — same seed, same block
 * @param {'box'|'cylinder'} opts.container
 * @param {[number,number,number]} opts.extents  container half-size
 * @param {number} opts.resolution    voxel grid edge (cost is O(n^3))
 * @param {number} opts.crystals      nucleation count
 * @param {number} opts.steps         growth iterations
 * @param {number} opts.roughness     surface noise amplitude
 * @returns {THREE.BufferGeometry} flat-shaded, non-indexed
 */
export function createIceBlockGeometry({
  seed = 1,
  container = 'box',
  extents = [0.62, 1.0, 0.62],
  resolution = 44,
  crystals = 7,
  steps = 34,
  roughness = 0.035,
  noiseScale = 3.4,
} = {}) {
  const rng = mulberry32(seed);
  const containerSDF = makeContainer(container, extents);
  const { crystals: grown, crystalSDF } = growCluster({
    rng, container: containerSDF, extents, count: crystals, steps,
  });

  // Sample the field. Pad by one cell so the surface always closes.
  const n = resolution;
  const dims = [n, n, n];
  const pad = 1.12;
  const scale = [
    (extents[0] * 2 * pad) / (n - 1),
    (extents[1] * 2 * pad) / (n - 1),
    (extents[2] * 2 * pad) / (n - 1),
  ];
  const origin = [-extents[0] * pad, -extents[1] * pad, -extents[2] * pad];

  const field = new Float32Array(n * n * n);
  const noiseOffset = rng() * 100;

  for (let z = 0; z < n; z++) {
    const wz = origin[2] + z * scale[2];
    for (let y = 0; y < n; y++) {
      const wy = origin[1] + y * scale[1];
      for (let x = 0; x < n; x++) {
        const wx = origin[0] + x * scale[0];

        // Union of crystals.
        let d = Infinity;
        for (let c = 0; c < grown.length; c++) {
          const dc = crystalSDF(grown[c], wx, wy, wz);
          if (dc < d) d = dc;
        }
        // Intersect with the container.
        d = Math.max(d, containerSDF(wx, wy, wz));
        // Frosted micro-relief.
        d += fbm3(wx * noiseScale + noiseOffset, wy * noiseScale, wz * noiseScale, 3) * roughness;

        field[x + n * (y + n * z)] = d;
      }
    }
  }

  const { positions, indices } = surfaceNets(field, dims, scale, origin);

  // Non-indexed so computeVertexNormals gives per-face normals — the facets are
  // the entire point of growing a crystal rather than using a blob.
  const flat = new Float32Array(indices.length * 3);
  for (let i = 0; i < indices.length; i++) {
    const v = indices[i] * 3;
    flat[i * 3 + 0] = positions[v + 0];
    flat[i * 3 + 1] = positions[v + 1];
    flat[i * 3 + 2] = positions[v + 2];
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.BufferAttribute(flat, 3));
  geometry.computeVertexNormals();
  geometry.computeBoundingSphere();
  geometry.userData.triangles = indices.length / 3;
  return geometry;
}

/**
 * The object encased in the ice.
 *
 * The original freezes an actual project asset in here. With no models to load,
 * this grows an abstract specimen from summed spheres through the same surface
 * nets — enough of a silhouette to read as "something is in there", which is all
 * the refraction lets you see anyway.
 */
export function createSpecimenGeometry({ seed = 1, resolution = 30, radius = 0.42 } = {}) {
  const rng = mulberry32(seed ^ 0x5f3759df);

  const blobs = [];
  const bodyR = radius * (0.85 + rng() * 0.3);
  blobs.push({ p: [0, -radius * 0.15, 0], r: bodyR });
  blobs.push({ p: [0, bodyR * 0.85, 0], r: bodyR * 0.62 });      // head
  for (let i = 0; i < 3 + Math.floor(rng() * 3); i++) {
    const a = rng() * Math.PI * 2;
    const h = (rng() * 2 - 1) * bodyR;
    blobs.push({
      p: [Math.cos(a) * bodyR * 0.85, h, Math.sin(a) * bodyR * 0.85],
      r: bodyR * (0.22 + rng() * 0.22),
    });
  }

  const extent = radius * 2.1;
  const n = resolution;
  const scale = [(extent * 2) / (n - 1), (extent * 2) / (n - 1), (extent * 2) / (n - 1)];
  const origin = [-extent, -extent, -extent];
  const field = new Float32Array(n * n * n);

  for (let z = 0; z < n; z++) {
    const wz = origin[2] + z * scale[2];
    for (let y = 0; y < n; y++) {
      const wy = origin[1] + y * scale[1];
      for (let x = 0; x < n; x++) {
        const wx = origin[0] + x * scale[0];
        // Smooth-min union, so the parts fuse into one body.
        //
        // Seeded from the first blob rather than Infinity: the polynomial
        // smooth-min multiplies the running distance by (1 - h), and with
        // d = Infinity the first blend evaluates Infinity * 0 = NaN, which then
        // poisons the whole field and the mesher emits nothing at all.
        const k = 0.12;
        let d = Math.hypot(wx - blobs[0].p[0], wy - blobs[0].p[1], wz - blobs[0].p[2]) - blobs[0].r;
        for (let bi = 1; bi < blobs.length; bi++) {
          const b = blobs[bi];
          const db = Math.hypot(wx - b.p[0], wy - b.p[1], wz - b.p[2]) - b.r;
          const h = Math.max(0, Math.min(1, 0.5 + (0.5 * (d - db)) / k));
          d = db * h + d * (1 - h) - k * h * (1 - h);
        }
        d += fbm3(wx * 7, wy * 7, wz * 7, 2) * 0.012;
        field[x + n * (y + n * z)] = d;
      }
    }
  }

  const { positions, indices } = surfaceNets(field, [n, n, n], scale, origin);
  const flat = new Float32Array(indices.length * 3);
  for (let i = 0; i < indices.length; i++) {
    const v = indices[i] * 3;
    flat[i * 3 + 0] = positions[v + 0];
    flat[i * 3 + 1] = positions[v + 1];
    flat[i * 3 + 2] = positions[v + 2];
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.BufferAttribute(flat, 3));
  geometry.computeVertexNormals();
  geometry.computeBoundingSphere();
  return geometry;
}
