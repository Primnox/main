# Primnox Calendar + Tasks + Notes — full design spec

The complete design vision for the unified Calendar + Tasks + Notes suite, preserved
verbatim so the mockups and reference aren't lost. The build-relevant summary also lives
in agent memory (`primnox-calendar-tasks-notes-design`); this file is the long-form artifact.

**North star:** don't copy a single app. Combine the strongest ideas from Google Calendar,
Notion, TickTick, and Todoist so an **event, task, note, project, and AI assistant are all
connected to the same underlying object** — a personal OS, not just a calendar.

> Note on "Notion two-way sync": this means **Primnox Notes ↔ Primnox Calendar** (internal),
> NOT an integration with Notion.com. Cleanest model = notes and calendar are two *views* of
> one object (a dated note IS a calendar entry), so there's nothing to sync.

---

## Layout

```text
┌──────────────────────────────────────────────────────┐
│ Top Bar                                               │
│ Search | Quick Add | AI Assistant | Notifications     │
├─────────────┬──────────────────────────┬─────────────┤
│ Left Panel  │ Main Calendar Area       │ Right Panel │
│             │                          │             │
│ Mini Cal    │ Week / Month / Day View  │ Details     │
│ Calendars   │                          │ Notes       │
│ Tasks       │ Events & Tasks           │ AI Actions  │
│ Projects    │                          │             │
└─────────────┴──────────────────────────┴─────────────┘
```

## Left Sidebar (Google + TickTick)

```text
📅 Calendar      [ + Create ]      June 2026

📂 Calendars        📝 Tasks          📁 Projects
🟦 Personal         ⭐ Today           Primnox
🟩 College          📋 Upcoming        Video Editor
🟪 Primnox          📌 Important       College
```

Google's mini-calendar + TickTick's task organization. Everything one click away.

## Center — Google-style grid

Week view = hourly blocks. Keep: drag & drop, resize events, color-coded events, multi-day
events. Drag up/down = change time, resize = duration, drag sideways = move day.
Views: **Day · Week · Month · Agenda(Schedule) · Year · Kanban · Timeline.**

## Floating Agenda Panel (Notion Calendar)

Below the calendar, switches automatically with the selected date:

```text
Upcoming
Today          • AI Assignment   • Database Lab
Tomorrow       • Primnox Testing • Meeting
```

## Right Sidebar (Notion + AI) — click an event

```text
Project Meeting
🕒 4 PM - 5 PM   👥 Participants   📍 Location
📝 Notes: - Backend - Database - Testing

✨ AI Actions:  Generate Summary | Create Tasks | Reschedule | Draft Follow-Up
```

This is where Primnox differs — Google has no real note integration.

## Task View (Todoist + TickTick)

Subtasks · priorities · tags · due dates. Checklist + Kanban + calendar-integrated views.

```text
Today      ☐ Finish Assignment  ☐ Push GitHub Update  ☑ Review Code
Tomorrow   ☐ Study DBMS         ☐ Team Meeting
```

## Kanban (per project)  ·  Timeline (project planning)

```text
To Do      Doing      Done            Mon ── Task
Task A     Task B     Task C          Tue ── Meeting
Task D                                Wed ── Development
```

## AI Command Bar (Ctrl+K) — should be everywhere

```text
> Schedule meeting tomorrow 4 PM
> Move all college tasks to weekend
> Create study plan
```

## Natural-language entry

`Finish DBMS assignment tomorrow at 7 PM` → Task "Finish DBMS assignment", Due: tomorrow 7 PM.

## Notes integration

Every event can contain Notes, Files, Links, Attachments, Recordings — Notion pages inside
calendar items.

## Dashboard (on open)

```text
Good Evening, Aniketh
Today — 📅 3 Events  📝 5 Tasks
Next Event: Database Lab    Due Soon: AI Assignment    Suggested Focus: Primnox Testing
```

## What to steal from each product

| Product         | Take                          |
| --------------- | ----------------------------- |
| Google Calendar | Calendar grid, scheduling UX  |
| Notion Calendar | Clean aesthetics, agenda      |
| Todoist         | Task organization             |
| TickTick        | Task management power         |
| Notion          | Notes and databases           |
| Primnox         | AI layer everywhere           |

---

## Reference: Google Calendar feature checklist (inspiration)

- **Events:** title, description, location, guests, color labels, recurring, notifications,
  file attachments, video-meeting links.
- **Tasks:** due date, subtasks, completion checkbox, appears inside the calendar (no fixed
  duration — focuses on completion).
- **Reminders:** lightweight ("call mom", "pay bill").
- **Goals (discontinued):** auto-find time for exercise/reading/study — the AI-scheduling idea.
- **Views:** Day, Week, Month, Schedule/Agenda, Year.
- **Notifications:** 10 min / 1 hr / 1 day before.
- **Search:** by event title, people, location, date range.
- **AI features to aim past Google:** NL scheduling, smart rescheduling, deadline prediction,
  workload balancing, notes attached to every event.

Other UIs worth studying: Notion Calendar, Outlook, Fantastical, TickTick, Todoist.
