# Coding Agents Prototype

Research prototype for UI patterns that transfer from coding agents (Cursor, Windsurf, Copilot, Replit, Devin) to Primnox's general-purpose agent interface.

## Components

### DiffViewer
Renders unified diffs with syntax highlighting and line-by-line change tracking.

**Props:**
```tsx
interface FileDiff {
  filename: string;
  language?: string;
  added: number;
  removed: number;
  blocks: DiffBlock[];
}

interface DiffBlock {
  lineNum: number;
  type: 'add' | 'remove' | 'context';
  content: string;
}
```

**Features:**
- Collapsible per-file
- Green highlighting for added lines
- Red highlighting for removed lines
- Change summary (+X −Y)

### FileTreeMarkers
Hierarchical file browser with modification markers.

**Props:**
```tsx
interface FileTreeItem {
  id: string;
  path: string;
  name: string;
  type: 'file' | 'folder';
  isModified?: boolean;
  isNew?: boolean;
  children?: FileTreeItem[];
}
```

**Features:**
- Expandable/collapsible folders
- Blue dot (●) for modified files
- Green plus (+) for new files
- Touch count badge
- Click file to select

### ApprovalPanel
Status-aware control panel for change approval workflow.

**Props:**
```tsx
interface ApprovalState {
  status: 'pending' | 'approved' | 'rejected';
  turnId: string;
  turnTitle: string;
  fileCount: number;
  timestamp?: number;
}
```

**Features:**
- Three-button workflow: Accept All, Review & Approve, Reject
- Status-aware styling (yellow/green/red)
- Keyboard shortcut hints (Tab to accept, Shift+Tab to reject)
- Emoji indicators on state change

### CodingAgentCard
Composite component combining all three for embedding in chat messages.

**Props:**
```tsx
interface CodingAgentCardProps {
  turnId: string;
  turnTitle: string;
  message: string;          // Assistant's explanation
  diffs: FileDiff[];        // Changes to show
  fileTree: FileTreeItem[]; // File structure
  approval: ApprovalState;  // Current approval state
  onApprove?: () => void;
  onReject?: () => void;
  onReview?: () => void;
}
```

## Demo

Run the interactive demo at port 5302:

```bash
npm run dev -- --port 5302
```

Then navigate to `http://localhost:5302/components/proto/coding-agents/Demo`

The demo showcases:
- Chat message with embedded CodingAgentCard
- All three approval states (pending, approved, rejected)
- Collapsible sections for diffs and file tree
- Sample data from a realistic refactoring scenario

## Integration Points

### In Chat Messages
When a turn creates a workspace, emit the diff data alongside the message:

```tsx
<ChatMessage>
  <p>{turn.assistant_message.text}</p>
  {turn.workspace_version && (
    <CodingAgentCard
      diffs={buildDiffsFromWorkspace(turn.workspace_version)}
      fileTree={buildFileTree(turn.workspace_version)}
      approval={turn.workspace_approval_status}
      // ...
    />
  )}
</ChatMessage>
```

### In Workspace Viewer
Show file tree markers in the sidebar:

```tsx
<ContextRail>
  <FileTreeMarkers
    items={workspace.files}
    touchCount={workspace.recent_changes_count}
  />
</ContextRail>
```

### In Approval Flow
Wire approval state to backend:

```tsx
const handleApprove = async () => {
  setApproval({ status: 'approved' });
  await fetch(`/api/workspaces/${workspace_id}/approve`, {
    method: 'POST',
  });
};
```

## Design Rationale

These components implement patterns from production coding agents:

| Pattern | Transferred From | For Primnox |
|---------|------------------|-----------|
| Staged edits | Cursor, Windsurf | Show changes before applying |
| Inline diff | Cursor, Copilot | Visual context in chat |
| File tree markers | Windsurf, Devin | Scope visibility |
| Accept/reject | Replit, Copilot | Human approval gate |
| Edit attribution | All agents | Audit trail |

See `docs/ui-research/02-coding-agents.md` for full analysis and gaps identified in Primnox.

## Styling

Components use:
- Tailwind CSS for styling
- Lucide React for icons
- No external diff libraries (inline implementation)

Colors:
- Green: additions (+), success, new files
- Red: deletions (−), rejection, errors
- Blue: modified files, reviews
- Yellow: pending changes

## Future Enhancements

- [ ] Side-by-side diff view (current: unified)
- [ ] Hunk-level approval (cherry-pick changes)
- [ ] Streaming diffs (show changes as agent generates them)
- [ ] Syntax highlighting per language
- [ ] Copy/paste individual code blocks
- [ ] Keyboard shortcuts for power users (Tab to accept, etc.)
- [ ] Undo/revert after approval
- [ ] Multi-turn planning visualization (Devin-like)

## Testing

Demo includes:
- 2 files modified
- 20 lines of context showing real-world refactoring
- All approval states testable via buttons
- Sample file tree with nested folders and multiple modification types

Click "Reset to Pending" to cycle through states.

---

**Status:** Research & prototype for Phase 1 of coding agents integration  
**Created:** 2026-08-26  
**Scope:** Primnox V2 artifacts + workspaces  
**Next:** Phase 2 backend schema, Phase 3 chat integration
