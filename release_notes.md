### ??? Native Dynamic Island
- Re-architected the Electron main process to render a transparent, floating desktop overlay window for ambient data.
- Replaces the standard UI with a 'Tech-Noir' HUD displaying active tasks, flow state, and system events.
- Minimizing the main app automatically transitions Primnox into Island Mode.

### ?? Ambient Data Tracking
- Tracks 'Flow State' duration based on app focus.
- Real-time Git Pulse (ahead/behind/uncommitted) monitoring.
- Tracks coding error streaks and resolutions natively.

### ? LLM Smart Paste & Error Handling
- `triggerSmartPaste`: Transform clipboard contents via LLM based on the active target application before pasting.
- `/api/error_explain`: Feed clipboard errors directly to the Dynamic Island for real-time explanations and glowing UI fixes.
- Optimized prompt parsing to gracefully handle markdown code fences in JSON responses.

### ??? UX Improvements
- Removed the Groq API key prompt from the Windows `.exe` installer wizard so users can install freely.
