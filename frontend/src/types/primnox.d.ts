export interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp?: number;
}

export interface Note {
  id: string;
  content: string;
  created_at: number;
}

export interface Session {
  id: string;
  title: string;
  created_at: number;
}

export interface TimelineClipData {
  id: string;
  name: string;
  type: 'video' | 'audio';
  duration: number;
  startPos: number;
  trackIndex: number;
  effects: string[];
}
