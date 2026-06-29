import React, { useState, useRef, useCallback } from 'react';
import { UploadCloud, X, FileText, Image as ImageIcon, Sparkles, Loader2, FileArchive } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

export const NoteGeneratorPanel = ({ onDone, activeWorkspace = 'General' }: { onDone: () => void, activeWorkspace?: string }) => {
  const [files, setFiles] = useState<File[]>([]);
  const [prompt, setPrompt] = useState("");
  const [project, setProject] = useState(activeWorkspace);
  const [mode, setMode] = useState<"separate" | "combined">("separate");
  const [status, setStatus] = useState<"idle" | "generating" | "error" | "success">("idle");
  const [errorMsg, setErrorMsg] = useState("");
  const [failedFile, setFailedFile] = useState<string | null>(null);
  
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      setFiles(prev => [...prev, ...Array.from(e.dataTransfer.files)]);
    }
  }, []);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      setFiles(prev => [...prev, ...Array.from(e.target.files!)]);
    }
  };

  const removeFile = (idx: number) => {
    setFiles(prev => prev.filter((_, i) => i !== idx));
    if (failedFile === files[idx].name) setFailedFile(null);
  };

  const handleSubmit = async () => {
    if (files.length === 0) return;
    setStatus("generating");
    setErrorMsg("");
    setFailedFile(null);

    const formData = new FormData();
    files.forEach(f => formData.append("files", f));
    if (prompt.trim()) formData.append("prompt", prompt.trim());
    formData.append("project", project);
    formData.append("mode", mode);

    try {
      const res = await fetch("http://localhost:4009/api/notes/generate-batch", {
        method: "POST",
        body: formData,
      });
      const data = await res.json();
      
      if (data.success) {
        setStatus("success");
        setTimeout(() => {
          onDone();
        }, 1500);
      } else {
        setStatus("error");
        setErrorMsg(data.error || "An unknown error occurred.");
        setFailedFile(data.failed_file || null);
      }
    } catch (err: any) {
      setStatus("error");
      setErrorMsg("Network error connecting to backend.");
    }
  };

  const getFileIcon = (name: string) => {
    const ext = name.split('.').pop()?.toLowerCase();
    if (['png', 'jpg', 'jpeg', 'webp'].includes(ext || '')) return <ImageIcon size={14} className="text-emerald-400/70" />;
    if (ext === 'pdf') return <FileArchive size={14} className="text-red-400/70" />;
    return <FileText size={14} className="text-blue-400/70" />;
  };

  return (
    <div className="bg-black/40 border-y border-white/10 p-4 shrink-0 flex flex-col gap-3 relative overflow-hidden">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-semibold text-white/80 flex items-center gap-2">
          <Sparkles size={14} className="text-emerald-400" /> AI Batch Generator
        </h3>
        <button onClick={onDone} className="text-white/40 hover:text-white transition-colors"><X size={14} /></button>
      </div>

      {/* Dropzone */}
      <div 
        onDragOver={handleDragOver}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        className="border border-dashed border-white/20 hover:border-emerald-500/50 hover:bg-emerald-500/5 rounded-lg p-6 flex flex-col items-center justify-center text-center cursor-pointer transition-colors"
      >
        <input 
          type="file" 
          multiple 
          className="hidden" 
          ref={fileInputRef} 
          onChange={handleFileChange} 
          accept=".pdf,.pptx,.ppt,.txt,.md,.csv,.json,.png,.jpg,.jpeg,.webp"
        />
        <UploadCloud size={24} className="text-white/40 mb-2" />
        <p className="text-xs text-white/60">Drag files here or click to browse</p>
        <p className="text-[9px] text-white/30 mt-1 uppercase tracking-wider">PDF, PPTX, TXT, IMG</p>
      </div>

      {/* File Queue */}
      {files.length > 0 && (
        <div className="space-y-1.5 max-h-32 overflow-y-auto custom-scrollbar">
          <AnimatePresence>
            {files.map((file, idx) => (
              <motion.div 
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                exit={{ opacity: 0, height: 0 }}
                key={idx + file.name}
                className={`flex items-center justify-between p-2 bg-white/5 rounded text-xs border ${failedFile === file.name ? 'border-red-500/50 bg-red-500/10' : 'border-white/5'}`}
              >
                <div className="flex items-center gap-2 overflow-hidden">
                  {getFileIcon(file.name)}
                  <span className="truncate text-white/80">{file.name}</span>
                </div>
                <button onClick={(e) => { e.stopPropagation(); removeFile(idx); }} className="text-white/40 hover:text-white p-1">
                  <X size={12} />
                </button>
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      )}

      {/* Error Message */}
      {status === 'error' && (
        <div className="text-[10px] text-red-400 bg-red-400/10 p-2 rounded border border-red-400/20">
          {errorMsg}
        </div>
      )}
      
      {/* Success Message */}
      {status === 'success' && (
        <div className="text-[10px] text-emerald-400 bg-emerald-400/10 p-2 rounded border border-emerald-400/20 text-center">
          Notes generated successfully!
        </div>
      )}

      {/* Options */}
      {files.length > 0 && (
        <div className="space-y-3">
          {files.length > 1 && (
            <div className="flex bg-black/40 p-1 rounded w-full text-xs">
              <button
                onClick={() => setMode('separate')}
                className={`flex-1 py-1 rounded transition-colors ${mode === 'separate' ? 'bg-white/10 text-white' : 'text-white/40 hover:text-white/80'}`}
              >
                Separate Notes
              </button>
              <button
                onClick={() => setMode('combined')}
                className={`flex-1 py-1 rounded transition-colors ${mode === 'combined' ? 'bg-white/10 text-white' : 'text-white/40 hover:text-white/80'}`}
              >
                Combined Note
              </button>
            </div>
          )}

          <div className="flex gap-2 text-xs">
            <span className="text-white/40 pt-1 shrink-0">Folder</span>
            <select 
              value={project} 
              onChange={e => setProject(e.target.value)}
              className="flex-1 bg-black/50 border border-white/10 rounded px-2 py-1 text-white/80 outline-none focus-visible:ring-1 focus-visible:ring-emerald-500/50"
            >
              <option value="General">General</option>
              <option value="Work">Work</option>
              <option value="Personal">Personal</option>
            </select>
          </div>

          <textarea 
            placeholder="Custom instructions (optional)..." 
            value={prompt}
            onChange={e => setPrompt(e.target.value)}
            className="w-full bg-black/50 border border-white/10 rounded p-2 text-xs text-white/90 placeholder-white/30 outline-none resize-none h-16 focus-visible:ring-1 focus-visible:ring-emerald-500/50"
          />

          <button 
            onClick={handleSubmit}
            disabled={status === 'generating'}
            className="w-full bg-emerald-500 hover:bg-emerald-400 text-black font-bold py-2 rounded text-xs flex items-center justify-center gap-2 transition-colors disabled:opacity-50"
          >
            {status === 'generating' ? (
              <><Loader2 size={14} className="animate-spin" /> Generating Notes...</>
            ) : (
              <><Sparkles size={14} /> Generate</>
            )}
          </button>
        </div>
      )}
    </div>
  );
};
