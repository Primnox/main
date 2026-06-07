import { useState, useEffect, useCallback, useRef } from 'react';

const API_BASE_URL = 'http://localhost:8000';

export interface Toast {
  id: string;
  type: 'success' | 'error' | 'info' | 'warning';
  message: string;
}

export function usePrimnox() {
  const [messages, setMessages] = useState<any[]>([]);
  const [state, setState] = useState('idle');
  const [micMuted, setMicMuted] = useState(false);
  const [vadLevel, setVadLevel] = useState(0);
  const [notes, setNotes] = useState<any[]>([]);
  const [tasks] = useState<any[]>([]);
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
  const [nowPlaying, setNowPlaying] = useState<{ title: string; artist: string; source: string } | null>(null);
  const [productivityScore, setProductivityScore] = useState<number>(100);
  const [parallelTasks, setParallelTasks] = useState<{ id: string; label: string; color: string }[]>([]);

  const [connectionLost, setConnectionLost] = useState(false);
  const [reconnectAttempt, setReconnectAttempt] = useState(0);
  const [startupComplete, setStartupComplete] = useState(false);
  
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttempts = useRef(0);
  const maxAttempts = 5;
  const tokenBufferRef = useRef<string>("");
  const animationFrameIdRef = useRef<number | null>(null);
  const parallelTaskTimers = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

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
  const triggerSmartPaste = useCallback(async () => {
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

  useEffect(() => {
    let reconnectTimer: NodeJS.Timeout;
    
    const connect = () => {
      const socket = new WebSocket(`${API_BASE_URL.replace('http', 'ws')}/ws`);
      
      socket.onopen = () => {
        reconnectAttempts.current = 0;
        setReconnectAttempt(0);
        setConnectionLost(false);
      };

      socket.onmessage = (event) => {
        const data = JSON.parse(event.data);
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
        else if (type === 'vad_level') setVadLevel(payload.rms);
        else if (type === 'transcript_added') setTranscripts(prev => [payload, ...prev]);
        else if (type === 'transcript') setCurrentTranscript(payload.text);
        else if (type === 'note_added') {
          fetch(`${API_BASE_URL}/notes`)
            .then(res => res.json())
            .then(data => {
              if (Array.isArray(data)) {
                const sorted = [...data].sort((a, b) => a.id - b.id);
                setNotes(sorted);
              }
            });
        }
        else if (type === 'task_added') { /* components handle fetching */ }
        else if (type === 'memory_updated') { /* components handle fetching */ }
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
          addToast('success', `Done: ${payload?.result || ''}`);
          setParallelTasks(prev => {
            if (prev.length === 0) return prev;
            const [completed, ...rest] = prev;
            const timer = parallelTaskTimers.current.get(completed.id);
            if (timer) {
              clearTimeout(timer);
              parallelTaskTimers.current.delete(completed.id);
            }
            return rest;
          });
        }
        else if (type === 'skill_unavailable') addToast('error', 'Skill unavailable');
        else if (type === 'fallback_triggered') addToast('warning', 'Fallback triggered');
        else if (type === 'rate_limit_hit') addToast('warning', 'Rate limit hit');
        else if (type === 'startup_complete') setStartupComplete(true);
        else if (type === 'proactive_message') {
          setMessages(prev => [...prev, { sender: 'Primnox', text: payload.message, timestamp: Date.now() }]);
          // Forward proactive message to Electron for Dynamic Island Window
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
        else if (type === 'reminder_triggered') addToast('info', `Reminder: ${payload.text}`);
        else if (type === 'backup_complete') addToast('success', 'Backup complete');
        else if (type === 'backup_failed') addToast('error', 'Backup failed');
        else if (type === 'error_island') triggerIslandError(payload?.error_message || 'unknown error', payload?.context);
        // ── Ambient island features ──────────────────────────────────────
        else if (type === 'flow_state') setFlowState(payload);
        else if (type === 'flow_broken') setFlowState(null);
        else if (type === 'error_streak') setErrorStreak(payload);
        else if (type === 'error_resolved') setErrorStreak(null);
        else if (type === 'now_playing') setNowPlaying(payload && typeof payload === 'object' && payload.title ? payload : null);
        else if (type === 'productivity_score') setProductivityScore(payload?.score ?? 100);
      };
      
      socket.onclose = () => {
        if (reconnectAttempts.current >= maxAttempts) {
          setConnectionLost(true);
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
  }, [addToast, triggerIslandError]);

  const sendMessage = useCallback(async (text: string, sessionId: string = 'current', file?: File | null) => {
    let displayText = text;
    if (file) {
      displayText = text ? `${text}\n[Attached: ${file.name}]` : `[Attached: ${file.name}]`;
    }
    await fetch(`${API_BASE_URL}/message`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: displayText, sessionId })
    });
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
    const resp = await fetch(`${API_BASE_URL}/settings`);
    const data = await resp.json();
    setSettings(data);
  }, []);

  const fetchChats = useCallback(async () => {
    const resp = await fetch(`${API_BASE_URL}/api/chats`);
    const data = await resp.json();
    if (data && data.sessions) {
      setChatSessions(data.sessions);
      setChatFolders(data.folders || []);
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
    const resp = await fetch(`${API_BASE_URL}/memory`);
    const data = await resp.json();
    if (data && typeof data === 'object') {
       setMemory(Object.values(data));
    }
  }, []);

  const fetchNotes = useCallback(async () => {
    const resp = await fetch(`${API_BASE_URL}/notes`);
    const data = await resp.json();
    if (Array.isArray(data)) {
      if (Array.isArray(data)) {
        const sorted = [...data].sort((a, b) => a.id - b.id);
        setNotes(sorted);
      }
    }
  }, []);

  const fetchLogs = useCallback(async () => {
    try {
      const resp = await fetch(`${API_BASE_URL}/logs?limit=50`);
      const data = await resp.json();
      if (Array.isArray(data)) {
        setActivity(data);
      }
    } catch (e) {
      console.error("Failed to fetch logs", e);
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
    fetchLogs();
    const timer = setInterval(() => {
      fetchLogs();
    }, 5000);
    return () => clearInterval(timer);
  }, [fetchSettings, fetchChats, fetchMemory, fetchNotes, fetchLogs]);
  
  const manualReconnect = useCallback(() => {
    reconnectAttempts.current = 0;
    setConnectionLost(false);
    window.location.reload(); 
  }, []);

  return {
    messages, state, micMuted, vadLevel, notes, tasks, memory,
    activity, meetings, debriefs, transcripts, currentTranscript, lastAttachedFile, incognito, settings,
    toasts, connectionLost, reconnectAttempt, maxAttempts, startupComplete,
    islandError, triggerIslandError, clearIslandError,
    flowState, errorStreak, nowPlaying, productivityScore, parallelTasks,
    triggerSmartPaste,
    sendMessage, toggleMic, toggleIncognito, manualReconnect, addToast, updateSettings, exportNotes,
    chatSessions,
    chatFolders,
    activeChatId,
    fetchChats,
    loadChat,
    createNewChat,
    scanEnvironment,
  };
}
