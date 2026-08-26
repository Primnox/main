# Unit 3: Research & Build Agents — Survey, Citation Primitive, Backend Audit

## Executive Summary

Research & build agents (Perplexity, Manus, Lovable, v0, AI Studio) are a new category of AI systems that combine web research, code generation, and real-time execution feedback into a unified workflow. They differ from conventional LLM chatbots by:

1. **Multi-hop search + synthesis** — retrieve from web sources, synthesize answers, link back to citations
2. **Interactive iteration** — run code or preview designs, observe failures, correct in context
3. **Transparent provenance** — users trust the system because they can see where each claim/resource came from

Primnox's existing `world_model.py` already implements a sophisticated provenance system (source, origin, confidence, sensitivity). The gap is in the **UI layer**: Primnox has no interface primitive for displaying research results with citations, nor any backend integration for research agent outputs.

This document proposes:
- A **Citation/Source Primitive** that bridges world_model provenance and research agent outputs
- A **UI component hierarchy** for displaying research results with sources
- **Backend audit findings** showing where Primnox can plug in research agent integrations
- A **working prototype** demonstrating the interaction model (port 5303)

---

## Part 1: Research Agents Landscape

### Perplexity
- **Model**: Claude/GPT + web search
- **Interaction**: Query → real-time search → synthesis → answer with citations
- **Citations**: Numbered links to source URLs; can trace back to which search result a claim came from
- **Inference**: Mixes user question, search results, and model reasoning; user sees only synthesis
- **UI pattern**: Answer blocks with inline citation numbers `[1]`, expandable source list below

### Manus
- **Model**: Claude + function calls (web search, code execution)
- **Interaction**: Agentic loop: think → act → observe → think
- **Citations**: URL list and execution results; no numbered inline citations
- **Inference**: Explicit reasoning shown; tool calls visible to user
- **UI pattern**: Thought blocks, action blocks (with tool I/O), result summary

### Lovable
- **Model**: Claude + code generation + live preview
- **Interaction**: Design → generate → preview → iterate
- **Citations**: Component library links, design system references, external packages
- **Inference**: Generated code shown; preview failures visible; user sees diffs
- **UI pattern**: Code blocks with syntax highlighting, side-by-side preview, error messages

### v0
- **Model**: Claude + Shadcn components + live rendering
- **Interaction**: Describe → generate React → preview → refine
- **Citations**: Installed packages, Shadcn component versions, Tailwind utility references
- **Inference**: Full component code visible; visual diffs between versions
- **UI pattern**: Code inspector, rendered preview, code diff view

### AI Studio (Google)
- **Model**: Gemini + web search + code execution
- **Interaction**: Prompt → multi-agent execution → result assembly
- **Citations**: URLs, execution context, parameter traces
- **Inference**: Intermediate steps shown; data flow visible
- **UI pattern**: Step timeline, expandable execution details, parameter inspector

---

## Part 2: Unified Citation/Source Primitive Design

### The Primitive: `Citation`

```typescript
interface Citation {
  // Stable identity for deduplication and linking
  id: string;
  
  // Where this came from (bridges world_model.Provenance)
  source: "web" | "code" | "tool" | "user" | "model" | "execution";
  origin: "stated" | "observed" | "inferred";
  confidence: number; // 0..1
  
  // The actual source reference
  ref: {
    url?: string;           // For web sources
    file?: string;          // For code/local sources
    line?: number;
    tool?: string;          // For tool outputs (fetch, exec, etc.)
    model?: string;         // For model inferences
    timestamp?: string;     // ISO 8601
  };
  
  // Display metadata
  title?: string;           // "Python docs: list.sort()", "GitHub issue #123"
  snippet?: string;         // Preview text
  type: "direct" | "synthesized" | "inferred"; // How much the claim relies on this source
  
  // Trust signal
  reliability: "verified" | "trusted" | "unverified";
  retrieved_at?: string;    // When this was last checked
  ttl?: number;             // Seconds until this citation should be refreshed
}
```

### Design Rationale

1. **Bridges world_model**: Uses same `source/origin/confidence` triad already in Primnox's database
2. **Traceable chains**: `type: "synthesized"` means this is a secondhand interpretation, not a direct quote
3. **Practical verification**: `reliability` field lets UI show trust signals without re-checking
4. **Live freshness**: `ttl` field supports refreshing stale web research without full re-run
5. **Universal**: Handles web URLs, code snippets, execution outputs, and model inferences uniformly

### Extending world_model

The Primnox backend should add a new entity type and fact slot:

```python
# world_model.py additions
ENTITY_TYPES.add("source")  # For web URLs, repos, documentation
RELATIONSHIPS.add("cited_by")  # A source was used in a fact
RELATIONSHIPS.add("originated_from")  # A claim originated from this source

# Example: Recording a research result
fact_id = record_fact(
    "The latest Python version supports type hints in function arguments.",
    kind="semantic",
    subject=entity_id("agent", "research_perplexity"),
    project="research_session_1",
    slot="research_result",
    prov=provenance(source="tool", origin="inferred", confidence=0.9),
)

# Link it back to the sources it came from
relate(
    src=entity_id("source", "https://python.org/docs"),
    rel="cited_by",
    dst=fact_id,
    prov=provenance(source="tool", origin="observed"),
)
```

---

## Part 3: UI Component Hierarchy

### ResearchResult Component (High-level container)

```tsx
<ResearchResult
  query="How do I use async/await in Python?"
  results={[
    {
      content: "Async/await allows you to write concurrent code...",
      citations: [citationA, citationB, citationC],
      source: "perplexity",
      timestamp: "2026-08-26T...",
      confidence: 0.92,
    },
    {
      content: "Here's a practical example: async def fetch()...",
      citations: [citationD],
      source: "model_inference",
      timestamp: "...",
      confidence: 0.85,
    },
  ]}
  onRefine={(query) => { /* re-search */ }}
/>
```

### CitationBadge Component (Inline citation marker)

```tsx
<CitationBadge
  number={1}
  citation={citation}
  onClick={() => scroll to source details}
/>
```

Renders as `[1]` inline; hovering or clicking shows preview; clicking scrolls to full details below.

### SourcePanel Component (Expandable source list)

```tsx
<SourcePanel
  citations={[citation1, citation2, citation3]}
  onVerify={(citation) => { /* check freshness */ }}
/>
```

Shows:
- URL or file path
- Title/snippet
- Reliability icon (verified ✓, trusted ◆, unverified ○)
- "Retrieved X minutes ago" timestamp
- "Refresh" button if TTL expired

### ExecutionTrace Component (For tool outputs)

Shows:
- Tool name (fetch, exec_python, etc.)
- Input parameters
- Output / error
- Wall-clock timing
- Reliability based on exit code

### SearchProgress Component (For active research)

Shows:
- "Searching..." state
- Number of sources found so far
- Estimated time remaining
- "Stop" button

---

## Part 4: Backend Audit — Primnox's world_model vs. Research Agent Integration Points

### Current Capabilities (world_model.py)

✓ **Provenance tracking**: source/origin/confidence triad
✓ **Fact supersession**: New research can replace old research without destroying history
✓ **Conflict resolution**: Disputed research results are marked, not silently overwritten
✓ **Soft forgetting**: Research can be marked stale without deletion
✓ **Scoped facts**: Research results can be kept per-conversation or global
✓ **Entity linking**: Research results can reference files, symbols, etc.

### Identified Gaps

| Gap | Impact | Fix |
|-----|--------|-----|
| No tool execution tracking | Research tools (web fetch, code exec) don't record their invocations persistently | Add `ExecutionTrace` entity type; record tool calls in relationships |
| No TTL/freshness management | Research from 3 months ago looks as fresh as today's | Add `expires_at` field to facts; UI prompts refresh when stale |
| No citation backlinks | A fact knows its sources; sources don't know what used them | Add `cited_by` index in facts table |
| No agent output bundling | Each fact is isolated; multi-part research results (answer + code + links) aren't grouped | Add `result_bundle_id` to facts; group by bundle in UI |
| No search query storage | Can't trace research back to original user question | Add `query_text` field to facts with `slot="research_query"` |
| No confidence evolution | Fact confidence is static; should update as sources are verified | Add `verification_history` JSON array to track confidence changes |

### Recommended Backend Changes

**Priority 1 (Ship with prototype):**
1. Add `source` entity type
2. Extend facts table with `query_text` and `result_bundle_id`
3. Add `cited_by` relationship type
4. Implement fact bundling in `record_fact()` for multi-part results

**Priority 2 (Next phase):**
1. Add TTL management to `mark_stale()` and fact queries
2. Implement execution trace tracking
3. Build `/api/research/execute` endpoint that records tool invocations

**Priority 3 (Polish):**
1. Confidence evolution tracking
2. Source verification caching
3. Research session grouping (multiple queries in one research bout)

---

## Part 5: Integration Pattern

### Proposed Flow: User asks research question

1. **User** → `/api/research` with query
2. **Backend** → Create fact with `slot="research_query"`, store original question
3. **Backend** → Call research agent (Perplexity / web search)
4. **Backend** → Receive: answer text + citations + metadata
5. **Backend** → For each citation: create/upsert `source` entity
6. **Backend** → Record result as fact bundle: one fact per answer paragraph, all linked to same `result_bundle_id`
7. **Backend** → For each citation: create `cited_by` relationship from source to fact
8. **Backend** → Return bundle ID to frontend
9. **Frontend** → Fetch bundle by ID; render with inline citation numbers
10. **User** → Hovers citation → sees source details (URL, snippet, reliability)
11. **User** → Clicks citation → scrolls to full source panel
12. **User** → Days later, asks follow-up → system sees research is 30 days old, suggests refresh

### Endpoint: `/api/research`

**POST** `/api/research`
```json
{
  "query": "How does Rust's ownership system work?",
  "scope": "conversation_id_123",
  "agent": "perplexity",
  "include_code": true,
  "max_sources": 10
}
```

**Response**:
```json
{
  "bundle_id": "research_20260826_abc123",
  "status": "complete",
  "answer": "Rust's ownership system...",
  "citations": [
    { "id": "src_1", "url": "https://doc.rust-lang.org/...", "title": "...", "reliability": "verified" },
    ...
  ],
  "sources": [...],
  "created_at": "2026-08-26T...",
  "ttl_seconds": 2592000
}
```

**GET** `/api/research/{bundle_id}`
- Retrieve a stored research result by ID
- Returns full facts + citations + metadata

**POST** `/api/research/{bundle_id}/verify`
- Re-check citations (especially URLs) for freshness
- Updates `reliability` field; decrements TTL if stale
- Non-blocking; returns updated bundle

---

## Part 6: Prototype Walkthrough

The prototype at `frontend/src/components/proto/research-build-agents/` demonstrates:

### File Structure
```
research-build-agents/
├── index.tsx                    # Main export
├── ResearchPanel.tsx            # Container (embedded or modal)
├── ResultBlock.tsx              # One research result with citations
├── CitationInline.tsx           # [1] [2] markers
├── SourcePanel.tsx              # Expandable source details
├── ExecutionBlock.tsx           # Tool execution traces
└── demo.json                    # Sample data (no network calls)
```

### Key Features (Demo)

1. **Search progress UI**: Shows query being researched
2. **Multi-source synthesis**: Three different answer formats (web, code, analysis)
3. **Citation tracking**: Inline numbers map to expandable source list
4. **Trust signals**: Verified ✓ vs unverified sources
5. **Execution traces**: Shows tool invocations (fetch, python_exec)
6. **Refresh capability**: Demonstrates TTL and re-check UX

### How to Run

```bash
# Start dev server
npm run dev

# Navigate to http://localhost:5173
# Then navigate to http://localhost:5173?proto=research-build-agents
# (Port 5303 would be a separate dedicated dev server for proto isolation)
```

Or run in isolation:

```bash
# In frontend/src/components/proto/research-build-agents
npm start  # if .env points to port 5303
```

---

## Part 7: Design Principles Applied

### 1. Privacy-First Source Handling
- Local sources (files, code, execution) are never stripped
- Web sources are fetched on-device; Primnox does not proxy through a research API
- Citations are stored in local database; not logged externally

### 2. Verifiable Trust
- Each citation has a `reliability` field, not a hidden algorithm
- "Verified" means checked against upstream; "unverified" means cache
- User can manually refresh to re-verify; system prompts when TTL expires

### 3. Persistent Memory
- Research results persist in world_model as facts
- User can search over all past research in Memory panel
- Graph panel shows sources as entities with relationships to facts that use them

### 4. Transparent Provenance
- Every claim is traceable to the sources that support it
- Model inferences are marked as such; user knows where to distrust
- Synthesized claims (combination of multiple sources) are labeled differently from direct quotes

### 5. Clear Failure Modes
- Broken source URLs → shown in SourcePanel with error state
- Timeout during research → state is saved; "Retry" button appears
- Stale results → "Refresh" button appears; no silent fallback

---

## Part 8: Future Roadmap

### Phase 1 (Prototype + MVP)
- [ ] Research panel UI with demo data
- [ ] Backend integration with Perplexity or web search API
- [ ] Citation primitive in world_model
- [ ] Memory panel integration (research results appear in "Everything it knows")

### Phase 2 (Interactive Research)
- [ ] Code execution agent (run Python/Node snippets from research)
- [ ] Artifact generation (save code samples from research as artifacts)
- [ ] Source verification endpoint (check if URLs still work)
- [ ] TTL-based refresh UI

### Phase 3 (Research Sessions)
- [ ] Multi-turn research (refine, follow-up questions)
- [ ] Research session grouping (multiple queries in one bout)
- [ ] Confidence evolution (track how source reliability changed)
- [ ] Export research to document

### Phase 4 (Advanced)
- [ ] Offline research (local documentation, cached repos)
- [ ] Controversial source handling (mark disputed/contradictory results)
- [ ] Source reputation scoring (trust based on past accuracy)
- [ ] Research agent selection (user picks Perplexity vs Claude vs Manus)

---

## Appendix A: Citation Primitive — Full Schema

```typescript
interface Citation {
  id: string;  // "src_<hash>" for deterministic deduplication
  
  source: 
    | "web"        // HTTP/HTTPS URL
    | "code"       // Local source file
    | "tool"       // Tool execution result
    | "user"       // User's own statement
    | "model"      // AI model output
    | "execution"; // Sandboxed code run result
  
  origin: "stated" | "observed" | "inferred";
  confidence: number; // 0.0–1.0
  
  ref: {
    url?: string;             // For web sources: full URL with query params
    url_domain?: string;      // Cached domain for display
    file?: string;            // For code: relative path in project
    line?: number;            // For code: line number or range
    tool?: string;            // For tools: "fetch", "python_exec", etc.
    tool_invocation_id?: string; // Link to execution trace
    model?: string;           // For model: model name/version
    prompt?: string;          // For model: what was asked
    timestamp?: string;       // ISO 8601: when this was retrieved
  };
  
  // Display
  title?: string;     // "Python 3.12 Release Notes", "GitHub Issue #5242"
  snippet?: string;   // Preview: first 200 chars of relevant text
  excerpt?: string;   // Full relevant quote (for inline display)
  
  // Claim type determines how much the result depends on this source
  type: 
    | "direct"          // Direct quote; result = source
    | "synthesized"     // Combined with other sources; result != any single source
    | "inferred";       // Model inference; may not appear literally in any source
  
  // Trust signal: helps UI decide whether to highlight or footnote
  reliability: 
    | "verified"        // Recently checked; URL works, content matches
    | "trusted"         // Known-good source (docs.python.org, etc.)
    | "unverified";     // Not checked since retrieval
  
  // Freshness
  retrieved_at?: string;  // ISO 8601: when this was fetched
  expires_at?: string;    // ISO 8601: when to prompt user to refresh
  ttl_seconds?: number;   // Suggested refresh interval (e.g., 30 days for docs)
  
  // Access tracking
  access_count?: number;
  last_verified_at?: string;
  verification_method?: "automated" | "user_click" | "hover_preview";
}
```

---

## Appendix B: Sample Research Result JSON

```json
{
  "bundle_id": "research_20260826_abc123",
  "query": "How do I use async/await in Python?",
  "agent": "perplexity",
  "scope": "conversation_c8e7f9a2",
  "status": "complete",
  "results": [
    {
      "id": "result_1",
      "content": "Async/await is Python's syntax for writing asynchronous code. The `async` keyword defines a coroutine function, and `await` pauses execution until a promise resolves.",
      "type": "synthesis",
      "citations": ["src_1", "src_3", "src_5"],
      "confidence": 0.95
    },
    {
      "id": "result_2",
      "content": "import asyncio\n\nasync def fetch_data(url):\n    await asyncio.sleep(1)\n    return f'Data from {url}'",
      "type": "code_example",
      "language": "python",
      "citations": ["src_2"],
      "confidence": 0.88
    }
  ],
  "citations": {
    "src_1": {
      "id": "src_1",
      "source": "web",
      "origin": "observed",
      "confidence": 0.95,
      "ref": {
        "url": "https://docs.python.org/3.11/library/asyncio.html",
        "timestamp": "2026-08-26T14:32:00Z"
      },
      "title": "asyncio — Asynchronous I/O",
      "type": "direct",
      "reliability": "verified",
      "retrieved_at": "2026-08-26T14:32:00Z",
      "ttl_seconds": 2592000
    },
    "src_2": {
      "id": "src_2",
      "source": "code",
      "origin": "inferred",
      "confidence": 0.88,
      "ref": {
        "file": "examples/async_fetch.py",
        "line": "12-18"
      },
      "title": "Example: async fetch",
      "type": "direct",
      "reliability": "trusted"
    },
    "src_3": {
      "id": "src_3",
      "source": "web",
      "origin": "observed",
      "confidence": 0.92,
      "ref": {
        "url": "https://realpython.com/async-io-python/",
        "timestamp": "2026-08-26T14:31:00Z"
      },
      "title": "Async IO in Python: A Complete Walkthrough",
      "type": "synthesized",
      "reliability": "unverified",
      "retrieved_at": "2026-08-26T14:31:00Z"
    }
  },
  "created_at": "2026-08-26T14:30:00Z",
  "expires_at": "2026-09-25T14:30:00Z",
  "ttl_seconds": 2592000
}
```

---

## Summary

The research & build agent landscape shows a consistent pattern: **sources are first-class, and users trust systems that make sources visible and verifiable**. Primnox already has the backend infrastructure (world_model provenance) to support this; the gaps are:

1. **UI components** to display research results with citations
2. **Citation primitive** to bridge research agent outputs and world_model
3. **Backend integration** to store research results persistently and link them to sources

This document provides the design for all three, grounded in:
- Analysis of how Perplexity, Manus, Lovable, v0, and AI Studio handle citations
- Primnox's existing provenance architecture
- Privacy-first principles (local research, no external logging)
- Clear failure modes and user control

The prototype demonstrates the interaction model and serves as a reference for implementation.

**Next steps**: Land prototype, integrate with one research agent (Perplexity or web search), extend world_model for source bundling, build `/api/research` endpoint.
