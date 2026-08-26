# Unit 6: Unified Artifact Interface Research

## Summary

Testing whether a unified Artifact model can drive both Canvas (editable workspaces) and AssetViewer (read-only asset previews). **Conclusion: No — the lifecycle differences are fundamental.** A unified model can represent shared properties but cannot abstract away the distinct state machines that govern their surfaces.

---

## Problem

Primnox has two artifact surfaces:

1. **Canvas** (`frontend/src/components/Canvas.tsx`)
   - Editable, versioned documents from the model
   - Multi-file support
   - Lives inline or in a side panel
   - Opens on-demand (inline) or always-open (panel)
   - Revert creates forward-only versions

2. **AssetViewer** (`frontend/src/components/AssetViewer.tsx`)
   - Read-only preview of uploaded files
   - Modal UI (fixed, centered, dismissible)
   - Single file
   - Never editable
   - No versioning

**Question:** Can one Artifact model drive both?

---

## Unified Artifact Model

### Proposed Structure

```typescript
type Artifact = {
  // Identity
  id: string;                           // ws:xxx or asset:xxx
  type: 'workspace' | 'asset';          // Determines lifecycle
  
  // Content
  title: string;                        // Display name
  content?: string;                     // Single-file string, or use files
  files?: Record<string, string>;       // Multi-file (workspace only)
  
  // Preview
  preview: {
    kind: 'markdown' | 'code' | 'pdf' | 'image' | 'sheets' | 'slides' | 'video' | 'unsupported';
    url?: string;                       // Asset download URL
    metadata?: Record<string, unknown>; // Kind-specific data
  };
  
  // Versioning (workspace only)
  versions?: Array<{
    version: number;
    summary: string | null;
    created_at: number;
  }>;
  version?: number;                     // Current version
  current_version?: number;             // Latest version
  
  // Capabilities
  capabilities: {
    editable: boolean;
    versionable: boolean;               // Has versions/revert
    downloadable: boolean;
    previewable: boolean;
  };
  
  // Persistence
  persistence: {
    source: 'generated' | 'uploaded';
    created_at: number;
    origin_turn_id?: string;            // Where it came from
    conversation_id?: string;           // Belongs to conversation
    sha256?: string;                    // Asset content hash
  };
  
  // Lifecycle actions
  actions: {
    open?: () => void;                  // Load/fetch
    close?: () => void;                 // Dismiss
    revert?: (version: number) => void; // Restore version
    download?: (path?: string) => void; // Download file(s)
    edit?: (path: string, content: string) => void;
  };
  
  // Runtime state
  status: 'idle' | 'loading' | 'ready' | 'error' | 'editing';
  error?: string;
  busy?: boolean;
};
```

---

## Lifecycle Analysis

### Canvas Lifecycle (Workspace)

State machine:

```
[Unmounted] 
  ↓ (inline variant mounts closed)
[Closed] ← (toggle open/close)
  ↓ (user clicks to open OR panel variant always open)
[Loading] 
  ↓ (fetch workspace)
[Ready] ← (can read, edit, revert)
  ↓ (toggle close OR navigate away)
[Closed]
```

Rules:
- **Inline**: Starts closed, lazy-loads only when opened
- **Panel**: Starts open, fetches immediately
- **Revert**: Creates a NEW version (forward-only), doesn't delete history
- **Edit**: Sends only changed files, previous versions carry forward
- **Close**: Can escape-dismiss (panel only)
- **Persistence**: Outlives the conversation

### Asset Lifecycle (AssetViewer)

State machine:

```
[Asset Exists] (on turn, metadata only)
  ↓ (user clicks attachment or preview trigger)
[Mounting Modal]
  ↓
[Loading Preview] (fetch file type, metadata)
  ↓
[Ready] ← (show modal, can download, can't edit)
  ↓ (click outside, press escape, click close)
[Unmounting Modal]
  ↓
[Dismissed]
```

Rules:
- **Modal**: Always modal UI, never inline (in Canvas.tsx path) OR bounded in transcript (in Attachment.tsx)
- **Preview**: Fetches metadata to determine render path (pdf iframe, image <img>, sheets table, etc.)
- **Download**: Always read-only, no editing
- **No versioning**: Asset is immutable (content-addressed)
- **Status tracking**: Ingesting → ready → ready (with metadata if OCR needed)
- **Bounded vs Full-Height**: Modal owns h-full; bounded inline version is capped

---

## Lifecycle Differences That Cannot Be Unified

| Aspect | Canvas | Asset | Unifiable? |
|--------|--------|-------|-----------|
| **Opening** | Toggle (inline) or panel open | Modal spawn | ✗ Different UX |
| **Loading Strategy** | Lazy on open (inline) or eager (panel) | Always fetch on mount | ✗ Different timing |
| **State Location** | Lives in conversation flow | Floats above | ✗ Different DOM context |
| **Editing** | Full CRUD on files | Read-only | ✗ Fundamentally different |
| **Versioning** | Immutable versions, revert | Content-addressed, no history | ✗ Different persistence model |
| **Dismissal** | Escape or navigation | Escape or click backdrop | ~ Similar but different triggers |
| **Preview Rendering** | Prose vs source (by ext) | Format-specific (8+ branches) | ✗ Different rendering logic |
| **Persistence** | Outlives conversation | Belongs to conversation | ~ Could go either way |

**Conclusion**: A unified model can represent metadata but CANNOT unify the lifecycle. The state machine is fundamentally different: Canvas is a toggle within a conversation flow; Asset is a modal that appears and disappears.

---

## What CAN Be Unified

### Shared Properties Layer

All artifacts have these in common:

```typescript
type ArtifactBase = {
  id: string;
  title: string;
  created_at: number;
  kind: string;  // 'markdown' | 'python' | 'pdf' | 'image' | etc.
};
```

### Shared Rendering

`AssetPreview` already handles 8 format branches. A Canvas document (markdown/code) is also a format branch. They could share a **unified preview renderer**:

```typescript
type PreviewProps = {
  artifact: ArtifactBase;
  bounded?: boolean;      // h-full or capped
  prose?: boolean;        // For markdown/text: render as prose
};
```

**Both Canvas and AssetViewer call the same preview renderer**, parameterized by `bounded` and `prose`. This is already partially done: `AssetPreview` and Canvas both render markdown, code, tables, etc.

### Shared Type Detection

Extract file-type inference into a shared utility:

```typescript
function detectKind(name: string, content?: string): ArtifactKind {
  // PROSE_EXT check from Canvas
  // _EXT_KIND mapping from AssetService
  // Combine both, return consistent enum
}
```

---

## Why Unified Lifecycle Fails

### Canvas Example: The Inline Variant

```tsx
// Canvas.tsx, inline mode
const inline = variant === 'inline';
const [open, setOpen] = useState(!inline);  // ← Closed by default
const [ws, setWs] = useState<Workspace | null>(null);  // ← No data yet

useEffect(() => {
  if (open && !ws) load();  // ← Lazy load on first open
}, [open, ws, load]);

// Close behavior: only exists in panel mode
useEffect(() => {
  if (inline || !onClose) return;  // ← No-op for inline
  const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
  window.addEventListener('keydown', onKey);
  return () => window.removeEventListener('keydown', onKey);
}, [inline, onClose]);
```

If we tried to unify with Asset:

```tsx
// Hypothetical unified component
const Artifact = ({ id, type, variant = 'panel' }: Props) => {
  const [open, setOpen] = useState(variant !== 'inline');  // type-dependent?
  const [data, setData] = useState(null);
  
  useEffect(() => {
    if (open && !data) load();  // Always lazy?
  }, [open, data, load]);
  
  // But Asset doesn't have "open" state — it's always rendering a modal
  // and the modal's presence is controlled by parent
  // Canvas toggle is LOCAL; Asset modal is PARENT-CONTROLLED
};
```

**Mismatch**: Canvas owns its open/close state. AssetViewer is parent-controlled (via `onClose` callback). Unifying them means one component has confused ownership.

### Asset Example: The Modal UI

```tsx
// AssetViewer.tsx
export function AssetViewer({ asset, onClose }: { asset: ...; onClose: () => void; }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center ...">
      <div role="dialog" aria-modal="true" ...>
        {/* Modal content */}
      </div>
    </div>
  );
}
```

If we tried to unify:

```tsx
// Hypothetical unified component
const Artifact = ({ id, onClose }: Props) => {
  const isAsset = type === 'asset';
  const isCanvas = type === 'workspace';
  
  if (isAsset) {
    return (
      <div className="fixed inset-0 z-50 flex ...">
        {/* Only makes sense for assets */}
      </div>
    );
  } else if (isCanvas && variant === 'panel') {
    return (
      <aside className="flex h-full w-full flex-col ...">
        {/* Makes sense for panels */}
      </aside>
    );
  }
};
```

**Mismatch**: The JSX structure is completely different. Canvas is `<aside>`, Asset is `<div fixed>`. Unifying them means embedding both under `type`-based conditionals, which is just "both components in one file."

---

## Prototype Results

Three artifact types implemented:

1. **Workspace Document** (Canvas-like): Editable, versioned, multi-file markdown
2. **Uploaded PDF**: Read-only, preview via iframe
3. **Generated Slide Deck**: Multi-page, navigation

### Findings

✅ **Unified representation works**: All three map to `Artifact` shape cleanly

✗ **Unified component fails**: Trying to unify lifecycle forces:
   - Branching on `type` at every decision point
   - Confusing state ownership (parent-controlled vs self-controlled)
   - Duplicate JSX under conditional branches
   - No code savings vs two lean, focused components

✓ **Unified preview renderer works**: All three use similar preview logic (iframe, image, markdown, code, tables)

---

## Recommendations

### DO: Unified Metadata Layer

```typescript
// One shape all artifacts conform to
type ArtifactMetadata = {
  id: string;
  type: 'workspace' | 'asset';
  title: string;
  kind: string;
  created_at: number;
  // ... other common fields
};

// Mapping between backend and UI
function toArtifactMetadata(workspace: Workspace): ArtifactMetadata { ... }
function toArtifactMetadata(asset: Asset): ArtifactMetadata { ... }
```

### DO: Unified Preview Rendering

```typescript
// Both Canvas and AssetViewer import this
import { ArtifactPreview } from './ArtifactPreview';

<ArtifactPreview 
  kind={metadata.kind} 
  bounded={isInline}
  prose={isProse}
  url={downloadUrl}
  content={fileContent}
/>
```

### DO NOT: Unified Component

Keep Canvas and AssetViewer separate. They have:
- Different state machines (toggle vs modal)
- Different storage (local state vs parent prop)
- Different UX patterns (inline toggle vs backdrop dismiss)
- Different mutation rules (versioned vs immutable)

Trying to merge them trades two focused, correct implementations for one confused, branchy one.

### DO: Unified Type Enums

```typescript
enum ArtifactKind {
  MARKDOWN = 'markdown',
  PYTHON = 'python',
  TYPESCRIPT = 'typescript',
  PDF = 'pdf',
  IMAGE = 'image',
  SHEETS = 'sheets',
  SLIDES = 'slides',
  VIDEO = 'video',
  HTML = 'html',
}
```

---

## Lifecycle Audit

### Canvas (Workspace)

**Full lifecycle**:

1. **Create** (model-generated turn)
   - `workspace.create()` in backend
   - Emits `workspace.created` event
   - Frontend renders closed chip (inline) or open panel

2. **Open** (user action, inline only)
   - Toggle button clicked
   - Lazy-loads: `api.workspace(id)`
   - Sets `ws` state → renders content

3. **Edit** (model action)
   - New turn modifies workspace
   - `workspace.update()` creates new version
   - Previous version still in history
   - Emits `workspace.updated` event

4. **Revert** (user action)
   - Version button clicked
   - User selects old version
   - `api.revert(id, version)` creates new version with old content
   - Revert itself is undoable (in history)

5. **Close** (user action, panel only)
   - Escape key or X button
   - `onClose()` callback removes panel
   - State persisted in backend

**Key**: All mutations create new versions. Deletion doesn't exist. Workspace outlives conversation.

### Asset (Uploaded File)

**Full lifecycle**:

1. **Upload** (user action)
   - File selected via input
   - `ingest_bytes()` hashes, stores, queues extraction
   - Returns immediately with `status: 'ingesting'`
   - Backend `asset.ingest` job runs async

2. **Extraction** (backend job)
   - `_run_ingest()` reads file, extracts text
   - Creates chunks for retrieval
   - Updates `status: 'ready'`
   - Indexes into knowledge graph
   - Emits `asset.ready` or `asset.failed`

3. **Preview** (user action)
   - Clicking asset or attachment
   - Modal mounts
   - `api.preview(asset_id)` fetches metadata (kind, dimensions, etc.)
   - Renders appropriate preview (pdf iframe, image <img>, table, etc.)

4. **Download** (user action)
   - Download button or file open
   - Serves from `GET /assets/{id}/download`
   - Saved as `original_name`

5. **Dismiss** (user action)
   - Escape key or backdrop click
   - Modal unmounts
   - Asset stays in turn's attachment list

**Key**: Immutable content-addressed storage. Identical uploads deduplicate. No versioning. Asset persists in conversation history.

### Divergence Points

| Phase | Canvas | Asset |
|-------|--------|-------|
| **Creation** | On-demand via model | Explicit user upload |
| **Storage** | Versioned (multiple versions per ID) | Content-addressed (one entry per hash) |
| **Editing** | Full mutation + version | Immutable |
| **Lifecycle** | Can revert (undo is forward) | Can't undo |
| **Persistence** | Outlives turn, conversation | Attached to turn |
| **Preview** | Prose vs source toggle | Format detection |

---

## Conclusion

A unified Artifact model can work at the **metadata and representation layer** but not at the **lifecycle and component layer**.

- **Representation layer**: One `Artifact` type for metadata, properties, preview kinds — YES
- **Component layer**: One component handling both Canvas and Asset — NO
- **Rendering layer**: Shared preview logic — YES

The split between Canvas and AssetViewer is a **good split**. It reflects the fundamentally different state machines they implement. Forcing them together would trade clarity for false unification.

**Better approach**: Keep them separate, but ensure they speak a common language at the metadata and preview rendering layers.

---

## References

- `frontend/src/components/Canvas.tsx` — Inline/panel document viewer with versions
- `frontend/src/components/AssetViewer.tsx` — Modal asset preview
- `frontend/src/components/AssetPreview.tsx` — Shared preview renderer (8 format branches)
- `backend/primnox2/workspaces/service.py` — Workspace versioning + mutation model
- `backend/primnox2/assets/service.py` — Asset ingestion + content addressing
