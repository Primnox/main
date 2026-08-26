# Coding Agents: Next Steps for Phase 2+

**Status:** Phase 1 (Research & Prototype) Complete  
**PR:** #5 — Merged to main  
**Created:** 2026-08-26

---

## What's Done (Phase 1)

✅ **Research document** — `02-coding-agents.md` (403 lines)
- Analyzed 5 coding agents: Cursor, Windsurf, GitHub Copilot, Replit, Devin
- Identified 6 universal patterns for staged, human-in-the-loop code approval
- Audited Primnox and found 5 gaps that these patterns fill
- Designed immediate, medium-term, and advanced recommendations

✅ **Interactive prototype** — `frontend/src/components/proto/coding-agents/`
- DiffViewer: unified diff with line-by-line tracking
- FileTreeMarkers: hierarchical tree with modification badges
- ApprovalPanel: three-state workflow (pending/approved/rejected)
- CodingAgentCard: chat-embeddable composite
- Demo: clickable showcase at port 5302

---

## Phase 2: Backend Schema (1-2 Sprints)

### 2.1 WorkspaceVersion Approval State

**Add to `schema/primnox_v2.sql`:**

```sql
ALTER TABLE workspace_versions ADD COLUMN (
    approval_status TEXT DEFAULT 'pending'
        CHECK (approval_status IN ('pending', 'approved', 'rejected')),
    approved_at INTEGER,
    rejected_at INTEGER,
    approved_by TEXT,  -- turn_id or user_id
    approval_reason TEXT
);

-- Create index for queries like "show pending approvals"
CREATE INDEX idx_workspace_versions_approval_status
    ON workspace_versions(approval_status, created_at DESC);
```

### 2.2 Turn → WorkspaceVersion Link

**Add to Turn model:**

```python
# turns.py
@dataclass
class Turn:
    # ... existing fields ...
    created_workspace_version_id: str | None  # link to the version this turn created
```

### 2.3 New Event Kinds

**Add to `CONVERSATION_RUNTIME_SPEC.md` §3.6:**

```
workspace.approval_requested
  payload: { workspace_id, version, file_count, turn_id }
  
workspace.approval_response
  payload: { workspace_id, version, status: 'approved'|'rejected', turn_id }
```

### 2.4 API Endpoints

```
POST /api/workspaces/{id}/versions/{version}/approve
    → emit workspace.approval_response(approved)
    → update workspace_versions.approval_status

POST /api/workspaces/{id}/versions/{version}/reject
    → emit workspace.approval_response(rejected)
    → (do NOT delete the version, keep for audit trail)

GET /api/workspaces/{id}/versions?status=pending
    → list versions awaiting approval (for UI queue)
```

---

## Phase 3: Chat Integration (2-3 Sprints)

### 3.1 Turn Creation Workflow

When a turn creates a workspace:

```
1. Turn completes with assistant_message
2. Workspace version created
3. Emit workspace.approval_requested event
4. Chat UI receives event
5. Render CodingAgentCard inline in the message
6. User clicks Approve/Reject
7. Emit workspace.approval_response event
8. Backend updates approval_status, applies or discards
```

### 3.2 Chat Rendering

**In `Chat.tsx` or message renderer:**

```tsx
if (turn.assistant_message.text) {
  <p>{turn.assistant_message.text}</p>
}

if (turn.created_workspace_version_id) {
  const diffs = await buildDiffsFromWorkspace(
    turn.created_workspace_version_id
  );
  const fileTree = await buildFileTree(
    turn.created_workspace_version_id
  );
  
  <CodingAgentCard
    diffs={diffs}
    fileTree={fileTree}
    approval={{
      status: turn.workspace_version.approval_status,
      turnId: turn.id,
      turnTitle: turn.user_message.text.substring(0, 60),
      fileCount: diffs.length,
    }}
    onApprove={() => emitApprovalResponse('approved')}
    onReject={() => emitApprovalResponse('rejected')}
  />
}
```

### 3.3 Diff Building

**New utility: `context/diff_builder.py`**

Convert `WorkspaceVersion.files` into `DiffViewer` input:

```python
def build_diffs_from_workspace(
    prev_version: WorkspaceVersion,
    current_version: WorkspaceVersion,
) -> list[FileDiff]:
    """Compute line-by-line diffs for all changed files."""
    # Use difflib.unified_diff() for each file
    # Count added/removed lines
    # Return structured DiffBlock[] per file
```

**File tree building: `context/tree_builder.py`**

```python
def build_file_tree(
    workspace_version: WorkspaceVersion,
    modified_files: set[str],
) -> list[FileTreeItem]:
    """Build hierarchy from flat file paths, mark modifications."""
```

---

## Phase 4: File Tree Integration (1-2 Sprints)

### 4.1 ContextRail Enhancement

**In `ContextRail.tsx`:**

When a turn creates a workspace, show an expandable section:

```tsx
if (turn.created_workspace_version_id) {
  <WorkspaceSection
    title="Files Modified in This Turn"
    files={turn.workspace_version.files}
    markers={buildMarkers(turn)}
  />
}
```

### 4.2 Workspace Viewer Integration

**In workspace viewer sidebar:**

Add collapsible "Recent Changes" tracking with:
- File markers (● modified, + new)
- Turn attribution ("modified in turn_01J8X3AB4N")
- Click to jump to diff view

---

## Testing Strategy

### Unit Tests
- `test/frontend/components/proto/coding-agents/` — component tests
- `test/backend/context/test_diff_builder.py` — diff computation
- `test/backend/context/test_tree_builder.py` — file tree hierarchy

### Integration Tests
- Emit `workspace.approval_requested` → verify chat renders CodingAgentCard
- Click approve → verify `workspace.approval_response` event fired
- Reject flow → verify version not applied, kept for audit

### Manual QA
- Run demo: `npm run dev -- --port 5302`
- In live Primnox: create a workspace (e.g., via code generation)
- Verify CodingAgentCard renders with real diffs
- Test all three approval states

---

## Risks & Mitigations

### Risk: Large diff rendering is slow
**Mitigation:** Virtualize table rows for large files; lazy-load code blocks

### Risk: Approval state becomes stale if websocket drops
**Mitigation:** Query server on reconnect to refresh approval_status

### Risk: Users forget to approve/reject, workspace hangs
**Mitigation:** Add "auto-approve after 24 hours" option; email digest

### Risk: Diff viewer not production-ready for all file types
**Mitigation:** Start with code (.js, .tsx, .py); add others later

---

## Success Criteria (Definition of Done)

**Phase 2:**
- [ ] Schema changes deployed, migrations tested
- [ ] New API endpoints tested with curl/Postman
- [ ] Event kinds added to CRS and emitted correctly

**Phase 3:**
- [ ] CodingAgentCard renders inline in chat for workspace turns
- [ ] Approve button wires to backend and applies changes
- [ ] Reject button discards without modifying workspace
- [ ] Manual QA on 3+ realistic scenarios passes

**Phase 4:**
- [ ] File tree shows modification markers
- [ ] Markers are clickable and jump to diff view
- [ ] No performance regression on ContextRail

---

## Spike Opportunities

If blocked or want to validate:

1. **Diff library evaluation** — is `difflib.unified_diff` sufficient, or do we need `python-diff-match-patch` for better readability?

2. **Large file handling** — test diff rendering with a 10k-line file; measure virtualization overhead

3. **Mobile/touch approval** — tablet users: is a three-button workflow usable, or do we need swipe/gesture?

4. **Audit trail** — validate that `approved_by` and `approval_reason` capture what we need for compliance

---

## Related Docs

- `docs/ARCHITECTURE_V2.md` — Workspace model, Turn model
- `docs/CONVERSATION_RUNTIME_SPEC.md` — Event protocol (will add workspace.approval_* kinds)
- `frontend/src/components/proto/coding-agents/README.md` — Component API
- `frontend/src/components/proto/coding-agents/Demo.tsx` — Reference implementation

---

## Contact & Ownership

**Phase 1 (Research & Prototype):** Unit 2 (Coding Agents agent)  
**Phase 2 (Backend):** TBD (likely backend team)  
**Phase 3 (Chat Integration):** TBD (likely frontend + chat)  
**Phase 4 (File Tree):** TBD (likely frontend/UX)

---

**Last Updated:** 2026-08-26  
**Estimated effort:** Phase 2 (3-5 days), Phase 3 (5-8 days), Phase 4 (2-3 days)
