/* The Part A matrix, as data.
 *
 * Kept apart from the component because the argument this unit is making lives
 * here, not in the rendering. Someone challenging a verdict should be able to
 * read one file, find the cell, and see the citation that put it there —
 * without reading a table layout to do it.
 *
 * Two rules this file exists to hold:
 *
 * 1. Competitor cells are BEHAVIOURS, not scores. "artifacts + publish" is
 *    checkable against Anthropic's help centre. A 4/5 is checkable against
 *    nothing, and a scored matrix invites the reader to sum a column, which is
 *    exactly the marketing document the brief warned against.
 *
 * 2. `UNKNOWN` is a real value and appears eleven times. It means nobody
 *    opened the product to look. It does not mean "probably fine" and nothing
 *    should be built against it.
 *
 * Every source is in docs/ui-research/13-benchmark-roadmap.md under Sources.
 */

export type Verdict =
  | 'BETTER'        // genuinely ahead, and the reason fits in one sentence
  | 'PARITY'        // same outcome, different route
  | 'BEHIND'        // mainstream is simply better; say so
  | 'CONVENTIONAL'  // Primnox should deliberately not innovate here
  | 'N/A'           // a constraint, not a gap
  | 'UNKNOWN';      // not verified

export type Action = 'CHANGE' | 'KEEP' | 'PROTOTYPE' | 'NONE';

export const COMPETITORS = [
  { id: 'chatgpt', label: 'ChatGPT' },
  { id: 'claude', label: 'Claude' },
  { id: 'gemini', label: 'Gemini' },
  { id: 'perplexity', label: 'Perplexity' },
  { id: 'copilot', label: 'Copilot' },
  { id: 'cursor', label: 'Cursor' },
  { id: 'manus', label: 'Manus' },
] as const;

export type CompetitorId = (typeof COMPETITORS)[number]['id'];

export interface Row {
  id: string;
  dimension: string;
  verdict: Verdict;
  /** Primnox's own cell — short enough to scan, honest enough to argue with. */
  primnox: string;
  cells: Record<CompetitorId, string>;
  /** Why the verdict is what it is. Shown on expand. */
  detail: string;
  /** What to do about it, and to which real file. */
  action: Action;
  file: string;
  sources: { label: string; href: string }[];
}

export const ROWS: Row[] = [
  {
    id: 'learning',
    dimension: 'Ease of learning',
    verdict: 'BEHIND',
    primnox: 'Track metaphor is unfamiliar at first contact',
    cells: {
      chatgpt: 'Suggested prompts, sidebar list',
      claude: 'Flat recency + projects',
      gemini: 'Flat recency list',
      perplexity: 'Query-first entry',
      copilot: 'Search-integrated',
      cursor: 'Steep — IDE plus modes',
      manus: 'Medium — agent framing',
    },
    detail:
      "Jakob's Law: users assemble their model of a product from every other product they " +
      'use. Unit 1 called the Dead Reckoning track "incompatible with mainstream expectations" ' +
      'and it is right about the navigational layer. Unit 12 defended the archetype on radius ' +
      'and monospace and is right about the visual layer. Those are different layers, which is ' +
      'what the target statement resolves: the shell should be familiar, the content should not.',
    action: 'KEEP',
    file: 'frontend/src/components/TrackRow.tsx (keep) — first contact is what changes',
    sources: [
      { label: "Laws of UX — Jakob's Law", href: 'https://lawsofux.com/jakobs-law/' },
      { label: 'NN/g — Mental Models', href: 'https://www.nngroup.com/articles/mental-models/' },
    ],
  },
  {
    id: 'speed',
    dimension: 'Speed — first useful output',
    verdict: 'UNKNOWN',
    primnox: 'Depends on local hardware; nothing benchmarked',
    cells: {
      chatgpt: 'UNKNOWN',
      claude: 'UNKNOWN',
      gemini: 'UNKNOWN',
      perplexity: 'Research 3–4 min; Assets 10 min+',
      copilot: 'UNKNOWN',
      cursor: 'UNKNOWN',
      manus: 'Minutes to hours',
    },
    detail:
      'Seven of eight cells are UNKNOWN and must stay that way. Nobody timed any of these. ' +
      'Primnox routes to local models on the user’s own machine, so a single number would ' +
      'not describe it anyway. The honest position is that this row cannot be won or lost until ' +
      'somebody benchmarks it.',
    action: 'NONE',
    file: '— no file; this row is a measurement request, not a design decision',
    sources: [
      {
        label: 'Perplexity — creating assets',
        href: 'https://www.perplexity.ai/help-center/en/articles/12528830-creating-assets-with-perplexity-overview',
      },
    ],
  },
  {
    id: 'speed-observability',
    dimension: 'Speed — observability of',
    verdict: 'BETTER',
    primnox: 'First-token latency and success rate are surfaced',
    cells: {
      chatgpt: 'UNKNOWN',
      claude: 'UNKNOWN',
      gemini: 'UNKNOWN',
      perplexity: 'UNKNOWN',
      copilot: 'UNKNOWN',
      cursor: 'UNKNOWN',
      manus: 'UNKNOWN',
    },
    detail:
      'Split out from the row above on purpose. Primnox is not demonstrably faster than anything ' +
      'here — but MissionControl reports first-token latency, success rate and benched providers, ' +
      'and no competitor was observed exposing equivalent numbers to an end user. Being the only ' +
      'one that shows its working is a smaller claim than being fastest, and it is the one the ' +
      'evidence supports.',
    action: 'KEEP',
    file: 'frontend/src/components/MissionControl.tsx',
    sources: [],
  },
  {
    id: 'discoverability',
    dimension: 'Discoverability',
    verdict: 'BEHIND',
    primnox: 'Hover-gated actions; model selector is a label, not a control',
    cells: {
      chatgpt: 'Model selector in composer',
      claude: 'Model selector in composer',
      gemini: 'Canvas button in prompt bar',
      perplexity: 'Mode selector',
      copilot: 'Tone selector',
      cursor: 'Shift+Tab rotates modes',
      manus: 'Computer panel always visible',
    },
    detail:
      'NN/g Heuristic 6: recognition rather than recall. TurnBlock.tsx:136–141 hides the copy ' +
      'button behind opacity-0 until hover or focus-within — which covers pointer and keyboard ' +
      'and leaves touch with nothing. The composer names the model but will not let you change it.',
    action: 'CHANGE',
    file: 'frontend/src/components/TurnBlock.tsx:136–141, frontend/src/App.tsx (composer)',
    sources: [
      {
        label: 'NN/g — Recognition and Recall',
        href: 'https://www.nngroup.com/articles/recognition-and-recall/',
      },
      { label: 'Cursor — Plan Mode', href: 'https://cursor.com/docs/agent/plan-mode' },
    ],
  },
  {
    id: 'agent-transparency',
    dimension: 'Agent transparency',
    verdict: 'BETTER',
    primnox: 'Four-valued outcomes including "unknown"',
    cells: {
      chatgpt: 'Reasoning summary',
      claude: 'Reasoning summary',
      gemini: 'UNKNOWN',
      perplexity: 'Assets tab of generated files',
      copilot: 'UNKNOWN',
      cursor: 'Diff view + checkpoints',
      manus: 'Computer panel + replayable sessions',
    },
    detail:
      'The strongest genuinely-differentiated row, and currently worth nothing to a user. Manus ' +
      'shows every step and replays sessions; Cursor shows diffs and snapshots agent changes. ' +
      'Neither has a vocabulary for "we do not know what happened". task_state.py does — ' +
      'completed / failed / partial / unknown — because a tool that crashed mid-write did not ' +
      'fail cleanly, and calling it failed invites a destructive blind retry. No UI reads it.',
    action: 'PROTOTYPE',
    file: 'backend/v2/task_state.py — surface via the agent-status layer, not a new nav entry',
    sources: [
      {
        label: 'MIT Tech Review — Manus',
        href: 'https://www.technologyreview.com/2025/03/11/1113133/manus-ai-review/',
      },
      { label: 'Cursor — Checkpoints', href: 'https://docs.cursor.com/agent/chat/checkpoints' },
    ],
  },
  {
    id: 'artifacts',
    dimension: 'Artifact handling',
    verdict: 'BEHIND',
    primnox: 'Canvas has versions; everything else is a modal',
    cells: {
      chatgpt: 'Writing + code blocks, inline',
      claude: 'Artifacts, publish, sidebar section',
      gemini: 'Canvas panel, export to Docs',
      perplexity: 'Assets — PPTX/DOCX/XLSX/HTML',
      copilot: 'Pages, .loop in SharePoint',
      cursor: 'Files in repo + diffs',
      manus: 'Files + replay',
    },
    detail:
      'The gap is real: Canvas.tsx has version history and revert, while SlideDeck, SheetTable, ' +
      'WebPreview and FlowchartBlock open as modals through AssetViewer.tsx with neither. But ' +
      'unit 6 tested the obvious fix and it failed: a unified METADATA layer works, a unified ' +
      'LIFECYCLE does not. Canvas owns its open state and lazy-loads; AssetViewer is ' +
      'parent-controlled and fetches on mount. Build the two layers unit 6 cleared and no more.',
    action: 'CHANGE',
    file: 'ArtifactMetadata + shared ArtifactPreview — NOT a unified component (unit 6 DO NOT)',
    sources: [
      {
        label: 'Anthropic — publish artifacts',
        href: 'https://support.claude.com/en/articles/9547008-publish-and-share-artifacts',
      },
      {
        label: 'Microsoft — Copilot Pages',
        href: 'https://support.microsoft.com/en-us/microsoft-365-copilot/how-microsoft-365-copilot-pages-works',
      },
    ],
  },
  {
    id: 'canvas',
    dimension: 'Canvas workflow',
    verdict: 'CONVENTIONAL',
    primnox: 'Keep canvas narrow — documents only',
    cells: {
      chatgpt: 'DEPRECATED for GPT-5.5+',
      claude: 'Artifacts panel',
      gemini: 'Canvas panel, code + preview',
      perplexity: 'Inline app / dashboard',
      copilot: 'Pages, side by side',
      cursor: 'The editor is the canvas',
      manus: 'UNKNOWN',
    },
    detail:
      'The most consequential finding in the matrix. OpenAI’s help centre states canvas is not ' +
      'supported by GPT-5.5 or later and that writing and coding now happen in inline writing ' +
      'blocks and code blocks. The largest canvas deployment in the world walked it back. Four ' +
      'vendors still ship one, so canvas is not wrong — but "everyone has a canvas, ours should ' +
      'be better" is no longer an argument. The model already agrees: Rich Block precedes ' +
      'Artifact, and Quick preview precedes Canvas.',
    action: 'KEEP',
    file: 'frontend/src/components/Canvas.tsx — scoped to documents, deliberately',
    sources: [
      { label: 'OpenAI — canvas', href: 'https://help.openai.com/en/articles/9930697' },
      {
        label: 'OpenAI — writing and code blocks',
        href: 'https://help.openai.com/en/articles/20001246-working-with-writing-blocks-and-code-blocks-in-chatgpt',
      },
      {
        label: 'Google — Gemini Canvas',
        href: 'https://support.google.com/gemini/answer/16047321',
      },
    ],
  },
  {
    id: 'rich-blocks',
    dimension: 'Rich blocks in the response',
    verdict: 'BEHIND',
    primnox: 'Every non-document goes straight to a modal',
    cells: {
      chatgpt: 'Writing + code blocks, editable inline',
      claude: 'Artifacts open beside the chat',
      gemini: 'Canvas panel',
      perplexity: 'Assets below the query',
      copilot: 'Pages beside the chat',
      cursor: 'Inline diffs in the editor',
      manus: 'UNKNOWN',
    },
    detail:
      'The step the model puts before Artifact and before Canvas, and the one Primnox skips ' +
      'entirely. SlideDeck, SheetTable, WebPreview and FlowchartBlock all exist and are all ' +
      'reachable only as modals. Promoting a modal to a bounded inline block with the modal kept ' +
      'as the expand action is a far smaller change than unifying two surfaces, and it is the one ' +
      'the evidence supports.',
    action: 'PROTOTYPE',
    file: 'SlideDeck.tsx, SheetTable.tsx, WebPreview.tsx, FlowchartBlock.tsx, AssetViewer.tsx',
    sources: [
      {
        label: 'OpenAI — writing and code blocks',
        href: 'https://help.openai.com/en/articles/20001246-working-with-writing-blocks-and-code-blocks-in-chatgpt',
      },
    ],
  },
  {
    id: 'visual',
    dimension: 'Visual comprehension',
    verdict: 'BETTER',
    primnox: '0 contrast failures across 19 text styles; state in form before hue',
    cells: {
      chatgpt: 'UNKNOWN',
      claude: 'UNKNOWN',
      gemini: 'UNKNOWN',
      perplexity: 'UNKNOWN',
      copilot: 'UNKNOWN',
      cursor: 'UNKNOWN',
      manus: 'UNKNOWN',
    },
    detail:
      'Every competitor cell is UNKNOWN and must stay UNKNOWN — nobody measured their contrast ' +
      'ratios. Primnox is not necessarily more legible than they are. It is the only one of the ' +
      'eight where somebody wrote the number down: DESIGN.md records /50 = 4.61:1, 71 sub-floor ' +
      'usages raised, 0 failures. That is a real advantage and a smaller one than it sounds.',
    action: 'KEEP',
    file: 'DESIGN.md:121–128',
    sources: [],
  },
  {
    id: 'customisation',
    dimension: 'Customisation',
    verdict: 'BETTER',
    primnox: 'Provider, model, routing, ten themes — structural, not a UI win',
    cells: {
      chatgpt: 'Custom instructions, Projects',
      claude: 'Projects, styles',
      gemini: 'Gems',
      perplexity: 'Spaces + custom instructions',
      copilot: 'Tenant policy',
      cursor: 'Rules, model choice',
      manus: 'UNKNOWN',
    },
    detail:
      'ChatGPT Projects and Perplexity Spaces are deep customisation surfaces. None of them lets ' +
      'you choose the model vendor, because none of them can. Primnox wins this row by ' +
      'architecture — PRODUCT.md commits to running fully local, any provider — so the UI’s job ' +
      'is only to not squander it, which it partly does by leaving the model as a dead label.',
    action: 'KEEP',
    file: 'OmniRoute.tsx, ModelProfiles.tsx, Tunables.tsx, ThemePicker.tsx',
    sources: [
      {
        label: 'OpenAI — Projects',
        href: 'https://help.openai.com/en/articles/10169521-using-projects-in-chatgpt',
      },
      {
        label: 'Perplexity — Spaces',
        href: 'https://www.perplexity.ai/help-center/en/articles/10352961-what-are-spaces',
      },
    ],
  },
  {
    id: 'scalability',
    dimension: 'Scalability — many objects',
    verdict: 'BEHIND',
    primnox: 'Folders and pinning; no Project object',
    cells: {
      chatgpt: 'Projects, project-only memory',
      claude: 'Projects',
      gemini: 'UNKNOWN',
      perplexity: 'Spaces, Brain tab, Tasks',
      copilot: 'Pages in SharePoint, audited',
      cursor: 'Workspaces / repos',
      manus: 'UNKNOWN',
    },
    detail:
      'Five of seven competitors converged on a project object, which is about as strong as ' +
      'convergent evidence gets. The model ends "Persistent object → Project" and that arrow ' +
      'points at nothing. It belongs in V2, not MVP: a Project is a container of persistent ' +
      'objects, and there is no common shape for a persistent object until ArtifactMetadata ' +
      'exists. Build it first and you get a folder with a nicer name.',
    action: 'PROTOTYPE',
    file: 'new surface; backend/v2/world_model.py already scopes facts by project',
    sources: [
      {
        label: 'OpenAI — Projects',
        href: 'https://help.openai.com/en/articles/10169521-using-projects-in-chatgpt',
      },
    ],
  },
  {
    id: 'mobile',
    dimension: 'Mobile usability',
    verdict: 'N/A',
    primnox: 'No mobile client; backend is loopback-only',
    cells: {
      chatgpt: 'Native apps',
      claude: 'Native apps',
      gemini: 'Native apps',
      perplexity: 'Native apps',
      copilot: 'Native apps',
      cursor: 'Desktop IDE',
      manus: 'Web',
    },
    detail:
      'Not a gap — a constraint. PRODUCT.md: the backend binds localhost and verifies Origin on ' +
      'every request, and the shell is a Windows Tauri app. A mobile client is a different ' +
      'architecture, not an unbuilt feature. Unit 5’s bottom sheets and swipe gestures describe ' +
      'a device class Primnox does not ship to. The one part that applies today is the ' +
      'touch-capable laptop, which is exactly what breaks the hover-gated copy button.',
    action: 'NONE',
    file: 'PRODUCT.md:54, PRODUCT.md:79 — keep unit 5 Part 3 as research, do not schedule',
    sources: [],
  },
  {
    id: 'cognitive-load',
    dimension: 'Cognitive load',
    verdict: 'BEHIND',
    primnox: 'ContextRail shows 15+ data points during a 2s turn',
    cells: {
      chatgpt: 'Progressive',
      claude: 'Progressive',
      gemini: 'Progressive',
      perplexity: 'Progressive',
      copilot: 'Progressive',
      cursor: 'High by design',
      manus: 'Medium',
    },
    detail:
      'Unit 7 counted it: stream cursor position and socket state are on screen during a ' +
      'two-second turn. Its Glance / Expand / Deep-Inspect hierarchy is the fix and matches unit ' +
      "8's five-level cascade. This is the load-bearing MVP item — level 2 IS the orthogonal " +
      'agent layer. Without it, the next person surfacing long-running work reaches for a fifth ' +
      "entry in AppRail's Section union, and the orthogonality is gone permanently.",
    action: 'CHANGE',
    file: 'frontend/src/components/ContextRail.tsx:55–162, TurnBlock.tsx LiveStatus',
    sources: [
      {
        label: 'NN/g — Progressive Disclosure',
        href: 'https://www.nngroup.com/articles/progressive-disclosure/',
      },
    ],
  },
];

/* Filters, as the three questions a reader actually arrives with.
 *
 * Not "sort by score". A reader opening a competitive matrix wants to know
 * where they are exposed, where they can push, and what the research failed to
 * establish — and the third is the one a scored table can never answer. */
export const FILTERS = [
  { id: 'all', label: 'All rows', match: () => true },
  { id: 'ahead', label: 'Where Primnox is ahead', match: (r: Row) => r.verdict === 'BETTER' },
  { id: 'behind', label: 'Where Primnox is behind', match: (r: Row) => r.verdict === 'BEHIND' },
  {
    id: 'unverified',
    label: 'Rows with unverified cells',
    match: (r: Row) =>
      r.verdict === 'UNKNOWN' || Object.values(r.cells).some((c) => c === 'UNKNOWN'),
  },
] as const;

export type FilterId = (typeof FILTERS)[number]['id'];

export const UNKNOWN_CELL_COUNT = ROWS.reduce(
  (n, r) => n + Object.values(r.cells).filter((c) => c === 'UNKNOWN').length,
  0,
);
