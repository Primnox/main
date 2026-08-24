# Design — Primnox V2

<!-- impeccable:design-schema 1 -->

UNIT / PRIMNOX-V2 · REV 2.0 · SUBSTRATE / DEACTIVATED CRT

## The world

**Tactical Telemetry.** A dark substrate, white phosphor, one hazard accent,
monospace by default, and no radius anywhere.

This replaced *Dead Reckoning* (seed f80a4f36) and the ten palettes ported from
primnox.github.io. Not a theme beside them — instead of them. Ten palettes,
four of them light, is the opposite of committing to an aesthetic: every
component had to decide twice and committed to neither.

The archetype fits what Primnox already is. It is a local runtime that reports
on itself — routing chains, circuit breakers, first-token latency, sandbox
boundaries — and a terminal is the honest shape for an instrument that spends
its time telling you what it just did.

## Substrate

| Token | Value | Role |
|---|---|---|
| `--bg` | `#0A0A0A` | Deactivated CRT. Never pure black. |
| `--text` | `#EAEAEA` | White phosphor. 16.46:1. |
| `--muted` | `rgba(234,234,234,0.62)` | Secondary. 6.53:1. |
| `--primary` / `--accent` | `#FF2A2A` | Hazard red **as text**. 5.30:1. |
| p-line / a-pill families | `#E61919` | Hazard red **as structure**. 4.26:1. |
| `--green` | `#4AF626` | Terminal green, rationed. |

**One accent, two legal values.** Both reds are named in the archetype. The
split is a measurement, not a preference: `#E61919` is 4.26:1 on this
substrate, which is fine for a rule, a fill or a border and fails WCAG AA for
text. `#FF2A2A` is 5.30:1 and clears it. So text takes the brighter one and
structure keeps the deeper one. Still one hue.

**Terminal green appears on exactly one class of element** — reachable,
healthy, connected. A terminal green that spreads is a second accent, and the
archetype has room for one.

**`tactical-dim`** (`#121212`) is the only variant. Substrate only; every other
decision is identical, which is what makes it a variant rather than a second
theme.

## Typography

| Role | Face | Treatment |
|---|---|---|
| Macro / display | **Syne 800** | Uppercase, `clamp()`, `-0.033em`, line-height 0.9 |
| Interface, data, telemetry | **JetBrains Mono** | Uppercase for labels, `0.12em`–`0.2em` tracking, 10–12px |
| Long-form reading | **DM Sans** | `.px-prose`, opted into by name |

All three are self-hosted in `public/fonts`. Syne carries macro-typography
rather than a system heavy sans, because "the closest installed font" is a
failure rather than a fallback.

### The documented exception

The interface is monospace: labels, controls, tables, navigation, telemetry.
**Long-form reading is not.** A 900-word guide or a model's reply set in a
terminal face is archetype compliance bought with the thing the text exists to
do, and this app is mostly reading.

`.px-prose` is applied deliberately and by name — currently the guide bodies
and the assistant reply. Nothing inherits it. A surface that wants out of the
terminal face has to say so.

## Geometry

**Zero radius, enforced structurally.** `--radius-control` and `--radius-panel`
are `0`, *and* Tailwind's entire `borderRadius` scale is overridden to `0` —
`rounded-lg`, `rounded-full` and `rounded-2xl` all resolve to a right angle.

That belt-and-braces is deliberate. A token nobody is obliged to use enforces
nothing: 141 `rounded-*` calls across the components would have kept their
curves out of habit, including the ones written next week by someone who never
read this file. Verified in the running app: **0 elements with a non-zero
computed border-radius.**

**No soft shadow.** `--shadow-panel` is an inset hairline. Compartments are
bounded, not floating. No gradients — `.px-panel` was a 145° linear-gradient
and is now a flat field with a 1px lip.

## Substrate texture

Two fixed, pointer-transparent layers under the content:

- **Scanlines** — `repeating-linear-gradient`, 3px period. At 2px it moirés
  against text baselines on a 1× display, which reads as shimmer rather than
  as a scanline.
- **Grain** — inline SVG `feTurbulence` at 3.5% with `mix-blend-mode: overlay`.
  No request, scales to any DPI, and cannot band the way a tiled bitmap does
  across a large dark field.

Neither moves. The trap is building a screensaver: a scanline you notice has
stopped being a substrate and started being an effect.

## Framing utilities

`.px-bracket` (`[ ]` via `::before`/`::after`, so the label stays one string
and a screen reader does not announce "left square bracket"), `.px-crosshair`
(`+` at a grid intersection), `.px-grid-hairline` (`gap: 1px` over a
contrasting parent — the archetype's own engineering directive, giving exact
1px rules with no border arithmetic and no doubled edges).

## Motion

State only. `.px-breathe` on the node currently serving a turn — a swell reads
as *working* where a static highlight reads as *selected*. `.px-sleep` for a
local model installed but not resident: greying out says "broken", a slow fade
says "idle, will wake". Latency counts up rather than snapping.

All of it off under `prefers-reduced-motion`, except the spinner, which slows
to 2.4s rather than stopping — a progress indicator that stops turning reads as
a hang.

## Accessibility

**WCAG 2.1 AA**, per PRODUCT.md, treated as a defect line rather than a polish
item. Measured in the running app rather than assumed.

The phosphor ramp on this substrate: `/40` = 3.35, `/45` = 3.94, **`/50` =
4.61**, `/60` = 6.20. **`/50` is the floor** for body text and 71 sub-floor
class usages were raised to it across the components, `App.tsx` and `md.tsx`.

Current state: **0 contrast failures across 19 distinct text styles.**

## What this world refuses

Gradients. Soft drop shadows. Translucent "glass". Border radius of any value.
A second accent. Light substrates. Quality ratings Primnox never measured, and
throughput figures nothing timed.
