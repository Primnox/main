import { ReactNode } from 'react';
import { Film, Music } from 'lucide-react';

interface TimelineTrackProps {
  id: string;
  name: string;
  type: 'video' | 'audio';
  children?: ReactNode;
  trackWidth?: number;
}

export const TimelineTrack = ({ id, name, type, children, trackWidth = 2000 }: TimelineTrackProps) => {
  return (
    <div className="flex h-20 w-full border-b border-white/5 bg-black/20 group">
      {/* Track Header */}
      <div className="w-48 shrink-0 border-r border-white/10 bg-zinc-950/80 flex items-center px-4 gap-3 z-10 sticky left-0 shadow-[4px_0_15px_rgba(0,0,0,0.5)]">
        <div className={`p-1.5 rounded-md ${type === 'video' ? 'bg-indigo-500/20 text-indigo-400' : 'bg-emerald-500/20 text-emerald-400'}`}>
          {type === 'video' ? <Film size={14} /> : <Music size={14} />}
        </div>
        <div className="flex flex-col">
          <span className="font-mono text-[11px] font-bold tracking-wider text-white/80">{name}</span>
          <span className="font-mono text-[9px] uppercase tracking-widest text-white/40">{type} track</span>
        </div>
      </div>

      {/* Track Canvas (Where clips live) */}
      <div className="flex-1 relative overflow-hidden bg-[url('data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNTAiIGhlaWdodD0iMjAiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+PHBhdGggZD0iTTAgMjBWMGgxdjIwaC0xeiIgZmlsbD0icmdiYSgyNTUsMjU1LDI1NSwwLjAyKSIvPjwvc3ZnPg==')]">
        {/* Horizontal scroll container for the clips */}
        <div className="absolute inset-y-0 left-0 flex items-center py-2" style={{ width: trackWidth }}>
          {children}
        </div>
      </div>
    </div>
  );
};
