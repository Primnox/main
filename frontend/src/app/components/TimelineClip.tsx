import { useMemo } from 'react';
import { motion, useDragControls } from 'framer-motion';
import { Scissors, Zap, Waves, FastForward, Maximize } from 'lucide-react';

interface TimelineClipProps {
  id: string;
  name: string;
  duration: number; // in seconds
  startPos: number; // X position in pixels
  trackIndex: number;
  effects?: string[]; // 'zoom_punch', 'cross_dissolve', etc.
  type: 'video' | 'audio';
  onDragEnd: (id: string, newPos: number) => void;
  pixelsPerSecond?: number;
}

export const TimelineClip = ({ 
  id, name, duration, startPos, trackIndex, effects = [], type, onDragEnd, pixelsPerSecond = 50 
}: TimelineClipProps) => {
  const width = duration * pixelsPerSecond;

  const waveformHeights = useMemo(() => {
    return Array.from({ length: 20 }).map(() => Math.random() * 80 + 20);
  }, [id]);

  const effectIcons: Record<string, any> = {
    'zoom_punch': <Maximize size={10} className="text-pink-500" />,
    'cross_dissolve': <Waves size={10} className="text-cyan-500" />,
    'speed_ramp': <FastForward size={10} className="text-yellow-500" />,
    'j_cut': <Scissors size={10} className="text-emerald-500" />,
    'smash_cut': <Zap size={10} className="text-orange-500" />
  };

  return (
    <motion.div
      drag="x"
      dragMomentum={false}
      dragElastic={0}
      onDragEnd={(e, info) => {
        // Calculate new snapped position
        onDragEnd(id, startPos + info.offset.x);
      }}
      initial={{ x: startPos }}
      animate={{ x: startPos }}
      className={`absolute h-16 rounded-md border flex flex-col justify-between overflow-hidden cursor-grab active:cursor-grabbing backdrop-blur-md shadow-lg transition-colors
        ${type === 'video' 
          ? 'bg-indigo-900/40 border-indigo-500/50 hover:bg-indigo-800/60' 
          : 'bg-emerald-900/30 border-emerald-500/40 hover:bg-emerald-800/50'}`}
      style={{ width }}
    >
      {/* Clip Header */}
      <div className="flex items-center justify-between px-2 py-1 bg-black/40 border-b border-white/10">
        <span className="text-[9px] font-mono text-white/70 truncate uppercase">{name}</span>
        
        {/* AI Effect Badges */}
        {effects.length > 0 && (
          <div className="flex gap-1 bg-black/60 rounded px-1 py-0.5">
            {effects.map((eff, i) => (
              <div key={i} title={eff}>{effectIcons[eff] || <Zap size={10} className="text-white/50" />}</div>
            ))}
          </div>
        )}
      </div>

      {/* Clip Body / Waveform Mock */}
      <div className="flex-1 flex items-center px-1 opacity-50 overflow-hidden">
        {type === 'audio' ? (
          // Mock Waveform SVG
          <svg width="100%" height="60%" preserveAspectRatio="none" viewBox="0 0 100 100">
            {waveformHeights.map((height, i) => (
              <rect key={i} x={i * 5} y={50 - height / 2} width="2" height={height} fill="currentColor" className="text-emerald-500/50" />
            ))}
          </svg>
        ) : (
          // Video Filmstrip dashes
          <div className="w-full h-full border-t border-b border-indigo-500/20 flex gap-2 items-center px-2">
             {Array.from({ length: Math.max(1, Math.floor(width / 30)) }).map((_, i) => (
               <div key={i} className="w-4 h-8 border border-white/5 rounded-sm bg-black/20" />
             ))}
          </div>
        )}
      </div>

      {/* Drag Handles (Visual Only) */}
      <div className="absolute left-0 top-0 bottom-0 w-2 hover:bg-white/20 cursor-col-resize transition-colors" />
      <div className="absolute right-0 top-0 bottom-0 w-2 hover:bg-white/20 cursor-col-resize transition-colors" />
    </motion.div>
  );
};
