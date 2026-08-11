import React, { useState, useRef, useCallback, useEffect } from 'react';
import { UploadCloud, X, FileText, Image as ImageIcon, Sparkles, Loader2, FileArchive, PenLine } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { API_BASE } from '../../config';

interface ActiveNoteRef {
  id: number;
  title: string;
  text: string;
}

export const NoteGeneratorPanel = ({
  onDone, activeWorkspace = 'General', activeNote, onGenerated, workspaces,
}: {
  onDone: () => void;
  activeWorkspace?: string;
  /** The note currently open in the editor, if any — lets "Write for me"
   * target it directly (add to / edit it) instead of only creating new pages. */
  activeNote?: ActiveNoteRef | null;
  /** Called with the created/updated note so the caller can patch the open
   * editor in place when it was the active note that got edited. */
  onGenerated?: (note: { id: number; title: string; text: string; project?: string }) => void;
  /** Real workspaces that actually have notes in them — the Folder picker
   * used to hardcode ["General","Work","Personal"], which meant a note
   * created here could never land in any workspace the user had actually
   * made themselves. */
  workspaces?: string[];
}) => {
  const folderOptions = workspaces && workspaces.length > 0 ? workspaces : ['General'];
  // "prompt" = Notion-AI-style "write this for me", no file needed.
  // "files" = the original batch generator (summarize uploaded docs/images).
  const [sourceMode, setSourceMode] = useState<"prompt" | "files">("prompt");
  // No mode picker — smart default instead: if a note is open and has
  // content, "Write for me" edits it; otherwise it creates a new one. A
  // small inline link overrides the default the one time it's wrong,
  // instead of making everyone choose up front every time.
  const hasEditableActiveNote = !!(activeNote && (activeNote.text?.trim() || activeNote.title?.trim()));
  const [forceNewNote, setForceNewNote] = useState(false);
  const editingCurrent = hasEditableActiveNote && !forceNewNote;
  const [files, setFiles] = useState<File[]>([]);
  const [prompt, setPrompt] = useState("");
  const [project, setProject] = useState(activeWorkspace);
  const [mode, setMode] = useState<"separate" | "combined">("separate");
  const [status, setStatus] = useState<"idle" | "generating" | "error" | "success">("idle");
  const [errorMsg, setErrorMsg] = useState("");
  const [failedFile, setFailedFile] = useState<string | null>(null);

  // A stale override shouldn't follow you to a different note (or to no
  // note at all) — each context starts back at the smart default.
  useEffect(() => { setForceNewNote(false); }, [activeNote?.id]);

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

  const handleGenerateFromPrompt = async () => {
    if (!prompt.trim()) return;
    setStatus("generating");
    setErrorMsg("");

    try {
      const res = await fetch(`${API_BASE}/api/notes/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt: prompt.trim(),
          project,
          note_id: editingCurrent && activeNote ? activeNote.id : undefined,
        }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || "The AI couldn't draft that note — try rephrasing.");
      }
      const note = await res.json();
      setStatus("success");
      onGenerated?.(note);
      setTimeout(() => onDone(), 800);
    } catch (err: any) {
      setStatus("error");
      setErrorMsg(err.message || "Network error connecting to backend.");
    }
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
      const res = await fetch(`${API_BASE}/api/notes/generate-batch`, {
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
    if (['png', 'jpg', 'jpeg', 'webp'].includes(ext || '')) return <ImageIcon size={14} className="text-success/70" />;
    if (ext === 'pdf') return <FileArchive size={14} className="text-error/70" />;
    return <FileText size={14} className="text-primary/70" />;
  };

  return (
    <div className="bg-surface/40 border-y border-on-surface/10 p-4 shrink-0 flex flex-col gap-3 relative overflow-hidden">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-semibold text-on-surface/80 flex items-center gap-2">
          <Sparkles size={14} className="text-success" /> AI Note Builder
        </h3>
        <button onClick={onDone} className="text-on-surface/60 hover:text-on-surface transition-colors"><X size={14} /></button>
      </div>

      {/* Source mode toggle — prompt (Notion-AI-style) vs files (batch summarizer) */}
      <div className="flex bg-surface/40 p-1 rounded w-full text-xs">
        <button
          onClick={() => { setSourceMode('prompt'); setStatus('idle'); setErrorMsg(''); }}
          className={`flex-1 py-1.5 rounded transition-colors flex items-center justify-center gap-1.5 ${sourceMode === 'prompt' ? 'bg-on-surface/10 text-on-surface' : 'text-on-surface/60 hover:text-on-surface/80'}`}
        >
          <PenLine size={12} /> Write for me
        </button>
        <button
          onClick={() => { setSourceMode('files'); setStatus('idle'); setErrorMsg(''); }}
          className={`flex-1 py-1.5 rounded transition-colors flex items-center justify-center gap-1.5 ${sourceMode === 'files' ? 'bg-on-surface/10 text-on-surface' : 'text-on-surface/60 hover:text-on-surface/80'}`}
        >
          <UploadCloud size={12} /> From files
        </button>
      </div>

      {status === 'error' && (
        <div className="text-[10px] text-error bg-error/10 p-2 rounded border border-error/20">
          {errorMsg}
        </div>
      )}
      {status === 'success' && (
        <div className="text-[10px] text-success bg-success/10 p-2 rounded border border-success/20 text-center">
          Note generated successfully!
        </div>
      )}

      {sourceMode === 'prompt' ? (
        <div className="space-y-3">
          <textarea
            autoFocus
            placeholder={editingCurrent ? 'What should change? e.g. "add a section on budget" or "make the intro shorter"' : 'What should this note say? e.g. "meeting notes for tomorrow\'s product sync"'}
            value={prompt}
            onChange={e => setPrompt(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey) && prompt.trim()) handleGenerateFromPrompt(); }}
            className="w-full bg-surface/50 border border-on-surface/10 rounded p-2 text-xs text-on-surface/90 placeholder-on-surface/30 outline-none resize-none h-24 focus-visible:ring-1 focus-visible:ring-success/50"
          />
          {hasEditableActiveNote && (
            <p className="text-[10px] text-on-surface/55">
              {editingCurrent ? (
                <>Editing "{activeNote?.title || 'this note'}" · <button onClick={() => setForceNewNote(true)} className="text-success/80 hover:text-success underline underline-offset-2">create a new note instead</button></>
              ) : (
                <>Creating a new note · <button onClick={() => setForceNewNote(false)} className="text-success/80 hover:text-success underline underline-offset-2">edit "{activeNote?.title || 'this note'}" instead</button></>
              )}
            </p>
          )}
          {!editingCurrent && (
            <div className="flex gap-2 text-xs">
              <span className="text-on-surface/60 pt-1 shrink-0">Folder</span>
              <select
                value={project}
                onChange={e => setProject(e.target.value)}
                className="flex-1 bg-surface/50 border border-on-surface/10 rounded px-2 py-1 text-on-surface/80 outline-none focus-visible:ring-1 focus-visible:ring-success/50"
              >
                {folderOptions.map(ws => <option key={ws} value={ws}>{ws}</option>)}
              </select>
            </div>
          )}
          <button
            onClick={handleGenerateFromPrompt}
            disabled={status === 'generating' || !prompt.trim()}
            className="w-full bg-success/20 hover:bg-success/25 text-surface font-bold py-2 rounded text-xs flex items-center justify-center gap-2 transition-colors disabled:opacity-50"
          >
            {status === 'generating' ? (
              <><Loader2 size={14} className="animate-spin" /> {editingCurrent ? 'Updating...' : 'Writing...'}</>
            ) : (
              <><Sparkles size={14} /> {editingCurrent ? 'Update Note' : 'Generate Note'}</>
            )}
          </button>
        </div>
      ) : (
        <>
          {/* Dropzone */}
          <div
            onDragOver={handleDragOver}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            className="border border-dashed border-on-surface/20 hover:border-success/50 hover:bg-success/5 rounded-lg p-6 flex flex-col items-center justify-center text-center cursor-pointer transition-colors"
          >
            <input
              type="file"
              multiple
              className="hidden"
              ref={fileInputRef}
              onChange={handleFileChange}
              accept=".pdf,.pptx,.ppt,.txt,.md,.csv,.json,.png,.jpg,.jpeg,.webp"
            />
            <UploadCloud size={24} className="text-on-surface/60 mb-2" />
            <p className="text-xs text-on-surface/60">Drag files here or click to browse</p>
            <p className="text-[9px] text-on-surface/55 mt-1 uppercase tracking-wider">PDF, PPTX, TXT, IMG</p>
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
                    className={`flex items-center justify-between p-2 bg-on-surface/5 rounded text-xs border ${failedFile === file.name ? 'border-error/50 bg-error/10' : 'border-on-surface/5'}`}
                  >
                    <div className="flex items-center gap-2 overflow-hidden">
                      {getFileIcon(file.name)}
                      <span className="truncate text-on-surface/80">{file.name}</span>
                    </div>
                    <button onClick={(e) => { e.stopPropagation(); removeFile(idx); }} className="text-on-surface/60 hover:text-on-surface p-1">
                      <X size={12} />
                    </button>
                  </motion.div>
                ))}
              </AnimatePresence>
            </div>
          )}

          {/* Options */}
          {files.length > 0 && (
            <div className="space-y-3">
              {files.length > 1 && (
                <div className="flex bg-surface/40 p-1 rounded w-full text-xs">
                  <button
                    onClick={() => setMode('separate')}
                    className={`flex-1 py-1 rounded transition-colors ${mode === 'separate' ? 'bg-on-surface/10 text-on-surface' : 'text-on-surface/60 hover:text-on-surface/80'}`}
                  >
                    Separate Notes
                  </button>
                  <button
                    onClick={() => setMode('combined')}
                    className={`flex-1 py-1 rounded transition-colors ${mode === 'combined' ? 'bg-on-surface/10 text-on-surface' : 'text-on-surface/60 hover:text-on-surface/80'}`}
                  >
                    Combined Note
                  </button>
                </div>
              )}

              <div className="flex gap-2 text-xs">
                <span className="text-on-surface/60 pt-1 shrink-0">Folder</span>
                <select
                  value={project}
                  onChange={e => setProject(e.target.value)}
                  className="flex-1 bg-surface/50 border border-on-surface/10 rounded px-2 py-1 text-on-surface/80 outline-none focus-visible:ring-1 focus-visible:ring-success/50"
                >
                  {folderOptions.map(ws => <option key={ws} value={ws}>{ws}</option>)}
                </select>
              </div>

              <textarea
                placeholder="Custom instructions (optional)..."
                value={prompt}
                onChange={e => setPrompt(e.target.value)}
                className="w-full bg-surface/50 border border-on-surface/10 rounded p-2 text-xs text-on-surface/90 placeholder-on-surface/30 outline-none resize-none h-16 focus-visible:ring-1 focus-visible:ring-success/50"
              />

              <button
                onClick={handleSubmit}
                disabled={status === 'generating'}
                className="w-full bg-success/20 hover:bg-success/25 text-surface font-bold py-2 rounded text-xs flex items-center justify-center gap-2 transition-colors disabled:opacity-50"
              >
                {status === 'generating' ? (
                  <><Loader2 size={14} className="animate-spin" /> Generating Notes...</>
                ) : (
                  <><Sparkles size={14} /> Generate</>
                )}
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
};
