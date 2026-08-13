import { useState, useEffect, useCallback, useRef, useSyncExternalStore } from 'react';
import { API_BASE } from '../config';

const API_BASE_URL = API_BASE;

export interface Toast {
  id: string;
  type: 'success' | 'error' | 'info' | 'warning';
  message: string;
}

import { vadBus } from './vadBus';

export function useVadLevel() {
  return useSyncExternalStore(vadBus.subscribe, vadBus.get);
}

export function usePrimnox() {
  const [messages, setMessages] = useState<any[]>([]);
  const [state, setState] = useState('idle');
  const [micMuted, setMicMuted] = useState(false);
    // vadLevel now lives in vadBus (see vadBus.ts) — not React state — to avoid
  // a full-app re-render on every 10Hz VAD tick. Kept out of this hook's
  // returned object; consumers use useVadLevel() directly.
  const [notes, setNotes] = useState<any[]>([]);
  const [tasks, setTasks] = useState<any[]>([]);
  const [memory, setMemory] = useState<any[]>([]);
  const [chatSessions, setChatSessions] = useState<any[]>([]);
  const [chatFolders, setChatFolders] = useState<any[]>([]);
  const [activeChatId, setActiveChatId] = useState<string>('current');
  
  const [activity, setActivity] = useState<any[]>([]);
  const [meetings] = useState<any[]>([]);
  const [debriefs] = useState<any[]>([]);
  const [transcripts, setTranscripts] = useState<any[]>([]);
  const [currentTranscript, setCurrentTranscript] = useState("");
  const [lastAttachedFile, setLastAttachedFile] = useState<string | null>(null);
  const [incognito, setIncognito] = useState(false);
  const [settings, setSettings] = useState<any>({});
  
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [islandError, setIslandError] = useState<{ summary: string; fix: string; hover_text: string } | null>(null);
  // What the Privacy Mirror pseudonymized before this exchange left the
  // device — backend already computed and broadcast this (core.py's
  // `privacy_scrub` event, fed by ScrubSession.mapping in privacy_mirror.py);
  // nothing on the frontend was listening for it, so the diff never reached
  // the UI. Cleared on each new send so a stale reveal doesn't linger under
  // an unrelated later reply.
  const [privacyScrub, setPrivacyScrub] = useState<{ mapping: { original: string; placeholder: string; label: string }[]; model: string } | null>(null);

  // ── Island ambient features ────────────────────────────────────────────
  const [flowState, setFlowState] = useState<{ duration_minutes: number; started_at: number; app: string } | null>(null);
  const [errorStreak, setErrorStreak] = useState<{ error: string; duration_minutes: number } | null>(null);
  const [nowPlaying, setNowPlaying] = useState<{
    title: string;
    artist: string;
    album?: string;
    source: string;
    is_playing?: boolean;
    position_ms?: number;
    duration_ms?: number;
    sampled_at?: number;
  } | null>(null);
  const [productivityScore, setProductivityScore] = useState<number>(100);
  const [parallelTasks, setParallelTasks] = useState<{ id: string; label: string; color: string }[]>([]);
  const [proactiveAlert, setProactiveAlert] = useState<{ message: string; suggestions: string[] } | null>(null);

  // ── Island Skills (pluggable strips e.g. calendar) ────────────────────────
  const [islandSkills, setIslandSkills] = useState<Record<string, any>>({});

  const [connectionLost, setConnectionLost] = useState(false);
  const [reconnectAttempt, setReconnectAttempt] = useState(0);
  const [startupComplete, setStartupComplete] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttempts = useRef(0);
  const maxAttempts = 5;
  const connectRef = useRef<(() => void) | null>(null);
  const tokenBufferRef = useRef<string>("");
  const animationFrameIdRef = useRef<number | null>(null);
  // Which message the current reply is streaming into. Streaming used to find
  // its target by scanning BACKWARDS for the last message from Primnox, which
  // is only correct while nothing else appends one mid-turn. A permission
  // card, a daily brief or a proactive nudge all do — and the scan would then
  // land on that instead, overwriting it and leaving the real reply stranded
  // half-written. An explicit id can't be aimed at the wrong message.
  const streamTargetRef = useRef<number | null>(null);
  const streamSeqRef = useRef(0);

  /** Writes whatever tokens have accumulated into the bubble being streamed. */
  const flushTokens = useCallback(() => {
    const flushed = tokenBufferRef.current;
    tokenBufferRef.current = "";
    if (!flushed) return;
    const sid = streamTargetRef.current;
    setMessages(prev => {
      const idx = sid == null ? -1 : prev.findIndex(m => m._sid === sid);
      if (idx === -1) return prev;
      const msg = { ...prev[idx] };
      if (msg.isTyping) {
        msg.isTyping = false;
        msg.text = flushed;
      } else {
        msg.text = (msg.text || '') + flushed;
      }
      const next = [...prev];
      next[idx] = msg;
      return next;
    });
  }, []);

  const cancelPendingFlush = useCallback(() => {
    if (animationFrameIdRef.current !== null) {
      clearTimeout(animationFrameIdRef.current);
      animationFrameIdRef.current = null;
    }
  }, []);

  // Batched on a timer, NOT requestAnimationFrame. rAF is frozen entirely
  // while the window is minimised, occluded or on another virtual desktop —
  // and sending a message then tabbing away while Primnox thinks is the
  // normal way to use it. Tokens would pile up in the buffer, unflushed, and
  // the reply appeared blank or half-written until something else forced a
  // render. A timer is throttled in the background but still fires.
  const scheduleFlush = useCallback(() => {
    if (animationFrameIdRef.current !== null) return;
    animationFrameIdRef.current = setTimeout(() => {
      animationFrameIdRef.current = null;
      flushTokens();
    }, 33) as unknown as number;
  }, [flushTokens]);
  const parallelTaskTimers = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());
  const proactiveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const triggerIslandError = useCallback(async (errorMessage: string, context?: string, preFilled?: { summary?: string; fix?: string }) => {
    // Stage 1 triage on the backend now returns summary/fix in the same call
    // that detects the error (see feed_manager.py's _stage1_uai_triage) —
    // when it did, use that directly instead of firing a THIRD LLM call
    // (/api/error_explain) for information we already have.
    if (preFilled?.summary && preFilled?.fix) {
      setIslandError({ summary: preFilled.summary, fix: preFilled.fix, hover_text: 'click to copy the fix' });
      return;
    }
    try {
      const resp = await fetch(`${API_BASE_URL}/api/error_explain`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ error_message: errorMessage, context: context || '' })
      });
      if (resp.ok) {
        const payload = await resp.json();
        setIslandError(payload);
      }
    } catch (e) {
      console.error('triggerIslandError failed', e);
      setIslandError({
        summary: "error handler itself errored out, classic",
        fix: "check the logs bro",
        hover_text: "click to copy the fix"
      });
    }
  }, []);

  const clearIslandError = useCallback(() => setIslandError(null), []);

  const addToast = useCallback((type: Toast['type'], message: string) => {
    const id = Math.random().toString(36).substring(7);
    setToasts(prev => [...prev, { id, type, message }]);
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id));
    }, 4000);
  }, []);

  // ── Smart Paste (defined after addToast so dep array is valid) ─────────
  // Primary path: global shortcut in electron.cjs reads clipboard natively
  // and sends 'smart-paste-result' IPC — no focus required, works in island mode.
  // Fallback path: if called in-app (e.g. future button), uses navigator.clipboard.
  const triggerSmartPaste = useCallback(async () => {
    // Prefer the native main-process path. navigator.clipboard.readText() rejects
    // when the island window is unfocused (focusable:false), so in Electron we
    // delegate to the same handler the global shortcut uses; the result comes back
    // over the 'smart-paste-result' IPC listener below.
    const electron = (window as any).electron;
    if (electron?.ipcRenderer) {
      electron.ipcRenderer.send('run-smart-paste');
      return;
    }
    // Fallback for non-Electron (browser) contexts: Web Clipboard API.
    try {
      const clipboardContent = await navigator.clipboard.readText();
      if (!clipboardContent.trim()) return;
      const resp = await fetch(`${API_BASE_URL}/api/smart_paste`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: clipboardContent })
      });
      if (resp.ok) {
        const { transformed } = await resp.json();
        await navigator.clipboard.writeText(transformed);
        addToast('success', 'Clipboard transformed — paste away');
      }
    } catch (e) {
      console.error('Smart paste failed', e);
      addToast('error', 'Smart paste failed — clipboard permission?');
    }
  }, [addToast]);

  // ── Listen for global-shortcut smart paste result from main process ──────
  useEffect(() => {
    const electron = (window as any).electron;
    if (!electron?.ipcRenderer) return;
    const unsub = electron.ipcRenderer.on('smart-paste-result', ({ ok, changed }: { ok: boolean, changed?: boolean }) => {
      if (!ok)          addToast('error',   'Smart paste failed — is the backend running?');
      else if (changed) addToast('success', 'Clipboard transformed — paste away');
      // silent when ok && !changed: content was already optimal, no toast needed
    });
    return () => { if (typeof unsub === 'function') unsub(); };
  }, [addToast]);

  // ── Push the Dynamic Island on/off setting to the main process (#13) ──────
  // Fires on initial settings load and whenever the toggle changes.
  // Skip the first render where settings is still empty ({}) to avoid sending
  // 'true' before the real value has loaded (race that could flip island on).
  useEffect(() => {
    if (Object.keys(settings || {}).length === 0) return;
    const electron = (window as any).electron;
    if (!electron?.ipcRenderer) return;
    electron.ipcRenderer.send('island:set-enabled', settings?.dynamic_island_enabled !== false);
  }, [settings?.dynamic_island_enabled]);

  useEffect(() => {
    let reconnectTimer: NodeJS.Timeout;
    
    const connect = () => {
      connectRef.current = connect;   // keep ref fresh for manualReconnect
      const socket = new WebSocket(`${API_BASE_URL.replace('http', 'ws')}/ws`);
      
      socket.onopen = () => {
        reconnectAttempts.current = 0;
        setReconnectAttempt(0);
        setConnectionLost(false);
      };

      socket.onmessage = (event) => {
        let data: any;
        try {
          data = JSON.parse(event.data);
        } catch {
          console.warn('[ws] malformed message, skipping', event.data?.slice?.(0, 80));
          return;
        }
        const type = data.type;
        const payload = data.data;

        if (type === 'message') {
          const isPrimnox = payload.sender?.toUpperCase() === 'PRIMNOX';

          if (isPrimnox && payload.isTyping) {
            // Start of a reply. Claim an id now so tokens and the final
            // message both know exactly which bubble they belong to.
            const sid = ++streamSeqRef.current;
            streamTargetRef.current = sid;
            flushTokens();
            setMessages(prev => [...prev, { ...payload, _sid: sid }]);
          } else if (isPrimnox) {
            // Final reply. Any buffered tokens are superseded by the full
            // text in this payload, so drop them rather than appending twice.
            cancelPendingFlush();
            tokenBufferRef.current = "";
            const sid = streamTargetRef.current;
            streamTargetRef.current = null;
            setMessages(prev => {
              const idx = sid == null ? -1 : prev.findIndex(m => m._sid === sid);
              // No bubble to land in (a reply with no preceding typing event —
              // a reminder firing, a tool result) is appended, never merged
              // into whatever happened to be last.
              if (idx === -1) return [...prev, payload];
              const next = [...prev];
              next[idx] = { ...payload, _sid: sid };
              return next;
            });
          } else {
            setMessages(prev => [...prev, payload]);
          }
        }
        else if (type === 'token') {
          tokenBufferRef.current += payload.text;
          scheduleFlush();
        }
        else if (type === 'privacy_scrub') {
          if (payload?.mapping?.length) setPrivacyScrub(payload);
        }
        else if (type === 'state') {
          setState(payload.value);
          if ((window as any).electron) {
            (window as any).electron.ipcRenderer.send('friday:state', { value: payload.value });
          }
        }
        else if (type === 'mic_state') {
          setMicMuted(payload.muted);
          if ((window as any).electron) {
            (window as any).electron.ipcRenderer.send('friday:mic-state', { muted: payload.muted });
          }
        }
        else if (type === 'vad_level') vadBus.set(payload.rms);
        else if (type === 'transcript_added') setTranscripts(prev => [payload, ...prev]);
        else if (type === 'transcript') setCurrentTranscript(payload.text);
        else if (type === 'note_added') {
          fetch(`${API_BASE_URL}/notes`)
            .then(res => res.json())
            .then(data => {
              if (Array.isArray(data)) {
                const sorted = [...data].sort((a, b) => a.id - b.id);
                setNotes(sorted);
                // Notify graph view to refresh
                window.dispatchEvent(new CustomEvent('primnox:notes-changed'));
              }
            });
        }
        else if (type === 'task_added') { fetchTasks(); }
        else if (type === 'memory_updated') {
          // Memory is deliberately silent — no toast. Announcing every stored
          // fact made the app feel like it was watching over your shoulder;
          // what was remembered is always inspectable in the Memory view.
          fetchMemory();
        }
        else if (type === 'permission_request') {
          // The backend is blocked mid-tool-call waiting on this (see
          // permission_manager.py) — render it as an Allow/Deny chat card
          // using the same structured-block shape a model reply can emit,
          // reusing StructuredBlock's `buttons` rendering rather than a
          // separate confirm-dialog component.
          const token = payload?.token;
          if (token) {
            const body = payload?.description || 'This action needs your confirmation.';
            // A scoped request covers every step of one task. Saying so is the
            // whole point of scoping it — otherwise the user has no way to
            // know whether Allow means "this line" or "the next five minutes".
            const scopeNote = payload?.covers_run
              ? '\n\n_One approval covers every step of this task._'
              : '';
            setMessages(prev => [...prev, {
              sender: 'Primnox',
              text: body + scopeNote,
              timestamp: Date.now(),
              permissionToken: token,
              permissionState: 'pending',
              blocks: [{
                type: 'buttons',
                buttons: [
                  { label: 'Allow', action: `permission:${token}:allow` },
                  { label: 'Deny', action: `permission:${token}:deny` },
                ],
              }],
            }]);
          }
        }
        else if (type === 'daily_debrief') {
          const briefText = payload?.debrief || 'Daily brief generated.';
          setMessages(prev => [...prev, {
            sender: 'Primnox',
            text: `**Daily Brief**\n\n${briefText}`,
            timestamp: Date.now(),
          }]);
          addToast('success', 'Daily brief ready — check chat');
        }
        else if (type === 'settings_updated') setSettings(payload);
        else if (type === 'incognito_changed') setIncognito(payload.active);
        else if (type === 'screenshot_taken') {
           addToast('success', 'ss saved fr');
           setLastAttachedFile(payload?.filename || 'SCREENSHOT.PNG');
        }
        else if (type === 'file_attached') {
           addToast('info', `Attached: ${payload?.filename || 'file'}`);
           setLastAttachedFile(payload?.filename || 'ATTACHMENT.DAT');
        }
        else if (type === 'skill_started') {
          addToast('info', 'working on it...');
          const taskId = `task-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
          const colors = ['#6366f1', '#8b5cf6', '#06b6d4', '#10b981', '#f59e0b'];
          const color = colors[Math.floor(Math.random() * colors.length)];
          const label = payload?.skill || 'task';
          setParallelTasks(prev => [...prev, { id: taskId, label, color }]);
          const pillTimer = setTimeout(() => {
            setParallelTasks(prev => prev.filter(t => t.id !== taskId));
            parallelTaskTimers.current.delete(taskId);
          }, 60000);
          parallelTaskTimers.current.set(taskId, pillTimer);
        }
        else if (type === 'skill_complete') {
          const skillName = payload?.skill || payload?.label || '';
          addToast('success', skillName ? `Done: ${skillName}` : 'skill complete');
          setParallelTasks(prev => {
            if (prev.length === 0) return prev;
            // Match by skill label; fall back to FIFO if no match
            const idx = skillName
              ? prev.findIndex(t => t.label === skillName)
              : -1;
            const targetIdx = idx >= 0 ? idx : 0;
            const completed = prev[targetIdx];
            const timer = parallelTaskTimers.current.get(completed.id);
            if (timer) {
              clearTimeout(timer);
              parallelTaskTimers.current.delete(completed.id);
            }
            return prev.filter((_, i) => i !== targetIdx);
          });
        }
        else if (type === 'skill_phase') {
          // Live step-by-step activity for a running skill, appended to the
          // in-flight Primnox message. A phase is emitted twice — once as
          // "running", once resolved — so match the existing entry and
          // replace it in place rather than stacking duplicates.
          setMessages(prev => {
            const newMsgs = [...prev];
            let i = newMsgs.length - 1;
            while (i >= 0 && newMsgs[i].sender?.toUpperCase() !== 'PRIMNOX') i--;
            if (i < 0) return prev;
            const activity = [...(newMsgs[i].activity || [])];
            const key = (p: any) => (p.step != null ? `s${p.step}` : `p${p.phase}`);
            const at = activity.findIndex(p => key(p) === key(payload));
            if (at >= 0) activity[at] = { ...activity[at], ...payload };
            else activity.push(payload);
            newMsgs[i] = { ...newMsgs[i], activity };
            return newMsgs;
          });
        }
        else if (type === 'tool_executing') {
          // LLM is calling a tool — show briefly in the island status area
          if (payload?.tool) addToast('info', `using: ${payload.tool.replace('_', ' ')}`);
        }
        else if (type === 'tool_call' || type === 'tool_result') {
          // What the model actually ran (and what came back), appended live to
          // the in-flight Primnox message so it's visible as it happens. The
          // final "message" broadcast carries the same blocks, so this stays
          // consistent after the turn completes and on reload.
          const block = { type, ...payload };
          setMessages(prev => {
            const newMsgs = [...prev];
            let i = newMsgs.length - 1;
            while (i >= 0 && newMsgs[i].sender?.toUpperCase() !== 'PRIMNOX') i--;
            if (i >= 0) newMsgs[i] = { ...newMsgs[i], blocks: [...(newMsgs[i].blocks || []), block] };
            return newMsgs;
          });
        }
        else if (type === 'privacy_scrub') {
          // What was pseudonymized before this turn hit the cloud. Attach to the
          // current (typing) Primnox message so ChatView can render the reveal.
          setMessages(prev => {
            const newMsgs = [...prev];
            let i = newMsgs.length - 1;
            while (i >= 0 && newMsgs[i].sender?.toUpperCase() !== 'PRIMNOX') i--;
            if (i >= 0) newMsgs[i] = { ...newMsgs[i], privacyScrub: payload };
            return newMsgs;
          });
        }
        else if (type === 'file_ready') {
          // A skill produced a file — let the user know
          const name = payload?.skill || 'skill';
          addToast('success', `${name} — file ready`);
        }
        else if (type === 'skill_unavailable') addToast('error', "can't do that one yet");
        else if (type === 'fallback_triggered') addToast('warning', 'main model bailed — using backup');
        else if (type === 'rate_limit_hit') addToast('warning', 'rate limited, give it a sec');
        else if (type === 'startup_complete') setStartupComplete(true);
        else if (type === 'proactive_message') {
          // Show in Dynamic Island only — do NOT pollute the chat history
          const alert = { message: payload.message, suggestions: payload.suggestions || [] };
          setProactiveAlert(alert);
          if (proactiveTimerRef.current) clearTimeout(proactiveTimerRef.current);
          proactiveTimerRef.current = setTimeout(() => setProactiveAlert(null), 15000);
          // Forward to the island overlay window
          if ((window as any).electron) {
            (window as any).electron.ipcRenderer.send('friday:proactive', {
              message: payload.message,
              suggestions: payload.suggestions || []
            });
          }
        }
        else if (type === 'clipboard_sensitive') {
          addToast('warning', 'Sensitive data detected on clipboard!');
          setState('copy');
          if ((window as any).electron) {
            (window as any).electron.ipcRenderer.send('friday:proactive', {
              message: 'Sensitive clipboard data detected. Clear it?',
              suggestions: ['Clear Clipboard']
            });
          }
        }
        else if (type === 'session_updated') {
          // A session title was auto-generated — refresh the sidebar
          fetchChats();
        }
        else if (type === 'reminder_triggered') {
          const msg = payload?.text || 'reminder';
          // Show in Dynamic Island (proactive alert panel)
          const alert = { message: `⏰  ${msg}`, suggestions: ['Got it', 'Snooze 5 min'] };
          setProactiveAlert(alert);
          if (proactiveTimerRef.current) clearTimeout(proactiveTimerRef.current);
          proactiveTimerRef.current = setTimeout(() => setProactiveAlert(null), 30000);
          // Forward to island overlay window if in island mode
          if ((window as any).electron) {
            (window as any).electron.ipcRenderer.send('friday:proactive', {
              message: `⏰  ${msg}`,
              suggestions: ['Got it', 'Snooze 5 min'],
            });
          }
          // Toast as secondary notification
          addToast('info', `⏰ ${msg}`);
        }
        else if (type === 'navigate') {
          // Backend wants to navigate to a screen — dispatch custom event App.tsx listens to
          const screen = payload?.screen;
          if (screen) window.dispatchEvent(new CustomEvent('primnox:navigate', { detail: { screen } }));
        }
        else if (type === 'backup_complete') addToast('success', 'backed up, encrypted');
        else if (type === 'backup_failed') addToast('error', "backup didn't go through");
        else if (type === 'emotion_updated') {
          if (payload?.mood) addToast('info', `vibe detected: ${payload.mood.toLowerCase()}`);
        }
        else if (type === 'profile_updated') {
          addToast('info', 'profile updated from recent activity');
        }
        else if (type === 'error_island') triggerIslandError(payload?.error_message || 'unknown error', payload?.context, { summary: payload?.summary, fix: payload?.fix });
        // ── Ambient island features ──────────────────────────────────────
        else if (type === 'flow_state') setFlowState(payload);
        else if (type === 'flow_broken') setFlowState(null);
        else if (type === 'error_streak') setErrorStreak(payload);
        else if (type === 'error_resolved') setErrorStreak(null);
        else if (type === 'now_playing') setNowPlaying(payload && typeof payload === 'object' && payload.title ? payload : null);
        else if (type === 'productivity_score') setProductivityScore(payload?.score ?? 100);
        else if (type === 'island_skill') {
          const skillName = payload?.skill;
          if (skillName) {
            setIslandSkills(prev => ({ ...prev, [skillName]: payload?.data ?? null }));
          }
        }
      };
      
      socket.onclose = () => {
        // A reply in flight when the socket drops will never get its closing
        // `message` event, so the bubble would sit on the typing animation
        // forever. Land whatever arrived and say plainly that it was cut off —
        // an unfinished answer the user can see beats one that pretends to
        // still be coming.
        cancelPendingFlush();
        flushTokens();
        const sid = streamTargetRef.current;
        streamTargetRef.current = null;
        // A non-null sid IS the "never finalised" signal — the final message
        // clears it. Don't also test isTyping: that flips to false on the
        // first flushed token, long before the reply is complete.
        if (sid != null) {
          setMessages(prev => prev.map(m => m._sid === sid
            ? { ...m, isTyping: false, text: (m.text || '') + '\n\n_(disconnected before Primnox finished replying)_' }
            : m));
        }

        if (reconnectAttempts.current >= maxAttempts) {
          setConnectionLost(true);
          // Auto-recover after 30 s so a restarted backend is picked up
          // without requiring the user to reload the page.
          reconnectTimer = setTimeout(() => {
            reconnectAttempts.current = 0;
            setConnectionLost(false);
            connect();
          }, 30000);
          return;
        }
        const delay = Math.pow(2, reconnectAttempts.current) * 1000;
        reconnectAttempts.current += 1;
        setReconnectAttempt(reconnectAttempts.current);
        reconnectTimer = setTimeout(connect, delay);
      };
      
      wsRef.current = socket;
    };

    connect();
    return () => {
      clearTimeout(reconnectTimer);
      // Cancel all pending pill expiry timers so they don't setState after unmount
      parallelTaskTimers.current.forEach(t => clearTimeout(t));
      parallelTaskTimers.current.clear();
      cancelPendingFlush();
      if (wsRef.current) {
        wsRef.current.onclose = null; // Prevent reconnect loop in StrictMode
        wsRef.current.close();
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [addToast, triggerIslandError]);

  const sendMessage = useCallback(async (text: string, sessionId: string = 'current', files?: File[] | null) => {
    setPrivacyScrub(null);
    if (files && files.length > 0) {
      // Upload files via multipart FormData so the backend receives actual bytes
      const formData = new FormData();
      formData.append('text', text);
      formData.append('sessionId', sessionId);
      for (const f of files) {
        formData.append('files', f);
      }
      await fetch(`${API_BASE_URL}/message`, {
        method: 'POST',
        body: formData,  // no Content-Type header — browser sets boundary automatically
      });
    } else {
      await fetch(`${API_BASE_URL}/message`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, sessionId })
      });
    }
  }, []);

  const respondToPermission = useCallback(async (token: string, allow: boolean) => {
    // Resolve the card optimistically. The buttons previously stayed live and
    // unchanged after a click, so an answered prompt looked identical to an
    // unanswered one — the user had no way to tell whether their Allow had
    // registered, and could answer the same token twice.
    setMessages(prev => prev.map(m =>
      m.permissionToken === token && m.permissionState === 'pending'
        ? { ...m, permissionState: allow ? 'allowed' : 'denied', blocks: null }
        : m
    ));
    try {
      await fetch(`${API_BASE_URL}/api/permission_response`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token, allow }),
      });
    } catch (e) {
      // The backend is blocked waiting on this answer and will time out into
      // a deny, so say so rather than leaving the card claiming "Allowed".
      console.error('Permission response failed', e);
      setMessages(prev => prev.map(m =>
        m.permissionToken === token ? { ...m, permissionState: 'failed' } : m
      ));
      addToast('error', "Couldn't send that answer — Primnox may have stopped.");
    }
  }, [addToast]);

  const toggleMic = useCallback(async () => {
    try {
      const resp = await fetch(`${API_BASE_URL}/mic/toggle`, { method: 'POST' });
      if (resp.ok) {
        const data = await resp.json();
        setMicMuted(data.muted ?? !micMuted);
      }
    } catch (e) {
      console.error('toggleMic failed', e);
    }
  }, [micMuted]);

  const toggleIncognito = useCallback(async () => {
    await fetch(`${API_BASE_URL}/incognito/toggle`, { method: 'POST' });
  }, []);

  const fetchSettings = useCallback(async () => {
    try {
      const resp = await fetch(`${API_BASE_URL}/settings`, { signal: AbortSignal.timeout(5000) });
      const data = await resp.json();
      setSettings(data);
    } catch (e) {
      console.error('fetchSettings failed', e);
    }
  }, []);

  const fetchChats = useCallback(async () => {
    try {
      const resp = await fetch(`${API_BASE_URL}/api/chats`, { signal: AbortSignal.timeout(5000) });
      const data = await resp.json();
      if (data && data.sessions) {
        setChatSessions(data.sessions);
        setChatFolders(data.folders || []);
      }
    } catch (e) {
      console.error('fetchChats failed', e);
    }
  }, []);

  const createNewChat = useCallback(async () => {
    const resp = await fetch(`${API_BASE_URL}/api/chats`, { method: 'POST' });
    const data = await resp.json();
    if (data && data.id) {
      await fetchChats();
      setActiveChatId(data.id);
      setMessages([]);
    }
  }, [fetchChats]);

  const loadChat = useCallback(async (sessionId: string) => {
    setActiveChatId(sessionId);
    const resp = await fetch(`${API_BASE_URL}/api/chats/${sessionId}`);
    const data = await resp.json();
    if (Array.isArray(data)) {
      const formatted = data.map(c => ({
        sender: c.speaker || 'Unknown',
        text: c.text,
        timestamp: c.timestamp ? new Date(c.timestamp).getTime() : Date.now()
      }));
      setMessages(formatted);
    } else {
      setMessages([]);
    }
  }, []);

  const fetchMemory = useCallback(async () => {
    try {
      const resp = await fetch(`${API_BASE_URL}/api/memories`);
      const data = await resp.json();
      if (data?.memories && Array.isArray(data.memories)) {
        setMemory(data.memories);
      }
    } catch (e) {
      console.error('fetchMemory failed', e);
    }
  }, []);

  const fetchNotes = useCallback(async () => {
    try {
      const resp = await fetch(`${API_BASE_URL}/notes`, { signal: AbortSignal.timeout(5000) });
      const data = await resp.json();
      if (Array.isArray(data)) {
        const sorted = [...data].sort((a, b) => a.id - b.id);
        setNotes(sorted);
      }
    } catch (e) {
      console.error('fetchNotes failed', e);
    }
  }, []);

  const fetchTasks = useCallback(async () => {
    try {
      const resp = await fetch(`${API_BASE_URL}/tasks`, { signal: AbortSignal.timeout(5000) });
      const data = await resp.json();
      if (Array.isArray(data)) setTasks(data);
    } catch (e) {
      console.error('fetchTasks failed', e);
    }
  }, []);

  const fetchLogs = useCallback(async () => {
    try {
      const resp = await fetch(`${API_BASE_URL}/logs?limit=50`, { signal: AbortSignal.timeout(5000) });
      const data = await resp.json();
      if (Array.isArray(data)) setActivity(data);
    } catch (e) {
      console.error('fetchLogs failed', e);
    }
  }, []);

  const updateSettings = useCallback(async (newSettings: any) => {
    await fetch(`${API_BASE_URL}/settings`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(newSettings)
    });
    setSettings(newSettings);
  }, []);

  const exportNotes = useCallback(async () => {
    const resp = await fetch(`${API_BASE_URL}/notes/export`, { method: 'POST' });
    const data = await resp.json();
    if (data.success) {
      addToast('success', 'exported to Documents/Primnox');
    } else {
      addToast('error', 'Export failed');
    }
  }, [addToast]);

  const dismissProactiveAlert = useCallback(() => {
    setProactiveAlert(null);
    if (proactiveTimerRef.current) clearTimeout(proactiveTimerRef.current);
  }, []);

  const triggerMediaControl = useCallback(async (action: 'play_pause' | 'next' | 'prev' | 'stop') => {
    try {
      await fetch(`${API_BASE_URL}/api/media/control`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action }),
      });
    } catch (e) {
      console.error('media control failed', e);
    }
  }, []);

  const scanEnvironment = useCallback(async () => {
    try {
      const resp = await fetch(`${API_BASE_URL}/api/onboarding/scan`);
      return await resp.json();
    } catch (e) {
      console.error(e);
      return null;
    }
  }, []);
  
  useEffect(() => {
    fetchSettings();
    fetchChats();
    fetchMemory();
    fetchNotes();
    fetchTasks();
    fetchLogs();
    // Note: previously polled fetchLogs() every 5s here regardless of which
    // screen was visible. The Logs view now polls itself only while mounted
    // (see LogView.tsx) — this initial fetch just seeds `activity` so it's
    // non-empty if the user opens Logs immediately.
  }, [fetchSettings, fetchChats, fetchMemory, fetchNotes, fetchTasks, fetchLogs]);
  
  const manualReconnect = useCallback(() => {
    reconnectAttempts.current = 0;
    setConnectionLost(false);
    connectRef.current?.();   // reconnect in place — no page reload needed
  }, []);

  return {
    messages, state, micMuted, notes, tasks, memory,
    activity, meetings, debriefs, transcripts, currentTranscript, lastAttachedFile, incognito, settings,
    toasts, connectionLost, reconnectAttempt, maxAttempts, startupComplete,
    islandError, triggerIslandError, clearIslandError,
    privacyScrub,
    flowState, errorStreak, nowPlaying, productivityScore, parallelTasks, proactiveAlert, dismissProactiveAlert,
    islandSkills,
    triggerSmartPaste, triggerMediaControl,
    sendMessage, respondToPermission, toggleMic, toggleIncognito, manualReconnect, addToast, updateSettings, exportNotes, fetchNotes, fetchLogs,
    chatSessions,
    chatFolders,
    activeChatId,
    fetchChats,
    fetchMemory,
    fetchTasks,
    loadChat,
    createNewChat,
    scanEnvironment,
  };
}
