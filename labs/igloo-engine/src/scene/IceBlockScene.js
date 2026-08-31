import * as THREE from 'three';
import { common, noise } from '../glsl/chunks.js';
import { IceMaterial } from '../materials/IceMaterial.js';
import { LeaderLines } from '../materials/LeaderLines.js';
import { SDFText, ORDER } from '../text/SDFText.js';
import { createIceBlockGeometry, createSpecimenGeometry } from '../gen/iceCrystal.js';
import { lerpFPS } from '../core/gpu.js';

/**
 * Section 2 — the portfolio ice blocks.
 *
 * From the case study: "Each project was represented by an object encased in
 * ice... during prototyping, we quickly realised that the projects looked too
 * similar to each other when scrolling past. To add some variation, we decided
 * to create a unique ice block design for each."
 *
 * So the section is a rail of blocks you scroll along, each grown from its own
 * seed with a different container shape and habit, each with a specimen frozen
 * inside and a set of technical annotations plotted around it.
 *
 * Everything sits in a flat grey void rather than the snowfield — the blocks are
 * presented as specimens, not as objects in a world.
 */

const PROJECTS = [
  {
    id: 'PORTFOLIO_CO_01',
    name: 'PUDGY PENGUINS',
    temp: 'TEMP -26.41 / -81.06',
    date: 'D 01.02.2020',
    container: 'box',
    extents: [0.60, 1.05, 0.60],
    crystals: 7,
  },
  {
    id: 'PORTFOLIO_CO_02',
    name: 'LIL PUDGYS',
    temp: 'TEMP -31.08 / -74.19',
    date: 'D 14.07.2022',
    container: 'cylinder',
    extents: [0.68, 0.92, 0.68],
    crystals: 5,
  },
  {
    id: 'PORTFOLIO_CO_03',
    name: 'OVERPASS IP',
    temp: 'TEMP -19.77 / -88.42',
    date: 'D 09.11.2023',
    container: 'box',
    extents: [0.72, 0.78, 0.55],
    crystals: 9,
  },
];

const SPACING = 4.2;

/** Backdrop: a soft radial gradient, parented to the camera so it never moves. */
function createBackdrop() {
  const mesh = new THREE.Mesh(
    new THREE.PlaneGeometry(2, 2),
    new THREE.ShaderMaterial({
      depthTest: false,
      depthWrite: false,
      uniforms: {
        uInner: { value: new THREE.Color(0.475, 0.495, 0.530) },
        uOuter: { value: new THREE.Color(0.315, 0.335, 0.375) },
        uAspect: { value: 1 },
      },
      vertexShader: /* glsl */ `
        varying vec2 vUv;
        void main() {
          vUv = uv;
          // Already in clip space: this is a fullscreen quad, not world geometry.
          gl_Position = vec4(position.xy, 1.0, 1.0);
        }
      `,
      fragmentShader: /* glsl */ `
        precision highp float;
        varying vec2 vUv;
        uniform vec3 uInner;
        uniform vec3 uOuter;
        uniform float uAspect;
        ${common}
        ${noise}
        void main() {
          vec2 p = (vUv - 0.5) * vec2(uAspect, 1.0);
          float d = length(p);
          vec3 c = mix(uInner, uOuter, smoothstep(0.05, 0.85, d));
          // Dither: an 8-bit gradient this shallow bands badly without it.
          c += (hash12(vUv * 2048.0) - 0.5) / 255.0;
          gl_FragColor = vec4(c, 1.0);
        }
      `,
    })
  );
  mesh.frustumCulled = false;
  mesh.renderOrder = -1;
  return mesh;
}

export class IceBlockScene {
  constructor(renderer, assets) {
    this.renderer = renderer;
    this.assets = assets;

    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(32, 1, 0.1, 60);
    this.camera.position.set(0, 0, 6.2);

    this.backdrop = createBackdrop();
    this.scene.add(this.backdrop);

    /**
     * One material for every block. They differ by geometry, not shading — the
     * case study's variation came from the growth algorithm, not from per-project
     * material tweaks.
     */
    this.iceMaterial = new IceMaterial({
      envMap: assets.envMap,
      sceneTexture: null,
      frostTexture: assets.frost,
      frostNormalTexture: assets.frostNormal,
      detailTexture: assets.noise,
      blueNoise: assets.blueNoise,
      fogColor: new THREE.Color(0.40, 0.42, 0.46),
      fogDensity: 0.004,
    });
    const u = this.iceMaterial.uniforms;
    u.uBlueSize.value.set(assets.blueNoise.image.width, assets.blueNoise.image.height);
    // A specimen block is thinner and clearer than a structural igloo brick —
    // you have to be able to see what is frozen inside it.
    u.uThickness.value = 0.72;
    u.uAttenuationDistance.value = 1.15;
    u.uAttenuationColor.value.setRGB(0.44, 0.58, 0.74);
    u.uScatter.value = 0.18;
    u.uScatterColor.value.setRGB(0.58, 0.66, 0.78);
    u.uRefractionStrength.value = 0.62;
    u.uDispersion.value = 0.055;      // stronger fringing; it is the hero object
    u.uEdgeGlow.value = 0.55;
    u.uEnvIntensity.value = 0.75;
    u.uDetailStrength.value = 0.06;   // the facets come from geometry, not normals

    this.blocks = [];
    this.iceGroup = new THREE.Group();
    this.scene.add(this.iceGroup);

    this._buildBlocks();

    this._targetScroll = 0;
    this._scroll = 0;
    this.revealProgress = 0;
  }

  _buildBlocks() {
    const specimenMaterial = new THREE.MeshBasicMaterial({
      color: new THREE.Color(0.11, 0.12, 0.145),
    });

    PROJECTS.forEach((project, i) => {
      const root = new THREE.Group();
      root.position.x = i * SPACING;

      const geometry = createIceBlockGeometry({
        seed: 1000 + i * 137,
        container: project.container,
        extents: project.extents,
        resolution: 46,
        crystals: project.crystals,
        steps: 34,
      });

      const block = new THREE.Mesh(geometry, this.iceMaterial);
      root.add(block);

      // The specimen must render into the refraction buffer, so it is a sibling
      // of the ice rather than a child — `setIceVisible` only hides the ice.
      const specimen = new THREE.Mesh(
        createSpecimenGeometry({ seed: 1000 + i * 137, radius: Math.min(project.extents[0], project.extents[1]) * 0.55 }),
        specimenMaterial
      );
      specimen.position.y = -0.05;
      root.add(specimen);

      /* ---- annotations ---- */

      const ex = project.extents;
      // Leaders run from a point on the block out to where the label sits.
      const paths = [
        [[-ex[0] * 0.5, ex[1] * 0.55, ex[2]], [-ex[0] * 1.5, ex[1] * 1.15, 0], [-ex[0] * 2.9, ex[1] * 1.15, 0]],
        [[ex[0] * 0.6, ex[1] * 0.05, ex[2] * 0.6], [ex[0] * 1.9, ex[1] * 0.42, 0], [ex[0] * 3.0, ex[1] * 0.42, 0]],
        [[ex[0] * 0.35, -ex[1] * 0.6, ex[2] * 0.7], [ex[0] * 1.7, -ex[1] * 0.85, 0], [ex[0] * 3.0, -ex[1] * 0.85, 0]],
        // Underline beneath the call to action.
        [[ex[0] * 1.75, -ex[1] * 1.05, 0], [ex[0] * 3.0, -ex[1] * 1.05, 0]],
      ];
      const lines = new LeaderLines(paths, { color: 0xffffff, width: 1.3, opacity: 0.9 });
      root.add(lines);

      const label = (text, x, y, size, align, color) => {
        const t = new SDFText(this.assets.font, this.assets.fontTexture, {
          text, size, align, lineHeight: 1.5, letterSpacing: 0.09, color,
        });
        t.position.set(x, y, 0);
        t.material.uniforms.uAnimationOrder.value = ORDER.GLYPH;
        t.material.uniforms.uAnimationDirection.value.set(0.12, 0, 0);
        t.material.uniforms.uAnimationMargin.value = 0.55;
        root.add(t);
        return t;
      };

      const texts = [
        label(`${project.id}\n${project.name}`, -ex[0] * 2.85, ex[1] * 1.22, 0.088, 'left', 0xffffff),
        label(project.temp, ex[0] * 3.05, ex[1] * 0.49, 0.075, 'left', 0xffffff),
        label(`${project.date}\nCLICK TO EXPLORE`, ex[0] * 3.05, -ex[1] * 0.78, 0.075, 'left', 0xffffff),
      ];

      // Ghosted background code, far behind and barely visible — the reference
      // has a whole layer of this drifting behind the block.
      const ghost = label(
        `${project.id}   ${project.date}`,
        -ex[0] * 3.5,
        -ex[1] * 1.9,
        0.34,
        'left',
        0x6c7078
      );
      ghost.position.z = -3.2;
      ghost.material.uniforms.uAlpha.value = 0.25;

      this.iceGroup.add(root);
      this.blocks.push({ root, block, specimen, lines, texts, ghost, project });
    });
  }

  setSize(width, height) {
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.iceMaterial.setSize(width, height);
    this.backdrop.material.uniforms.uAspect.value = width / height;
    for (const b of this.blocks) b.lines.setSize(width, height);
  }

  setRefractionTexture(texture) {
    this.iceMaterial.uniforms.tScene.value = texture;
  }

  /** Hide only the ice, so the specimen still lands in the refraction buffer. */
  setIceVisible(visible) {
    for (const b of this.blocks) b.block.visible = visible;
  }

  bindFrost(frost) {
    this.iceMaterial.uniforms.tFrost.value = frost.texture;
    this.iceMaterial.uniforms.tFrostNormal.value = frost.normalTexture;
  }

  /** @param {number} t 0..1 across the whole rail of blocks. */
  setRailPosition(t) {
    this._targetScroll = t * (this.blocks.length - 1) * SPACING;
  }

  /** @param {number} t drives the annotation plot-in and label reveal. */
  setReveal(t) {
    this.revealProgress = t;
  }

  update(dt, time, blueOffset) {
    this._scroll = lerpFPS(this._scroll, this._targetScroll, 0.09, dt);
    this.camera.position.x = this._scroll;

    this.iceMaterial.update(time, blueOffset);

    for (let i = 0; i < this.blocks.length; i++) {
      const b = this.blocks[i];

      // Distance from the camera's current rail position, in block units.
      const focus = 1 - Math.min(1, Math.abs(b.root.position.x - this._scroll) / SPACING);

      // Slow presentation spin, offset per block so they are never in phase.
      b.block.rotation.y = time * 0.16 + i * 1.7;
      b.specimen.rotation.y = b.block.rotation.y;
      b.block.position.y = Math.sin(time * 0.5 + i) * 0.045;
      b.specimen.position.y = -0.05 + b.block.position.y;

      // Annotations only draw for the block you are actually looking at.
      const reveal = this.revealProgress * focus;
      b.lines.progress = reveal;
      for (const t of b.texts) {
        t.progress = reveal;
        t.update(time);
      }
      b.ghost.progress = reveal;
      b.ghost.update(time);
    }
  }

  dispose() {
    this.iceMaterial.dispose();
    for (const b of this.blocks) {
      b.block.geometry.dispose();
      b.specimen.geometry.dispose();
    }
  }
}
