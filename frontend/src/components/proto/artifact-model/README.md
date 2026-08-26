# Unit 6: Artifact Model Prototype

## Research Goal

Test whether a unified Artifact interface can drive both Canvas (editable workspaces) and AssetViewer (read-only asset previews).

**Conclusion**: Unified metadata layer works. Unified lifecycle fails.

## Components

### `types.ts`
Core types for the unified Artifact model:
- `Artifact` — main type, works for all artifact kinds
- `ArtifactMetadata` — the subset that CAN be shared
- `WorkspaceData`, `AssetData` — mock backend types

### `converters.ts`
Three converter functions proving metadata unification works:
- `workspaceToArtifact(WorkspaceData)` — generates artifact from editable workspace
- `pdfAssetToArtifact(AssetData)` — generates artifact from uploaded PDF
- `slideAssetToArtifact(AssetData)` — generates artifact from slide deck
- `imageAssetToArtifact(AssetData)` — generates artifact from image

### `demo.tsx`
Three side-by-side viewers showcasing the three artifact types:
1. **Workspace Viewer** (blue) — Canvas-like, editable, versioned, toggles open/close
2. **PDF Viewer** (purple) — AssetViewer-like, modal, read-only
3. **Slide Viewer** (green) — Asset with pagination, multistate rendering

### `index.tsx`
Export point for the prototype.

## Running the Prototype

### Option 1: Route in Main App (Recommended)

Add to `frontend/src/App.tsx` or create a new route:

```tsx
import { ArtifactModelDemo } from './components/proto/artifact-model';

// In your router:
// <Route path="/proto/artifact-model" component={ArtifactModelDemo} />

// Or mount directly:
// <ArtifactModelDemo />
```

Then visit `http://localhost:5273/proto/artifact-model`

### Option 2: Standalone Dev Server

Create `frontend/src/proto-main.tsx`:

```tsx
import React from 'react'
import ReactDOM from 'react-dom/client'
import { ArtifactModelDemo } from './components/proto/artifact-model'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ArtifactModelDemo />
  </React.StrictMode>,
)
```

Then create a separate vite config or update the main one to support a proto entry point.

## Key Findings

### What Works: Metadata Layer

All three artifacts conform to a single `Artifact` type:

```typescript
{
  id, type, title, preview.kind, capabilities, persistence, status
}
```

Converting from backend types to this shape is straightforward and proves metadata can be unified.

### What Doesn't Work: Lifecycle Layer

**Canvas (Workspace)**:
- Owns `open/close` state locally (toggle button)
- Lazy-loads on first open (inline variant)
- Renders as `<aside>` for panel variant
- Editable with versioning

**Asset**:
- Open/close controlled by parent (modal props)
- Always eager-loads on mount
- Renders as `<div fixed>` modal
- Read-only, immutable

**Trying to unify them**:
- Requires branching on `type` at every lifecycle decision
- Confuses state ownership (local vs parent)
- Different JSX structure for each type
- Duplicate code under conditionals

Result: Unified component is worse than two separate, focused ones.

### What Works: Rendering Layer

Both can share a unified preview renderer:
- Format detection (markdown, code, pdf, image, sheets, slides, video)
- Parameter-driven rendering (bounded, prose, content-specific rendering)

## Lifecycle Differences

| Aspect | Canvas | Asset |
|--------|--------|-------|
| **Open/Close** | Toggle (local) | Modal (parent) |
| **Loading** | Lazy (on open) | Eager (on mount) |
| **UI** | `<aside>` (panel/inline) | `<div fixed>` (modal) |
| **Editing** | Full CRUD + versions | Read-only |
| **Versioning** | Yes | No (content-addressed) |
| **State Machine** | Closed → Loading → Ready | Exists → Modal → Ready |

## Recommendations

### DO
- Unified metadata type (`ArtifactMetadata`)
- Unified type detection enum
- Shared preview rendering logic
- Consistent metadata shape across Canvas and AssetViewer

### DO NOT
- Unified component handling both Canvas and Asset
- Try to abstract the lifecycle — it's fundamentally different

### INSTEAD
- Keep Canvas and AssetViewer separate
- Have them both inherit from `ArtifactMetadata`
- Share a `PreviewRenderer` component
- Use the same type enums

## References

- `docs/ui-research/06-artifact-model.md` — full research document
- `frontend/src/components/Canvas.tsx` — existing Canvas implementation
- `frontend/src/components/AssetViewer.tsx` — existing Asset viewer
- `backend/primnox2/workspaces/service.py` — workspace versioning model
- `backend/primnox2/assets/service.py` — asset ingestion model
