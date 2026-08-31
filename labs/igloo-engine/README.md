# igloo-engine

A from-scratch recreation of the render engine architecture behind
[igloo.inc](https://www.igloo.inc/).

Not a copy of their code — the shaders here are written independently. What is
reproduced is the *architecture*: the pass structure, the simulation techniques,
the text pipeline, and the post stack, rebuilt so each decision is legible.

```bash
npm install
npm run dev
```

**Scroll** (~5 notches to the exploded view, ~9 to the ice blocks, ~17 to the
end of the rail). **Move the pointer** anywhere to paint frost.

### Frost is a post effect, not a material effect

Originally the frost mask was sampled only inside `IceMaterial`. That is where
the sim data is most *useful*, but the ice covers maybe 15% of the frame, so
most of the pointer trail landed on snow and did nothing — the headline
interaction was effectively invisible.

It now runs in the grade pass over the whole composited image: the frost normal
displaces the sample UV, the mask crushes colour toward luminance and tints it
cold, and the sim's growth-front channel lights the advancing edge. This also
matches the case study, which lists frost as a *scene transition* effect
alongside chromatic aberration and tech displacement, not as a material.

### Scroll timeline

One scroll value, 0..2, drives four deliberately **overlapping** phases:

```
scroll  0 ────────── 0.66 ─ 0.72 ── 0.86 ── 1.0 ──────────── 2.0
exploded  [=====================]
cut                  [==================]
annotations                      [==========]
block rail                              [=================]
```

The overlaps matter. If the cut waited for the exploded view to settle it would
catch a static frame; if the annotations waited for the cut to finish they would
pop in on an already-composed shot. Nothing in the sequence waits on anything
else finishing.

### Hover is the primary interaction

The igloo's headline effect is **hover**, not scroll. Point at the dome and the
cluster of blocks under the cursor lifts clear of its neighbours and turns from
matte packed snow into blazing white ice; move away and it settles back. Only
that cluster reacts — the rest of the dome stays solid.

- A dome-shaped **proxy mesh** is raycast instead of the 136 blocks. The original
  raycasts the real geometry, which is why the case study lists `three-mesh-bvh`;
  a proxy gets the same hit point for one sphere test. The proxy is deliberately
  kept out of the scene graph, because `Raycaster` skips `visible === false`.
- Per-block influence is a smoothstep on world distance from the hit point,
  measured against each block's **rest** position — measured against its current
  position, a block that lifts away from the cursor leaves its own influence
  radius and oscillates.
- The `uHover` value reaches the shader through each mesh's `onBeforeRender`.
  three.js fires that before uploading uniforms for the draw, so one shared
  material carries per-object values without being cloned 136 times.
- Hover interpolates *scatter* as well as glow. Glow alone reads as a light
  moving; changing opacity is what sells snow turning to ice.

Scroll then opens the whole dome into an **exploded diagram**, not a demolition. Upper blocks lift
about a third of a block-width and hang there with their bevels lit, dark joints
opening between them, while the foundation course and porch stay planted. The
igloo silhouette stays fully readable throughout — that is the whole point of
the effect, and blowing blocks across the screen destroys it.

Blocks separate **crown-first**, staggered by height, each running its own eased
sub-animation over a 0.55-wide window of the global progress.

---

## What the original actually is

Analysed from the shipped bundles:

| Asset | Size | What it is |
| --- | --- | --- |
| `index-*.js` | 16 KB | Svelte + Vite shell. DOM/UI only. |
| `App3D-*.js` | 1.49 MB | The engine. Vanilla Three.js + GSAP. **111 custom shaders**, ~300 custom uniforms. |
| `bitmapworker-*.js` | 2.9 KB | Three's `ImageBitmapLoader` moved off the main thread. |
| `msdfworker-*.js` | 3.2 KB | A complete MSDF text layout engine. |

Loaders in the bundle: Draco, KTX2/basis, meshopt. Post: SMAA, TAA, bokeh,
godrays, 3D LUT. No React — it's vanilla Three.js driving a Svelte UI layer.

### What the case study says

Per the [Awwwards case study](https://www.awwwards.com/igloo-inc-case-study.html)
(by [Abeto](https://abeto.co/), built with Bureaux), the site is **three
sections** plus a real-time intro animation:

1. **Igloo** — the outdoor snow scene.
2. **Ice blocks** — one per portfolio project, each an object *encased in ice*.
   They're modelled by a custom algorithm that "mimicked the growth of ice
   crystals inside a container": pick a base shape (cube, cylinder), grow a
   detailed ice structure inside it. Each project gets a unique block because in
   prototyping "the projects looked too similar to each other when scrolling
   past".
3. **Interactive particles** — the links footer. A particle sim that forms
   different models from VDB volume data, via a custom VDB→browser exporter with
   a compression step. Particles change colour by speed and glow when shifting
   shapes.

Scene transitions use "a mix of chromatic aberration, tech displacement and
frost effect".

The **UI is rendered in WebGL, not HTML** — deliberately, for two text effects:
glitches (cheap as a shader, expensive as CSS clipping/masking) and text
scrambles, where they "change letters by simply adjusting the offset of the SDF
texture" instead of forcing style recalculation.

**The case study does not describe the igloo disassembling.** What the live site
shows is an exploded-view diagram — blocks separated by a fraction of their own
width, glowing, with annotation leaders — reached early in the scroll.

### The five techniques worth stealing

1. **The frost trail is not a fluid sim.** It's max-propagation dilation
   (`next = max(l,r,t,b)`) with noise-advected sampling and per-frame damping.
   Frost only ever advances, then melts. Far cheaper than Navier–Stokes and it
   looks more like ice because it grows along a ragged front.

2. **A separate real fluid solver** (curl → vorticity confinement → divergence →
   Jacobi pressure → projection) exists for the drifting vapour layers, where
   motion has to shear and curl.

3. **The MSDF worker emits ordering weights, not just quads.** Every vertex
   carries its normalised position within five nested orderings — glyph-in-block,
   word-in-block, glyph-in-line, word-in-line, line-in-block. One uniform then
   selects which ordering drives the reveal, so the same geometry animates five
   completely different ways with zero CPU work.

4. **The section transition is a displacement map, not a wipe.** Two fully
   rendered scene buffers, blended along a diagonal front whose position is
   warped per-pixel by a noise texture, with three fronts at different softness
   driving the cut, the UV displacement, and the chromatic aberration
   independently. Opposing parallax on either side sells it as depth.

5. **Blue noise everywhere.** Their CA loop is 5 taps; the seams that leaves are
   hidden by a per-frame-jittered blue noise lookup rather than by adding taps.

---

## Architecture

```
src/
  glsl/chunks.js        Shared GLSL includes (the ${ae}/${Ht}/${Ue} pattern)
  core/
    gpu.js              Fullscreen-triangle Pass, PingPong RT, framerate-independent damping
    pointer.js          Pointer state with previous-position tracking
  gen/textures.js       Every lookup table, generated at boot — no binary assets
  gen/iceCrystal.js     Crystal growth in a container + surface nets mesher
  sim/
    FrostSim.js         Max-propagation frost trail + derived normal map
    FluidSim.js         Stable-fluids solver (Stam 1999)
    ParticleSim.js      GPGPU curl-noise particle field
  materials/
    IceMaterial.js      Screen-space refraction, dispersion, Beer–Lambert, frost coat
    LeaderLines.js      Screen-space-width ribbon polylines for annotations
  text/
    sdfFont.js          Runtime SDF atlas via 8SSEDT
    layout.worker.js    Off-thread layout emitting ordering weights
    SDFText.js          Geometry + staggered reveal material
  post/Composer.js      Cut transition -> LUT grade
  scene/
    IceScene.js         Section 1: igloo, terrain, atmosphere
    IceBlockScene.js    Section 2: portfolio blocks, specimens, annotations
  main.js               Boot, resize, frame loop
```

### Crystal growth

`gen/iceCrystal.js` implements the case study's described workflow — "an
algorithm that mimicked the growth of ice crystals inside a container" — at load
time instead of in Houdini:

1. Nucleate N crystals at random points inside a container (box or cylinder).
2. Give each a hexagonal ice habit — 6 prism faces, 2 basal, 12 pyramidal — in
   its own random orientation, with a randomised basal:prism growth-rate ratio
   (this is what decides plate vs. needle in real ice).
3. Grow each facet outward one step at a time. A facet freezes when it would
   leave the container **or push into a neighbouring crystal**.
4. Union the crystals, intersect with the container, perturb with fbm.
5. Mesh with naive surface nets, flat-shaded so the facets read.

Step 3's collision test is what makes it look grown rather than modelled.
Crystals that nucleate early claim space and stay chunky; late ones get boxed in
and end up as thin wedges. You cannot get that interlock by unioning random
polyhedra.

Surface nets rather than marching cubes: no 256-entry triangle table, and one
vertex per cell instead of up to five, which keeps the mesh small enough to
flat-shade. ~17–25k triangles per block, ~50ms each.

### Frame order

```
1. frost.update()                    ping-pong sim step + normal derivation
2. render scene WITHOUT ice   -> refractionRT   (half res)
3. render scene WITH ice      -> composer.sceneA
4. render readout scene       -> composer.sceneB   (skipped when progress == 0)
5. transition(A, B)           -> transitionRT
6. grade(transitionRT)        -> default framebuffer
```

Step 2 is why the ice can refract everything behind it including other ice. The
opaque interior shell stays visible during it, so blocks refract the dome's dark
inside rather than the snowfield behind it.

### No binary assets

Everything is synthesised at boot (~200–400 ms):

- **Blue noise** — void-and-cluster (Ulichney 1993), 4 independent 64² channels,
  with an incrementally maintained Gaussian energy field so each rank step is
  O(kernel) rather than O(n·kernel).
- **3D LUT** — the "ice" grade baked into a 32³ strip texture.
- **Noise / caustics tiles** — GPU passes using periodic value-noise fbm.
- **Environment** — procedural overcast equirect with softbox lobes, mip-chained
  so the ice material can use an LOD bias in place of a prefiltered probe.
- **SDF font atlas** — glyphs rasterised to canvas, distance field computed with
  8SSEDT.

---

## Deviations from the original, and why

- **Single-channel SDF text, not MSDF.** A true multi-channel field needs glyph
  outlines, which the browser will not expose. Corners round off at large
  scales. The shader's `median3` degrades to identity on greyscale, so dropping
  in a real msdfgen atlas works unchanged.
- **Igloo blocks are laid out analytically**, not grown by a procedural
  crystal-growth simulation authored in Houdini. Courses are derived from arc
  length per ring with masonry bonding offsets.
- **Edge glow is a sharpened Fresnel term**, not total internal reflection. It's
  a deliberate exaggeration — it's the strongest single cue in the reference.
- **No SMAA/TAA/bokeh/godrays.** The bundle has them; this doesn't.
- **No per-block annotation overlay.** The original draws thin glowing leader
  lines and part labels over individual blocks (its `attribute float side` /
  `uWidth` ribbon-line shader, plus `tNumbers`/`uCount`). Not implemented.
- **The encased objects are abstract.** The original freezes real project assets
  in the ice. With no models to load, `createSpecimenGeometry` grows a blob from
  summed spheres through the same mesher — enough silhouette to read through
  refraction, which is all you see of it anyway.
- **Section 3 is not built.** The interactive particle footer, which forms
  models from VDB volume data via their custom exporter, is missing. `ParticleSim`
  here is ambient snow, not a shape-forming volume sim.
- **No text glitch or SDF scramble.** The case study calls these out explicitly
  as the reason the whole UI is WebGL. The atlas and material here support the
  UV-offset trick; the effect itself isn't wired up.
- **Blocks aren't clickable.** The labels say `CLICK TO EXPLORE`; nothing
  listens. There's no per-project detail view.

## Performance notes

~60 fps at 1.3× DPR, 154 draw calls, 660k triangles.

- DPR capped at 2 — beyond that the refraction and CA passes are pure fill cost.
- The refraction buffer runs at half resolution: it's only ever read through a
  heavily distorted, dispersed lookup, so the detail is unrecoverable anyway.
- Scene B is skipped entirely while the transition is idle.
- Every damped value is corrected for real delta time (`lerpFPS`). Without it,
  every eased value moves at a different speed on a 144 Hz display — the most
  common bug in scroll-driven WebGL sites.
- `createRT` defaults to `depthBuffer: false` because most targets here are 2D
  simulation state. Scene targets must opt in, or occlusion silently falls back
  to draw order.
