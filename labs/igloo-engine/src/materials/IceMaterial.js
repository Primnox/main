import * as THREE from 'three';
import { common, easings, noise } from '../glsl/chunks.js';

/**
 * Screen-space refractive ice.
 *
 * three.js' built-in 'transmission' gives you one refracted sample and a fixed
 * IOR. igloo.inc replaces it wholesale, and this does the same, because the ice
 * look depends on three things three.js won't give you:
 *
 *  1. **Dispersion** — R/G/B refracted at *different* IORs, so edges fringe.
 *     Sampled over CA_ITERATIONS spectral taps, not 3, or the fringe banding is
 *     visible on any gradient.
 *  2. **Thickness-driven attenuation** — Beer-Lambert over an approximated path
 *     length, so thick parts of the mesh go deep blue and thin edges stay clear.
 *  3. **A frost coat** that is authored in *screen space* from the frost sim and
 *     blended into both roughness and scattering, rather than being a texture on
 *     the model.
 *
 * The mesh is rendered after the scene has been resolved into 'tScene', so it
 * refracts everything behind it including other ice.
 */
export class IceMaterial extends THREE.ShaderMaterial {
  constructor({
    envMap = null,
    sceneTexture = null,
    frostTexture = null,
    frostNormalTexture = null,
    detailTexture = null,
    blueNoise = null,
    fogColor = new THREE.Color(0.855, 0.875, 0.905),
    fogDensity = 0.0125,
  } = {}) {
    super({
      transparent: false,
      side: THREE.FrontSide,
      uniforms: {
        tScene: { value: sceneTexture },
        tEnv: { value: envMap },
        tFrost: { value: frostTexture },
        tFrostNormal: { value: frostNormalTexture },
        tDetail: { value: detailTexture },
        tBlue: { value: blueNoise },
        uBlueOffset: { value: new THREE.Vector2() },
        uBlueSize: { value: new THREE.Vector2(64, 64) },

        uResolution: { value: new THREE.Vector2(1, 1) },
        uTime: { value: 0 },

        uIor: { value: 1.31 },                                  // ice, not glass
        uDispersion: { value: 0.035 },
        uChromaticAberration: { value: 0.9 },
        uRefractionStrength: { value: 0.42 },

        // Against a white snowfield the blocks have to *absorb* to be visible at
        // all — a physically thin, clear slab would vanish. Short attenuation
        // distance with a saturated blue-grey tint gives the mid-grey body the
        // bright edges then read against.
        uThickness: { value: 1.05 },
        uAttenuationDistance: { value: 1.6 },
        uAttenuationColor: { value: new THREE.Color(0.46, 0.54, 0.62) },

        uRoughness: { value: 0.22 },
        uEnvIntensity: { value: 0.48 },
        uFresnelPower: { value: 2.8 },
        uReflectivity: { value: 0.45 },
        // The bright rim along every block edge is the single strongest cue in
        // the reference. It is a deliberate exaggeration, not physical Fresnel.
        uEdgeGlow: { value: 0.42 },
        uEdgeColor: { value: new THREE.Color(1.0, 1.0, 1.0) },
        // Internal cloudiness: ice is full of trapped air, so some of the
        // "transmitted" light is really forward scatter.
        uScatter: { value: 0.62 },
        uScatterColor: { value: new THREE.Color(0.80, 0.86, 0.94) },

        uFogColor: { value: fogColor.clone() },
        uFogDensity: { value: fogDensity },
        // Must match the softbox direction baked into the environment map, or
        // the hard specular lands somewhere the reflection says is dim.
        uSunDir: { value: new THREE.Vector3(-0.35, 0.72, 0.60).normalize() },

        // Per-block hover, pushed by each mesh's onBeforeRender. At 0 the block
        // is matte grey stone; at 1 it is blazing white ice. On the reference
        // this is the entire difference between the resting igloo and the
        // cluster under your cursor.
        uHover: { value: 0 },

        uFrostAmount: { value: 1.0 },
        uFrostColor: { value: new THREE.Color(0.86, 0.93, 1.0) },
        // Detail normals read as *frost crust* very quickly. Anything past ~0.15
        // stops looking like a solid with structure inside it and starts looking
        // like a rock, because the silhouette lighting goes high-frequency.
        uDetailScale: { value: 1.1 },
        uDetailStrength: { value: 0.12 },
      },

      vertexShader: /* glsl */ `
        varying vec3 vWorldPos;
        varying vec3 vWorldNormal;
        varying vec4 vScreenPos;
        varying vec2 vUv;

        void main() {
          vUv = uv;
          vec4 world = modelMatrix * vec4(position, 1.0);
          vWorldPos = world.xyz;
          // normalMatrix is view-space; we want world-space for env lookups.
          vWorldNormal = normalize(mat3(modelMatrix) * normal);

          vec4 clip = projectionMatrix * viewMatrix * world;
          vScreenPos = clip;
          gl_Position = clip;
        }
      `,

      fragmentShader: /* glsl */ `
        precision highp float;

        varying vec3 vWorldPos;
        varying vec3 vWorldNormal;
        varying vec4 vScreenPos;
        varying vec2 vUv;

        uniform sampler2D tScene;
        uniform sampler2D tEnv;
        uniform sampler2D tFrost;
        uniform sampler2D tFrostNormal;
        uniform sampler2D tDetail;
        uniform sampler2D tBlue;
        uniform vec2  uBlueOffset;
        uniform vec2  uBlueSize;

        uniform vec2  uResolution;
        uniform float uTime;

        uniform float uIor;
        uniform float uDispersion;
        uniform float uChromaticAberration;
        uniform float uRefractionStrength;

        uniform float uThickness;
        uniform float uAttenuationDistance;
        uniform vec3  uAttenuationColor;

        uniform float uRoughness;
        uniform float uEnvIntensity;
        uniform float uFresnelPower;
        uniform float uReflectivity;
        uniform float uEdgeGlow;
        uniform vec3  uEdgeColor;
        uniform float uScatter;
        uniform vec3  uScatterColor;
        uniform vec3  uFogColor;
        uniform float uFogDensity;
        uniform vec3  uSunDir;

        uniform float uHover;
        uniform float uFrostAmount;
        uniform vec3  uFrostColor;
        uniform float uDetailScale;
        uniform float uDetailStrength;

        #define CA_ITERATIONS 8

        ${common}
        ${easings}
        ${noise}

        vec2 equirectUv(vec3 dir) {
          return vec2(atan(dir.x, dir.z) / TAU + 0.5, asin(clamp(dir.y, -1.0, 1.0)) / PI + 0.5);
        }

        // Roughness -> mip bias. The env texture has a full mip chain, so a bias
        // is a cheap stand-in for a prefiltered radiance probe.
        vec3 sampleEnv(vec3 dir, float roughness) {
          float bias = roughness * 8.0;
          return texture2D(tEnv, equirectUv(normalize(dir)), bias).rgb;
        }

        // The baked noise tile stores a unit flow vector in GB; that reads
        // directly as a tangent-space normal without a separate normal map.
        vec3 detailSample(vec2 uv) {
          return vec3(texture2D(tDetail, uv).gb * 2.0 - 1.0, 1.0);
        }

        // Triplanar object-space detail normal: no UV seams on a deformed mesh.
        vec3 detailNormal(vec3 p, vec3 n) {
          vec3 blend = pow(abs(n), vec3(4.0));
          blend /= max(dot(blend, vec3(1.0)), 1e-4);
          vec3 sx = detailSample(p.yz * uDetailScale).zxy;
          vec3 sy = detailSample(p.zx * uDetailScale).yzx;
          vec3 sz = detailSample(p.xy * uDetailScale).xyz;
          return normalize(sx * blend.x + sy * blend.y + sz * blend.z);
        }

        void main() {
          vec2 screenUv = (vScreenPos.xy / vScreenPos.w) * 0.5 + 0.5;
          vec3 viewDir = normalize(vWorldPos - cameraPosition);
          vec3 N = normalize(vWorldNormal);

          // --- surface perturbation --------------------------------------
          vec3 detail = detailNormal(vWorldPos * 0.5, N);
          N = normalize(N + detail * uDetailStrength);

          // Frost is authored in screen space by the sim, then folded into the
          // surface normal so it distorts refraction as well as tinting.
          vec4 frost = texture2D(tFrost, screenUv);
          vec3 frostN = texture2D(tFrostNormal, screenUv).rgb * 2.0 - 1.0;
          float frostMask = saturate_(frost.r * uFrostAmount);
          N = normalize(N + frostN * frostMask * 0.55);

          float roughness = mix(uRoughness, 0.65, power1In(frostMask));
          float fresnel = pow(1.0 - saturate_(dot(-viewDir, N)), uFresnelPower);

          // --- dispersion ------------------------------------------------
          // Blue noise jitters the spectral sample position per pixel; without it
          // the finite tap count shows up as concentric colour rings on gradients.
          float jitter = texture2D(tBlue, gl_FragCoord.xy / uBlueSize + uBlueOffset).r;

          vec3 refracted = vec3(0.0);
          vec3 weightSum = vec3(0.0);

          for (int i = 0; i < CA_ITERATIONS; i++) {
            float t = (float(i) + jitter) / float(CA_ITERATIONS);

            // Spectral weights: a coarse but well-behaved RGB response curve.
            vec3 w = vec3(
              saturate_(1.5 - abs(t * 3.0 - 0.5)),
              saturate_(1.5 - abs(t * 3.0 - 1.5)),
              saturate_(1.5 - abs(t * 3.0 - 2.5))
            );

            float ior = uIor + (t - 0.5) * uDispersion * uChromaticAberration;
            vec3 dir = refract(viewDir, N, 1.0 / max(ior, 1.001));

            // Project the refracted ray back onto the screen. A full path trace
            // is overkill here: offsetting the screen UV by the ray's tangential
            // component is indistinguishable at this thickness and costs one tap.
            vec2 offset = dir.xy * uRefractionStrength * uThickness;
            offset.x /= max(uResolution.x / uResolution.y, 1e-4);

            refracted += w * texture2D(tScene, clamp(screenUv + offset, 0.001, 0.999)).rgb;
            weightSum += w;
          }
          refracted /= max(weightSum, vec3(1e-4));

          // --- volume absorption (Beer-Lambert) --------------------------
          // Grazing angles travel further through the solid, so path length
          // scales with 1/cos(theta) — that is what darkens the silhouette edge.
          float cosTheta = max(abs(dot(viewDir, N)), 0.15);
          float pathLength = uThickness / cosTheta;
          vec3 absorption = exp(-(vec3(1.0) - uAttenuationColor) * (pathLength / max(uAttenuationDistance, 1e-3)));
          refracted *= absorption;

          // --- hover state ------------------------------------------------
          // A resting block is near-opaque packed snow; a hovered one turns to
          // clear, blazing ice. Interpolating scatter as well as glow is what
          // sells the state change — glow alone just looks like a light moved.
          float hover = clamp(uHover, 0.0, 1.0);
          float scatter = clamp(mix(uScatter * 2.6, uScatter, hover), 0.0, 1.0);
          float envIntensity = uEnvIntensity * mix(0.55, 1.35, hover);
          float edgeGlow = uEdgeGlow * mix(0.55, 3.4, hover);

          // --- internal scatter ------------------------------------------
          // Trapped air makes ice cloudy. Blending toward a very rough env
          // sample is a cheap stand-in for multiple scattering and is what
          // stops the blocks reading as clean glass.
          vec3 cloud = sampleEnv(N, 0.95) * uScatterColor;
          refracted = mix(refracted, cloud, scatter);

          // --- reflection ------------------------------------------------
          vec3 reflected = sampleEnv(reflect(viewDir, N), roughness) * envIntensity;

          vec3 color = mix(refracted, reflected, saturate_(fresnel * uReflectivity + 0.04));

          // --- frost coat ------------------------------------------------
          // Frost scatters rather than refracts: lerp toward a rough env sample
          // tinted white, and let the sim's rim channel light the growing edge.
          if (frostMask > 0.001) {
            vec3 frostScatter = sampleEnv(N, 0.9) * uFrostColor;
            color = mix(color, frostScatter, power1Out(frostMask) * 0.85);
            color += uFrostColor * saturate_(frost.b) * 0.6;
          }

          // --- specular ---------------------------------------------------
          // One explicit sun highlight on top of the env reflection. The
          // prefiltered environment alone is too soft to survive the fog, and
          // without a hard glint the blocks look matte.
          vec3 H = normalize(uSunDir - viewDir);
          float spec = pow(max(dot(N, H), 0.0), mix(220.0, 24.0, roughness));
          color += vec3(1.0) * spec * 0.9;

          // --- edge glow --------------------------------------------------
          // Every block in the reference is outlined in bright white. Physically
          // this is total internal reflection piping light along the bevel; a
          // sharpened Fresnel term reproduces it for a fraction of the cost.
          // Two lobes: a wide soft halo and a tight bright line right at the
          // silhouette, which is what actually separates block from block.
          float edgeSoft = pow(fresnel, 1.4);
          float edgeHard = pow(fresnel, 5.0);
          color += uEdgeColor * (edgeSoft * 0.35 + edgeHard * 1.6) * edgeGlow;

          float dist = length(vWorldPos - cameraPosition);
          float fogFactor = 1.0 - exp(-dist * dist * uFogDensity * uFogDensity);
          color = mix(color, uFogColor, saturate_(fogFactor));

          gl_FragColor = vec4(color, 1.0);
        }
      `,
    });
  }

  setSize(width, height) {
    this.uniforms.uResolution.value.set(width, height);
  }

  update(time, blueNoiseOffset) {
    this.uniforms.uTime.value = time;
    this.uniforms.uBlueOffset.value.copy(blueNoiseOffset);
  }
}
