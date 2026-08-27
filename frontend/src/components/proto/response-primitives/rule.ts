/* The response-primitive level rule.
 *
 * This file is the entire deliverable of Unit 4. Everything else in this
 * directory exists to show that it runs.
 *
 * The question it answers: given a thing a turn wants to show — a paragraph, a
 * table, a chart, a permission prompt, a generated spreadsheet, or a primitive
 * that does not exist yet — where does it go? Inline in the prose, in a
 * bounded block inside the turn, in a side panel, or full screen?
 *
 * The answer is deliberately NOT a function of what the thing IS. `kind` is
 * carried on the descriptor and is never read here; grep this file for it and
 * you will find it only in the type. A chart and a paragraph of the same
 * extent, with the same handling, land in the same place. What decides the
 * level is what the reader has to DO with the payload, and every input below
 * is a property the runtime can already observe in an event rather than a
 * judgement someone has to make at render time.
 *
 * That is the load-bearing claim, and §"Visual-first" in
 * docs/ui-research/04-response-primitives.md is where it is argued against the
 * evidence. The short version: semantic type selects the RENDERER inside a
 * level. It never selects the level.
 */

/** The four surfaces Primnox already has, in ascending order of how much of
 *  the screen they take from the conversation.
 *
 *  - `inline`     the prose measure itself — `md.tsx`
 *  - `block`      a bounded compartment in the turn — ThinkingBlock, PlanBlock,
 *                 ExecutionBlock, Attachment, FlowchartBlock, Canvas/inline
 *  - `panel`      beside the conversation, outliving the turn — Canvas/panel
 *  - `fullscreen` the viewport — AssetViewer, FlowchartBlock's portal
 */
export type Level = 'inline' | 'block' | 'panel' | 'fullscreen';

const ORDER: Level[] = ['inline', 'block', 'panel', 'fullscreen'];
const rank = (l: Level) => ORDER.indexOf(l);

/** How tall the payload actually is, measured — never estimated.
 *
 *  `lines` is the common denominator: rows for a table, entries for a
 *  timeline, series points for a chart, wrapped lines for prose. A primitive
 *  nobody has thought of yet still has an extent, which is why the rule can
 *  place one. */
export type Extent = {
  lines: number;
  /** Present when the payload is two-dimensional. A single column of three
   *  rows reads inline; three columns of three rows does not, because the
   *  prose measure cannot hold a grid without becoming a scroller. */
  cols?: number;
};

/* Where the thresholds come from.
 *
 * INLINE_CEIL is calibrated, not derived: three lines is what fits in a
 * reply's measure without the reader losing the sentence that introduced it.
 * It is an inference, and the doc labels it as one.
 *
 * SCROLLER_AT is the point where a block stops growing the page and starts
 * owning its own scroll region. `md.tsx` already draws this line for tables
 * and code (`overflow-x-auto`); this generalises it to the vertical axis.
 *
 * Deliberately absent: any threshold that promotes to `panel` or
 * `fullscreen`. See `decide()`. */
export const INLINE_CEIL = 3;
export const SCROLLER_AT = 12;

/** One thing a turn wants to show.
 *
 *  The five booleans are the whole input surface. Each is answerable from a
 *  CRS event payload without inspecting the content, which is what keeps the
 *  rule mechanical: two engineers filling this in for the same event get the
 *  same descriptor. */
export type PrimitiveDescriptor = {
  id: string;
  /** For the renderer's switch and for nothing else. `decide()` never reads
   *  it. A kind it has never heard of still gets a level. */
  kind: string;
  label: string;
  extent: Extent;

  /** The turn cannot proceed until the user answers this.
   *  Observable: `permission.request`, `question.asked`. */
  blocking: boolean;

  /** Reading it requires a gesture — pan, zoom, sort, step, scrub, play.
   *  Observable: the renderer for this kind binds pointer handlers. */
  interact: boolean;

  /** It substantiates a claim rather than making one: a tool result, a
   *  citation, a scrub map, a stack trace, a source excerpt.
   *  Observable: it arrived as support for text, not as the text. */
  evidence: boolean;

  /** The user will act on it outside this turn — edit it, download it, cite
   *  it, feed it somewhere. Observable: the payload carries a durable id and
   *  a verb (`workspace.created` is editable; `asset.ready` is downloadable).
   *
   *  Primnox can observe this directly, which is the reason this rule can
   *  afford to be stricter than the shipping assistants — see the doc's
   *  "Why not size" section. */
  handle: boolean;

  /** It has an id that outlives the turn. `turn_workspaces` and `assets` rows
   *  do; a `tool.call` does not. Observable: `turnsFromHistory` in `crs.ts`
   *  rehydrates it, or it does not. */
  persists: boolean;

  /** It conveys meaning through spatial encoding: a chart, a diagram, a map,
   *  an image. Drives the WCAG check below, not the level. */
  visual: boolean;

  /** The text equivalent. WCAG 2.1 §1.1.1 requires one for any non-text
   *  content that carries information, and W3C's complex-image guidance is
   *  specifically that a chart's alternative is the data behind it.
   *  https://www.w3.org/WAI/tutorials/images/complex/ */
  textAlternative?: string;

  /** The prose this payload replaces. Present means the renderer must show
   *  the payload INSTEAD of the sentence, never beside it — Sweller's
   *  redundancy effect. See `Decision.violations`. */
  restates?: string;

  /** Whatever the payload actually is. Untyped on purpose: the rule holds for
   *  primitives this file has never seen. */
  payload?: unknown;
};

/** One input's claim on the level, with the reason attached.
 *
 *  Kept as a list rather than collapsed into a number because a level with no
 *  attributable cause is a level nobody can argue with — and arguing with it
 *  is how the rule gets corrected. */
export type Floor = {
  input: 'extent' | 'interact' | 'evidence' | 'blocking' | 'handle';
  level: Level;
  why: string;
};

export type Decision = {
  level: Level;
  /** Every floor that was raised, in evaluation order. */
  floors: Floor[];
  /** The one that won. Ties break toward the earliest, so the explanation
   *  names the most fundamental cause rather than the last one checked. */
  driver: Floor;
  /** Levels the user may promote this to. Empty means the block is the end of
   *  the road for this payload, and no expand affordance should be drawn. */
  offers: Level[];
  /** The block opens closed. Evidence is meant to be available, not asserted. */
  collapsed: boolean;
  /** The block cannot be collapsed away. A parked turn that can be folded
   *  shut is a turn the user cannot find again. */
  pinned: boolean;
  /** The block owns a scroll region instead of growing the page. */
  scroller: boolean;
  /** Things the descriptor got wrong. These are defects, not preferences —
   *  each one names a rule the payload breaks. */
  violations: string[];
};

/** THE RULE.
 *
 *  Five inputs, each independently imposing a FLOOR. The level is the highest
 *  floor. There is no weighting, no scoring and no tie-break by taste: an
 *  input either claims a level or it does not.
 *
 *  The clamp at the end is the part that matters most, so it is stated twice.
 *  Nothing here ever returns `panel` or `fullscreen`. Those are things the
 *  USER does, and the rule's only say in them is whether to offer the door.
 *
 *  Why: a transcript that rearranges itself around the shape of an answer is
 *  a transcript the reader cannot build a mental model of, which is the
 *  central objection to generative UI and the one its critics have not been
 *  answered on. Primnox's target — familiar at first contact, deeper as the
 *  work gets complex — is served by a transcript that always looks the same
 *  and doors that appear on the things worth opening. */
export function decide(p: PrimitiveDescriptor): Decision {
  const floors: Floor[] = [];

  // 1. Extent. The only input that can hold a payload at `inline`; every
  //    other one is a promotion. A grid is never inline regardless of size,
  //    because the prose measure cannot carry columns.
  const fitsMeasure = p.extent.lines <= INLINE_CEIL && !p.extent.cols;
  floors.push(
    fitsMeasure
      ? { input: 'extent', level: 'inline', why: `${p.extent.lines} line(s), no columns — fits the measure` }
      : { input: 'extent', level: 'block', why: p.extent.cols
          ? `${p.extent.cols} columns — a grid cannot sit in the measure`
          : `${p.extent.lines} lines exceeds the ${INLINE_CEIL}-line measure` },
  );

  // 2. Interaction. Anything the reader has to grab needs a hit area and a
  //    boundary, and inline prose has neither. This is why a map and a chart
  //    with a tooltip end up in a block while a static sparkline need not.
  if (p.interact) {
    floors.push({ input: 'interact', level: 'block', why: 'reading it requires a gesture; a gesture needs a boundary' });
  }

  // 3. Evidence. Support for a claim is not the claim. Giving it a block —
  //    collapsed — is what lets the reader check it without having to read
  //    past it. PrivacyMirrorBlock and ThinkingBlock already do exactly this.
  if (p.evidence) {
    floors.push({ input: 'evidence', level: 'block', why: 'substantiates rather than states — available, not asserted' });
  }

  // 4. Blocking. The turn is parked. This does not raise the level above a
  //    block; it changes the block's manners — see `pinned`.
  if (p.blocking) {
    floors.push({ input: 'blocking', level: 'block', why: 'the turn is parked on it; it must be findable and unfoldable' });
  }

  // 5. Handle or persistence. The one input that opens a door. Note it still
  //    only floors at `block`: an artifact renders in the turn that made it,
  //    and the wider surface is offered rather than taken.
  if (p.handle || p.persists) {
    floors.push({ input: 'handle', level: 'block', why: p.persists
      ? 'outlives the turn — it needs a name the user can come back to'
      : 'the user will act on it elsewhere — it needs a handle' });
  }

  const driver = floors.reduce((a, b) => (rank(b.level) > rank(a.level) ? b : a));

  // THE CLAMP. Said again because it is the rule's teeth: the automatic
  // decision stops at `block`. `panel` and `fullscreen` are user acts.
  const level: Level = rank(driver.level) > rank('block') ? 'block' : driver.level;

  const violations: string[] = [];
  // WCAG 2.1 AA §1.1.1. A chart without its data is not an accessibility
  // shortfall to schedule; it is a payload the renderer should refuse.
  if (p.visual && !p.textAlternative) {
    violations.push('visual payload with no text alternative (WCAG 2.1 §1.1.1)');
  }
  // Sweller's redundancy effect: two channels carrying identical information
  // cost working memory and return nothing. A rich rendering earns its place
  // by REPLACING the sentence, not by illustrating it.
  if (p.restates && level === 'inline') {
    violations.push('restates prose it does not replace — redundancy, not reinforcement');
  }
  // A door onto nothing. Offering a canvas for a payload with no handle is
  // how "open in canvas" becomes noise on every block in the transcript.
  if (p.persists && !p.handle && level === 'inline') {
    violations.push('persists but renders inline — it has no name to come back to');
  }

  return {
    level,
    floors,
    driver,
    // The door is offered on handling, never on size. This is the deliberate
    // divergence from ChatGPT Canvas (>10 lines) and Claude Artifacts (>15
    // lines): those products use size as a proxy for reuse-intent because
    // they cannot see the intent. Primnox can — `workspace.created` and
    // `asset.ready` are separate events from `token`.
    offers: p.handle || p.persists ? ['panel', 'fullscreen'] : [],
    collapsed: p.evidence && !p.blocking,
    pinned: p.blocking,
    scroller: p.extent.lines > SCROLLER_AT || (p.extent.cols ?? 0) > 0,
    violations,
  };
}

/** One sentence naming the level and the reason for it.
 *
 *  Exported because the demo is not the only consumer that should be able to
 *  ask "why is this here" — a devtools overlay and a test assertion both want
 *  this string, and a rule that can only be explained by reading its source
 *  is a rule that will be worked around. */
export function explain(p: PrimitiveDescriptor): string {
  const d = decide(p);
  const door = d.offers.length ? `, offering ${d.offers.join(' / ')}` : '';
  return `${d.level} — ${d.driver.why}${door}`;
}

/** The escape hatch, and the proof that the rule is total.
 *
 *  Anything at all can be levelled: measure it, assume no handling, and the
 *  rule places it. A primitive invented next year renders as bounded,
 *  scrollable, inert text rather than as a crash or a blank space. */
export function describeUnknown(id: string, kind: string, text: string): PrimitiveDescriptor {
  return {
    id,
    kind,
    label: kind,
    extent: { lines: text.split('\n').length },
    blocking: false,
    interact: false,
    evidence: false,
    handle: false,
    persists: false,
    visual: false,
    payload: text,
  };
}
