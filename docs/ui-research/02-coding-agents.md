# Coding Agents: UI Patterns & Transfers to General-Purpose Agents

**Date:** 2026-08-26  
**Status:** Research & Analysis  
**Scope:** Cursor, Windsurf, GitHub Copilot, Replit, Devin; patterns that transfer to Primnox

---

## Executive Summary

Coding agents (Cursor, Windsurf, GitHub Copilot, Replit, Devin) solve a specific problem: **collaborative code editing where human and AI both modify the same files in real-time.** Their UI patterns address this through:

1. **Unified diff/approval workflow** — show changes before committing
2. **File tree as persistent context** — navigate while working
3. **Streaming edits with staged acceptance** — don't auto-apply, wait for OK
4. **Edit attribution** — which edits came from AI vs human
5. **Cancellation and undo** — revert AI work in-progress

**What transfers to Primnox:** A general-purpose agent UI needs these patterns whenever it can **mutate external state** (file system, cloud, database, configuration). Primnox's workspace/artifact system already has versioning; the gap is **human-in-the-loop approval before application** and **visible diff summaries in chat context**.

---

## 1. Coding Agents Surveyed

### 1.1 Cursor
**Model:** VS Code + native AI copilot, keyboard-driven  
**Key UI patterns:**
- **Inline edits:** Suggests changes directly in the editor, highlighted in a diff sidebar
- **Accept/Reject buttons** on each suggestion block
- **Cmd+Shift+L** opens edit history with full diff review
- **File tree synchronized** — open file reflected in tree, drop to open
- **Context panel** shows relevant files + AST symbol search
- **Streaming edits** — changes appear live but don't save until accepted

**Diff approach:** Side-by-side or unified diff in a sidebar; each suggestion is independently approvable.

### 1.2 Windsurf
**Model:** VS Code + agentic AI, naturally conversational  
**Key UI patterns:**
- **Chat sidebar** for natural-language prompting
- **Suggested edits appear in editor** with a blue highlight and "Accept/Reject" UI
- **Multi-file edits** batched and reviewable as a single "change set"
- **File tree expansion** to show which files will be touched
- **Terminal integration** — can run commands, see output, loop back to chat
- **Search within chat** for past requests
- **"Create workspace" button** to snapshot the current state before a big change

**Diff approach:** Inline in editor with a preview pane; can see full change set before accepting any part.

### 1.3 GitHub Copilot
**Model:** IDE-agnostic (VS Code, JetBrains, Neovim, etc.)  
**Key UI patterns:**
- **Inline suggestions** (autocomplete-style) with Accept/Reject
- **Chat interface** for asking questions and requesting edits
- **Slash commands** (`/explain`, `/test`, `/fix`, `/refactor`) for scoped actions
- **Showing intent** before editing — explains what it will do
- **Context window** in chat can reference files, selection, or entire workspace
- **Edit tracking** — knows which lines were edited in the last turn

**Diff approach:** Minimal in IDE (just highlighting); relies on IDE's native diff viewer for review before acceptance.

### 1.4 Replit
**Model:** Cloud IDE with AI collaboration  
**Key UI patterns:**
- **Real-time collaborative editing** (like Google Docs for code)
- **AI sidebar chat** for requests
- **Suggested edits appear as "ghosts"** (translucent) until clicked to apply
- **File tree on left** with "recently edited" pinning
- **Diff viewer modal** when you hover/click on a change
- **AI can see all files** in the workspace; chat references them by name
- **Version history** for each file
- **Terminal available** for running code, testing edits

**Diff approach:** Modal popup showing before/after; can apply entire suggestion or edit manually.

### 1.5 Devin
**Model:** Autonomous agent that can run full dev workflows  
**Key UI patterns:**
- **Plan visualization** — shows the agent's multi-step plan at the start
- **File browser** shows which files the agent is reading/writing
- **Terminal output** streamed live as the agent works
- **Chat history** with references to specific files and line numbers
- **Agent stop/resume** buttons for long-running tasks
- **Summary cards** at the end showing files created/modified
- **User approval gates** — "I found the bug, approve to apply the fix?"

**Diff approach:** Summary cards; can drill down to see exact changes in a modal.

---

## 2. Common Patterns Across All Agents

### Pattern 1: Staged Edits (Don't Auto-Apply)
All agents show changes **before** applying them. Never surprise the user with modifications.

**UI implementation:**
- Suggested change appears visually distinct (blue border, different background, ghost text)
- Accept button required to commit to the filesystem
- Reject button discards without touching the file
- Optional: keyboard shortcut (Cmd/Ctrl+Shift+Enter typically)

### Pattern 2: Diff + Context Together
The **change itself** is shown alongside **why it's needed** (or which request prompted it).

**UI implementation:**
- Left pane: file tree + chat history
- Center pane: editor with inline edits highlighted
- Right pane: side-by-side diff or change summary
- Context breadcrumb: "In response to: 'add error handling to this function'"

### Pattern 3: File Tree as Navigation
When an agent can touch multiple files, the tree **shows which ones will be changed**.

**UI implementation:**
- Files being edited marked with a dot (●), icon, or highlight
- Clicking a file in the tree jumps to it in the editor
- Batch operations can be previewed at the file-tree level
- Tree is always visible (not hidden in a modal)

### Pattern 4: Cancellation & Undo
The ability to **stop an in-progress edit** and **undo after accepting** is critical UX.

**UI implementation:**
- Red "Stop" button appears while agent is working
- Stopping leaves partial work in place (doesn't erase)
- Ctrl+Z on accepted edits still works (uses editor's native undo)
- "Revert this change" button on individual suggestions

### Pattern 5: Edit Attribution
**Which changes came from AI vs. human?** Must be visible for audit trail.

**UI implementation:**
- AI-generated edits have a marker (badge, color, or sidebar annotation)
- Hover shows timestamp + which request prompted it
- Can filter history to show "only AI changes" or "only my changes"
- Commit messages can auto-tag: "AI-assisted: add error handling"

### Pattern 6: Streaming Feedback Loop
**Show progress while working** (don't leave users staring at a spinner).

**UI implementation:**
- Agent is "thinking" → show reasoning in a sidebar
- Agent starts writing code → show it in real-time
- Agent runs tests → show results live
- User can interrupt at any point

---

## 3. Primnox Audit: Where These Patterns Apply

### 3.1 Current Strengths (Already Present)
- ✅ **Workspace versioning** (WorkspaceVersion table with file diffs)
- ✅ **Turn-level tracking** (which turn created which change)
- ✅ **Event-driven architecture** (can push live updates)
- ✅ **Multi-provider support** (agents can be swapped)

### 3.2 Gaps (Needs Implementation)

#### Gap 1: No Visual Diff in Chat Context
**Problem:** When an agent generates code or edits a file, the user sees only the final result in a workspace, not the before/after side-by-side in chat.

**Affects:** Code review, understanding what changed, auditing agent decisions.

**Transfer pattern from Cursor/Windsurf:** Inline diff viewer in chat messages that reference file changes.

#### Gap 2: No Approval Gate Before Applying Changes
**Problem:** Workspaces are versioned, but there's no UI affordance to "approve before commit."

**Affects:** Safety (agent could silently break things), trust (user doesn't know what's happening).

**Transfer pattern from Cursor/Replit:** Suggested changes appear in a staging area; explicit accept/reject buttons required.

#### Gap 3: File Tree Not Integrated with Agent Context
**Problem:** When an agent says "I'll update these 3 files," there's no visual representation in the UI showing which files are about to change.

**Affects:** Large refactorings, understanding scope.

**Transfer pattern from Windsurf/Devin:** File tree with visual markers (●, color, count badge) showing "touched by this turn."

#### Gap 4: No "Agent is Working" Feedback in the Tree
**Problem:** File tree is static; it doesn't reflect which files the agent is currently reading/writing.

**Affects:** Perception of responsiveness, understanding agent progress.

**Transfer pattern from Devin:** Dynamic annotations on file tree entries (spinner, "reading", "writing", etc.).

#### Gap 5: No Undo/Revert UI for Versioned Changes
**Problem:** WorkspaceVersion exists in the schema, but frontend has no "revert to previous version" or "apply selected changes only" UI.

**Affects:** Recovery from mistakes, selective acceptance of changes.

**Transfer pattern from Cursor:** "Revert" button on each version; or "cherry-pick" mode to accept only some changes.

---

## 4. Design Recommendations

### 4.1 Immediate (Fills Biggest Gaps)

**1. Inline Diff Viewer in Chat**
- When a turn modifies a workspace, show a collapsible diff card in the assistant message
- Format: filename, line-by-line ± changes, line numbers
- Controls: "View full," "Accept all," "Accept selectively," "Discard"

**2. Approval UI for Workspaces**
- New workspace state: `PENDING_REVIEW` (like a draft)
- UI: Yellow banner "3 changes pending review"
- Button group: "Accept All" / "Review & Approve" / "Discard"
- "Review & Approve" opens an approval modal with inline diff viewer

**3. File Tree Annotations**
- When a turn creates/edits files, mark them in the tree with a blue dot
- Hover shows: "Modified in this turn" + turn title
- Count badge: "3 files touched"
- Click the dot to jump to the diff viewer

### 4.2 Medium Term (Polish + Power Users)

**4. Selective Accept (Cherry-Pick)**
- Approval modal lets you accept/reject individual files or hunks
- Generates a new WorkspaceVersion with only the approved changes

**5. Undo & Revert**
- Right-click on workspace version → "Revert to this version"
- Undo button in chat (undoes the latest workspace edit)
- Shows as a new version, not destructive

**6. Agent Context Sidebar**
- "This agent can see X files" sidebar in chat
- Shows which files are in the context bundle
- Search to add/remove files

### 4.3 Advanced (Future, Enables Devin-like Autonomy)

**7. Multi-Turn Planning Visualization**
- When agent is working on a multi-step task, show a plan card
- "Step 1: Audit code for bugs [DONE]"
- "Step 2: Write fixes [IN PROGRESS - reading file X]"
- Approve/reject each step

**8. Streaming Edits (Like Cursor)**
- Edits appear in the editor as the agent generates them
- Accept button required to persist; Ctrl+Z to discard

---

## 5. Implementation Strategy for Primnox

### 5.1 Phase 1: Research Prototype (This Sprint)
Build a clickable component at `/frontend/src/components/proto/coding-agents/` that shows:
- Chat message with a file change notification
- Collapsible diff card (before/after code)
- Approval buttons (Accept/Review/Discard)
- File tree marker (● dot for modified files)

Port: 5302, can be previewed standalone or integrated into chat.

### 5.2 Phase 2: Backend Schema (Next Sprint)
Add to Primnox V2 schema:
- `WorkspaceVersion.approval_status` (pending_review, approved, rejected)
- `Turn.created_workspace_version_id` (link to which version this turn created)
- Event kind: `workspace.approval_requested` and `workspace.approval_response`

### 5.3 Phase 3: Chat Integration (Sprints After)
- When turn modifies workspace, emit `workspace.approval_requested` event
- Chat renders diff card inline
- User clicks Approve → emits `workspace.approval_response` event
- Backend applies the workspace change

### 5.4 Phase 4: File Tree Integration
- ContextRail or sidebar tree shows file markers
- Integration with existing workspace viewer

---

## 6. Pattern Transfers Summary Table

| Coding Agent Pattern | Cursor | Windsurf | Copilot | Replit | Devin | For Primnox |
|---|---|---|---|---|---|---|
| **Staged edits** | ✅ | ✅ | ✅ | ✅ | ✅ | → Approval gate before workspace apply |
| **Inline diff** | ✅ | ✅ | ✅ | ✅ | ⚠️ | → Diff card in chat messages |
| **File tree markers** | ✅ | ✅ | ✅ | ✅ | ✅ | → Blue dots for modified files |
| **Cancellation** | ✅ | ✅ | ⚠️ | ✅ | ✅ | → Stop button during turn |
| **Undo/Revert** | ✅ | ✅ | ⚠️ | ✅ | ✅ | → Revert workspace version |
| **Edit attribution** | ✅ | ✅ | ✅ | ✅ | ✅ | → Turn ID + agent name on changes |
| **Streaming feedback** | ⚠️ | ✅ | ⚠️ | ✅ | ✅ | → Already in Primnox V2 events |
| **Multi-file scoping** | ✅ | ✅ | ⚠️ | ✅ | ✅ | → File tree + diff summary |

---

## 7. Risk & Mitigation

### Risk: "Approval UI adds friction; users want fast iteration"
**Mitigation:** 
- Default to "Accept" for small changes (< 5 lines)
- Keyboard shortcut for power users: Tab → Accept (like Cursor)
- Can be toggled off in settings: `workspace.auto_accept_small_changes`

### Risk: "Diff viewer is complex to implement correctly"
**Mitigation:**
- Use existing library: `react-diff-viewer-continued` or similar
- Start simple: unified diff, not side-by-side
- Reuse Primnox's existing code highlighter (already has syntax coloring)

### Risk: "File tree markers add visual clutter"
**Mitigation:**
- Use a subtle dot (●) only when files are modified
- Optional via setting: `ui.show_file_markers`
- Hide automatically after user approves/rejects

### Risk: "Versioning → storage bloat"
**Mitigation:**
- WorkspaceVersion already exists in schema (not new cost)
- Prune old versions after N days or M versions kept
- Workspace is optional feature (not all turns create workspaces)

---

## 8. What NOT to Transfer

Some coding-agent patterns don't apply to general-purpose Primnox:

1. **IDE-like file editing** — Primnox is chat-first, not editor-first. Don't embed an IDE.
2. **Language-specific linting** — Primnox is multi-domain; can't assume code context.
3. **Terminal integration** — Primnox runs in a web browser, not a native app (yet).
4. **Collaborative simultaneous editing** — Primnox is single-user for now.

---

## 9. Competitors' Approaches (Brief Comparison)

| Aspect | Cursor | Windsurf | Copilot | Replit | Devin |
|---|---|---|---|---|---|
| **UX Philosophy** | Power users (keyboard first) | Conversational (chat first) | IDE-agnostic (integrates) | Collaborative (real-time) | Autonomous (plan → execute) |
| **Edit Safety** | Accept/reject per edit | Accept/reject per batch | Integrated into editor | Modal preview | Summary + drill-down |
| **Learning Curve** | Medium (lots of shortcuts) | Low (natural chat) | Very low (IDE-native) | Low (visual) | Medium (autonomous) |
| **Best For** | Experienced developers | Quick edits & refactoring | Quick questions | Learning + collab | Full feature buildout |

**For Primnox:** Lean toward Windsurf's philosophy (chat-first, approval by batch) with elements of Cursor's power-user affordances (keyboard shortcuts, undo).

---

## 10. References & Further Reading

- Cursor: https://www.cursor.com/ (official docs on edit acceptance)
- Windsurf: https://www.codeium.com/windsurf (agent-driven approach)
- GitHub Copilot: https://github.com/features/copilot (slash commands, chat UI)
- Replit: https://replit.com (collaborative editing + AI sidebar)
- Devin: https://www.devin.ai (autonomous agent planning)
- Primnox V2 Architecture: `docs/ARCHITECTURE_V2.md` (Workspace, WorkspaceVersion, Turn)
- Primnox Conversation Runtime Spec: `docs/CONVERSATION_RUNTIME_SPEC.md` (event protocol)

---

## Appendix A: Primnox Gaps in Detail

### A.1 Workspace Approval State Machine
**Current:** Workspace is created → versioned immediately.  
**Desired:**
```
CREATED → PENDING_REVIEW → APPROVED → APPLIED
                       ↓ (reject)
                    REJECTED
```

### A.2 File Tree Enhancement
**Current:** Static file list in workspace viewer.  
**Desired:**
```
src/
  ├ components/
  │  ├ Chat.tsx                    (● modified in turn_01J8X)
  │  ├ Canvas.tsx
  │  └ Sidebar.tsx                 (● modified in turn_01J8X)
  └ utils/
     └ helpers.ts                  (● new file, added in turn_01J8X)
     
[3 files modified] [View diff] [Approve] [Reject]
```

### A.3 Diff Card in Chat
**Current:** Workspace link in message; user must click to view changes.  
**Desired:**
```
Assistant: I've refactored the Chat component:

┌─ diff: src/components/Chat.tsx (45 lines changed)
│ 
│ const ChatComponent = () => {
│   - const messages = useState([]);
│   + const { messages, loading } = useMessages();
│   
│   return (
│     <div>
│       {messages.map(m => <Message key={m.id} {...m} />)}
│   + {loading && <Spinner />}
│     </div>
│   );
│ };
│
└─ [View full] [Accept] [Reject] [Review & Approve]
```

