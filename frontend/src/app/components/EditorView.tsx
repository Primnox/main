import { useState } from 'react';
import { Play, Pause, SkipBack, Download, Sparkles, SlidersHorizontal } from 'lucide-react';
import { TimelineTrack } from './TimelineTrack';
import { TimelineClip } from './TimelineClip';

export const EditorView = () => {
  const [isPlaying, setIsPlaying] = useState(false);
  const [clips, setClips] = useState([
    { id: 'c1', name: 'drone_flyover.mp4', type: 'video', duration: 5, startPos: 0, trackIndex: 0, effects: ['zoom_punch'] },
    { id: 'c2', name: 'interview_main.mp4', type: 'video', duration: 8, startPos: 250, trackIndex: 0, effects: ['cross_dissolve'] },
    { id: 'a1', name: 'bg_music.wav', type: 'audio', duration: 15, startPos: 0, trackIndex: 1, effects: [] },
    { id: 'a2', name: 'swoosh_sfx.wav', type: 'audio', duration: 2, startPos: 240, trackIndex: 2, effects: ['smash_cut'] },
  ]);

  const handleDragEnd = (id: string, newPos: number) => {
    setClips(prev => prev.map(c => c.id === id ? { ...c, startPos: Math.max(0, newPos) } : c));
  };

  const handleRender = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/video/export/openshot', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          edl: { project_id: 'test', timeline: clips, duration: 60.0 },
          output_path: 'C:/temp/export.osp',
        }),
      });
      const data = await res.json();
      alert(`Export successful: ${JSON.stringify(data)}`);
    } catch (err) {
      alert(`Export failed: ${err instanceof Error ? err.message : String(err)}`);
    }
  };

  return (
    <div className="flex flex-col w-full h-full bg-[#0a0a0a]">
      {/* Top Half: Video Preview & Inspector */}
      <div className="flex-1 flex gap-4 p-4 border-b border-white/5">
        
        {/* Video Preview Canvas */}
        <div className="flex-1 bg-black/50 rounded-xl border border-white/5 shadow-2xl flex flex-col overflow-hidden relative">
          <div className="flex-1 flex items-center justify-center relative bg-zinc-950">
            {/* Mock Video Frame */}
            <div className="w-[80%] h-[80%] border border-white/10 rounded shadow-2xl bg-gradient-to-br from-indigo-900/20 to-black flex items-center justify-center overflow-hidden relative">
              <span className="font-mono text-white/20 tracking-widest uppercase">Video Preview Offline</span>
              
              {/* AI Badge Overlay Preview */}
              <div className="absolute top-4 right-4 flex items-center gap-2 bg-black/60 backdrop-blur border border-white/10 px-3 py-1.5 rounded-full">
                <Sparkles size={12} className="text-primary" />
                <span className="text-[10px] font-mono uppercase tracking-widest text-white/70">AI Auto-Reframe Active</span>
              </div>
            </div>
          </div>
          
          {/* Transport Controls */}
          <div className="h-14 bg-zinc-950/80 backdrop-blur border-t border-white/5 flex items-center justify-center gap-6">
            <button className="text-white/40 hover:text-white transition-colors"><SkipBack size={18} /></button>
            <button 
              className="w-10 h-10 rounded-full bg-white text-black flex items-center justify-center hover:scale-105 transition-transform"
              onClick={() => setIsPlaying(!isPlaying)}
            >
              {isPlaying ? <Pause size={18} /> : <Play size={18} className="ml-1" />}
            </button>
            <div className="w-48 h-1 bg-white/10 rounded-full overflow-hidden mx-4">
              <div className="h-full bg-primary w-1/3" />
            </div>
            <span className="font-mono text-[10px] text-white/50">00:00:04:12</span>
          </div>
        </div>

        {/* AI Inspector Panel */}
        <div className="w-80 bg-zinc-950/50 rounded-xl border border-white/5 flex flex-col p-4">
          <div className="flex items-center gap-2 pb-4 border-b border-white/5 mb-4">
            <SlidersHorizontal size={14} className="text-white/50" />
            <h3 className="font-mono text-[11px] uppercase tracking-widest font-bold text-white/80">AI Inspector</h3>
          </div>
          
          <div className="space-y-4">
            <div className="p-3 rounded-lg bg-indigo-500/10 border border-indigo-500/20 flex flex-col gap-2">
              <span className="font-mono text-[10px] uppercase text-indigo-400 font-bold">Detected Scene</span>
              <span className="text-sm text-white/80">High-Energy Motion</span>
              <p className="text-xs text-white/40">AI recommends inserting a Speed Ramp here to match the tempo.</p>
            </div>
            
            <button className="w-full py-2 bg-white/5 hover:bg-white/10 rounded border border-white/10 text-xs font-mono uppercase tracking-widest transition-colors">
              Apply AI Recommendation
            </button>
          </div>

          <div className="mt-auto">
            <button onClick={handleRender} className="w-full py-3 bg-primary hover:bg-primary/90 text-white rounded font-mono text-[11px] uppercase tracking-widest shadow-[0_0_15px_rgba(79,70,229,0.3)] transition-all">
              Render to OpenShot
            </button>
          </div>
        </div>

      </div>

      {/* Bottom Half: The Timeline */}
      <div className="h-80 bg-zinc-950 flex flex-col overflow-y-auto">
        {/* Timeline Ruler */}
        <div className="h-6 w-full border-b border-white/10 bg-black/40 flex items-end px-48">
          <div className="flex-1 h-full flex justify-between px-2 opacity-30 text-[9px] font-mono">
            <span>00:00:00</span>
            <span>00:00:05</span>
            <span>00:00:10</span>
            <span>00:00:15</span>
          </div>
        </div>

        {/* Tracks */}
        <TimelineTrack id="t0" name="Main Camera" type="video">
          {clips.filter(c => c.trackIndex === 0).map(c => (
             <TimelineClip key={c.id} {...c} type={c.type as 'video'} onDragEnd={handleDragEnd} />
          ))}
        </TimelineTrack>
        
        <TimelineTrack id="t1" name="B-Roll / Effects" type="video">
          {/* Empty Track */}
        </TimelineTrack>

        <TimelineTrack id="t2" name="Dialogue" type="audio">
           {clips.filter(c => c.trackIndex === 1).map(c => (
             <TimelineClip key={c.id} {...c} type={c.type as 'audio'} onDragEnd={handleDragEnd} />
          ))}
        </TimelineTrack>

        <TimelineTrack id="t3" name="SFX / Music" type="audio">
           {clips.filter(c => c.trackIndex === 2).map(c => (
             <TimelineClip key={c.id} {...c} type={c.type as 'audio'} onDragEnd={handleDragEnd} />
          ))}
        </TimelineTrack>

      </div>
    </div>
  );
};
