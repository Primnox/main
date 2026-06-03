import { create } from 'zustand';

interface PrimnoxStore {
  messages: any[];
  sendMessage: (text: string, file?: File | null) => void;
  chatSessions: any[];
  chatFolders: any[];
  activeChatId: string;
  activeSessionId: string;
  loadChat: (id: string) => void;
  setCurrentSession: (id: string) => void;
}

export const useStore = create<PrimnoxStore>(() => ({
  messages: [],
  sendMessage: () => {},
  chatSessions: [],
  chatFolders: [],
  activeChatId: 'current',
  activeSessionId: 'current',
  loadChat: () => {},
  setCurrentSession: () => {},
}));
