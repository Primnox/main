from pathlib import Path

# Was an absolute path on the original author's Windows machine: it leaked a
# username and the script could not run anywhere else.
_FRONTEND_DIR = Path(__file__).resolve().parent
import os
import re

components_dir = str(_FRONTEND_DIR / 'src/app')

# 1. Update App.tsx
with open(os.path.join(components_dir, 'App.tsx'), 'r', encoding='utf-8') as f:
    app_content = f.read()

app_content = app_content.replace("import { usePrimnox } from '../hooks/usePrimnox';", "import { usePrimnox } from '../hooks/usePrimnox';\nimport { useStore } from '../store/useStore';")

# Replace massive destructuring in App.tsx
old_destructure = """  const { 
    messages: liveMessages, 
    state: liveState, 
    vadLevel, 
    notes, 
    memory,
    toasts,
    activity,
    currentTranscript,
    lastAttachedFile,
    settings,
    micMuted,
    connectionLost,
    manualReconnect,
    toggleMic,
    sendMessage,
    updateSettings,
    exportNotes,
    chatSessions,
    chatFolders,
    activeChatId,
    fetchChats,
    loadChat,
    addToast
  } = usePrimnox();"""

new_destructure = """  usePrimnox(); // Initialize WebSocket
  const liveState = useStore(s => s.state);
  const toasts = useStore(s => s.toasts);
  const connectionLost = useStore(s => s.connectionLost);
  const reconnectAttempt = useStore(s => s.reconnectAttempt);"""

app_content = app_content.replace(old_destructure, new_destructure)

# We need to remove the props from the components in App.tsx!
# ChatExpandedSidebar
app_content = re.sub(
    r'<ChatExpandedSidebar[^>]*>',
    r'<ChatExpandedSidebar aiName="Primnox" userName="Operator" setStatus={setStatus} />',
    app_content, flags=re.DOTALL
)

# 2. Update ChatView.tsx
with open(os.path.join(components_dir, 'components', 'ChatView.tsx'), 'r', encoding='utf-8') as f:
    chat_content = f.read()

chat_content = chat_content.replace("import { motion } from 'motion/react';", "import { motion } from 'motion/react';\nimport { useStore } from '../../store/useStore';")

old_chat_props = """export const ChatExpandedSidebar = ({ 
  aiName, 
  userName, 
  setStatus,
  liveMessages = [],
  sendMessage = () => {},
  chatSessions = [],
  chatFolders = [],
  activeChatId = 'current',
  loadChat = () => {}
}: { 
  aiName: string, 
  userName: string, 
  setStatus: (s: AiStatus) => void,
  liveMessages?: any[],
  sendMessage?: (text: string, sessionId?: string) => void,
  chatSessions?: any[],
  chatFolders?: any[],
  activeChatId?: string,
  loadChat?: (id: string) => void
}) => {"""

new_chat_props = """export const ChatExpandedSidebar = ({ 
  aiName, 
  userName, 
  setStatus
}: { 
  aiName: string, 
  userName: string, 
  setStatus: (s: AiStatus) => void
}) => {
  const liveMessages = useStore(s => s.messages);
  const sendMessage = useStore(s => s.sendMessage);
  const chatSessions = useStore(s => s.chatSessions);
  const chatFolders = useStore(s => s.chatFolders);
  const activeChatId = useStore(s => s.activeChatId);
  const loadChat = useStore(s => s.loadChat);
"""

chat_content = chat_content.replace(old_chat_props, new_chat_props)

with open(os.path.join(components_dir, 'components', 'ChatView.tsx'), 'w', encoding='utf-8') as f:
    f.write(chat_content)

with open(os.path.join(components_dir, 'App.tsx'), 'w', encoding='utf-8') as f:
    f.write(app_content)
print("Patched ChatView and App.tsx")
