import{A as e,C as t,D as n,E as r,F as i,M as a,N as o,O as s,P as c,S as l,T as u,_ as d,a as f,b as p,c as m,d as h,f as g,g as _,h as v,i as y,j as b,k as x,l as S,m as C,n as ee,o as w,p as T,r as E,s as te,t as D,u as O,v as ne,w as k,x as re,y as ie}from"./App3D-CwN3mH59.js";(function(){let e=document.createElement(`link`).relList;if(e&&e.supports&&e.supports(`modulepreload`))return;for(let e of document.querySelectorAll(`link[rel="modulepreload"]`))n(e);new MutationObserver(e=>{for(let t of e)if(t.type===`childList`)for(let e of t.addedNodes)e.tagName===`LINK`&&e.rel===`modulepreload`&&n(e)}).observe(document,{childList:!0,subtree:!0});function t(e){let t={};return e.integrity&&(t.integrity=e.integrity),e.referrerPolicy&&(t.referrerPolicy=e.referrerPolicy),t.credentials=e.crossOrigin===`use-credentials`?`include`:e.crossOrigin===`anonymous`?`omit`:`same-origin`,t}function n(e){if(e.ep)return;e.ep=!0;let n=t(e);fetch(e.href,n)}})();var ae=new y;ae.setAttribute(`position`,new E(new Float32Array([-1,-1,0,3,-1,0,-1,3,0]),3)),ae.setAttribute(`uv`,new E(new Float32Array([0,0,2,0,0,2]),2));var oe=`
  varying vec2 vUv;
  void main() {
    vUv = uv;
    gl_Position = vec4(position.xy, 0.0, 1.0);
  }
`,se=new ie(-1,1,1,-1,0,1),A=class{constructor(e){this.material=new x({vertexShader:oe,depthTest:!1,depthWrite:!1,...e}),this.mesh=new _(ae,this.material),this.mesh.frustumCulled=!1,this.scene=new s,this.scene.add(this.mesh)}get uniforms(){return this.material.uniforms}render(e,t=null){let n=e.getRenderTarget();return e.setRenderTarget(t),e.render(this.scene,se),e.setRenderTarget(n),t}dispose(){this.material.dispose()}},ce={depthBuffer:!1,stencilBuffer:!1,type:T,format:k,minFilter:C,magFilter:C,wrapS:w,wrapT:w,generateMipmaps:!1};function j(e,t,n={}){let r=new i(Math.max(1,e|0),Math.max(1,t|0),{...ce,...n});return r.texture.colorSpace=``,r}var le=class{constructor(e,t,n={}){this.a=j(e,t,n),this.b=j(e,t,n),this.options=n,this.width=e,this.height=t}get read(){return this.a}get write(){return this.b}swap(){let e=this.a;this.a=this.b,this.b=e}setSize(e,t){(e!==this.width||t!==this.height)&&(this.width=e,this.height=t,this.a.setSize(e,t),this.b.setSize(e,t))}clear(e,t=new m(0,0,0),n=1){let r=e.getRenderTarget(),i=new m,a=e.getClearAlpha();e.getClearColor(i),e.setClearColor(t,n);for(let t of[this.a,this.b])e.setRenderTarget(t),e.clear(!0,!1,!1);e.setRenderTarget(r),e.setClearColor(i,a)}dispose(){this.a.dispose(),this.b.dispose()}};function M(e,t,n,r){return e+(t-e)*(1-(1-n)**(r*60))}var ue=class{constructor(e=0,t=.1){this.value=e,this.target=e,this.coef=t,this.velocity=0}set(e){return this.value=this.target=e,this.velocity=0,this}update(e){let t=this.value;return this.value=M(this.value,this.target,this.coef,e),this.velocity=e>0?(this.value-t)/e:0,this.value}},de=class{constructor(e,{smoothing:t=.35}={}){this.element=e,this.smoothing=t,this.x=.5,this.y=.5,this.px=.5,this.py=.5,this.speed=0,this.active=!1,this.down=!1,this._tx=.5,this._ty=.5,this._idle=0,this._onMove=e=>{let t=this.element.getBoundingClientRect();this._tx=(e.clientX-t.left)/t.width,this._ty=1-(e.clientY-t.top)/t.height,this.active=!0,this._idle=0},this._onLeave=()=>{this.active=!1},this._onDown=()=>{this.down=!0},this._onUp=()=>{this.down=!1},window.addEventListener(`pointermove`,this._onMove,{passive:!0}),window.addEventListener(`pointerdown`,this._onDown,{passive:!0}),window.addEventListener(`pointerup`,this._onUp,{passive:!0}),window.addEventListener(`pointerleave`,this._onLeave,{passive:!0})}update(e){this.px=this.x,this.py=this.y,this.x=M(this.x,this._tx,this.smoothing,e),this.y=M(this.y,this._ty,this.smoothing,e);let t=this.x-this.px,n=this.y-this.py;this.speed=Math.hypot(t,n),this._idle+=e,this.speed<1e-4&&this._idle>.4?this.active=!1:this.speed>=1e-4&&(this.active=!0,this._idle=0)}dispose(){window.removeEventListener(`pointermove`,this._onMove),window.removeEventListener(`pointerdown`,this._onDown),window.removeEventListener(`pointerup`,this._onUp),window.removeEventListener(`pointerleave`,this._onLeave)}},N=`
  #ifndef PI
  #define PI  3.141592653589793
  #define TAU 6.283185307179586
  #endif

  float saturate_(float x) { return clamp(x, 0.0, 1.0); }
  vec3  saturate_(vec3 x)  { return clamp(x, vec3(0.0), vec3(1.0)); }

  // Remap v from [a,b] into [c,d], clamped.
  float fit(float v, float a, float b, float c, float d) {
    return c + (d - c) * saturate_((v - a) / (b - a));
  }
  float fit01(float v, float c, float d) { return fit(v, 0.0, 1.0, c, d); }
  float linearstep(float a, float b, float v) { return saturate_((v - a) / (b - a)); }

  /**
   * Soft directional wipe.
   *
   * Sweeps a threshold from below 'lo' to above 'hi' as 'progress' goes 0 -> 1,
   * with 'softness' controlling the width of the gradient edge. Returns 0 for
   * "not yet reached", 1 for "fully past". Larger softness = blurrier front.
   */
  float falloff(float v, float lo, float hi, float softness, float progress) {
    float threshold = mix(lo - softness, hi + softness, progress);
    return saturate_((threshold - v) / max(softness, 1e-4));
  }

  float luma(vec3 c) { return dot(c, vec3(0.2126, 0.7152, 0.0722)); }

  vec2 rotateUV(vec2 uv, float a, vec2 pivot) {
    float s = sin(a), c = cos(a);
    uv -= pivot;
    uv = mat2(c, -s, s, c) * uv;
    return uv + pivot;
  }
  vec2 scaleUV(vec2 uv, vec2 s, vec2 pivot) { return (uv - pivot) / s + pivot; }

  // Cover-fit a texture into a viewport of a given aspect (CSS background-size: cover).
  vec2 coverUV(vec2 uv, float viewAspect, float texAspect) {
    vec2 s = viewAspect > texAspect
      ? vec2(1.0, texAspect / viewAspect)
      : vec2(viewAspect / texAspect, 1.0);
    return (uv - 0.5) * s + 0.5;
  }
`,P=`
  float power1In(float t)  { return t * t; }
  float power1Out(float t) { return 1.0 - (1.0 - t) * (1.0 - t); }
  float power2In(float t)  { return t * t * t; }
  float power2Out(float t) { float f = 1.0 - t; return 1.0 - f * f * f; }
  float power3In(float t)  { return t * t * t * t; }
  float power3Out(float t) { float f = 1.0 - t; return 1.0 - f * f * f * f; }
  float power4In(float t)  { return t * t * t * t * t; }
  float power4Out(float t) { float f = 1.0 - t; return 1.0 - f * f * f * f * f; }
  float sineIn(float t)    { return 1.0 - cos(t * PI * 0.5); }
  float sineOut(float t)   { return sin(t * PI * 0.5); }
  float sineInOut(float t) { return -0.5 * (cos(PI * t) - 1.0); }
  float expoOut(float t)   { return t >= 1.0 ? 1.0 : 1.0 - pow(2.0, -10.0 * t); }
  float backOut(float t)   { float f = t - 1.0; return f * f * (2.70158 * f + 1.70158) + 1.0; }
  float circularOut(float t) { return sqrt((2.0 - t) * t); }
  float cubicInOut(float t) {
    return t < 0.5 ? 4.0 * t * t * t : 0.5 * pow(2.0 * t - 2.0, 3.0) + 1.0;
  }
`,F=`
  float hash11(float p) {
    p = fract(p * 0.1031);
    p *= p + 33.33;
    return fract(p * (p + p));
  }
  float hash12(vec2 p) {
    vec3 p3 = fract(vec3(p.xyx) * 0.1031);
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.x + p3.y) * p3.z);
  }
  vec2 hash22(vec2 p) {
    vec3 p3 = fract(vec3(p.xyx) * vec3(0.1031, 0.1030, 0.0973));
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.xx + p3.yz) * p3.zy);
  }
  vec3 hash33(vec3 p) {
    p = fract(p * vec3(0.1031, 0.1030, 0.0973));
    p += dot(p, p.yxz + 33.33);
    return fract((p.xxy + p.yxx) * p.zyx);
  }

  // Ashima / Gustavson simplex noise (public domain).
  vec3 mod289(vec3 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
  vec4 mod289(vec4 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
  vec4 permute(vec4 x) { return mod289(((x * 34.0) + 1.0) * x); }
  vec4 taylorInvSqrt(vec4 r) { return 1.79284291400159 - 0.85373472095314 * r; }

  float snoise(vec3 v) {
    const vec2 C = vec2(1.0 / 6.0, 1.0 / 3.0);
    const vec4 D = vec4(0.0, 0.5, 1.0, 2.0);
    vec3 i  = floor(v + dot(v, C.yyy));
    vec3 x0 = v - i + dot(i, C.xxx);
    vec3 g = step(x0.yzx, x0.xyz);
    vec3 l = 1.0 - g;
    vec3 i1 = min(g.xyz, l.zxy);
    vec3 i2 = max(g.xyz, l.zxy);
    vec3 x1 = x0 - i1 + C.xxx;
    vec3 x2 = x0 - i2 + C.yyy;
    vec3 x3 = x0 - D.yyy;
    i = mod289(i);
    vec4 p = permute(permute(permute(
               i.z + vec4(0.0, i1.z, i2.z, 1.0))
             + i.y + vec4(0.0, i1.y, i2.y, 1.0))
             + i.x + vec4(0.0, i1.x, i2.x, 1.0));
    float n_ = 0.142857142857;
    vec3 ns = n_ * D.wyz - D.xzx;
    vec4 j = p - 49.0 * floor(p * ns.z * ns.z);
    vec4 x_ = floor(j * ns.z);
    vec4 y_ = floor(j - 7.0 * x_);
    vec4 x = x_ * ns.x + ns.yyyy;
    vec4 y = y_ * ns.x + ns.yyyy;
    vec4 h = 1.0 - abs(x) - abs(y);
    vec4 b0 = vec4(x.xy, y.xy);
    vec4 b1 = vec4(x.zw, y.zw);
    vec4 s0 = floor(b0) * 2.0 + 1.0;
    vec4 s1 = floor(b1) * 2.0 + 1.0;
    vec4 sh = -step(h, vec4(0.0));
    vec4 a0 = b0.xzyw + s0.xzyw * sh.xxyy;
    vec4 a1 = b1.xzyw + s1.xzyw * sh.zzww;
    vec3 p0 = vec3(a0.xy, h.x);
    vec3 p1 = vec3(a0.zw, h.y);
    vec3 p2 = vec3(a1.xy, h.z);
    vec3 p3 = vec3(a1.zw, h.w);
    vec4 norm = taylorInvSqrt(vec4(dot(p0, p0), dot(p1, p1), dot(p2, p2), dot(p3, p3)));
    p0 *= norm.x; p1 *= norm.y; p2 *= norm.z; p3 *= norm.w;
    vec4 m = max(0.6 - vec4(dot(x0, x0), dot(x1, x1), dot(x2, x2), dot(x3, x3)), 0.0);
    m = m * m;
    return 42.0 * dot(m * m, vec4(dot(p0, x0), dot(p1, x1), dot(p2, x2), dot(p3, x3)));
  }

  float fbm(vec3 p, int octaves, float lacunarity, float gain) {
    float sum = 0.0, amp = 0.5, norm = 0.0;
    for (int i = 0; i < 8; i++) {
      if (i >= octaves) break;
      sum  += amp * snoise(p);
      norm += amp;
      p    *= lacunarity;
      amp  *= gain;
    }
    return sum / max(norm, 1e-4);
  }

  // Divergence-free flow field. Used to advect the frost/particle buffers.
  vec3 curlNoise(vec3 p) {
    const float e = 0.1;
    float x1 = snoise(p + vec3(0.0, e, 0.0)) - snoise(p - vec3(0.0, e, 0.0));
    float x2 = snoise(p + vec3(0.0, 0.0, e)) - snoise(p - vec3(0.0, 0.0, e));
    float y1 = snoise(p + vec3(0.0, 0.0, e)) - snoise(p - vec3(0.0, 0.0, e));
    float y2 = snoise(p + vec3(e, 0.0, 0.0)) - snoise(p - vec3(e, 0.0, 0.0));
    float z1 = snoise(p + vec3(e, 0.0, 0.0)) - snoise(p - vec3(e, 0.0, 0.0));
    float z2 = snoise(p + vec3(0.0, e, 0.0)) - snoise(p - vec3(0.0, e, 0.0));
    return normalize(vec3(x1 - x2, y1 - y2, z1 - z2) / (2.0 * e));
  }
`,fe=`
  uniform sampler2D tBlue;
  uniform vec2 uBlueOffset;   // per-frame jitter, in tiles
  uniform vec2 uBlueSize;     // blue noise texture dimensions

  vec4 getNoise(sampler2D tex, vec2 fragCoord, vec2 offset) {
    return texture2D(tex, (fragCoord / uBlueSize) + offset);
  }
  vec4 blueNoise4(vec2 fragCoord) { return getNoise(tBlue, fragCoord, uBlueOffset); }
`,pe=`
  #ifndef CA_ITERATIONS
  #define CA_ITERATIONS 5
  #endif

  vec2 ca_barrelDistortion(vec2 coord, float amt) {
    vec2 cc = coord - 0.5;
    return coord + 2.0 * cc * amt * dot(cc, cc);
  }
  // Map a normalized spectral position to an RGB weight (approx. visible spectrum).
  vec3 ca_spectrumOffset(float t) {
    float lo = step(t, 0.5);
    float hi = 1.0 - lo;
    float w = (1.0 - abs(2.0 * t - 1.0));
    return vec3(lo, 1.0, hi) * vec3(1.0 - w, w, 1.0 - w);
  }

  vec4 chromatic_aberration(sampler2D tex, vec2 uv, float modulator, float strength) {
    if (strength <= 0.0) return texture2D(tex, uv);

    vec3 sumCol = vec3(0.0);
    vec3 sumWeight = vec3(0.0);
    float alpha = 0.0;
    float amount = strength * modulator * 0.002;

    for (int i = 0; i < CA_ITERATIONS; ++i) {
      float t = (float(i) + 0.5) / float(CA_ITERATIONS);
      vec3 w = ca_spectrumOffset(t);
      sumWeight += w;
      vec4 s = texture2D(tex, ca_barrelDistortion(uv, amount * t));
      sumCol += w * s.rgb;
      alpha += s.a;
    }
    return vec4(sumCol / max(sumWeight, vec3(1e-4)), alpha / float(CA_ITERATIONS));
  }
`,me=`
  vec3 lutLookup(sampler2D tex, vec3 rgb, float size) {
    float sliceSize = 1.0 / size;
    float slicePixelSize = sliceSize / size;
    float sliceInnerSize = slicePixelSize * (size - 1.0);
    float zSlice0 = floor(rgb.b * (size - 1.0));
    float zOffset = fract(rgb.b * (size - 1.0));

    vec2 uv0 = vec2(
      zSlice0 * sliceSize + slicePixelSize * 0.5 + rgb.r * sliceInnerSize,
      1.0 - (slicePixelSize * 0.5 + rgb.g * (1.0 - slicePixelSize))
    );
    vec2 uv1 = uv0 + vec2(sliceSize, 0.0);
    return mix(texture2D(tex, uv0).rgb, texture2D(tex, uv1).rgb, zOffset);
  }

  vec3 apply3DLUT(sampler2D tex, vec3 color, float size, float intensity) {
    return mix(color, lutLookup(tex, clamp(color, 0.0, 1.0), size), intensity);
  }
`,he=`
  float median3(vec3 v) { return max(min(v.r, v.g), min(max(v.r, v.g), v.b)); }

  // 'range' is the distance field spread in texels; screen-space derivative gives
  // resolution-independent antialiasing at any scale.
  float sdfAlpha(vec3 sample_, float range, float weight) {
    float sd = median3(sample_) - 0.5 + weight;
    float w = max(fwidth(sd), 1e-5);
    return clamp(sd / w + 0.5, 0.0, 1.0);
  }
`,ge=`
  vec3 dither8(vec3 color, vec2 fragCoord, float amount) {
    float g = hash12(fragCoord + fract(color.rg) * 13.7);
    return color + (g - 0.5) * amount;
  }
`;function _e(e,t){let n=e*e,r=1.9,i=new Float32Array(121);for(let e=-5;e<=5;e++)for(let t=-5;t<=5;t++)i[(e+5)*11+(t+5)]=Math.exp(-(t*t+e*e)/(2*r*r));let a=new Float32Array(n),o=new Uint8Array(n),s=(t,n)=>{let r=t%e,o=t/e|0;for(let t=-5;t<=5;t++){let s=(o+t+e)%e;for(let o=-5;o<=5;o++){let c=(r+o+e)%e;a[s*e+c]+=n*i[(t+5)*11+(o+5)]}}},c=()=>{let e=-1,t=-1/0;for(let r=0;r<n;r++)o[r]&&a[r]>t&&(t=a[r],e=r);return e},l=()=>{let e=-1,t=1/0;for(let r=0;r<n;r++)!o[r]&&a[r]<t&&(t=a[r],e=r);return e},u=Math.max(1,Math.round(n/10)),d=0;for(;d<u;){let e=t()*n|0;o[e]||(o[e]=1,s(e,1),d++)}for(let e=0;e<n*4;e++){let e=c();o[e]=0,s(e,-1);let t=l();if(t===e){o[e]=1,s(e,1);break}o[t]=1,s(t,1)}let f=new Int32Array(n).fill(-1),p=Uint8Array.from(o);for(let e=u-1;e>=0;e--){let t=c();o[t]=0,s(t,-1),f[t]=e}o.set(p),a.fill(0);for(let e=0;e<n;e++)o[e]&&s(e,1);for(let e=u;e<n;e++){let t=l();if(t<0)break;o[t]=1,s(t,1),f[t]=e}let m=new Float32Array(n);for(let e=0;e<n;e++)m[e]=Math.max(0,f[e])/n;return m}function ve(e){let t=e>>>0;return()=>{t=t+1831565813>>>0;let e=Math.imul(t^t>>>15,1|t);return e=e+Math.imul(e^e>>>7,61|e)^e,((e^e>>>14)>>>0)/4294967296}}function ye(e=64){let t=new Uint8Array(e*e*4);for(let n=0;n<4;n++){let r=_e(e,ve(2654435769+n*7919));for(let i=0;i<e*e;i++)t[i*4+n]=Math.min(255,r[i]*256|0)}let n=new S(t,e,e,k);return n.wrapS=n.wrapT=r,n.minFilter=n.magFilter=ne,n.needsUpdate=!0,n.userData.size=e,n}var be=(e,t)=>e+((e<.5?4*e*e*e:1-(-2*e+2)**3/2)-e)*t;function xe(e=32){let t=e*e,n=new Uint8Array(t*e*4);for(let r=0;r<e;r++)for(let i=0;i<e;i++)for(let a=0;a<e;a++){let o=a/(e-1),s=i/(e-1),c=r/(e-1),l=.2126*o+.7152*s+.0722*c,u=(1-l)**2,d=l**2;o+=u*-.02+d*.03,s+=u*.006+d*.018,c+=u*.055+d*-.01,o=be(o,.28),s=be(s,.28),c=be(c,.28);let f=.2126*o+.7152*s+.0722*c,p=.88;o=f+(o-f)*p,s=f+(s-f)*p,c=f+(c-f)*p*1.12;let m=r*e+a,h=((e-1-i)*t+m)*4;n[h+0]=Math.max(0,Math.min(255,Math.round(o*255))),n[h+1]=Math.max(0,Math.min(255,Math.round(s*255))),n[h+2]=Math.max(0,Math.min(255,Math.round(c*255))),n[h+3]=255}let r=new S(n,t,e,k);return r.wrapS=r.wrapT=w,r.minFilter=r.magFilter=C,r.needsUpdate=!0,r.userData.size=e,r}var Se=`
  float vhash(vec2 p, float period) {
    p = mod(p, period);
    return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123);
  }
  float tileNoise(vec2 p, float period) {
    vec2 i = floor(p), f = fract(p);
    vec2 u = f * f * (3.0 - 2.0 * f);
    float a = vhash(i + vec2(0.0, 0.0), period);
    float b = vhash(i + vec2(1.0, 0.0), period);
    float c = vhash(i + vec2(0.0, 1.0), period);
    float d = vhash(i + vec2(1.0, 1.0), period);
    return mix(mix(a, b, u.x), mix(c, d, u.x), u.y);
  }
  float tileFbm(vec2 p, float period, int octaves) {
    float sum = 0.0, amp = 0.5, norm = 0.0, per = period;
    for (int i = 0; i < 6; i++) {
      if (i >= octaves) break;
      sum += amp * tileNoise(p, per);
      norm += amp;
      p *= 2.0; per *= 2.0; amp *= 0.5;
    }
    return sum / norm;
  }
`;function Ce(e,t=256){let n=j(t,t,{type:a});n.texture.wrapS=n.texture.wrapT=r;let i=new A({uniforms:{uPeriod:{value:8}},fragmentShader:`
      precision highp float;
      varying vec2 vUv;
      uniform float uPeriod;
      ${Se}
      void main() {
        vec2 p = vUv * uPeriod;
        float base = tileFbm(p, uPeriod, 5);
        // Finite-difference gradient of a second field -> a divergence-light flow.
        float e = 1.0 / 256.0;
        float nx = tileFbm(p + vec2(e, 0.0) * uPeriod, uPeriod, 3) - tileFbm(p - vec2(e, 0.0) * uPeriod, uPeriod, 3);
        float ny = tileFbm(p + vec2(0.0, e) * uPeriod, uPeriod, 3) - tileFbm(p - vec2(0.0, e) * uPeriod, uPeriod, 3);
        vec2 flow = normalize(vec2(ny, -nx) + 1e-5) * 0.5 + 0.5;
        float ridged = 1.0 - abs(tileFbm(p * 2.0, uPeriod * 2.0, 4) * 2.0 - 1.0);
        gl_FragColor = vec4(base, flow.x, flow.y, ridged);
      }
    `});return i.render(e,n),i.dispose(),n.texture}function we(e,t=512){let n=j(t,t,{type:a});n.texture.wrapS=n.texture.wrapT=r;let i=new A({uniforms:{uPeriod:{value:6}},fragmentShader:`
      precision highp float;
      varying vec2 vUv;
      uniform float uPeriod;
      ${Se}
      void main() {
        vec2 p = vUv * uPeriod;
        float a = tileFbm(p, uPeriod, 4) * 2.0 - 1.0;
        float b = tileFbm(p + vec2(3.7, 1.3), uPeriod, 4) * 2.0 - 1.0;
        float ridgeA = pow(1.0 - abs(a), 12.0);
        float ridgeB = pow(1.0 - abs(b), 12.0);
        float c = clamp(ridgeA + ridgeB * 0.7, 0.0, 1.0);
        gl_FragColor = vec4(vec3(c), 1.0);
      }
    `});return i.render(e,n),i.dispose(),n.texture}function Te(e,t=1024){let n=t/2,a=new i(t,n,{depthBuffer:!1,stencilBuffer:!1,type:T,minFilter:v,magFilter:C,wrapS:r,wrapT:w,generateMipmaps:!0});a.texture.colorSpace=``,a.texture.mapping=303;let o=new A({uniforms:{},fragmentShader:`
      precision highp float;
      varying vec2 vUv;
      ${N}

      // Rectangular area light: angular distance to a box lobe, so the highlight
      // has a straight edge instead of the round blob a dot-power gives.
      float softbox(vec3 d, vec3 dir, vec2 halfAngle, float sharpness) {
        vec3 f = normalize(dir);
        vec3 r = normalize(cross(vec3(0.0, 1.0, 0.0), f) + vec3(1e-4));
        vec3 u = cross(f, r);
        float fwd = dot(d, f);
        if (fwd <= 0.0) return 0.0;
        vec2 local = vec2(dot(d, r), dot(d, u)) / fwd;
        vec2 q = abs(local) - halfAngle;
        float dist = length(max(q, 0.0)) + min(max(q.x, q.y), 0.0);
        return pow(saturate_(1.0 - dist * sharpness), 3.0) * step(0.0, fwd);
      }

      void main() {
        // Equirect: u -> azimuth, v -> elevation.
        float phi = (vUv.x - 0.5) * TAU;
        float theta = (vUv.y - 0.5) * PI;
        vec3 d = vec3(cos(theta) * sin(phi), sin(theta), cos(theta) * cos(phi));

        // Overcast polar daylight: a bright, almost uniform dome. This is the
        // whole reason the reference reads as snow — an HDRI with strong dark
        // regions would put black in every reflection and kill the high key.
        float h = d.y * 0.5 + 0.5;
        vec3 ground = vec3(0.72, 0.75, 0.80);
        vec3 horizon = vec3(0.86, 0.89, 0.93);
        vec3 zenith = vec3(1.05, 1.08, 1.14);
        vec3 col = mix(ground, horizon, smoothstep(0.30, 0.52, h));
        col = mix(col, zenith, smoothstep(0.5, 1.0, h));

        // Diffuse sun disc behind cloud: a broad, soft, barely-warm lobe. Ice
        // still needs one bright anchor or the specular streaks disappear.
        col += vec3(1.6, 1.58, 1.5) * softbox(d, vec3(-0.35, 0.72, 0.60), vec2(0.30, 0.22), 2.2);
        col += vec3(0.35, 0.38, 0.45) * softbox(d, vec3(0.9, 0.15, -0.4), vec2(0.5, 0.4), 1.6);

        gl_FragColor = vec4(col, 1.0);
      }
    `});return o.render(e,a),o.dispose(),a.texture}var I=0x56bc75e2d63100000;function Ee(e,t,n){let r=r=>{let i=new Float32Array(t*n),a=new Float32Array(t*n);for(let o=0;o<t*n;o++)(r?e[o]:!e[o])?(i[o]=0,a[o]=0):(i[o]=I,a[o]=I);return{dx:i,dy:a}},i=({dx:e,dy:r})=>{let i=t=>e[t]===I?I:e[t]*e[t]+r[t]*r[t],a=(a,o,s,c,l)=>{let u=c+o,d=l+s;if(u<0||d<0||u>=t||d>=n)return;let f=d*t+u;if(e[f]===I)return;let p=e[f]-o,m=r[f]-s;p*p+m*m<i(a)&&(e[a]=p,r[a]=m)};for(let e=0;e<n;e++){for(let n=0;n<t;n++){let r=e*t+n;a(r,0,-1,n,e),a(r,-1,0,n,e),a(r,-1,-1,n,e),a(r,1,-1,n,e)}for(let n=t-2;n>=0;n--)a(e*t+n,1,0,n,e)}for(let e=n-1;e>=0;e--){for(let n=t-1;n>=0;n--){let r=e*t+n;a(r,0,1,n,e),a(r,1,0,n,e),a(r,1,1,n,e),a(r,-1,1,n,e)}for(let n=1;n<t;n++)a(e*t+n,-1,0,n,e)}},a=r(!0),o=r(!1);i(a),i(o);let s=new Float32Array(t*n);for(let e=0;e<t*n;e++){let t=a.dx[e]===I?I:Math.hypot(a.dx[e],a.dy[e]),n=o.dx[e]===I?I:Math.hypot(o.dx[e],o.dy[e]);s[e]=(n===I?0:n)-(t===I?0:t)}return s}var De=` !"#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_\`abcdefghijklmnopqrstuvwxyz{|}~`;function Oe({family:e=`system-ui, sans-serif`,weight:t=600,charset:n=De,em:r=48,padding:i=10,distanceRange:a=8,columns:o=16}={}){let s=Math.ceil(r*1.7)+i*2,c=Math.ceil(n.length/o),l=o*s,u=c*s,d=document.createElement(`canvas`);d.width=l,d.height=u;let f=d.getContext(`2d`,{willReadFrequently:!0});f.font=`${t} ${r}px ${e}`,f.textBaseline=`alphabetic`,f.fillStyle=`#fff`;let p={},m=new Uint8Array(l*u*4);n.split(``).forEach((e,t)=>{let n=t%o,c=Math.floor(t/o),u=n*s,d=c*s,h=f.measureText(e),g=h.width/r;if(e.trim().length===0){p[e]={unicode:e.codePointAt(0),advance:g,isWhitespace:!0,planeBounds:{left:0,right:0,top:0,bottom:0},atlasBounds:{left:0,right:0,top:0,bottom:0}};return}let _=h.actualBoundingBoxLeft??0,v=h.actualBoundingBoxRight??h.width,y=h.actualBoundingBoxAscent??r*.8,b=h.actualBoundingBoxDescent??r*.2;f.clearRect(u,d,s,s),f.fillText(e,u+i+_,d+i+y);let x=f.getImageData(u,d,s,s).data,S=new Uint8Array(s*s);for(let e=0;e<s*s;e++)S[e]=+(x[e*4+3]>127);let C=Ee(S,s,s);for(let e=0;e<s;e++)for(let t=0;t<s;t++){let n=Math.max(0,Math.min(255,Math.round((C[e*s+t]/a+.5)*255))),r=((d+e)*l+(u+t))*4;m[r]=m[r+1]=m[r+2]=n,m[r+3]=255}let ee=_+v,w=y+b;p[e]={unicode:e.codePointAt(0),advance:g,isWhitespace:!1,planeBounds:{left:(-_-i)/r,right:(v+i)/r,top:(y+i)/r,bottom:(-b-i)/r},atlasBounds:{left:u,right:u+ee+i*2,top:d,bottom:d+w+i*2}}});let h=new S(m,l,u,k);return h.minFilter=C,h.magFilter=C,h.generateMipmaps=!1,h.flipY=!1,h.colorSpace=``,h.needsUpdate=!0,{texture:h,font:{metrics:{lineHeight:1},atlas:{width:l,height:u,distanceRange:a},glyphs:p,kerning:[],placeholderChar:`?`}}}var ke=class{constructor(e,{resolution:t=512,advectTexture:n=null}={}){this.renderer=e,this.resolution=t,this.buffer=new le(t,t,{type:T}),this.buffer.clear(e,new m(0,0,0),1),this.step=new A({uniforms:{tBuffer:{value:null},tAdvect:{value:n},uTexel:{value:new o(1/t,1/t)},uSplatCoords:{value:new o(-1,-1)},uSplatPrevCoords:{value:new o(-1,-1)},uSplatRadius:{value:0},uAdvectStrength:{value:1.6},uWaveSpeed:{value:1},uDamping:{value:.985},uAspect:{value:1},uTime:{value:0}},fragmentShader:`
        precision highp float;
        varying vec2 vUv;

        uniform sampler2D tBuffer;
        uniform sampler2D tAdvect;
        uniform vec2  uTexel;
        uniform vec2  uSplatCoords;
        uniform vec2  uSplatPrevCoords;
        uniform float uSplatRadius;
        uniform float uAdvectStrength;
        uniform float uWaveSpeed;
        uniform float uDamping;
        uniform float uAspect;
        uniform float uTime;

        ${N}
        ${P}

        // Distance from uv to the segment [a,b], aspect-corrected so the brush
        // stays circular on a non-square viewport.
        float segmentDistance(vec2 uv, vec2 a, vec2 b) {
          vec2 pa = uv - a, ba = b - a;
          pa.x *= uAspect;
          ba.x *= uAspect;
          float h = clamp(dot(pa, ba) / max(dot(ba, ba), 1e-6), 0.0, 1.0);
          return length(pa - ba * h);
        }

        void main() {
          vec2 uv = vUv;

          // Advect the sampling position along a slowly drifting noise field.
          vec2 flow = texture2D(tAdvect, uv * 3.0 + vec2(uTime * 0.01, -uTime * 0.013)).gb * 2.0 - 1.0;
          uv += flow * uTexel * uAdvectStrength;

          // Dilate: the frost front only ever advances.
          vec2 o = uTexel * uWaveSpeed;
          float l = texture2D(tBuffer, uv - vec2(o.x, 0.0)).r;
          float r = texture2D(tBuffer, uv + vec2(o.x, 0.0)).r;
          float t = texture2D(tBuffer, uv + vec2(0.0, o.y)).r;
          float b = texture2D(tBuffer, uv - vec2(0.0, o.y)).r;
          float next = max(max(l, r), max(t, b));

          // Pointer splat as a capsule, so fast mouse movement leaves an unbroken
          // stroke instead of a dotted line at low framerates.
          float radius = 0.075 * smoothstep(0.0, 0.8, uSplatRadius);
          if (radius > 0.0) {
            float d = segmentDistance(vUv, uSplatPrevCoords, uSplatCoords);
            next += power2In(clamp(1.0 - d / radius, 0.0, 1.0));
          }

          next = min(next * uDamping, 1.0);

          vec4 prev = texture2D(tBuffer, uv);
          float rim = next - prev.r;
          float rimSmooth = (prev.b + rim) * 0.9;

          gl_FragColor = vec4(next, rim, rimSmooth, 1.0);
        }
      `}),this.normalRT=new i(t,t,{depthBuffer:!1,stencilBuffer:!1,type:T,minFilter:C,magFilter:C}),this.normalRT.texture.colorSpace=``,this.normalPass=new A({uniforms:{tBuffer:{value:null},uTexel:{value:new o(1/t,1/t)},uStrength:{value:2.4},tAdvect:{value:n}},fragmentShader:`
        precision highp float;
        varying vec2 vUv;
        uniform sampler2D tBuffer;
        uniform sampler2D tAdvect;
        uniform vec2 uTexel;
        uniform float uStrength;
        ${N}

        float height(vec2 uv) {
          float h = texture2D(tBuffer, uv).r;
          // Modulate the height by high-frequency noise so the surface breaks up
          // into facets rather than reading as a smooth blob.
          float detail = texture2D(tAdvect, uv * 6.0).a;
          return h * mix(0.75, 1.0, detail);
        }

        void main() {
          float l = height(vUv - vec2(uTexel.x, 0.0));
          float r = height(vUv + vec2(uTexel.x, 0.0));
          float b = height(vUv - vec2(0.0, uTexel.y));
          float t = height(vUv + vec2(0.0, uTexel.y));
          vec3 n = normalize(vec3((l - r) * uStrength, (b - t) * uStrength, 1.0));
          gl_FragColor = vec4(n * 0.5 + 0.5, texture2D(tBuffer, vUv).r);
        }
      `})}get texture(){return this.buffer.read.texture}get normalTexture(){return this.normalRT.texture}setAdvectTexture(e){this.step.uniforms.tAdvect.value=e,this.normalPass.uniforms.tAdvect.value=e}setAspect(e){this.step.uniforms.uAspect.value=e}update(e,t,n){let r=this.step.uniforms;r.tBuffer.value=this.buffer.read.texture,r.uTime.value=n,r.uSplatCoords.value.set(t.x,t.y),r.uSplatPrevCoords.value.set(t.px,t.py),r.uSplatRadius.value=t.active?Math.min(1,.45+t.speed*16):0,r.uDamping.value=.9905**(Math.min(e,1/20)*60),this.step.render(this.renderer,this.buffer.write),this.buffer.swap(),this.normalPass.uniforms.tBuffer.value=this.buffer.read.texture,this.normalPass.render(this.renderer,this.normalRT)}setSize(e,t){this.setAspect(e/t)}dispose(){this.buffer.dispose(),this.normalRT.dispose(),this.step.dispose(),this.normalPass.dispose()}},Ae=class{constructor(e,{blueNoiseTexture:t,lutTexture:n,noiseTexture:r}){this.renderer=e;let i=e.getDrawingBufferSize(new o);this.sceneA=j(i.x,i.y,{depthBuffer:!0}),this.sceneB=j(i.x,i.y,{depthBuffer:!0}),this.transitionRT=j(i.x,i.y);let a=new o(t.image.width,t.image.height);this.transition=new A({uniforms:{tScene1:{value:this.sceneA.texture},tScene2:{value:this.sceneB.texture},tScroll:{value:r},tBlue:{value:t},uBlueOffset:{value:new o},uBlueSize:{value:a},uProgress:{value:0},uProgressVel:{value:0},uAspect:{value:i.x/i.y},uSlope:{value:-.2},uParallax:{value:.35}},fragmentShader:`
        precision highp float;
        varying vec2 vUv;

        uniform sampler2D tScene1;
        uniform sampler2D tScene2;
        uniform sampler2D tScroll;
        uniform float uProgress;
        uniform float uProgressVel;
        uniform float uAspect;
        uniform float uSlope;
        uniform float uParallax;

        #define CA_ITERATIONS 5

        ${N}
        ${P}
        ${F}
        ${fe}
        ${pe}

        void main() {
          // Early out on the common case: no transition in flight.
          if (uProgress <= 0.0) {
            gl_FragColor = vec4(texture2D(tScene1, vUv).rgb, 1.0);
            return;
          }
          if (uProgress >= 1.0) {
            gl_FragColor = vec4(texture2D(tScene2, vUv).rgb, 1.0);
            return;
          }

          // Aspect-corrected lookup so the warp texture isn't stretched.
          vec2 uvTex = vec2((vUv.x - 0.5) * uAspect + 0.5, vUv.y);
          vec3 scroll = texture2D(tScroll, uvTex).rgb;

          // The cut is a diagonal whose slope tracks scroll velocity, displaced
          // per-pixel by the noise so the front is ragged.
          float slope = uSlope * uAspect;
          float slopeDisp = (scroll.b * 2.0 - 1.0) * 0.4;
          float inclination = mix(1.0 - vUv.x + slopeDisp, vUv.x + slopeDisp, step(slope, 0.0));
          float axis = vUv.y + inclination * abs(slope);
          float front = fit(uProgress, 0.0, 1.0, 0.0, 1.0 + abs(slope));

          // Three fronts at different softness, from the same axis: a wide one
          // for CA, a medium one for UV displacement, a tight one for the cut.
          float caFront   = falloff(axis, 0.0, 1.0, 2.0, front);
          float dispFront = falloff(axis, 0.0, 1.0, 0.9, front);
          float cutFront  = falloff(axis, 0.0, 1.0, 0.2, front);

          float disp = falloff(scroll.g, 0.0, 1.0, 1.0, dispFront);
          float cut  = falloff(scroll.r, 0.0, 1.0, 2.0, cutFront);

          // Vignette the aberration so the centre of frame stays clean.
          float modulator = 12.0
            * smoothstep(1.0, 0.7, abs(vUv.x * 2.0 - 1.0))
            * smoothstep(1.0, 0.7, abs(vUv.y * 2.0 - 1.0));
          modulator *= 1.0 + abs(uProgressVel) * 4.0;

          vec4 n = blueNoise4(gl_FragCoord.xy);

          const float displacement = 0.025;
          vec3 a = vec3(0.0);
          vec3 b = vec3(0.0);

          // Skip the 5-tap CA loop entirely on pixels that are fully one side.
          if (cut < 1.0) {
            vec2 uvA = vUv - vec2(0.0, uParallax * power2In(uProgress) + displacement * disp);
            a = chromatic_aberration(tScene1, uvA, modulator, caFront * n.r).rgb;
          }
          if (cut > 0.0) {
            vec2 uvB = vUv + vec2(0.0, uParallax * power2In(1.0 - uProgress) + displacement * (1.0 - disp));
            b = chromatic_aberration(tScene2, uvB, modulator, (1.0 - caFront) * n.g).rgb;
          }

          gl_FragColor = vec4(clamp(mix(a, b, cut), 0.0, 1.0), 1.0);
        }
      `}),this.grade=new A({uniforms:{tDiffuse:{value:this.transitionRT.texture},tLUT:{value:n},tBlue:{value:t},tFrost:{value:null},tFrostNormal:{value:null},uBlueOffset:{value:new o},uBlueSize:{value:a},uFrostAmount:{value:1},uFrostColor:{value:new m(.9,.95,1)},uFrostDisplace:{value:.028},uLUTSize:{value:n.userData.size},uLUTIntensity:{value:.45},uVignette:{value:.14},uGrain:{value:.022},uExposure:{value:1.15},uTime:{value:0}},fragmentShader:`
        precision highp float;
        varying vec2 vUv;

        uniform sampler2D tDiffuse;
        uniform sampler2D tLUT;
        uniform sampler2D tFrost;
        uniform sampler2D tFrostNormal;
        uniform float uFrostAmount;
        uniform vec3  uFrostColor;
        uniform float uFrostDisplace;
        uniform float uLUTSize;
        uniform float uLUTIntensity;
        uniform float uVignette;
        uniform float uGrain;
        uniform float uExposure;
        uniform float uTime;

        ${N}
        ${F}
        ${fe}
        ${me}
        ${ge}

        // AgX-flavoured tonemap: rolls highlights without the saturation crush
        // Reinhard gives you, and keeps the specular streaks on ice from clipping.
        vec3 tonemap(vec3 x) {
          x = max(vec3(0.0), x);
          return (x * (2.51 * x + 0.03)) / (x * (2.43 * x + 0.59) + 0.14);
        }

        void main() {
          // --- frost -----------------------------------------------------
          // The case study lists frost alongside chromatic aberration and tech
          // displacement as a *scene* effect. Applying it only to the ice
          // material made it invisible: the ice covers a small fraction of the
          // frame, so most of the pointer trail landed on snow and did nothing.
          // Here it refracts and freezes the whole composited image.
          vec4 frost = texture2D(tFrost, vUv);
          vec3 frostN = texture2D(tFrostNormal, vUv).rgb * 2.0 - 1.0;
          float mask = clamp(frost.r * uFrostAmount, 0.0, 1.0);

          vec2 uv = vUv + frostN.xy * mask * uFrostDisplace;
          vec3 color = texture2D(tDiffuse, uv).rgb * uExposure;

          if (mask > 0.001) {
            // Frost scatters: crush toward luminance, tint cold, lift.
            float l = luma(color);
            vec3 frozen = mix(color, vec3(l), 0.38) * uFrostColor + 0.03 * uFrostColor;
            color = mix(color, frozen, mask);
            // The advancing growth front is the bright part of real frost.
            color += uFrostColor * clamp(frost.b, 0.0, 1.0) * 1.1;
          }

          color = tonemap(color);
          color = apply3DLUT(tLUT, color, uLUTSize, uLUTIntensity);

          float d = length((vUv - 0.5) * vec2(1.0, 0.85));
          color *= 1.0 - uVignette * smoothstep(0.35, 0.95, d);

          // Animated grain, then a blue-noise dither below it. The dither is what
          // actually removes banding; the grain is taste.
          float g = hash12(vUv * 1024.0 + fract(uTime) * 91.7) - 0.5;
          color += g * uGrain;
          color += (blueNoise4(gl_FragCoord.xy).a - 0.5) / 255.0;

          gl_FragColor = vec4(color, 1.0);
        }
      `})}bindFrost(e){this.grade.uniforms.tFrost.value=e.texture,this.grade.uniforms.tFrostNormal.value=e.normalTexture}setFrame(e,t){let n=e*.7548776662%1,r=e*.5698402909%1;this.transition.uniforms.uBlueOffset.value.set(n,r),this.grade.uniforms.uBlueOffset.value.set(r,n),this.grade.uniforms.uTime.value=t}setSize(e,t){this.sceneA.setSize(e,t),this.sceneB.setSize(e,t),this.transitionRT.setSize(e,t),this.transition.uniforms.uAspect.value=e/t}render(e,t){this.transition.uniforms.uProgress.value=e,this.transition.uniforms.uProgressVel.value=t,this.transition.render(this.renderer,this.transitionRT),this.grade.render(this.renderer,null)}dispose(){this.sceneA.dispose(),this.sceneB.dispose(),this.transitionRT.dispose(),this.transition.dispose(),this.grade.dispose()}},je=class extends x{constructor({envMap:e=null,sceneTexture:t=null,frostTexture:n=null,frostNormalTexture:r=null,detailTexture:i=null,blueNoise:a=null,fogColor:s=new m(.855,.875,.905),fogDensity:l=.0125}={}){super({transparent:!1,side:0,uniforms:{tScene:{value:t},tEnv:{value:e},tFrost:{value:n},tFrostNormal:{value:r},tDetail:{value:i},tBlue:{value:a},uBlueOffset:{value:new o},uBlueSize:{value:new o(64,64)},uResolution:{value:new o(1,1)},uTime:{value:0},uIor:{value:1.31},uDispersion:{value:.035},uChromaticAberration:{value:.9},uRefractionStrength:{value:.42},uThickness:{value:1.05},uAttenuationDistance:{value:1.6},uAttenuationColor:{value:new m(.46,.54,.62)},uRoughness:{value:.22},uEnvIntensity:{value:.48},uFresnelPower:{value:2.8},uReflectivity:{value:.45},uEdgeGlow:{value:.42},uEdgeColor:{value:new m(1,1,1)},uScatter:{value:.62},uScatterColor:{value:new m(.8,.86,.94)},uFogColor:{value:s.clone()},uFogDensity:{value:l},uSunDir:{value:new c(-.35,.72,.6).normalize()},uHover:{value:0},uFrostAmount:{value:1},uFrostColor:{value:new m(.86,.93,1)},uDetailScale:{value:1.1},uDetailStrength:{value:.12}},vertexShader:`
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
      `,fragmentShader:`
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

        ${N}
        ${P}
        ${F}

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
      `})}setSize(e,t){this.uniforms.uResolution.value.set(e,t)}update(e,t){this.uniforms.uTime.value=e,this.uniforms.uBlueOffset.value.copy(t)}},Me=class{constructor(e,{size:t=128,bounds:n=new c(9,6,6),noiseScale:r=.16,speed:i=.35,pointSize:a=2.2}={}){this.renderer=e,this.size=t,this.count=t*t,this.bounds=n,this.positions=new le(t,t,{type:h}),this.velocities=new le(t,t,{type:h}),this._seed(e),this.simPass=new A({uniforms:{tPosition:{value:null},tVelocity:{value:null},tOrigin:{value:this.originTexture},uTime:{value:0},uDelta:{value:.016},uNoiseScale:{value:r},uSpeed:{value:i},uBounds:{value:n},uMouse:{value:new c(0,0,0)},uInteractForce:{value:0}},fragmentShader:`
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

        ${N}
        ${F}

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
      `}),this.velPass=new A({uniforms:this.simPass.uniforms,defines:{WRITE_VELOCITY:``},fragmentShader:this.simPass.material.fragmentShader}),this._buildPoints(a)}_seed(e){let{size:t,count:n,bounds:r}=this,i=new Float32Array(n*4),a=new Float32Array(n*4);for(let e=0;e<n;e++)i[e*4+0]=(Math.random()*2-1)*r.x,i[e*4+1]=(Math.random()*2-1)*r.y,i[e*4+2]=(Math.random()*2-1)*r.z,i[e*4+3]=Math.random(),a[e*4+3]=Math.random();let o=e=>{let n=new S(e,t,t,k,h);return n.needsUpdate=!0,n.minFilter=n.magFilter=ne,n.colorSpace=``,n};this.originTexture=o(i);let s=o(a),c=new A({uniforms:{tSrc:{value:null}},fragmentShader:`
        precision highp float;
        varying vec2 vUv;
        uniform sampler2D tSrc;
        void main() { gl_FragColor = texture2D(tSrc, vUv); }
      `});for(let[t,n]of[[this.positions,this.originTexture],[this.velocities,s]])c.uniforms.tSrc.value=n,c.render(e,t.a),c.render(e,t.b);c.dispose()}_buildPoints(t){let{size:n,count:r}=this,i=new Float32Array(r*3);for(let e=0;e<r;e++)i[e*3+0]=(e%n+.5)/n,i[e*3+1]=(Math.floor(e/n)+.5)/n,i[e*3+2]=0;let a=new y;a.setAttribute(`position`,new E(i,3)),a.boundingSphere=new e(new c,32),this.material=new x({transparent:!0,depthWrite:!1,blending:2,uniforms:{tPosition:{value:null},uSize:{value:t},uPixelRatio:{value:1},uColor:{value:new m(.72,.85,1)},uOpacity:{value:.9}},vertexShader:`
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
      `,fragmentShader:`
        precision highp float;
        varying float vLife;
        varying float vDepth;
        uniform vec3 uColor;
        uniform float uOpacity;
        ${N}
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
      `}),this.points=new l(a,this.material),this.points.frustumCulled=!1}update(e,t,n,r=0){let i=this.simPass.uniforms;i.uTime.value=t,i.uDelta.value=Math.min(e,1/30),i.uInteractForce.value=r,n&&i.uMouse.value.copy(n),i.tPosition.value=this.positions.read.texture,i.tVelocity.value=this.velocities.read.texture,this.velPass.render(this.renderer,this.velocities.write),this.simPass.render(this.renderer,this.positions.write),this.velocities.swap(),this.positions.swap(),this.material.uniforms.tPosition.value=this.positions.read.texture}setPixelRatio(e){this.material.uniforms.uPixelRatio.value=e}dispose(){this.positions.dispose(),this.velocities.dispose(),this.simPass.dispose(),this.velPass.dispose(),this.points.geometry.dispose(),this.material.dispose()}},L={GLYPH:0,WORD:1,LINE_GLYPH:2,LINE_WORD:3,LINE:4,RANDOM:5},R=null,Ne=0,z=new Map;function Pe(){return R||(R=new Worker(new URL(`/assets/layout.worker-CJOvL5KN.js`,``+import.meta.url),{type:`module`}),R.onmessage=e=>{let t=z.get(e.data.id);t&&(z.delete(e.data.id),t(e.data.buffers))}),R}function Fe(e,t){let n=++Ne;return new Promise(r=>{z.set(n,r),Pe().postMessage({id:n,font:e,options:t})})}var Ie=class extends x{constructor({map:e,distanceRange:t=8,color:n=new m(858922)}={}){super({transparent:!0,depthWrite:!1,side:2,uniforms:{tMap:{value:e},uColor:{value:n},uAlpha:{value:1},uRange:{value:t},uOutlineWidth:{value:0},uOutlineColor:{value:new m(16777215)},uWeight:{value:0},uAnimationProgress:{value:0},uAnimationOrder:{value:L.GLYPH},uAnimationDirection:{value:new c(0,-1,0)},uAnimationAmount:{value:.6},uAnimationMargin:{value:.35},uAnimationRotation:{value:.5},uAnimationScale:{value:.4},uTime:{value:0},uWobble:{value:0}},vertexShader:`
        attribute vec3 aCenter;
        attribute vec2 textWeights;
        attribute vec3 lineWeights;
        attribute vec4 uvBounds;

        uniform float uAnimationProgress;
        uniform float uAnimationOrder;
        uniform vec3  uAnimationDirection;
        uniform float uAnimationAmount;
        uniform float uAnimationMargin;
        uniform float uAnimationRotation;
        uniform float uAnimationScale;
        uniform float uTime;
        uniform float uWobble;

        varying vec2 vUv;
        varying float vReveal;

        ${N}
        ${P}
        ${F}

        // Select the ordinal this glyph animates on. Branchless: five mixes cost
        // less than a dynamic branch on most mobile GPUs and the compiler folds
        // the whole thing once uAnimationOrder is a constant per draw.
        float pickOrdinal() {
          float o = uAnimationOrder;
          float v = textWeights.x;
          v = mix(v, textWeights.y,  step(0.5, o) * step(o, 1.5));
          v = mix(v, lineWeights.x,  step(1.5, o) * step(o, 2.5));
          v = mix(v, lineWeights.y,  step(2.5, o) * step(o, 3.5));
          v = mix(v, lineWeights.z,  step(3.5, o) * step(o, 4.5));
          v = mix(v, hash12(aCenter.xy * 17.3), step(4.5, o));
          return v;
        }

        void main() {
          vUv = uv;

          float ordinal = pickOrdinal();
          // Soft front sweeping across the ordering.
          float reveal = falloff(ordinal, 0.0, 1.0, uAnimationMargin, uAnimationProgress);
          reveal = power2Out(reveal);
          vReveal = reveal;

          vec3 local = position - aCenter;

          // Scale and rotate about the glyph's own centre while it flies in.
          float s = mix(1.0 - uAnimationScale, 1.0, reveal);
          float a = (1.0 - reveal) * uAnimationRotation * (hash12(aCenter.xy) * 2.0 - 1.0);
          float c = cos(a), sn = sin(a);
          local.xy = mat2(c, -sn, sn, c) * local.xy * s;

          vec3 offset = uAnimationDirection * uAnimationAmount * (1.0 - reveal);

          // Idle wobble, decorrelated per glyph so the block breathes.
          offset += vec3(
            snoise(vec3(aCenter.xy * 0.6, uTime * 0.25)),
            snoise(vec3(aCenter.xy * 0.6 + 31.7, uTime * 0.25)),
            0.0
          ) * uWobble;

          vec3 world = aCenter + local + offset;
          gl_Position = projectionMatrix * modelViewMatrix * vec4(world, 1.0);
        }
      `,fragmentShader:`
        precision highp float;
        varying vec2 vUv;
        varying float vReveal;

        uniform sampler2D tMap;
        uniform vec3  uColor;
        uniform vec3  uOutlineColor;
        uniform float uAlpha;
        uniform float uRange;
        uniform float uOutlineWidth;
        uniform float uWeight;

        ${N}
        ${he}

        void main() {
          vec3 s = texture2D(tMap, vUv).rgb;
          float fill = sdfAlpha(s, uRange, uWeight);

          vec3 color = uColor;
          float alpha = fill;

          if (uOutlineWidth > 0.0) {
            // A second threshold further out gives a stroke; subtracting the
            // fill leaves a ring rather than a filled halo.
            float outer = sdfAlpha(s, uRange, uWeight + uOutlineWidth);
            color = mix(uOutlineColor, uColor, fill);
            alpha = outer;
          }

          alpha *= uAlpha * vReveal;
          if (alpha < 0.003) discard;
          gl_FragColor = vec4(color, alpha);
        }
      `})}},B=class extends _{constructor(e,t,n={}){let r=new Ie({map:t,distanceRange:e.atlas.distanceRange,color:n.color?new m(n.color):new m(858922)});super(new y,r),this.font=e,this.options={text:``,size:1,align:`center`,width:1/0,lineHeight:1.15,letterSpacing:0,wordSpacing:0,...n},this.frustumCulled=!1,this.ready=this.rebuild()}async rebuild(){let e=await Fe(this.font,this.options),t=new y;return t.setIndex(new E(e.index,1)),t.setAttribute(`position`,new E(e.position,3)),t.setAttribute(`uv`,new E(e.uv,2)),t.setAttribute(`aCenter`,new E(e.centroid,3)),t.setAttribute(`uvBounds`,new E(e.uvBounds,4)),t.setAttribute(`textWeights`,new E(e.textWeights,2)),t.setAttribute(`lineWeights`,new E(e.lineWeights,3)),t.computeBoundingSphere(),this.geometry.dispose(),this.geometry=t,this.blockWidth=e.blockWidth,this.blockHeight=e.blockHeight,this}setText(e){return this.options.text=e,this.rebuild()}set progress(e){this.material.uniforms.uAnimationProgress.value=e}get progress(){return this.material.uniforms.uAnimationProgress.value}update(e){this.material.uniforms.uTime.value=e}},V=new m(.845,.865,.895),Le=.0062,Re=`
  uniform vec3  uFogColor;
  uniform float uFogDensity;

  // Exponential-squared fog. Matches THREE.FogExp2 so the DOM background colour
  // and the far terrain converge on exactly the same value at the horizon.
  vec3 applyFog(vec3 color, float dist) {
    float f = 1.0 - exp(-dist * dist * uFogDensity * uFogDensity);
    return mix(color, uFogColor, clamp(f, 0.0, 1.0));
  }
`,ze=()=>({uFogColor:{value:V.clone()},uFogDensity:{value:Le}});function Be({noiseTexture:e}){return new x({uniforms:{tNoise:{value:e},uTime:{value:0},uSnow:{value:new m(.97,.98,1)},uShadow:{value:new m(.44,.52,.66)},uSunDir:{value:new c(-.35,.72,.6).normalize()},...ze()},vertexShader:`
      varying vec3 vWorldPos;
      varying vec3 vNormal;
      varying float vHeight;

      ${N}
      ${F}

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
    `,fragmentShader:`
      precision highp float;
      varying vec3 vWorldPos;
      varying vec3 vNormal;
      varying float vHeight;

      uniform sampler2D tNoise;
      uniform vec3 uSnow;
      uniform vec3 uShadow;
      uniform vec3 uSunDir;

      ${N}
      ${Re}

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
    `})}function Ve(e){let t=e>>>0;return()=>{t=t+1831565813>>>0;let e=Math.imul(t^t>>>15,1|t);return e=e+Math.imul(e^e>>>7,61|e)^e,((e^e>>>14)>>>0)/4294967296}}function He({material:e,radius:n=3.1,courses:r=7,rng:i}){let a=new g,o=new g;a.add(o);let s=[],l=.1,u=Math.PI/2;for(let t=0;t<r;t++){let a=u-t/r*(u-l),c=u-(t+1)/r*(u-l),d=(a+c)*.5,f=n*Math.sin(d),p=n*Math.cos(d),m=n*Math.abs(a-c)*1.02,h=Math.max(5,Math.round(2*Math.PI*f/1.15)),g=2*Math.PI/h,v=f*g*.92,y=new D(v,m*.9,.42,5,.12),b=t%2*g*.5;for(let n=0;n<h;n++){let r=n*g+b,a=Math.abs(Math.atan2(Math.sin(r),Math.cos(r))-Math.PI/2);if(t<2&&a<.42)continue;let c=new _(y,e),l=1+(i()-.5)*.05;c.position.set(Math.cos(r)*f*l,p,Math.sin(r)*f*l),c.lookAt(0,0,0),c.rotateZ((i()-.5)*.05),c.rotateX((i()-.5)*.03),c.scale.setScalar(1+(i()-.5)*.06),o.add(c),s.push(c)}}let p=new _(new D(.95,.95,.42,5,.12),e);p.position.set(0,n*Math.cos(l*.4),0),p.rotation.y=i()*Math.PI,o.add(p),s.push(p);{let t=n*.94;for(let n=0;n<3;n++){let r=-.02+n*.49;for(let n=0;n<3;n++){let a=t+.35+n*.55;for(let t of[-1,1]){let n=new D(.34,.46,.52,5,.1),c=new _(n,e);c.position.set(t*.82,r,a),c.rotation.y=(i()-.5)*.06,c.rotation.z=(i()-.5)*.04,c.userData.anchored=!0,o.add(c),s.push(c)}}}for(let n=0;n<3;n++){let r=new D(1.98,.36,.52,5,.1),a=new _(r,e);a.position.set(0,1.45,t+.35+n*.55),a.rotation.z=(i()-.5)*.03,a.userData.anchored=!0,o.add(a),s.push(a)}}{let t=n*1.02,r=Math.round(2*Math.PI*t/1.35),a=2*Math.PI/r,c=new D(t*a*.92,.62,.62,5,.12);for(let n=0;n<r;n++){let r=n*a+a*.5,l=new _(c,e);l.position.set(Math.cos(r)*t,-.22+(i()-.5)*.05,Math.sin(r)*t),l.lookAt(0,l.position.y,0),l.rotateY((i()-.5)*.06),l.userData.anchored=!0,o.add(l),s.push(l)}}let h=new _(new b(n*.9,32,20,0,Math.PI*2,0,Math.PI/2),new d({color:new m(.3,.35,.43),side:1}));a.add(h);let v=new _(new f(n*.92,32),new d({color:new m(.38,.43,.51)}));v.rotation.x=-Math.PI/2,v.position.y=.01,a.add(v);{let e=1/0,n=-1/0;for(let t of s)e=Math.min(e,t.position.y),n=Math.max(n,t.position.y);let r=Math.max(n-e,.001),a=new c;for(let n of s){let o=(n.position.y-e)/r,s=n.position.clone();s.y*=.35,s.lengthSq()<1e-6&&s.set(0,1,0),s.normalize();let l=s.clone().addScaledVector(new c(0,1,0),.3+i()*.25).normalize();a.set(i()*2-1,i()*2-1,i()*2-1).normalize(),n.userData.rest={position:n.position.clone(),quaternion:n.quaternion.clone()},n.userData.blast={direction:l,distance:n.userData.anchored?0:.1+i()*.34,spin:new t().setFromAxisAngle(a,(i()*2-1)*.2),order:1-o,hoverDistance:n.userData.anchored?0:.55+i()*.62,hoverSpin:new t().setFromAxisAngle(a,(i()*2-1)*.55)},n.userData.hover=0,n.onBeforeRender=(e,t,r,i,a)=>{a.uniforms.uHover.value=n.userData.hover}}}return a.userData.blocks=s,a.userData.brickGroup=o,a.userData.interior=h,a.userData.floor=v,a}var Ue=class{constructor(e,n){this.renderer=e,this.assets=n,this.scene=new s,this.scene.background=V.clone(),this.scene.environment=n.envMap,this.camera=new p(34,1,.1,600),this.camera.position.set(.6,2.2,16.5),this.cameraTarget=new c(0,1.35,0);let r=new _(new re(520,520,380,380),Be({noiseTexture:n.noise}));r.rotation.x=-Math.PI/2,r.position.y=-1.35,r.frustumCulled=!1,this.terrain=r,this.scene.add(r),this.iceMaterial=new je({envMap:n.envMap,sceneTexture:null,frostTexture:n.frost,frostNormalTexture:n.frostNormal,detailTexture:n.noise,blueNoise:n.blueNoise,fogColor:V,fogDensity:Le}),this.iceMaterial.uniforms.uBlueSize.value.set(n.blueNoise.image.width,n.blueNoise.image.height);let i=Ve(11);this.igloo=He({material:this.iceMaterial,radius:3.4,courses:8,rng:i}),this.igloo.position.y=-1.28,this.scene.add(this.igloo),this.particles=new Me(e,{size:96,bounds:new c(16,7,10),speed:.26,pointSize:2}),this.particles.material.uniforms.uColor.value.setRGB(1,1,1),this.particles.material.uniforms.uOpacity.value=.5,this.particles.material.blending=1,this.scene.add(this.particles.points),this.headline=new B(n.font,n.fontTexture,{text:`IGLOO`,size:1.25,align:`center`,lineHeight:1,letterSpacing:.06,color:2240832}),this.headline.position.set(0,3.3,5.6),this.headline.material.uniforms.uAnimationOrder.value=L.GLYPH,this.headline.material.uniforms.uAnimationDirection.value.set(0,-.5,.9),this.headline.material.uniforms.uAnimationMargin.value=.45,this.headline.material.uniforms.uWobble.value=.006,this.scene.add(this.headline),this.subline=new B(n.font,n.fontTexture,{text:`// PROCEDURAL ICE / SCREEN-SPACE REFRACTION`,size:.16,align:`center`,lineHeight:1.4,letterSpacing:.14,color:5464433}),this.subline.position.set(0,2.72,5.6),this.subline.material.uniforms.uAnimationOrder.value=L.GLYPH,this.subline.material.uniforms.uAnimationDirection.value.set(.25,0,0),this.subline.material.uniforms.uAnimationMargin.value=.6,this.scene.add(this.subline),this.hoverProxy=new _(new b(3.55,24,16),new d),this.hoverProxy.position.copy(this.igloo.position),this.hoverProxy.updateMatrixWorld(),this._raycaster=new u,this._pointerNDC=new o,this._hoverPoint=new c,this._hoverActive=!1,this._parallax={x:0,y:0,tx:0,ty:0},this._mouseWorld=new c,this._blastQuat=new t,this._blastVec=new c,this.assembly=0}setSize(e,t){this.camera.aspect=e/t,this.camera.updateProjectionMatrix(),this.iceMaterial.setSize(e,t)}setRefractionTexture(e){this.iceMaterial.uniforms.tScene.value=e}bindFrost(e){this.iceMaterial.uniforms.tFrost.value=e.texture,this.iceMaterial.uniforms.tFrostNormal.value=e.normalTexture}setIceVisible(e){this.igloo.userData.brickGroup.visible=e}setAssembly(e,t=1/60){let n=this.igloo.userData.blocks;for(let r=0;r<n.length;r++){let i=n[r],a=i.userData.rest,o=i.userData.blast,s=o.order*.44999999999999996,c=1-(1-Math.min(1,Math.max(0,(e-s)/.55)))**3,l=0;if(this._hoverActive&&!i.userData.anchored){let e=this._hoverPoint.distanceTo(this._blastVec.copy(a.position).add(this.igloo.position)),t=Math.min(1,e/2.6);l=1-t*t*(3-2*t)}i.userData.hover=M(i.userData.hover,l,.12,t);let u=i.userData.hover,d=o.distance*c+o.hoverDistance*u;i.position.copy(a.position).addScaledVector(o.direction,d);let f=Math.min(1,c+u),p=u>c?o.hoverSpin:o.spin;i.quaternion.copy(a.quaternion).slerp(this._blastQuat.multiplyQuaternions(p,a.quaternion),f)}this.iceMaterial.uniforms.uEdgeGlow.value=.42+e*.85,this.assembly=e}update(e,t,n,r){this._parallax.tx=(n.x-.5)*1.3,this._parallax.ty=(n.y-.5)*.6,this._parallax.x=M(this._parallax.x,this._parallax.tx,.05,e),this._parallax.y=M(this._parallax.y,this._parallax.ty,.05,e);let i=Math.sin(t*.06)*.9;this.camera.position.x=this._parallax.x+i,this.camera.position.y=2.4+this._parallax.y+this.assembly*.35,this.camera.position.z=16.5-this.assembly*3.2,this.camera.lookAt(this.cameraTarget),this._pointerNDC.set(n.x*2-1,n.y*2-1),this._raycaster.setFromCamera(this._pointerNDC,this.camera);let a=this._raycaster.intersectObject(this.hoverProxy,!1);this._hoverActive=a.length>0,this._hoverActive&&this._hoverPoint.copy(a[0].point),this._mouseWorld.set(n.x*2-1,n.y*2-1,.5).unproject(this.camera).sub(this.camera.position).normalize().multiplyScalar(11).add(this.camera.position),this.terrain.material.uniforms.uTime.value=t,this.iceMaterial.update(t,r),this.particles.update(e,t,this._mouseWorld,n.active?.9:0),this.headline.update(t),this.subline.update(t)}dispose(){this.particles.dispose(),this.iceMaterial.dispose(),this.terrain.geometry.dispose(),this.terrain.material.dispose()}},We=class extends _{constructor(e,{color:t=16777215,width:n=1.4,opacity:r=.85}={}){let i=[],a=[],s=[],c=[],l=[],u=[];e.forEach((t,n)=>{let r=[0];for(let e=1;e<t.length;e++){let n=t[e-1],i=t[e];r.push(r[e-1]+Math.hypot(i[0]-n[0],i[1]-n[1],i[2]-n[2]))}let o=r[r.length-1]||1,d=i.length/3;for(let f=0;f<t.length;f++){let p=t[f],m=f<t.length-1?t[f+1]:t[f-1],h=f<t.length-1?1:-1;for(let t of[-1,1])i.push(p[0],p[1],p[2]),a.push(m[0],m[1],m[2]),s.push(t*h),c.push(r[f]/o),l.push(n/Math.max(1,e.length-1));if(f<t.length-1){let e=d+f*2;u.push(e,e+1,e+2,e+1,e+3,e+2)}}});let d=new y;d.setAttribute(`position`,new O(i,3)),d.setAttribute(`nextPosition`,new O(a,3)),d.setAttribute(`side`,new O(s,1)),d.setAttribute(`along`,new O(c,1)),d.setAttribute(`pathIndex`,new O(l,1)),d.setIndex(u);let f=new x({transparent:!0,depthWrite:!1,depthTest:!1,side:2,uniforms:{uColor:{value:new m(t)},uWidth:{value:n},uOpacity:{value:r},uResolution:{value:new o(1,1)},uProgress:{value:0},uMargin:{value:.4}},vertexShader:`
        attribute vec3 nextPosition;
        attribute float side;
        attribute float along;
        attribute float pathIndex;

        uniform float uWidth;
        uniform vec2 uResolution;
        uniform float uProgress;
        uniform float uMargin;

        varying float vReveal;

        ${N}
        ${P}

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
      `,fragmentShader:`
        precision highp float;
        uniform vec3 uColor;
        uniform float uOpacity;
        varying float vReveal;
        void main() {
          if (vReveal < 0.5) discard;
          gl_FragColor = vec4(uColor, uOpacity);
        }
      `});super(d,f),this.frustumCulled=!1}setSize(e,t){this.material.uniforms.uResolution.value.set(e,t)}set progress(e){this.material.uniforms.uProgress.value=e}};function Ge(e){let t=e>>>0;return()=>{t=t+1831565813>>>0;let e=Math.imul(t^t>>>15,1|t);return e=e+Math.imul(e^e>>>7,61|e)^e,((e^e>>>14)>>>0)/4294967296}}function Ke(e,t,n){let r=Math.imul(e|0,374761393)^Math.imul(t|0,668265263)^Math.imul(n|0,2147483647);return r=Math.imul(r^r>>>13,1274126177),((r^r>>>16)>>>0)/4294967296}var qe=e=>e*e*e*(e*(e*6-15)+10);function Je(e,t,n){let r=Math.floor(e),i=Math.floor(t),a=Math.floor(n),o=qe(e-r),s=qe(t-i),c=qe(n-a),l=0;for(let e=0;e<2;e++){let t=e?c:1-c;for(let n=0;n<2;n++){let c=n?s:1-s;for(let s=0;s<2;s++){let u=s?o:1-o;l+=Ke(r+s,i+n,a+e)*u*c*t}}}return l*2-1}function Ye(e,t,n,r=3){let i=0,a=.5,o=0,s=1;for(let c=0;c<r;c++)i+=a*Je(e*s,t*s,n*s),o+=a,s*=2.07,a*=.5;return i/o}function Xe(e,t){let[n,r,i]=t;if(e===`cylinder`){let e=Math.min(n,i);return(t,n,i)=>{let a=Math.hypot(t,i)-e,o=Math.abs(n)-r;return Math.hypot(Math.max(a,0),Math.max(o,0))+Math.min(Math.max(a,o),0)}}return(e,t,a)=>{let o=Math.abs(e)-n,s=Math.abs(t)-r,c=Math.abs(a)-i;return Math.hypot(Math.max(o,0),Math.max(s,0),Math.max(c,0))+Math.min(Math.max(o,Math.max(s,c)),0)}}function Ze(){let e=[];for(let t=0;t<6;t++){let n=t/6*Math.PI*2;e.push([Math.cos(n),0,Math.sin(n)])}e.push([0,1,0],[0,-1,0]);for(let t=0;t<6;t++){let n=t/6*Math.PI*2+Math.PI/6;for(let t of[1,-1]){let r=[Math.cos(n)*.75,t*.66,Math.sin(n)*.75],i=Math.hypot(r[0],r[1],r[2]);e.push([r[0]/i,r[1]/i,r[2]/i])}}return e}function Qe(e){let t=e(),n=e(),r=e(),i=Math.sqrt(1-t),a=Math.sqrt(t),[o,s,c,l]=[i*Math.sin(2*Math.PI*n),i*Math.cos(2*Math.PI*n),a*Math.sin(2*Math.PI*r),a*Math.cos(2*Math.PI*r)];return[1-2*(s*s+c*c),2*(o*s-c*l),2*(o*c+s*l),2*(o*s+c*l),1-2*(o*o+c*c),2*(s*c-o*l),2*(o*c-s*l),2*(s*c+o*l),1-2*(o*o+s*s)]}function $e({rng:e,container:t,extents:n,count:r,steps:i}){let a=Ze(),o=[];for(let i=0;i<r;i++){let r;for(let i=0;i<40;i++){let i=[(e()*2-1)*n[0]*.75,(e()*2-1)*n[1]*.8,(e()*2-1)*n[2]*.75];if(t(i[0],i[1],i[2])<-.05){r=i;break}}if(!r)continue;let i=Qe(e),s=.35+e()*1.9,c=a.map(t=>{let n=Math.abs(t[1]);return(1-n+n*s)*(.7+e()*.6)});o.push({origin:r,basis:i,normals:a,rates:c,offsets:new Float32Array(a.length).fill(.02),frozen:new Uint8Array(a.length)})}let s=(e,t,n,r)=>{let i=t-e.origin[0],a=n-e.origin[1],o=r-e.origin[2],s=e.basis,c=s[0]*i+s[3]*a+s[6]*o,l=s[1]*i+s[4]*a+s[7]*o,u=s[2]*i+s[5]*a+s[8]*o,d=-1/0;for(let t=0;t<e.normals.length;t++){let n=e.normals[t],r=n[0]*c+n[1]*l+n[2]*u-e.offsets[t];r>d&&(d=r)}return d},c=Math.max(...n)/i*1.6;for(let e=0;e<i;e++)for(let e=0;e<o.length;e++){let n=o[e],r=n.basis;for(let i=0;i<n.normals.length;i++){if(n.frozen[i])continue;let a=n.normals[i],l=n.offsets[i]+n.rates[i]*c,u=a[0]*l,d=a[1]*l,f=a[2]*l,p=n.origin[0]+r[0]*u+r[1]*d+r[2]*f,m=n.origin[1]+r[3]*u+r[4]*d+r[5]*f,h=n.origin[2]+r[6]*u+r[7]*d+r[8]*f;if(t(p,m,h)>-.01){n.frozen[i]=1;continue}let g=!1;for(let t=0;t<o.length;t++)if(t!==e&&s(o[t],p,m,h)<0){g=!0;break}if(g){n.frozen[i]=1;continue}n.offsets[i]=l}}return{crystals:o,crystalSDF:s}}var et=[0,1,0,2,0,4,1,3,1,5,2,3,2,6,3,7,4,5,4,6,5,7,6,7];function tt(e,t,n,r){let[i,a,o]=t,s=[],c=new Int32Array(i*a*o).fill(-1),l=new Float32Array(8),u=(e,t,n)=>e+i*(t+a*n);for(let t=0;t<o-1;t++)for(let o=0;o<a-1;o++)for(let a=0;a<i-1;a++){let i=0;for(let n=0;n<8;n++){let r=e[u(a+(n&1),o+(n>>1&1),t+(n>>2&1))];l[n]=r,r<0&&(i|=1<<n)}if(i===0||i===255)continue;let d=0,f=0,p=0,m=0;for(let e=0;e<12;e++){let t=et[e*2],n=et[e*2+1],r=l[t],i=l[n];if(r<0==i<0)continue;let a=r/(r-i),o=t&1,s=t>>1&1,c=t>>2&1,u=n&1,h=n>>1&1,g=n>>2&1;d+=o+(u-o)*a,f+=s+(h-s)*a,p+=c+(g-c)*a,m++}let h=1/m;c[u(a,o,t)]=s.length/3,s.push(r[0]+(a+d*h)*n[0],r[1]+(o+f*h)*n[1],r[2]+(t+p*h)*n[2])}let d=[];for(let t=1;t<o-1;t++)for(let n=1;n<a-1;n++)for(let r=1;r<i-1;r++){let i=c[u(r,n,t)];if(i<0)continue;let a=e[u(r,n,t)]<0;if(e[u(r+1,n,t)]<0!==a){let e=c[u(r,n-1,t)],o=c[u(r,n-1,t-1)],s=c[u(r,n,t-1)];e>=0&&o>=0&&s>=0&&(a?d.push(i,e,o,i,o,s):d.push(i,o,e,i,s,o))}if(e[u(r,n+1,t)]<0!==a){let e=c[u(r-1,n,t)],o=c[u(r-1,n,t-1)],s=c[u(r,n,t-1)];e>=0&&o>=0&&s>=0&&(a?d.push(i,o,e,i,s,o):d.push(i,e,o,i,o,s))}if(e[u(r,n,t+1)]<0!==a){let e=c[u(r-1,n,t)],o=c[u(r-1,n-1,t)],s=c[u(r,n-1,t)];e>=0&&o>=0&&s>=0&&(a?d.push(i,e,o,i,o,s):d.push(i,o,e,i,s,o))}}return{positions:s,indices:d}}function nt({seed:e=1,container:t=`box`,extents:n=[.62,1,.62],resolution:r=44,crystals:i=7,steps:a=34,roughness:o=.035,noiseScale:s=3.4}={}){let c=Ge(e),l=Xe(t,n),{crystals:u,crystalSDF:d}=$e({rng:c,container:l,extents:n,count:i,steps:a}),f=r,p=[f,f,f],m=1.12,h=[n[0]*2*m/(f-1),n[1]*2*m/(f-1),n[2]*2*m/(f-1)],g=[-n[0]*m,-n[1]*m,-n[2]*m],_=new Float32Array(f*f*f),v=c()*100;for(let e=0;e<f;e++){let t=g[2]+e*h[2];for(let n=0;n<f;n++){let r=g[1]+n*h[1];for(let i=0;i<f;i++){let a=g[0]+i*h[0],c=1/0;for(let e=0;e<u.length;e++){let n=d(u[e],a,r,t);n<c&&(c=n)}c=Math.max(c,l(a,r,t)),c+=Ye(a*s+v,r*s,t*s,3)*o,_[i+f*(n+f*e)]=c}}}let{positions:b,indices:x}=tt(_,p,h,g),S=new Float32Array(x.length*3);for(let e=0;e<x.length;e++){let t=x[e]*3;S[e*3+0]=b[t+0],S[e*3+1]=b[t+1],S[e*3+2]=b[t+2]}let C=new y;return C.setAttribute(`position`,new E(S,3)),C.computeVertexNormals(),C.computeBoundingSphere(),C.userData.triangles=x.length/3,C}function rt({seed:e=1,resolution:t=30,radius:n=.42}={}){let r=Ge(e^1597463007),i=[],a=n*(.85+r()*.3);i.push({p:[0,-n*.15,0],r:a}),i.push({p:[0,a*.85,0],r:a*.62});for(let e=0;e<3+Math.floor(r()*3);e++){let e=r()*Math.PI*2,t=(r()*2-1)*a;i.push({p:[Math.cos(e)*a*.85,t,Math.sin(e)*a*.85],r:a*(.22+r()*.22)})}let o=n*2.1,s=t,c=[o*2/(s-1),o*2/(s-1),o*2/(s-1)],l=[-o,-o,-o],u=new Float32Array(s*s*s);for(let e=0;e<s;e++){let t=l[2]+e*c[2];for(let n=0;n<s;n++){let r=l[1]+n*c[1];for(let a=0;a<s;a++){let o=l[0]+a*c[0],d=.12,f=Math.hypot(o-i[0].p[0],r-i[0].p[1],t-i[0].p[2])-i[0].r;for(let e=1;e<i.length;e++){let n=i[e],a=Math.hypot(o-n.p[0],r-n.p[1],t-n.p[2])-n.r,s=Math.max(0,Math.min(1,.5+.5*(f-a)/d));f=a*s+f*(1-s)-d*s*(1-s)}f+=Ye(o*7,r*7,t*7,2)*.012,u[a+s*(n+s*e)]=f}}}let{positions:d,indices:f}=tt(u,[s,s,s],c,l),p=new Float32Array(f.length*3);for(let e=0;e<f.length;e++){let t=f[e]*3;p[e*3+0]=d[t+0],p[e*3+1]=d[t+1],p[e*3+2]=d[t+2]}let m=new y;return m.setAttribute(`position`,new E(p,3)),m.computeVertexNormals(),m.computeBoundingSphere(),m}var it=[{id:`PORTFOLIO_CO_01`,name:`PUDGY PENGUINS`,temp:`TEMP -26.41 / -81.06`,date:`D 01.02.2020`,container:`box`,extents:[.6,1.05,.6],crystals:7},{id:`PORTFOLIO_CO_02`,name:`LIL PUDGYS`,temp:`TEMP -31.08 / -74.19`,date:`D 14.07.2022`,container:`cylinder`,extents:[.68,.92,.68],crystals:5},{id:`PORTFOLIO_CO_03`,name:`OVERPASS IP`,temp:`TEMP -19.77 / -88.42`,date:`D 09.11.2023`,container:`box`,extents:[.72,.78,.55],crystals:9}],at=4.2;function ot(){let e=new _(new re(2,2),new x({depthTest:!1,depthWrite:!1,uniforms:{uInner:{value:new m(.475,.495,.53)},uOuter:{value:new m(.315,.335,.375)},uAspect:{value:1}},vertexShader:`
        varying vec2 vUv;
        void main() {
          vUv = uv;
          // Already in clip space: this is a fullscreen quad, not world geometry.
          gl_Position = vec4(position.xy, 1.0, 1.0);
        }
      `,fragmentShader:`
        precision highp float;
        varying vec2 vUv;
        uniform vec3 uInner;
        uniform vec3 uOuter;
        uniform float uAspect;
        ${N}
        ${F}
        void main() {
          vec2 p = (vUv - 0.5) * vec2(uAspect, 1.0);
          float d = length(p);
          vec3 c = mix(uInner, uOuter, smoothstep(0.05, 0.85, d));
          // Dither: an 8-bit gradient this shallow bands badly without it.
          c += (hash12(vUv * 2048.0) - 0.5) / 255.0;
          gl_FragColor = vec4(c, 1.0);
        }
      `}));return e.frustumCulled=!1,e.renderOrder=-1,e}var st=class{constructor(e,t){this.renderer=e,this.assets=t,this.scene=new s,this.camera=new p(32,1,.1,60),this.camera.position.set(0,0,6.2),this.backdrop=ot(),this.scene.add(this.backdrop),this.iceMaterial=new je({envMap:t.envMap,sceneTexture:null,frostTexture:t.frost,frostNormalTexture:t.frostNormal,detailTexture:t.noise,blueNoise:t.blueNoise,fogColor:new m(.4,.42,.46),fogDensity:.004});let n=this.iceMaterial.uniforms;n.uBlueSize.value.set(t.blueNoise.image.width,t.blueNoise.image.height),n.uThickness.value=.72,n.uAttenuationDistance.value=1.15,n.uAttenuationColor.value.setRGB(.44,.58,.74),n.uScatter.value=.18,n.uScatterColor.value.setRGB(.58,.66,.78),n.uRefractionStrength.value=.62,n.uDispersion.value=.055,n.uEdgeGlow.value=.55,n.uEnvIntensity.value=.75,n.uDetailStrength.value=.06,this.blocks=[],this.iceGroup=new g,this.scene.add(this.iceGroup),this._buildBlocks(),this._targetScroll=0,this._scroll=0,this.revealProgress=0}_buildBlocks(){let e=new d({color:new m(.11,.12,.145)});it.forEach((t,n)=>{let r=new g;r.position.x=n*at;let i=nt({seed:1e3+n*137,container:t.container,extents:t.extents,resolution:46,crystals:t.crystals,steps:34}),a=new _(i,this.iceMaterial);r.add(a);let o=new _(rt({seed:1e3+n*137,radius:Math.min(t.extents[0],t.extents[1])*.55}),e);o.position.y=-.05,r.add(o);let s=t.extents,c=new We([[[-s[0]*.5,s[1]*.55,s[2]],[-s[0]*1.5,s[1]*1.15,0],[-s[0]*2.9,s[1]*1.15,0]],[[s[0]*.6,s[1]*.05,s[2]*.6],[s[0]*1.9,s[1]*.42,0],[s[0]*3,s[1]*.42,0]],[[s[0]*.35,-s[1]*.6,s[2]*.7],[s[0]*1.7,-s[1]*.85,0],[s[0]*3,-s[1]*.85,0]],[[s[0]*1.75,-s[1]*1.05,0],[s[0]*3,-s[1]*1.05,0]]],{color:16777215,width:1.3,opacity:.9});r.add(c);let l=(e,t,n,i,a,o)=>{let s=new B(this.assets.font,this.assets.fontTexture,{text:e,size:i,align:a,lineHeight:1.5,letterSpacing:.09,color:o});return s.position.set(t,n,0),s.material.uniforms.uAnimationOrder.value=L.GLYPH,s.material.uniforms.uAnimationDirection.value.set(.12,0,0),s.material.uniforms.uAnimationMargin.value=.55,r.add(s),s},u=[l(`${t.id}\n${t.name}`,-s[0]*2.85,s[1]*1.22,.088,`left`,16777215),l(t.temp,s[0]*3.05,s[1]*.49,.075,`left`,16777215),l(`${t.date}\nCLICK TO EXPLORE`,s[0]*3.05,-s[1]*.78,.075,`left`,16777215)],d=l(`${t.id}   ${t.date}`,-s[0]*3.5,-s[1]*1.9,.34,`left`,7106680);d.position.z=-3.2,d.material.uniforms.uAlpha.value=.25,this.iceGroup.add(r),this.blocks.push({root:r,block:a,specimen:o,lines:c,texts:u,ghost:d,project:t})})}setSize(e,t){this.camera.aspect=e/t,this.camera.updateProjectionMatrix(),this.iceMaterial.setSize(e,t),this.backdrop.material.uniforms.uAspect.value=e/t;for(let n of this.blocks)n.lines.setSize(e,t)}setRefractionTexture(e){this.iceMaterial.uniforms.tScene.value=e}setIceVisible(e){for(let t of this.blocks)t.block.visible=e}bindFrost(e){this.iceMaterial.uniforms.tFrost.value=e.texture,this.iceMaterial.uniforms.tFrostNormal.value=e.normalTexture}setRailPosition(e){this._targetScroll=e*(this.blocks.length-1)*at}setReveal(e){this.revealProgress=e}update(e,t,n){this._scroll=M(this._scroll,this._targetScroll,.09,e),this.camera.position.x=this._scroll,this.iceMaterial.update(t,n);for(let e=0;e<this.blocks.length;e++){let n=this.blocks[e],r=1-Math.min(1,Math.abs(n.root.position.x-this._scroll)/at);n.block.rotation.y=t*.16+e*1.7,n.specimen.rotation.y=n.block.rotation.y,n.block.position.y=Math.sin(t*.5+e)*.045,n.specimen.position.y=-.05+n.block.position.y;let i=this.revealProgress*r;n.lines.progress=i;for(let e of n.texts)e.progress=i,e.update(t);n.ghost.progress=i,n.ghost.update(t)}}dispose(){this.iceMaterial.dispose();for(let e of this.blocks)e.block.geometry.dispose(),e.specimen.geometry.dispose()}},ct=document.getElementById(`app`),lt=document.getElementById(`hud`),ut=document.getElementById(`boot`),H=new ee({antialias:!1,powerPreference:`high-performance`,stencil:!1,depth:!0});H.setClearColor(14343640,1),H.outputColorSpace=n,H.toneMapping=0,H.info.autoReset=!1,ct.appendChild(H.domElement);var dt=2,U=Math.min(window.devicePixelRatio||1,dt),ft=performance.now(),pt=ye(64),mt=xe(32),ht=Ce(H,256),gt=we(H,512),_t=Te(H,1024),{texture:vt,font:yt}=Oe({family:`"IBM Plex Mono", ui-monospace, Menlo, monospace`,weight:600,em:44,distanceRange:8}),W=new ke(H,{resolution:512,advectTexture:ht}),bt={envMap:_t,noise:ht,caustics:gt,blueNoise:pt,font:yt,fontTexture:vt,frost:W.texture,frostNormal:W.normalTexture},G=new Ue(H,bt),K=new st(H,bt),q=new Ae(H,{blueNoiseTexture:pt,lutTexture:mt,noiseTexture:ht}),J=j(1,1,{depthBuffer:!0});G.setRefractionTexture(J.texture),K.setRefractionTexture(J.texture);var Y=new de(H.domElement);function xt(){let e=ct.clientWidth,t=ct.clientHeight;U=Math.min(window.devicePixelRatio||1,dt),H.setPixelRatio(U),H.setSize(e,t,!1);let n=Math.round(e*U),r=Math.round(t*U);q.setSize(n,r),J.setSize(Math.max(1,n>>1),Math.max(1,r>>1)),G.setSize(e,t),K.setSize(e,t),W.setSize(e,t),G.particles.setPixelRatio(U)}window.addEventListener(`resize`,xt),xt();var St=2,X=new ue(0,.075),Z=0;window.addEventListener(`wheel`,e=>{Z+=e.deltaY*.0012,Z=Math.max(0,Math.min(St,Z)),X.target=Z},{passive:!0});var Q=null;window.addEventListener(`touchstart`,e=>{Q=e.touches[0].clientY},{passive:!0}),window.addEventListener(`touchmove`,e=>{if(Q===null)return;let t=e.touches[0].clientY;Z=Math.max(0,Math.min(St,Z+(Q-t)*.004)),X.target=Z,Q=t},{passive:!0});var Ct=-1,wt=2.2,Tt=e=>1-(1-e)**3,Et=new te,Dt=0,$=0,Ot=0,kt=0;function At(){requestAnimationFrame(At);let e=Math.min(Et.getDelta(),1/20),t=Et.elapsedTime;Dt++,H.info.reset(),Ct<0&&(Ct=t);let n=Math.min(1,(t-Ct)/wt);Y.update(e),X.update(e),q.setFrame(Dt,t),W.update(e,Y,t),G.bindFrost(W),q.bindFrost(W);let r=X.value,i=e=>Math.min(1,Math.max(0,e)),a=i(r/.72),o=i((r-.66)/.34),s=i((r-.86)/.3),c=i((r-1)/1),l=q.transition.uniforms.uBlueOffset.value;if(G.update(e,t,Y,l),G.setAssembly(a,e),G.headline.progress=Tt(n),K.bindFrost(W),K.setRailPosition(c),K.setReveal(Tt(s)),K.update(e,t,l),G.setIceVisible(!1),H.setRenderTarget(J),H.clear(),H.render(G.scene,G.camera),G.setIceVisible(!0),H.setRenderTarget(q.sceneA),H.clear(),H.render(G.scene,G.camera),o>.001&&(K.setIceVisible(!1),H.setRenderTarget(J),H.clear(),H.render(K.scene,K.camera),K.setIceVisible(!0),H.setRenderTarget(q.sceneB),H.clear(),H.render(K.scene,K.camera)),H.setRenderTarget(null),q.render(o,X.velocity),$+=e,Ot++,$>.5){kt=Math.round(Ot/$),$=0,Ot=0;let e=H.info.render;lt.textContent=`${kt} fps · ${U.toFixed(1)}x dpr · ${e.calls} draws · ${(e.triangles/1e3).toFixed(0)}k tris\nscroll: igloo → ice blocks · move to frost`}}ut.classList.add(`done`),console.info(`[igloo-engine] assets generated in ${(performance.now()-ft).toFixed(0)}ms`),At(),window.engine={renderer:H,scene:G,blockScene:K,frost:W,composer:q,progress:X,pointer:Y};