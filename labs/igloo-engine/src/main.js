import * as THREE from 'three';
import { Pointer } from './core/pointer.js';
import { Damped, createRT } from './core/gpu.js';
import {
  makeBlueNoiseTexture,
  makeLUTTexture,
  bakeNoiseTile,
  bakeCausticsTile,
  bakeEnvironment,
} from './gen/textures.js';
import { createSDFFont } from './text/sdfFont.js';
import { FrostSim } from './sim/FrostSim.js';
import { Composer } from './post/Composer.js';
import { IceScene } from './scene/IceScene.js';
import { IceBlockScene } from './scene/IceBlockScene.js';

const container = document.getElementById('app');
const hud = document.getElementById('hud');
const boot = document.getElementById('boot');

/* ------------------------------------------------------------------ *
 * Renderer
 * ------------------------------------------------------------------ */

const renderer = new THREE.WebGLRenderer({
  antialias: false, // the composite pass is the last write; MSAA on the default
  powerPreference: 'high-performance', // framebuffer would be thrown away anyway
  stencil: false,
  depth: true,
});
// Matches the scene fog colour, so anything that fails to draw blends in
// rather than punching a dark hole in the snow.
renderer.setClearColor(0xdaddd8, 1);
renderer.outputColorSpace = THREE.SRGBColorSpace;
// Tone mapping happens in the grade pass, not here — doing it twice crushes the
// highlights that make ice read as ice.
renderer.toneMapping = THREE.NoToneMapping;
// Manual reset: the HUD reads draw counts after the final pass, and the default
// auto-reset would zero them on every render() call.
renderer.info.autoReset = false;
container.appendChild(renderer.domElement);

// Cap DPR at 2. Past that the fill cost of the refraction + CA passes dominates
// and the visual difference is nil.
const maxDPR = 2;
let dpr = Math.min(window.devicePixelRatio || 1, maxDPR);

/* ------------------------------------------------------------------ *
 * Boot: generate every asset procedurally
 * ------------------------------------------------------------------ */

const t0 = performance.now();

const blueNoise = makeBlueNoiseTexture(64);
const lutTexture = makeLUTTexture(32);
const noiseTexture = bakeNoiseTile(renderer, 256);
const caustics = bakeCausticsTile(renderer, 512);
const envMap = bakeEnvironment(renderer, 1024);
const { texture: fontTexture, font } = createSDFFont({
  family: '"IBM Plex Mono", ui-monospace, Menlo, monospace',
  weight: 600,
  em: 44,
  distanceRange: 8,
});

const frost = new FrostSim(renderer, { resolution: 512, advectTexture: noiseTexture });

const assets = {
  envMap,
  noise: noiseTexture,
  caustics,
  blueNoise,
  font,
  fontTexture,
  frost: frost.texture,
  frostNormal: frost.normalTexture,
};

// Section 1: the igloo on the snowfield.
const scene = new IceScene(renderer, assets);
// Section 2: the portfolio ice blocks. Growing three crystals costs ~150ms at
// boot, which is why the loading overlay exists.
const blockScene = new IceBlockScene(renderer, assets);

const composer = new Composer(renderer, {
  blueNoiseTexture: blueNoise,
  lutTexture,
  noiseTexture,
});

// Buffer the ice refracts: the scene rendered with the ice hidden.
// Shared by both sections: section A is fully composited before section B's
// refraction pass overwrites it, so one buffer is enough.
let refractionRT = createRT(1, 1, { depthBuffer: true });
scene.setRefractionTexture(refractionRT.texture);
blockScene.setRefractionTexture(refractionRT.texture);

const pointer = new Pointer(renderer.domElement);

/* ------------------------------------------------------------------ *
 * Resize
 * ------------------------------------------------------------------ */

function resize() {
  const width = container.clientWidth;
  const height = container.clientHeight;
  dpr = Math.min(window.devicePixelRatio || 1, maxDPR);

  renderer.setPixelRatio(dpr);
  renderer.setSize(width, height, false);

  const bw = Math.round(width * dpr);
  const bh = Math.round(height * dpr);

  composer.setSize(bw, bh);
  // The refraction buffer is half resolution: it is only ever read through a
  // heavily distorted, dispersed lookup, so the detail is unrecoverable anyway.
  refractionRT.setSize(Math.max(1, bw >> 1), Math.max(1, bh >> 1));
  scene.setSize(width, height);
  blockScene.setSize(width, height);
  frost.setSize(width, height);
  scene.particles.setPixelRatio(dpr);
}
window.addEventListener('resize', resize);
resize();

/* ------------------------------------------------------------------ *
 * Scroll -> transition progress
 * ------------------------------------------------------------------ */

// Scroll runs 0..2: the first unit covers the igloo and the cut, the second
// travels the rail of portfolio blocks.
const MAX_SCROLL = 2;
const progress = new Damped(0, 0.075);
let wheelAccum = 0;

window.addEventListener('wheel', (e) => {
  wheelAccum += e.deltaY * 0.0012;
  wheelAccum = Math.max(0, Math.min(MAX_SCROLL, wheelAccum));
  progress.target = wheelAccum;
}, { passive: true });

let touchY = null;
window.addEventListener('touchstart', (e) => { touchY = e.touches[0].clientY; }, { passive: true });
window.addEventListener('touchmove', (e) => {
  if (touchY === null) return;
  const y = e.touches[0].clientY;
  wheelAccum = Math.max(0, Math.min(MAX_SCROLL, wheelAccum + (touchY - y) * 0.004));
  progress.target = wheelAccum;
  touchY = y;
}, { passive: true });

/* ------------------------------------------------------------------ *
 * Intro reveal
 * ------------------------------------------------------------------ */

let introStart = -1;
const INTRO_DURATION = 2.2;
const easeOut = (t) => 1 - Math.pow(1 - t, 3);

/* ------------------------------------------------------------------ *
 * Loop
 * ------------------------------------------------------------------ */

const clock = new THREE.Clock();
let frame = 0;
let fpsAccum = 0;
let fpsFrames = 0;
let fps = 0;

function frameLoop() {
  requestAnimationFrame(frameLoop);

  // Clamp: a backgrounded tab returns a huge delta that would blow up every
  // integrator in the engine on the first frame back.
  const dt = Math.min(clock.getDelta(), 1 / 20);
  const time = clock.elapsedTime;
  frame++;
  renderer.info.reset();

  if (introStart < 0) introStart = time;
  const intro = Math.min(1, (time - introStart) / INTRO_DURATION);

  pointer.update(dt);
  progress.update(dt);
  composer.setFrame(frame, time);

  frost.update(dt, pointer, time);
  // Rebind after the sim steps: the ping-pong swap means the "current" frost
  // texture is a different object every frame.
  scene.bindFrost(frost);
  composer.bindFrost(frost);

  // One scroll value drives four overlapping phases. The overlaps matter: the
  // cut starts while the dome joints are still opening, and the block
  // annotations start plotting before the cut has finished, so nothing in the
  // sequence ever waits on anything else finishing.
  const scroll = progress.value;
  const clamp01 = (v) => Math.min(1, Math.max(0, v));

  const assembly = clamp01(scroll / 0.72);          // igloo exploded view
  const cut = clamp01((scroll - 0.66) / 0.34);      // transition into section 2
  const blockReveal = clamp01((scroll - 0.86) / 0.30); // annotations plot in
  const rail = clamp01((scroll - 1.0) / 1.0);       // travel across the blocks

  const blueOffset = composer.transition.uniforms.uBlueOffset.value;

  // update() first: it positions the camera and runs the hover raycast, and
  // setAssembly consumes that hit point. Reversed, hover trails a frame behind
  // the camera parallax and the cluster visibly lags the cursor.
  scene.update(dt, time, pointer, blueOffset);
  scene.setAssembly(assembly, dt);
  scene.headline.progress = easeOut(intro);

  blockScene.bindFrost(frost);
  blockScene.setRailPosition(rail);
  blockScene.setReveal(easeOut(blockReveal));
  blockScene.update(dt, time, blueOffset);

  // 1. Refraction source: everything except the ice.
  scene.setIceVisible(false);
  renderer.setRenderTarget(refractionRT);
  renderer.clear();
  renderer.render(scene.scene, scene.camera);
  scene.setIceVisible(true);

  // 2. Scene A, with the ice sampling that buffer.
  renderer.setRenderTarget(composer.sceneA);
  renderer.clear();
  renderer.render(scene.scene, scene.camera);

  // 3. Section 2 — skipped entirely while the cut is idle. Same two-pass
  //    refraction: the specimen has to be in the buffer the ice samples, or
  //    the blocks refract the empty backdrop and look hollow.
  if (cut > 0.001) {
    blockScene.setIceVisible(false);
    renderer.setRenderTarget(refractionRT);
    renderer.clear();
    renderer.render(blockScene.scene, blockScene.camera);
    blockScene.setIceVisible(true);

    renderer.setRenderTarget(composer.sceneB);
    renderer.clear();
    renderer.render(blockScene.scene, blockScene.camera);
  }

  // 4. Transition + grade to the screen.
  renderer.setRenderTarget(null);
  composer.render(cut, progress.velocity);

  fpsAccum += dt;
  fpsFrames++;
  if (fpsAccum > 0.5) {
    fps = Math.round(fpsFrames / fpsAccum);
    fpsAccum = 0;
    fpsFrames = 0;
    const info = renderer.info.render;
    hud.textContent =
      `${fps} fps · ${dpr.toFixed(1)}x dpr · ${info.calls} draws · ${(info.triangles / 1000).toFixed(0)}k tris\n` +
      `scroll: igloo → ice blocks · move to frost`;
  }
}

boot.classList.add('done');
console.info(`[igloo-engine] assets generated in ${(performance.now() - t0).toFixed(0)}ms`);
frameLoop();

// Expose for console poking.
window.engine = { renderer, scene, blockScene, frost, composer, progress, pointer };
