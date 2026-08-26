# Long-Running Agents UI Prototype

Research prototype for delegation UX: how users leave tasks running and return to them safely.

## Components

### BackgroundTaskIndicator
Small header badge showing open task count, elapsed time, and progress.

```tsx
<BackgroundTaskIndicator
  task={task}
  onExpand={openPanel}
  onPause={pauseTask}
  onResume={resumeTask}
  onCancel={cancelTask}
/>
```

**Props:**
- `task`: TaskRecord | null — current background task, or null if none
- `onExpand()`: open the full task panel
- `onPause()`: pause an active task
- `onResume()`: resume a paused task
- `onCancel()`: cancel/abandon a task

**Placement:** App header, right side, near provider selector

---

### TaskPanel
Full-width side panel showing task progress, actions, constraints, and recovery options.

```tsx
<TaskPanel
  task={task}
  onClose={closePanel}
  onPause={pauseTask}
  onResume={resumeTask}
  onCancel={cancelTask}
  onRetarget={retargetTask}
/>
```

**Features:**
- Action timeline with expand/collapse for errors and details
- Status indicators: completed ✓, failed ✗, pending ?, unknown ⚠
- Next action highlight (what's about to run)
- Constraints and known facts sidebar
- Retarget dialog (change goal, keep completed work)

**Placement:** Slide in from right edge, modal overlay

---

### TaskNotification
Non-blocking toast notification when a background task completes.

```tsx
<TaskNotification
  task={{
    id: 'task_123',
    goal: 'reduce tool-call cost',
    status: 'completed',
    elapsed_seconds: 3600,
    completed_actions: 8,
    total_actions: 8,
    latest_observation: 'Cached writes save 35% vs uncached',
    error: null,
  }}
  onDismiss={dismissNotification}
  onOpen={openTaskPanel}
/>
```

**Features:**
- Auto-dismisses after 8 seconds (dismissal timer paused on hover)
- Non-blocking: doesn't freeze chat or interrupt user
- Shows summary: goal, action count, elapsed time, key finding
- Error callout if task failed
- Open/dismiss buttons

**Placement:** Bottom-right corner, z-50 (above chat)

---

### CatchUpSummary
Inline summary shown when a user returns to a task after a long gap.

```tsx
<CatchUpSummary
  goal="reduce tool-call cost"
  status="active"
  elapsed_since_update="2h 15m"
  completed_count={5}
  total_actions={8}
  failed_actions={[
    { action: 'measure cache behaviour', error: 'timeout after 30s' }
  ]}
  unresolved_actions={[
    {
      action: 'design immutable compaction',
      status: 'unknown',
      detail: 'process crashed; unclear if it wrote output'
    }
  ]}
  known_facts={[
    'tool transcripts accumulate superlinearly',
    'repeated context transmission is expensive'
  ]}
  latest_observation="Cached writes save 35% vs uncached baseline"
  next_action="design immutable compaction"
  onVerify={verifyUnknownActions}
  onResume={continueTask}
/>
```

**Features:**
- Animated progress bar
- Verification alert if actions are unknown/partial
- Failed actions callout with error messages
- Key findings and known facts
- Next action indicator
- Resume button

**Placement:** Inline in chat, above task panel, after greeting/system message

---

## Integration Guide

### Step 1: Backend API

Create API endpoints in the v2 backend:

```python
# routes/task.py
@app.get('/api/v2/tasks/current')
def get_current_task():
    """Get the most recently touched unfinished task."""
    return task_state.resume()

@app.post('/api/v2/tasks/{task_id}/pause')
def pause_task(task_id: str):
    """Pause a task (set status to 'blocked')."""
    return task_state.finish(task_id, status='blocked')

@app.post('/api/v2/tasks/{task_id}/resume')
def resume_task(task_id: str):
    """Resume a paused task (set status to 'active')."""
    task = task_state.get(task_id)
    if task:
        # Re-verify completed/unknown actions before resuming
        task_state.verify(task_id, verifier=system_verifier)
    return task_state.finish(task_id, status='active')

@app.post('/api/v2/tasks/{task_id}/cancel')
def cancel_task(task_id: str):
    """Cancel a task (set status to 'abandoned')."""
    return task_state.finish(task_id, status='abandoned')

@app.post('/api/v2/tasks/{task_id}/retarget')
def retarget_task(task_id: str, goal: str):
    """Change a task's goal, dropping pending but keeping done work."""
    return task_state.retarget(task_id, goal=goal, drop_pending=True)
```

### Step 2: Frontend Hook

Create a hook to fetch and poll task state:

```tsx
// lib/useBackgroundTask.ts
import { useEffect, useState } from 'react';
import { api } from './crs';

export function useBackgroundTask() {
  const [task, setTask] = useState(null);
  const [polling, setPolling] = useState(false);

  const fetch = async () => {
    try {
      const current = await api.get('/api/v2/tasks/current');
      setTask(current);
      // Keep polling if task is active or blocked
      setPolling(current?.status === 'active' || current?.status === 'blocked');
    } catch (e) {
      setTask(null);
      setPolling(false);
    }
  };

  useEffect(() => {
    fetch();
  }, []);

  // Poll while task is in progress (4-8 second intervals)
  useEffect(() => {
    if (!polling) return;
    const interval = setInterval(fetch, 4000);
    return () => clearInterval(interval);
  }, [polling]);

  return { task, fetch };
}
```

### Step 3: App Integration

Add indicator to header and panel to layout:

```tsx
// App.tsx
import { BackgroundTaskIndicator, TaskPanel, TaskNotification } from './components/proto/long-running-agents';
import { useBackgroundTask } from './lib/useBackgroundTask';

export function App() {
  const [panelOpen, setPanelOpen] = useState(false);
  const [notification, setNotification] = useState(null);
  const { task, fetch } = useBackgroundTask();

  const handlePause = async () => {
    await api.post(`/api/v2/tasks/${task.id}/pause`);
    await fetch();
  };

  const handleResume = async () => {
    await api.post(`/api/v2/tasks/${task.id}/resume`);
    await fetch();
  };

  const handleCancel = async () => {
    await api.post(`/api/v2/tasks/${task.id}/cancel`);
    await fetch();
    setPanelOpen(false);
  };

  const handleRetarget = async (newGoal: string) => {
    await api.post(`/api/v2/tasks/${task.id}/retarget`, { goal: newGoal });
    await fetch();
  };

  // Show notification on completion
  useEffect(() => {
    if (task?.status === 'completed' && !notification) {
      setNotification({
        ...task,
        elapsed_seconds: Math.round((new Date() - new Date(task.created_at)) / 1000),
      });
    }
  }, [task?.status]);

  return (
    <>
      {/* Header */}
      <header className="flex items-center justify-between px-4 py-2 border-b">
        <h1>Primnox</h1>
        <BackgroundTaskIndicator
          task={task}
          onExpand={() => setPanelOpen(true)}
          onPause={handlePause}
          onResume={handleResume}
          onCancel={handleCancel}
        />
      </header>

      {/* Main content */}
      <main className="flex-1">
        {/* Chat, settings, etc. */}
      </main>

      {/* Side panel */}
      {panelOpen && task && (
        <TaskPanel
          task={task}
          onClose={() => setPanelOpen(false)}
          onPause={handlePause}
          onResume={handleResume}
          onCancel={handleCancel}
          onRetarget={handleRetarget}
        />
      )}

      {/* Toast notifications */}
      {notification && (
        <TaskNotification
          task={notification}
          onDismiss={() => setNotification(null)}
          onOpen={() => {
            setNotification(null);
            setPanelOpen(true);
          }}
        />
      )}
    </>
  );
}
```

---

## Task Record Shape

These components expect a TaskRecord matching `backend/v2/task_state.py`:

```typescript
interface TaskRecord {
  id: string;
  goal: string;
  status: 'active' | 'blocked' | 'completed' | 'failed' | 'partial' | 'abandoned';
  constraints: string[];
  created_at: string; // ISO 8601
  updated_at: string; // ISO 8601
  latest_observation: string | null;
  next_actions: string[];
  known: string[];
  actions: Array<{
    id: string;
    sequence: number;
    description: string;
    status: 'pending' | 'running' | 'completed' | 'failed' | 'partial' | 'unknown' | 'skipped';
    started_at: string | null; // ISO 8601
    finished_at: string | null; // ISO 8601
    error: string | null;
    detail: string | null;
  }>;
}
```

---

## Testing Checklist

- [ ] Indicator shows/hides correctly (has task → show, no task → hide)
- [ ] Elapsed time updates every second
- [ ] Panel expands on click, closes on click
- [ ] Pause button works (status changes to 'blocked', indicator stops spinning)
- [ ] Resume button works (status changes to 'active', polling resumes)
- [ ] Cancel button works (status changes to 'abandoned', panel closes)
- [ ] Action timeline expands/collapses on click
- [ ] Error details show in expanded actions
- [ ] Retarget dialog opens/closes
- [ ] Notification appears on task completion
- [ ] Notification auto-dismisses after 8 seconds
- [ ] Notification dismiss/open buttons work
- [ ] CatchUpSummary shows on first render after resumption
- [ ] Verification alert appears if actions are unknown/partial

---

## Design Decisions

### Polling vs. WebSocket
**Decision:** Polling (4-8 second intervals)
**Rationale:** Simpler client implementation, acceptable latency for background tasks, reduces server load

**Future:** Switch to WebSocket/SSE in Phase 3 for sub-second updates

### Single Task vs. Multiple Concurrent
**Decision:** One active task at a time (task_state.resume() returns most recent)
**Rationale:** Simpler UX, aligns with current agent architecture (one thing at a time)

**Future:** Support multiple concurrent tasks with task switching in Phase 2

### Auto-Resume on Return
**Decision:** Show task in panel, prompt "Resume?" — do not auto-start
**Rationale:** User control, safety (no surprise resumption), allows verification first

**Future:** Add preference toggle for auto-resume in settings

---

## Performance Notes

- **Context cost:** task_state.render() ≈ 500 tokens vs. full transcript ≈ 2000 tokens
- **Polling cost:** Every 4 seconds, ~10 KB request → negligible at scale (< 1 req/sec per user)
- **Memory:** One TaskRecord + actions array → < 50 KB in memory
- **Rendering:** Motion animations disabled if `prefers-reduced-motion: reduce`

---

## Future Phases

**Phase 1 (done):** Background task indicator + basic panel
**Phase 2:** Multiple concurrent tasks, task switching
**Phase 3:** WebSocket for live updates, notification consolidation
**Phase 4:** Verification UI, recovery action suggestions, memory integration
