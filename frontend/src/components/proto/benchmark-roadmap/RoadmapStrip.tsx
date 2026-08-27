import { Chip, Panel, SectionHeader } from '../../ui';

/* The roadmap, rendered as three columns rather than one list.
 *
 * A numbered list implies "do these in order", which is the wrong reading:
 * M1, M2, M3 and M4 have no dependency on each other and could ship in any
 * order or in parallel. What actually constrains the sequence is the two edges
 * called out at the bottom, and burying those in a list is how a roadmap gets
 * reordered by whoever is free that week.
 *
 * `unblocks` is a required field on every item on purpose. An item that
 * unblocks nothing and is not itself the deliverable is an item somebody wanted
 * rather than an item somebody needed.
 */

interface Item {
  id: string;
  title: string;
  action: 'CHANGE' | 'KEEP' | 'PROTOTYPE' | 'SCOPING';
  file: string;
  depends: string;
  unblocks: string;
}

const MVP: Item[] = [
  {
    id: 'M0',
    title: 'Correct the gap list',
    action: 'SCOPING',
    file: 'TurnBlock.tsx:138 (copy exists), App.tsx:479–500 (search exists)',
    depends: '—',
    unblocks: 'a third of unit 1’s Phase 1, freed for the items below',
  },
  {
    id: 'M1',
    title: 'Message actions always visible; add regenerate',
    action: 'CHANGE',
    file: 'frontend/src/components/TurnBlock.tsx:136–141',
    depends: '—',
    unblocks: 'the “familiar at first contact” half of the target statement',
  },
  {
    id: 'M2',
    title: 'Composer model label becomes a selector',
    action: 'CHANGE',
    file: 'frontend/src/App.tsx (composer control row)',
    depends: '—',
    unblocks: 'the one architectural edge over every mainstream competitor',
  },
  {
    id: 'M3',
    title: 'AgentStatus levels 1 and 2',
    action: 'CHANGE',
    file: 'TurnBlock.tsx LiveStatus, ContextRail.tsx:55–162',
    depends: '—',
    unblocks: 'EVERYTHING in the agent layer — level 2 is the orthogonal layer',
  },
  {
    id: 'M4',
    title: 'ArtifactMetadata + one shared preview renderer',
    action: 'CHANGE',
    file: 'new shared module; Canvas.tsx and AssetViewer.tsx both consume it',
    depends: 'lands after M3 so level 2 has a shape to render',
    unblocks: 'M5, V4, and the Quick-preview node of the model',
  },
  {
    id: 'M5',
    title: 'Slides, sheets, previews and flowcharts render inline',
    action: 'PROTOTYPE',
    file: 'SlideDeck / SheetTable / WebPreview / FlowchartBlock, AssetViewer.tsx',
    depends: 'M4',
    unblocks: 'the Rich Block node — the step Primnox currently skips entirely',
  },
];

const V2: Item[] = [
  {
    id: 'V1',
    title: 'Task panel + catch-up summary',
    action: 'PROTOTYPE',
    file: 'backend/v2/task_state.py — four-valued outcomes, verify() before retry',
    depends: 'M3, hard — or it becomes a fifth nav destination',
    unblocks: 'the matrix’s one genuinely differentiated row, and V5',
  },
  {
    id: 'V2',
    title: 'Light theme as an accessibility accommodation',
    action: 'CHANGE',
    file: 'frontend/src/styles/themes.css — re-verify every ratio',
    depends: '—',
    unblocks: 'nothing; it closes a compliance gap (unit 12’s one CHANGE of three)',
  },
  {
    id: 'V3',
    title: 'Approval gate, with the diff as a rich block',
    action: 'PROTOTYPE',
    file: 'unit 2’s coding-agents prototype → workspace approval state',
    depends: 'M5 — or the diff becomes a sixth one-off modal',
    unblocks: 'the Action branch of { Text | Rich Block | Action }',
  },
  {
    id: 'V4',
    title: 'The Project object',
    action: 'PROTOTYPE',
    file: 'new surface; world_model.py already scopes facts by project',
    depends: 'M4 — a Project contains persistent objects',
    unblocks: 'the final Persistent object → Project arrow of the model',
  },
  {
    id: 'V5',
    title: 'Citation and provenance blocks',
    action: 'PROTOTYPE',
    file: 'backend/v2/world_model.py — six schema gaps first (unit 3)',
    depends: 'M5 for the block, V1 for the pattern',
    unblocks: 'the trust argument for a local-first assistant',
  },
];

const FUTURE: { title: string; why: string }[] = [
  {
    title: 'Episodic timeline — “what was I doing yesterday”',
    why: 'Needs V1 as a home. And nobody measured how often a user returns after a gap — episodes.py picks 30 minutes as an assumption, not a finding.',
  },
  {
    title: 'Voice input',
    why: 'Unit 11 leaves local-vs-cloud undecided, and a cloud default contradicts PRODUCT.md’s “local is the default, not the fallback”.',
  },
  {
    title: 'Mobile client',
    why: 'Blocked by the loopback-only backend. An architecture decision nobody asked for, not a backlog item.',
  },
  {
    title: 'Parallel / delegated agent sessions',
    why: 'Needs task-switching UI. V1 deliberately ships one active task. Prove one first.',
  },
  {
    title: 'Published / shareable artifacts',
    why: 'Claude and Copilot are network products. A loopback-only app publishing to the internet is a new trust boundary, and PRODUCT.md requires every boundary to be measured.',
  },
  {
    title: 'Unified Canvas / AssetViewer component',
    why: 'STRUCK from every horizon. Unit 6 built it and it failed. Listing it as “future” lets it return as an aspiration.',
  },
];

function ItemRow({ item }: { item: Item }) {
  return (
    <li className="border-b border-on-surface/10 px-4 py-3 last:border-b-0">
      <div className="flex items-baseline gap-2">
        <span className="shrink-0 font-mono text-[10px] tabular-nums text-on-surface/50">
          {item.id}
        </span>
        <span className="text-[12px] leading-snug text-on-surface">{item.title}</span>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <Chip tone={item.action === 'CHANGE' ? 'primary' : 'neutral'}>{item.action}</Chip>
        <span className="min-w-0 font-mono text-[10px] leading-snug text-on-surface/55">
          {item.file}
        </span>
      </div>
      <dl className="mt-2 space-y-0.5 text-[11px] leading-snug">
        <div className="flex gap-2">
          <dt className="w-[5rem] shrink-0 text-on-surface/50">depends on</dt>
          <dd className="text-on-surface/70">{item.depends}</dd>
        </div>
        <div className="flex gap-2">
          <dt className="w-[5rem] shrink-0 text-on-surface/50">unblocks</dt>
          <dd className="text-on-surface/70">{item.unblocks}</dd>
        </div>
      </dl>
    </li>
  );
}

export function RoadmapStrip() {
  return (
    <div className="h-full overflow-auto bg-bg text-on-surface">
      <div className="space-y-5 px-6 py-5">
        <SectionHeader
          title="Unit 13 — roadmap"
          level={2}
          note="Sequenced by dependency and evidence of value, not by ease. Every item states what it unblocks; an item that unblocks nothing is an item somebody wanted rather than needed."
        />

        <div className="grid gap-4 lg:grid-cols-3">
          <Panel variant="bare" className="min-w-0">
            <div className="border-b border-on-surface/15 px-4 py-3">
              <h3 className="px-eyebrow">MVP — the smallest set that delivers the target</h3>
              <p className="mt-1 text-[11px] leading-snug text-on-surface/55">
                Five items, four of them code. M1–M4 have no dependency on each other.
              </p>
            </div>
            <ul>
              {MVP.map((i) => (
                <ItemRow key={i.id} item={i} />
              ))}
            </ul>
          </Panel>

          <Panel variant="bare" className="min-w-0">
            <div className="border-b border-on-surface/15 px-4 py-3">
              <h3 className="px-eyebrow">V2 — once the MVP is proven</h3>
              <p className="mt-1 text-[11px] leading-snug text-on-surface/55">
                Proven means: level 2 is where people look when a turn runs long, and inline blocks
                beat the modals they replaced.
              </p>
            </div>
            <ul>
              {V2.map((i) => (
                <ItemRow key={i.id} item={i} />
              ))}
            </ul>
          </Panel>

          <Panel variant="bare" className="min-w-0">
            <div className="border-b border-on-surface/15 px-4 py-3">
              <h3 className="px-eyebrow">Future — worth wanting, not worth building</h3>
              <p className="mt-1 text-[11px] leading-snug text-on-surface/55">
                Each fails at least one of: no proven dependency below it, nobody measured demand, or
                a constraint blocks it.
              </p>
            </div>
            <ul>
              {FUTURE.map((f) => (
                <li key={f.title} className="border-b border-on-surface/10 px-4 py-3 last:border-b-0">
                  <p className="text-[12px] leading-snug text-on-surface">{f.title}</p>
                  <p className="mt-1 text-[11px] leading-snug text-on-surface/60">{f.why}</p>
                </li>
              ))}
            </ul>
          </Panel>
        </div>

        {/* Stated separately and last, because these two edges are the whole
            sequencing argument and a three-column layout hides them. */}
        <Panel variant="bare" className="space-y-2 p-4">
          <SectionHeader
            title="The two edges that actually constrain the order"
            level={3}
          />
          <p className="text-[12px] leading-relaxed text-on-surface/70">
            <span className="font-mono text-[11px] text-on-surface">M3 → V1</span> — or agent work
            becomes a nav destination and the model breaks. A rail entry is easier to build than a
            layer, which is why this is the edge most likely to be got wrong under schedule pressure.
          </p>
          <p className="text-[12px] leading-relaxed text-on-surface/70">
            <span className="font-mono text-[11px] text-on-surface">M4 → M5 → V3 / V4</span> — or
            every artifact type gets its own bespoke surface, which is the condition Primnox is
            already in.
          </p>
        </Panel>
      </div>
    </div>
  );
}
