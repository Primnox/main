# Research & Build Agents Prototype

This prototype demonstrates Primnox's integration with research & build agents (Perplexity, Manus, Lovable, v0, AI Studio).

## Features

- **Citation Tracking**: Inline [1] [2] markers map to expandable source list
- **Source Panel**: Full details on each citation with URL, title, snippet, reliability
- **Execution Traces**: Shows tool invocations (web fetch, code execution) with timing
- **Trust Signals**: Verified ✓, trusted ◆, unverified ○ indicators
- **Freshness Tracking**: Retrieved timestamps and TTL-based refresh prompts
- **Multi-Format Results**: Synthesis, code examples, and analysis

## Components

### ResearchPanel
Main container. Handles:
- Search input (takes a query, loads demo data on submit)
- Result display
- Source panel expansion
- Age tracking and refresh UI

### ResultBlock
Individual research result. Shows:
- Result type (synthesis/code/analysis) with icon
- Confidence score
- Content with inline citation markers
- Citation summary bar

### CitationInline
Numbered citation marker [1], [2], etc. Features:
- Hover preview with title, snippet, URL
- Selected state highlighting
- Reliability indicator

### SourcePanel
Expandable list of all sources. Shows:
- Source type icon (web, code, tool, execution)
- URL/file path with domain or filename
- Title and snippet preview
- Reliability status
- Retrieved timestamp
- Direct/synthesized/inferred type
- "Refresh" button if stale

### ExecutionBlock
Tool execution trace. Shows:
- Tool type (fetch, python_exec, node_exec, shell)
- Status (success ✓, error ⚠, timeout ⏱)
- Expandable input/output/error/timing details

## How to Run

### Option 1: In main dev server
```bash
npm run dev

# Navigate to http://localhost:5173
# Components available via import
```

### Option 2: As isolated prototype
```bash
# This requires a separate .claude/proto-config.json pointing to port 5303
# For now, import into App.tsx or use ?proto=research-build-agents route param
```

## Demo Data

`demo.json` contains a sample research result about "How do I use async/await in Python?"

When you click "Search", it loads this sample data, demonstrating:

1. **Multi-part results**: Synthesis, code example, analysis
2. **Citation mapping**: Results reference sources [1], [2], [3], [4]
3. **Execution traces**: Two tool runs (python_exec, fetch)
4. **Trust signals**: Mix of verified, trusted, and unverified sources
5. **Freshness**: TTL info showing when to refresh

## Design Patterns

### Citation Primitive
```typescript
interface Citation {
  id: string;
  source: "web" | "code" | "tool" | "model" | "execution";
  origin: "stated" | "observed" | "inferred";
  confidence: number;
  ref: { url?: string; file?: string; tool?: string; ... };
  reliability: "verified" | "trusted" | "unverified";
  retrieved_at?: string;
  expires_at?: string;
}
```

### Result Bundling
Results are grouped by `bundle_id` so:
- Multiple results stay together
- Sources are deduplicated across results
- Refresh operates on the whole bundle
- User can save/export the entire research session

### Trust Signal Hierarchy
1. **Verified** (✓): Recently checked; URL works, content verified
2. **Trusted** (◆): Known-good source (docs.python.org, GitHub, etc.)
3. **Unverified** (○): Not checked since retrieval; may be stale

## Backend Integration

This prototype is **UI-only** (uses demo.json). For real integration:

### Needed backend endpoints:
- **POST** `/api/research` — Execute research query
  - Input: query, scope, agent, options
  - Output: bundle_id, results, citations, executions

- **GET** `/api/research/{bundle_id}` — Retrieve stored research
  - Returns: full bundle with facts and relationships

- **POST** `/api/research/{bundle_id}/verify` — Re-check citations
  - Updates reliability status
  - Decrements TTL if sources are stale

### World Model Integration

Research results should be stored as facts:
```python
# Store research result
fact = record_fact(
    "Async/await is Python's syntax for asynchronous code...",
    kind="semantic",
    subject=entity_id("agent", "research_perplexity"),
    slot="research_result",
    prov=provenance(source="tool", origin="inferred", confidence=0.92),
)

# Link to sources
relate(
    src=entity_id("source", "https://docs.python.org/..."),
    rel="cited_by",
    dst=fact_id,
)
```

This allows:
- Persistent research in Memory panel
- Graph relationships from sources to results
- History tracking (supersession when new research replaces old)
- Deduplication (same research done twice = one fact, re-confirmed)

## Future Work

1. **Real API integration**: Replace demo.json with `/api/research` calls
2. **Artifact generation**: Save code examples from research as artifacts
3. **Multi-turn research**: Refine results with follow-up questions
4. **Research sessions**: Group related queries in one "research bout"
5. **Export**: Save research to document or markdown
6. **Offline mode**: Local documentation and cached repos

## Files

```
research-build-agents/
├── index.tsx              # Exports
├── ResearchPanel.tsx      # Main container
├── ResultBlock.tsx        # Individual result
├── CitationInline.tsx     # [1] marker
├── SourcePanel.tsx        # Source list
├── ExecutionBlock.tsx     # Tool trace
├── demo.json              # Sample data
└── README.md              # This file
```

## Design Principles

1. **Trust is traceable**: Every claim links back to sources
2. **Freshness is explicit**: Timestamps and TTL are visible
3. **Complexity is revealed progressively**: Summary first, details on demand
4. **Failure is specific**: Errors and stale data don't hide behind generic messages
5. **Local first**: Sources and results live in Primnox's database, not in the cloud
