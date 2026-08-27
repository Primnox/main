import type { PrimitiveDescriptor } from './rule';

/* The bench.
 *
 * Every primitive named in Unit 4's brief, described rather than designed.
 * The point of the list is that no entry here was placed by hand: each one
 * carries measurements and five booleans, and `decide()` puts it somewhere.
 * If a row lands in the wrong place, the argument is about the descriptor,
 * not about the layout — which is the whole reason for having a rule.
 *
 * Hardcoded and inert. Nothing in this directory talks to the backend. */

export const BENCH: PrimitiveDescriptor[] = [
  {
    id: 'p-text',
    kind: 'text',
    label: 'Plain answer',
    extent: { lines: 2 },
    blocking: false, interact: false, evidence: false, handle: false, persists: false,
    visual: false,
    payload:
      'The scrub map never leaves the machine. It is emitted over the local socket only, ' +
      'which is why the placeholder and the original can both be shown here.',
  },
  {
    id: 'p-heading',
    kind: 'heading',
    label: 'Heading',
    extent: { lines: 1 },
    blocking: false, interact: false, evidence: false, handle: false, persists: false,
    visual: false,
    payload: 'What the runtime actually stored',
  },
  {
    id: 'p-command',
    kind: 'command',
    label: 'One shell command',
    extent: { lines: 1 },
    blocking: false, interact: false, evidence: false, handle: false, persists: false,
    visual: false,
    payload: 'primnox vault status --json',
  },
  {
    id: 'p-code-short',
    kind: 'code',
    label: 'Three-line snippet',
    extent: { lines: 3 },
    blocking: false, interact: false, evidence: false, handle: false, persists: false,
    visual: false,
    payload: 'const s = emptyState();\nconst next = reduce(s, event);\nrender(next);',
  },
  {
    id: 'p-code-long',
    kind: 'code',
    label: 'A module the user asked for',
    extent: { lines: 34 },
    // `handle` is what separates this from the snippet above, and it is
    // observable: the turn emitted `workspace.created`, so the runtime already
    // knows the user is meant to take this away.
    blocking: false, interact: false, evidence: false, handle: true, persists: true,
    visual: false,
    payload:
      "export function reduce(state, e) {\n" +
      "  const seq = e.sequence;\n" +
      "  const cursor = seq != null && seq > state.cursor ? seq : state.cursor;\n" +
      "  const s = { ...state, cursor };\n" +
      "  if (e.scope !== 'conversation' || !e.turn_id) return s;\n" +
      "  // … 29 more lines\n" +
      "}",
  },
  {
    id: 'p-table',
    kind: 'table',
    label: 'Provider comparison',
    extent: { lines: 4, cols: 4 },
    blocking: false, interact: false, evidence: false, handle: false, persists: false,
    visual: false,
    payload: {
      header: ['Profile', 'Tool calling', 'Vision', 'Context'],
      rows: [
        ['local-qwen', 'emulated', 'none', '32,768'],
        ['anthropic', 'native', 'native', '200,000'],
        ['openrouter', 'native', 'native', '128,000'],
        ['ollama-llama', 'emulated', 'none', '8,192'],
      ],
    },
  },
  {
    id: 'p-chart',
    kind: 'chart',
    label: 'First-token latency by profile',
    extent: { lines: 4 },
    blocking: false, interact: false, evidence: false, handle: false, persists: false,
    visual: true,
    // The rule refuses a visual payload without this. Note it is the DATA, not
    // a description of the picture — W3C's complex-image guidance is explicit
    // that a chart's long description is the table behind it.
    textAlternative:
      'local-qwen 210 ms; anthropic 640 ms; openrouter 890 ms; ollama-llama 1,450 ms.',
    restates: 'The local profile answers first by a wide margin.',
    payload: {
      unit: 'ms',
      series: [
        { label: 'local-qwen', value: 210 },
        { label: 'anthropic', value: 640 },
        { label: 'openrouter', value: 890 },
        { label: 'ollama-llama', value: 1450 },
      ],
    },
  },
  {
    id: 'p-checklist',
    kind: 'checklist',
    label: 'Plan for this turn',
    extent: { lines: 4 },
    blocking: false, interact: false, evidence: false, handle: false, persists: false,
    visual: false,
    payload: [
      { text: 'Read the vault header', done: true },
      { text: 'Confirm the keychain entry exists', done: true },
      { text: 'Re-derive the key from the mnemonic', done: false },
      { text: 'Report which of the three failed', done: false },
    ],
  },
  {
    id: 'p-citation',
    kind: 'citation',
    label: 'Sources for the claim above',
    extent: { lines: 3 },
    // Evidence: it supports the sentence, it is not the sentence. That is what
    // gets it a block, and a collapsed one.
    blocking: false, interact: false, evidence: true, handle: false, persists: false,
    visual: false,
    payload: [
      { title: 'CONVERSATION_RUNTIME_SPEC.md §8.4.3', detail: 'the client never synthesises state' },
      { title: 'crs.ts:209 — case "token"', detail: 'append-only; never replaces delivered text' },
      { title: 'test_reconnect_replay.py', detail: 'proves the cursor survives a socket drop' },
    ],
  },
  {
    id: 'p-tool-result',
    kind: 'tool_result',
    label: 'graph.query returned 12 nodes',
    extent: { lines: 12 },
    blocking: false, interact: false, evidence: true, handle: false, persists: false,
    visual: false,
    payload:
      'node  crs.reduce            fold, 41 refs\n' +
      'node  CrsSocket.drain       buffer flush\n' +
      'node  turnsFromHistory      rehydration\n' +
      '… 9 more',
  },
  {
    id: 'p-permission',
    kind: 'permission',
    label: 'Run shell command in the sandbox?',
    extent: { lines: 2 },
    // Blocking. It does not get a bigger surface — it gets a block that cannot
    // be folded away, which is a different thing and the one that matters.
    blocking: true, interact: false, evidence: false, handle: false, persists: false,
    visual: false,
    payload: {
      detail: 'python -c "import sqlite3; …" inside the AppContainer, no network.',
      options: [{ id: 'once', label: 'Allow once' }, { id: 'deny', label: 'Deny' }],
    },
  },
  {
    id: 'p-form',
    kind: 'form',
    label: 'Which database, and what retention?',
    extent: { lines: 3 },
    blocking: true, interact: true, evidence: false, handle: false, persists: false,
    visual: false,
    payload: {
      detail: 'Two answers are needed before the migration can be planned.',
      options: [{ id: 'primnox', label: 'primnox.db' }, { id: 'other', label: 'Somewhere else' }],
    },
  },
  {
    id: 'p-map',
    kind: 'map',
    label: 'Where the three replicas live',
    extent: { lines: 8 },
    blocking: false, interact: true, evidence: false, handle: false, persists: false,
    visual: true,
    textAlternative: 'Replicas in Dublin, Oregon and Singapore; the Dublin node is primary.',
    payload: { places: ['Dublin (primary)', 'Oregon', 'Singapore'] },
  },
  {
    id: 'p-timeline',
    kind: 'timeline',
    label: 'What this turn did, in order',
    extent: { lines: 5 },
    blocking: false, interact: false, evidence: true, handle: false, persists: false,
    visual: false,
    payload: [
      { at: '+0.0s', text: 'context assembled — 4 memories, 2 assets' },
      { at: '+0.4s', text: 'scrub replaced 3 values' },
      { at: '+1.1s', text: 'first token' },
      { at: '+6.8s', text: 'sandbox execution started' },
      { at: '+9.2s', text: 'completed' },
    ],
  },
  {
    id: 'p-spreadsheet',
    kind: 'spreadsheet',
    label: 'quarterly-routing.xlsx',
    extent: { lines: 240, cols: 7 },
    blocking: false, interact: false, evidence: false, handle: true, persists: true,
    visual: false,
    payload: { rows: 240, cols: 7, bytes: 48_112 },
  },
  {
    id: 'p-deck',
    kind: 'slides',
    label: 'runtime-overview.pptx',
    extent: { lines: 18 },
    blocking: false, interact: true, evidence: false, handle: true, persists: true,
    visual: true,
    textAlternative: '18 slides: the event protocol, the fold, the reconnect path, the test layers.',
    payload: { slides: 18 },
  },
  {
    id: 'p-progress',
    kind: 'progress',
    label: 'Ingesting 340 documents',
    extent: { lines: 1 },
    // One line, no handle, nothing to check — so it stays inline, which is
    // exactly what a progress indicator should do. A determinate progress bar
    // that claims a compartment is a compartment that empties itself.
    blocking: false, interact: false, evidence: false, handle: false, persists: false,
    visual: false,
    payload: { done: 214, total: 340 },
  },
  {
    id: 'p-reasoning',
    kind: 'reasoning',
    label: 'Thinking',
    extent: { lines: 22 },
    blocking: false, interact: false, evidence: true, handle: false, persists: false,
    visual: false,
    payload:
      'The user said "the vault", but there are two things that could mean: the\n' +
      'encrypted database and the OS keychain entry that holds its key. The\n' +
      'error they pasted names a keychain code, so it is the second…',
  },
  {
    id: 'p-warning',
    kind: 'warning',
    label: 'Two of eight documents were skipped',
    extent: { lines: 2 },
    blocking: false, interact: false, evidence: false, handle: false, persists: false,
    visual: false,
    payload: 'scan-07.pdf and scan-08.pdf are image-only and no OCR engine is installed.',
  },
  {
    id: 'p-error',
    kind: 'error',
    label: 'Turn failed — provider_unreachable',
    extent: { lines: 4 },
    // Evidence, because the trace substantiates the failure. It is not
    // blocking: nothing is waiting on the user, the turn is already over.
    blocking: false, interact: false, evidence: true, handle: false, persists: false,
    visual: false,
    payload:
      'provider_unreachable — anthropic\n' +
      'circuit open, 47s remaining, 3 consecutive failures\n' +
      'last error: ECONNREFUSED 127.0.0.1:11434\n' +
      'retryable: yes',
  },
];

/* The primitive nobody has thought of yet.
 *
 * Not in BENCH, because the demo introduces it separately: the point it makes
 * is that the rule is total, and that lands better after the bench has shown
 * what it does with things it recognises. */
export const UNKNOWN_TEXT =
  'plan.horizon = 6 weeks\n' +
  'plan.confidence = 0.41 (below the 0.6 floor)\n' +
  'plan.branches = 3\n' +
  'plan.blocked_on = ["vault recovery", "OCR engine"]';
