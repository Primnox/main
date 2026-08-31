import * as THREE from 'three';
import { common, easings } from '../glsl/chunks.js';

/**
 * Screen-space-width polylines for the technical annotations.
 *
 * `gl.LINES` gives you 1px lines with no width control on most platforms, so the
 * standard fix — and the one the original bundle uses, judging by its
 * `attribute float side` / `uniform float uWidth` pair — is to expand each
 * segment into a two-triangle ribbon in the vertex shader. Each vertex is
 * duplicated with `side = ±1` and pushed along the segment normal *after*
 * projection, which keeps the ribbon a constant pixel width at any depth.
 *
 * Lines draw in with a per-vertex `along` parameter so they can be revealed as
 * if being plotted, rather than popping in whole.
 */
export class LeaderLines extends THREE.Mesh {
  /**
   * @param {Array<Array<[number,number,number]>>} polylines world-space paths
   */
  constructor(polylines, {
    color = 0xffffff,
    width = 1.4,
    opacity = 0.85,
  } = {}) {
    const positions = [];
    const nextPositions = [];
    const sides = [];
    const along = [];      // 0..1 along the whole polyline
    const pathIndex = [];  // which polyline, so they can stagger
    const indices = [];

    polylines.forEach((points, pi) => {
      // Cumulative length, for a constant-speed draw-in.
      const lengths = [0];
      for (let i = 1; i < points.length; i++) {
        const a = points[i - 1], b = points[i];
        lengths.push(lengths[i - 1] + Math.hypot(b[0] - a[0], b[1] - a[1], b[2] - a[2]));
      }
      const total = lengths[lengths.length - 1] || 1;

      const base = positions.length / 3;
      for (let i = 0; i < points.length; i++) {
        const p = points[i];
        // The neighbour used to derive the segment direction. The last vertex
        // looks backwards so the final segment still has a direction.
        const q = i < points.length - 1 ? points[i + 1] : points[i - 1];
        const flip = i < points.length - 1 ? 1 : -1;

        for (const s of [-1, 1]) {
          positions.push(p[0], p[1], p[2]);
          nextPositions.push(q[0], q[1], q[2]);
          sides.push(s * flip);
          along.push(lengths[i] / total);
          pathIndex.push(pi / Math.max(1, polylines.length - 1));
        }

        if (i < points.length - 1) {
          const v = base + i * 2;
          indices.push(v, v + 1, v + 2, v + 1, v + 3, v + 2);
        }
      }
    });

    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
    geometry.setAttribute('nextPosition', new THREE.Float32BufferAttribute(nextPositions, 3));
    geometry.setAttribute('side', new THREE.Float32BufferAttribute(sides, 1));
    geometry.setAttribute('along', new THREE.Float32BufferAttribute(along, 1));
    geometry.setAttribute('pathIndex', new THREE.Float32BufferAttribute(pathIndex, 1));
    geometry.setIndex(indices);

    const material = new THREE.ShaderMaterial({
      transparent: true,
      depthWrite: false,
      depthTest: false, // annotations overlay the block, they don't intersect it
      // Ribbon winding flips with segment direction, so half the quads face away
      // from the camera and vanish under the default FrontSide culling.
      side: THREE.DoubleSide,
      uniforms: {
        uColor: { value: new THREE.Color(color) },
        uWidth: { value: width },
        uOpacity: { value: opacity },
        uResolution: { value: new THREE.Vector2(1, 1) },
        uProgress: { value: 0 },
        uMargin: { value: 0.4 },
      },
      vertexShader: /* glsl */ `
        attribute vec3 nextPosition;
        attribute float side;
        attribute float along;
        attribute float pathIndex;

        uniform float uWidth;
        uniform vec2 uResolution;
        uniform float uProgress;
        uniform float uMargin;

        varying float vReveal;

        ${common}
        ${easings}

        void main() {
          vec4 current = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
          vec4 next    = projectionMatrix * modelViewMatrix * vec4(nextPosition, 1.0);

          // Perspective divide to NDC, then to aspect-corrected screen space.
          vec2 aspect = vec2(uResolution.x / uResolution.y, 1.0);
          vec2 currentScreen = current.xy / max(current.w, 1e-5) * aspect;
          vec2 nextScreen    = next.xy    / max(next.w, 1e-5)    * aspect;

          vec2 dir = normalize(nextScreen - currentScreen + vec2(1e-6));
          vec2 normal = vec2(-dir.y, dir.x);
          normal /= aspect;

          // uWidth is in pixels; convert to NDC and undo the perspective divide
          // so the offset survives the pipeline at a constant screen width.
          float pixel = uWidth / uResolution.y * 2.0;
          current.xy += normal * side * pixel * 0.5 * current.w;

          // Stagger the paths, then plot each one along its own length.
          float start = pathIndex * (1.0 - uMargin);
          float local = clamp((uProgress - start) / max(uMargin, 1e-3), 0.0, 1.0);
          vReveal = step(along, power2Out(local));

          gl_Position = current;
        }
      `,
      fragmentShader: /* glsl */ `
        precision highp float;
        uniform vec3 uColor;
        uniform float uOpacity;
        varying float vReveal;
        void main() {
          if (vReveal < 0.5) discard;
          gl_FragColor = vec4(uColor, uOpacity);
        }
      `,
    });

    super(geometry, material);
    this.frustumCulled = false;
  }

  setSize(width, height) {
    this.material.uniforms.uResolution.value.set(width, height);
  }

  set progress(v) {
    this.material.uniforms.uProgress.value = v;
  }
}
