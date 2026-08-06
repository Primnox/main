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
  const parallelTaskTimers = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());
  const proactiveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const triggerIslandError = useCallback(async (errorMessage: string, context?: string) => {
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
          if (animationFrameIdRef.current) {
            cancelAnimationFrame(animationFrameIdRef.current);
            animationFrameIdRef.current = null;
          }
          tokenBufferRef.current = "";

          setMessages(prev => {
            if (payload.sender?.toUpperCase() === 'PRIMNOX' && !payload.isTyping) {
              const newMsgs = [...prev];
              let lastMsgIdx = newMsgs.length - 1;
              while (lastMsgIdx >= 0 && newMsgs[lastMsgIdx].sender?.toUpperCase() !== 'PRIMNOX') {
                lastMsgIdx--;
              }
              const lastMsg = lastMsgIdx >= 0 ? newMsgs[lastMsgIdx] : null;
              if (lastMsg) {
                newMsgs[lastMsgIdx] = payload;
                return newMsgs;
              }
              return [...newMsgs, payload];
            } else {
              return [...prev, payload];
            }
          });
        }
        else if (type === 'token') {
          tokenBufferRef.current += payload.text;
          
          if (!animationFrameIdRef.current) {
            animationFrameIdRef.current = requestAnimationFrame(() => {
              const flushedText = tokenBufferRef.current;
              tokenBufferRef.current = "";
              animationFrameIdRef.current = null;
              
              setMessages(prev => {
                const newMsgs = [...prev];
                let lastMsgIdx = newMsgs.length - 1;
                while (lastMsgIdx >= 0 && newMsgs[lastMsgIdx].sender?.toUpperCase() !== 'PRIMNOX') {
                  lastMsgIdx--;
                }
                const lastMsg = lastMsgIdx >= 0 ? newMsgs[lastMsgIdx] : null;
                
                if (lastMsg) {
                  const updatedMsg = { ...lastMsg };
                  if (updatedMsg.isTyping) {
                    updatedMsg.isTyping = false;
                    updatedMsg.text = flushedText;
                  } else {
                    updatedMsg.text += flushedText;
                  }
                  newMsgs[lastMsgIdx] = updatedMsg;
                }
                return newMsgs;
              });
            });
          }
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
          // Show a subtle toast so the user knows something was remembered
          if (payload?.text) addToast('info', `remembered: ${payload.text.slice(0, 60)}`);
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
        else if (type === 'tool_executing') {
          // LLM is calling a tool — show briefly in the island status area
          if (payload?.tool) addToast('info', `using: ${payload.tool.replace('_', ' ')}`);
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
        else if (type === 'skill_unavailable') addToast('error', 'Skill unavailable');
        else if (type === 'fallback_triggered') addToast('warning', 'Fallback triggered');
        else if (type === 'rate_limit_hit') addToast('warning', 'Rate limit hit');
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
        else if (type === 'backup_complete') addToast('success', 'Backup complete');
        else if (type === 'backup_failed') addToast('error', 'Backup failed');
        else if (type === 'emotion_updated') {
          if (payload?.mood) addToast('info', `vibe detected: ${payload.mood.toLowerCase()}`);
        }
        else if (type === 'profile_updated') {
          addToast('info', 'profile updated from recent activity');
        }
        else if (type === 'error_island') triggerIslandError(payload?.error_message || 'unknown error', payload?.context);
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
      if (animationFrameIdRef.current) {
        cancelAnimationFrame(animationFrameIdRef.current);
      }
      if (wsRef.current) {
        wsRef.current.onclose = null; // Prevent reconnect loop in StrictMode
        wsRef.current.close();
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [addToast, triggerIslandError]);

  const sendMessage = useCallback(async (text: string, sessionId: string = 'current', files?: File[] | null) => {
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
      addToast('success', 'Notes exported to Documents/Primnox');
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
    flowState, errorStreak, nowPlaying, productivityScore, parallelTasks, proactiveAlert, dismissProactiveAlert,
    islandSkills,
    triggerSmartPaste, triggerMediaControl,
    sendMessage, toggleMic, toggleIncognito, manualReconnect, addToast, updateSettings, exportNotes, fetchNotes, fetchLogs,
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
