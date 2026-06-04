import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { Search, Plus, FileText, ChevronRight, Trash2, Sparkles, X, Loader2, Folder, Pin } from 'lucide-react';
import "@blocknote/core/fonts/inter.css";
import "@blocknote/mantine/style.css";
import { BlockNoteView } from "@blocknote/mantine";
import { useCreateBlockNote, SuggestionMenuController, getDefaultReactSlashMenuItems } from "@blocknote/react";
import { BlockNoteSchema, defaultBlockSpecs } from "@blocknote/core";
import { NoteGeneratorPanel } from './NoteGeneratorPanel';

/*
// ─── AI Custom Block (disabled - not yet integrated into schema) ─────
const AiBlock = createReactBlockSpec(
  {
    type: "ai",
    propSchema: {
      textAlignment: { default: "left", values: ["left", "center", "right", "justify"] },
      textColor: { default: "default" },
    },
    content: "none",
  },
  {
    render: (props) => {
      const [prompt, setPrompt] = useState("");
      const [isGenerating, setIsGenerating] = useState(false);

      const handleGenerate = async () => {
        if (!prompt) return;
        setIsGenerating(true);
        try {
          const res = await fetch("http://localhost:8000/api/generate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ prompt: `Generate content strictly based on this prompt. Output ONLY markdown content for the editor, no conversational filler. Prompt: ${prompt}` }),
          });
          const data = await res.json();
          let generatedText = "";
          if (data.choices && data.choices[0] && data.choices[0].message) {
             generatedText = data.choices[0].message.content;
          } else if (data.text) {
             generatedText = data.text;
          } else {
             generatedText = "No content generated.";
          }
          
          const blocks = await props.editor.tryParseMarkdownToBlocks(generatedText);
          props.editor.replaceBlocks([props.block], blocks);
        } catch (e) {
          console.error("AI Generation failed:", e);
          setIsGenerating(false);
        }
      };

      return (
        <div className="w-full bg-emerald-500/10 border border-emerald-500/30 rounded-lg p-3 my-2 flex flex-col gap-2 shadow-[0_0_15px_rgba(16,185,129,0.1)]">
          <div className="flex items-center gap-2 text-emerald-400 font-mono text-xs uppercase tracking-widest font-bold">
            <Sparkles size={14} /> AI Generation
          </div>
          <div className="flex gap-2">
            <input 
              autoFocus
              disabled={isGenerating}
              className="flex-1 bg-black/50 border border-emerald-500/20 rounded px-3 py-1.5 text-sm focus:outline-none focus:border-emerald-500/50 text-white placeholder-white/30"
              placeholder="What do you want me to write?..."
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleGenerate();
              }}
            />
            <button 
              disabled={isGenerating}
              onClick={handleGenerate}
              className="px-3 py-1.5 bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-400 rounded text-sm transition-colors flex items-center gap-2 disabled:opacity-50"
            >
              {isGenerating ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
              {isGenerating ? "Generating..." : "Generate"}
            </button>
          </div>
        </div>
      );
    },
  }
);

const insertAiItem = (editor: any) => ({
  title: "AI Generate",
  onItemClick: () => {
    editor.insertBlocks(
      [{ type: "ai" }],
      editor.getTextCursorPosition().block,
      "after"
    );
  },
  aliases: ["ai", "generate", "magic"],
  group: "Advanced",
  icon: <Sparkles size={18} />,
  subtext: "Generate content using Primnox AI"
});
*/

const schema = BlockNoteSchema.create({
  blockSpecs: {
    ...defaultBlockSpecs,
  },
});

export interface Note {
  title: string;
  text: string;
  timestamp: string;
  id?: number;
  pinned?: boolean;
  icon?: string;
  project?: string;
  parent_id?: number;
}

// ─── Auto-Save Status Type ──────────────────────────────────────
type SaveStatus = 'idle' | 'saving' | 'saved';

export const NotesIconSidebar = ({ notes = [], onExport }: { notes: Note[], onExport?: () => void, sendMessage?: (text: string) => void }) => {
  const [activeNoteId, setActiveNoteId] = useState<number | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [editText, setEditText] = useState("");
  const [search, setSearch] = useState("");
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle');
  const [showAskAI, setShowAskAI] = useState(false);
  const [aiQuery, setAiQuery] = useState("");
  const [aiAnswer, setAiAnswer] = useState("");
  const [aiLoading, setAiLoading] = useState(false);
  const [activeWorkspace, setActiveWorkspace] = useState<string>("General");
  const [showGenerator, setShowGenerator] = useState(false);

  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const activeNote = notes.find(n => n.id === activeNoteId) ?? notes[0];

  const prevNoteIdRef = useRef<number | null | undefined>(undefined);

  // Sync editor state when switching notes
  useEffect(() => {
    if (activeNote && prevNoteIdRef.current !== activeNote?.id) {
      setEditTitle(activeNote.title || "");
      setEditText(activeNote.text || "");
      prevNoteIdRef.current = activeNote?.id;
      setShowAskAI(false);
      setAiAnswer("");
      setAiQuery("");
    }
  }, [activeNoteId, activeNote]);

  useEffect(() => {
    const handleOpenNote = (e: any) => {
      const targetId = e.detail?.id;
      if (targetId) {
        const idx = notes.findIndex(n => n.id === targetId);
        if (idx !== -1) {
          setActiveNoteId(notes[idx]?.id ?? null);
          if (notes[idx].project) {
            setActiveWorkspace(notes[idx].project);
          }
        }
      }
    };
    window.addEventListener('primnox:open-note', handleOpenNote);
    return () => window.removeEventListener('primnox:open-note', handleOpenNote);
  }, [notes]);

  const editorOptions = useMemo(() => ({ schema }), []);
  const editor = useCreateBlockNote(editorOptions);

  useEffect(() => {
    async function loadContent() {
      if (activeNote && prevNoteIdRef.current === activeNote?.id) {
        if (activeNote.text) {
          const blocks = await editor.tryParseMarkdownToBlocks(activeNote.text);
          editor.replaceBlocks(editor.document, blocks);
        } else {
          editor.replaceBlocks(editor.document, [{ type: "paragraph", content: "" }]);
        }
      }
    }
    // Only load if the text has changed significantly or we just switched (we rely on the previous effect to set text)
    loadContent();
  }, [activeNote?.id, editor]); // We trigger this when activeNote?.id changes

  const onEditorChange = async () => {
    const markdown = await editor.blocksToMarkdownLossy(editor.document);
    setEditText(markdown);
    debouncedSave(editTitle, markdown, activeNote?.id ?? 0, activeWorkspace);
  };

  // ─── Auto-Save with Debounce ────────────────────────────────
  const persistNote = useCallback(async (title: string, text: string, id: number, project: string) => {
    setSaveStatus('saving');
    try {
      const res = await fetch('http://localhost:8000/notes/update', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ index: id, id: id, title, text, project })
      });
      const data = await res.json();
      if (data.id && data.id !== id) {
        setActiveNoteId(data.id);
      }
      setSaveStatus('saved');
      setTimeout(() => setSaveStatus('idle'), 2000);
    } catch (e) {
      console.error("Auto-save failed:", e);
      setSaveStatus('idle');
    }
  }, []);

  const debouncedSave = useCallback((title: string, text: string, id: number, project: string) => {
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    saveTimerRef.current = setTimeout(() => {
      persistNote(title, text, id, project);
    }, 1500);
  }, [persistNote]);

  const deleteNote = async () => {
    if (notes.length === 0 || !activeNote?.id) return;
    try {
      await fetch(`http://localhost:8000/notes/${activeNote.id}`, {
        method: 'DELETE'
      });
      setActiveNoteId(null);
    } catch (e) {
      console.error("Delete failed:", e);
    }
  };

  // ─── New Note ───────────────────────────────────────────────
  const handleNewNote = useCallback(async () => {
    try {
      const res = await fetch('http://localhost:8000/notes/update', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: "Untitled", text: "", project: activeWorkspace })
      });
      const data = await res.json();
      if (data.id) setActiveNoteId(data.id);
    } catch (e) {
      console.error("Failed to create note:", e);
    }
  }, [activeWorkspace]);

  // Keyboard shortcut: Ctrl+S and Ctrl+N
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
        e.preventDefault();
        if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
        persistNote(editTitle, editText, activeNote?.id ?? 0, activeWorkspace);
      }
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'n') {
        e.preventDefault();
        handleNewNote();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [editTitle, editText, activeNote?.id, persistNote, handleNewNote, activeWorkspace]);

  const onTitleChange = (val: string) => {
    setEditTitle(val);
    debouncedSave(val, editText, activeNote?.id ?? 0, activeWorkspace);
  };

  // onTextChange is reserved for future use with plain text editor
  // const onTextChange = (val: string) => {
  //   setEditText(val);
  //   debouncedSave(editTitle, val, activeNoteIdx, activeWorkspace);
  // };

  // ─── Ask AI Logic ───────────────────────────────────────────
  const handleAskAI = async () => {
    if (!aiQuery.trim() || !activeNote) return;
    setAiLoading(true);
    setAiAnswer("");
    try {
      const selectedText = editor ? editor.getSelectedText() : "";
      const selectionContext = selectedText ? `The user has highlighted this specific text: "${selectedText}"\n\n` : "";
      const contextPrompt = `The user has a note titled "${activeNote.title}" with this content:\n\n${activeNote.text}\n\n${selectionContext}Their question about this note is: "${aiQuery}"\n\nAnswer concisely and helpfully.`;
      
      const res = await fetch('http://localhost:8000/api/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: contextPrompt })
      });
      const data = await res.json();
      let answer = "";
      if (data.choices && data.choices[0] && data.choices[0].message) {
         answer = data.choices[0].message.content;
      } else if (data.text) {
         answer = data.text;
      } else {
         answer = "Sorry, I couldn't generate an answer.";
      }
      setAiAnswer(answer);
    } catch (e) {
      console.error("Ask AI failed:", e);
      setAiAnswer("Failed to reach AI service.");
    } finally {
      setAiLoading(false);
    }
  };



  const handleNewSubNote = async (parentId: number) => {
    try {
      const res = await fetch('http://localhost:8000/notes/update', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: "Untitled", text: "", project: activeWorkspace, parent_id: parentId })
      });
      const data = await res.json();
      if (data.id) setActiveNoteId(data.id);
    } catch (e) {
      console.error("Failed to create subnote:", e);
    }
  };

  const togglePin = async (id: number, currentStatus: boolean) => {
    try {
      await fetch('http://localhost:8000/notes/pin', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id, pinned: !currentStatus })
      });
    } catch (e) {
      console.error("Failed to pin note:", e);
    }
  };

  const renderNoteTree = (parentId: number | undefined | null = null, depth: number = 0) => {
    const children = notes
      .map((n, i) => ({ ...n, originalIdx: i }))
      .filter(n => (n.project || "General") === activeWorkspace)
      .filter(n => (n.parent_id || null) === parentId)
      .filter(n => 
        (n.title?.toLowerCase() || "").includes(search.toLowerCase()) || 
        (n.text?.toLowerCase() || "").includes(search.toLowerCase())
      )
      .sort((a, b) => {
        if (a.pinned && !b.pinned) return -1;
        if (!a.pinned && b.pinned) return 1;
        return 0;
      });

    return children.map(note => (
      <div key={note.id || `temp-${note.originalIdx}`} className="w-full">
        <div 
          onClick={() => setActiveNoteId(note.id ?? null)}
          className={`px-3 py-1.5 text-sm cursor-pointer rounded flex items-center justify-between group transition-colors duration-300 ${activeNoteId === note.id ? 'bg-white/10 text-white' : 'text-white/60 hover:bg-white/5 hover:text-white/90'}`}
          style={{ paddingLeft: `${0.75 + depth * 1.5}rem` }}
        >
          <div className="flex items-center gap-2 overflow-hidden">
            <span className="text-base leading-none">{note.icon || '📄'}</span>
            <span className="truncate">{note.title || "Untitled"}</span>
          </div>
          <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
            {note.id && (
              <>
                <button 
                  onClick={(e) => {
                    e.stopPropagation();
                    togglePin(note.id!, note.pinned || false);
                  }} 
                  className={`p-1 hover:bg-white/20 rounded transition-colors ${note.pinned ? 'text-yellow-400 opacity-100' : 'text-white/50 hover:text-white'}`} 
                  title={note.pinned ? "Unpin" : "Pin to top"}
                >
                  <Pin size={12} className={note.pinned ? "fill-yellow-400" : ""} />
                </button>
              <button 
                onClick={(e) => {
                  e.stopPropagation();
                  handleNewSubNote(note.id!);
                }} 
                className="p-1 hover:bg-white/20 rounded text-white/50 hover:text-white transition-colors" title="Add Subpage"
              >
                <Plus size={12} />
              </button>
              </>
            )}
          </div>
        </div>
        {note.id && renderNoteTree(note.id, depth + 1)}
      </div>
    ));
  };

  const wordCount = editText.split(/\s+/).filter(Boolean).length;
  const readingTime = Math.max(1, Math.ceil(wordCount / 200));

  return (
    <div className="h-full flex flex-col md:flex-row overflow-hidden bg-black text-[#D4D4D4] font-sans">
      
      {/* ─── Sidebar ─────────────────────────────────────────── */}
      <aside className="w-full md:w-64 h-auto md:h-full border-r border-white/10 flex flex-col bg-white/5 backdrop-blur-2xl pb-20 shrink-0 z-10">
        <div className="p-4 space-y-4 pt-8">
          <div className="flex justify-between items-center mb-2">
            <div className="flex gap-2 bg-black/40 p-1 rounded-lg w-full text-xs overflow-x-auto custom-scrollbar flex-nowrap shrink-0">
              {['General', ...Array.from(new Set(notes.map(n => n.project).filter((p): p is string => Boolean(p)))).filter(p => p !== 'General')].map(ws => (
                <button
                  key={ws}
                  onClick={() => setActiveWorkspace(ws)}
                  className={`flex-1 min-w-[max-content] px-3 py-1 rounded transition-colors ${activeWorkspace === ws ? 'bg-white/10 text-white' : 'text-white/40 hover:text-white/80'}`}
                >
                  {ws}
                </button>
              ))}
              <button 
                onClick={() => {
                  const newWs = window.prompt("Enter new project name:");
                  if (newWs && newWs.trim() !== "") {
                    setActiveWorkspace(newWs.trim());
                  }
                }}
                className="px-2 py-1 rounded transition-colors text-white/40 hover:text-white hover:bg-white/10 flex items-center shrink-0"
                title="Add Project"
              >
                <Plus size={12} />
              </button>
            </div>
          </div>
          <div className="flex justify-between items-center">
            <h2 className="text-sm font-semibold text-white/80 tracking-wide flex items-center gap-2">
              <Folder size={14} /> {activeWorkspace}
            </h2>
            <div className="flex gap-1">
              <button onClick={() => setShowGenerator(!showGenerator)} title="Generate AI Notes" className="w-6 h-6 flex items-center justify-center hover:bg-white/10 rounded transition-colors text-emerald-400/70 hover:text-emerald-400">
                <Sparkles size={14} />
              </button>
              <button onClick={handleNewNote} title="New page (Ctrl+N)" className="w-6 h-6 flex items-center justify-center hover:bg-white/10 rounded transition-colors text-white/50 hover:text-white">
                <Plus size={14} />
              </button>
            </div>
          </div>
          
          <div className="relative group">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-white/30 group-focus-within:text-white/80 transition-colors" />
            <input 
              className="w-full bg-black/20 border border-transparent pl-9 pr-3 py-1.5 text-xs focus-visible:ring-1 focus-visible:ring-emerald-500/50 outline-none transition-all placeholder-white/30 rounded" 
              placeholder="Search notes..." 
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
          </div>
          {showGenerator && <NoteGeneratorPanel onDone={() => setShowGenerator(false)} activeWorkspace={activeWorkspace} />}
        </div>

        <div className="flex-1 overflow-y-auto custom-scrollbar px-2 space-y-0.5">
          {renderNoteTree(null, 0)}
        </div>

        {/* Sidebar Footer */}
        <div className="px-4 py-3 border-t border-white/5 text-[10px] text-white/30 font-mono">
          {notes.length} page{notes.length !== 1 ? 's' : ''}
        </div>
      </aside>

      {/* ─── Main Editor ─────────────────────────────────────── */}
      <section className="flex-1 h-full flex flex-col bg-transparent relative z-0">
        
        {/* Top bar */}
        <div className="h-12 border-b border-white/10 flex items-center px-6 justify-between bg-transparent shrink-0">
          <div className="flex items-center gap-4 text-xs text-white/50">
            <span>Workspace</span>
            <ChevronRight size={12} />
            <span className="text-white/80">{activeNote?.title || "Untitled"}</span>
          </div>
          <div className="flex items-center gap-2">
            {/* Auto-save indicator */}
            <div className="flex items-center gap-1.5 text-[10px] font-mono mr-2">
              {saveStatus === 'saving' && (
                <span className="text-yellow-400/80 flex items-center gap-1"><Loader2 size={10} className="animate-spin" /> Saving...</span>
              )}
              {saveStatus === 'saved' && (
                <span className="text-emerald-400/80">✓ Saved</span>
              )}
              {saveStatus === 'idle' && activeNote && (
                <span className="text-white/20">Auto-save on</span>
              )}
            </div>
            
            {/* Ask AI Button */}
            <button 
              onClick={() => setShowAskAI(!showAskAI)} 
              className={`flex items-center gap-1.5 text-xs px-3 py-1.5 rounded transition-colors ${showAskAI ? 'bg-purple-500/20 text-purple-400' : 'text-white/60 hover:text-white hover:bg-white/5'}`}
              title="Ask AI about this note"
            >
              <Sparkles size={14} /> Ask AI
            </button>
            <button onClick={onExport} className="text-xs text-white/60 hover:text-white px-3 py-1.5 rounded hover:bg-white/5 transition-colors">
              Export
            </button>
            <button onClick={deleteNote} className="text-white/40 hover:text-red-400 p-1.5 rounded hover:bg-red-400/10 transition-colors" title="Delete note">
              <Trash2 size={14} />
            </button>
          </div>
        </div>

        {/* Ask AI Panel */}
        {showAskAI && (
          <div className="border-b border-white/5 bg-purple-500/[0.03] px-6 py-4 flex flex-col gap-3 shrink-0">
            <div className="flex items-center gap-2 text-xs text-purple-300/80 font-semibold">
              <Sparkles size={14} /> Ask Primnox about "{activeNote?.title}"
              <button onClick={() => { setShowAskAI(false); setAiAnswer(""); }} className="ml-auto text-white/40 hover:text-white"><X size={14} /></button>
            </div>
            <div className="flex gap-2">
              <input
                value={aiQuery}
                onChange={e => setAiQuery(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleAskAI()}
                placeholder="e.g. 'What are the action items?' or 'Summarize in 3 bullets'"
                className="flex-1 bg-black/30 border border-white/10 px-3 py-2 text-sm rounded outline-none focus-visible:ring-1 focus-visible:ring-emerald-500/50 placeholder-white/20"
              />
              <button 
                onClick={handleAskAI} 
                disabled={aiLoading || !aiQuery.trim()}
                className="px-4 py-2 bg-purple-500/20 text-purple-300 rounded text-xs font-bold hover:bg-purple-500/30 transition-colors disabled:opacity-40"
              >
                {aiLoading ? <Loader2 size={14} className="animate-spin" /> : 'Ask'}
              </button>
            </div>
            {aiAnswer && (
              <div className="bg-black/30 border border-purple-500/10 rounded p-3 text-sm text-white/70 leading-relaxed">
                {aiAnswer}
              </div>
            )}
            <div className="flex gap-2 flex-wrap">
              {['Summarize this note', 'What are the action items?', 'Key takeaways'].map(q => (
                <button key={q} onClick={() => { setAiQuery(q); }} className="text-[10px] px-2 py-1 bg-white/5 border border-white/10 rounded text-white/50 hover:text-white/80 hover:bg-white/10 transition-colors">
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Editor Content */}
        <div className="flex-1 overflow-y-auto custom-scrollbar relative">
          {activeNote ? (
            <div className="notion-page-wrapper">
              <input
                value={editTitle}
                onChange={e => onTitleChange(e.target.value)}
                className="bg-transparent border-none outline-none text-4xl font-bold text-white w-full placeholder-white/20 mb-3"
                placeholder="Untitled"
              />
              <p className="text-[10px] text-white/20 font-mono mb-10">
                {wordCount} words · {readingTime} min read · {activeNote.timestamp ? new Date(activeNote.timestamp).toLocaleDateString() : 'just now'}
              </p>
              
              <div className="notion-editor-wrapper">
                <BlockNoteView 
                  editor={editor} 
                  theme="dark" 
                  onChange={onEditorChange}
                >
                  <SuggestionMenuController
                    triggerCharacter={"/"}
                    getItems={async (query: string) =>
                      [
                        // insertAiItem(editor),
                        ...getDefaultReactSlashMenuItems(editor),
                      ].filter((item) =>
                        item.title.toLowerCase().includes(query.toLowerCase()) ||
                        (item.aliases && item.aliases.some((a: string) => a.toLowerCase().includes(query.toLowerCase())))
                      )
                    }
                  />
                </BlockNoteView>
              </div>
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center h-full gap-6 p-8">
              <div className="relative flex items-center justify-center w-24 h-24">
                <div className="absolute inset-0 bg-emerald-500/20 rounded-full blur-2xl animate-pulse" />
                <div className="relative bg-white/5 border border-emerald-500/30 rounded-2xl p-6 shadow-[0_0_20px_rgba(16,185,129,0.15)] flex items-center justify-center">
                  <FileText size={40} className="text-emerald-400/80 drop-shadow-[0_0_8px_rgba(16,185,129,0.5)]" />
                </div>
              </div>
              
              <div className="text-center space-y-2">
                <h3 className="text-xl font-bold text-white tracking-wide">Workspace Empty</h3>
                <p className="text-sm text-white/40 max-w-sm">Select a page from the sidebar to view its contents, or create a new one to start writing.</p>
              </div>
              
              <div className="flex gap-4 mt-2">
                <button 
                  onClick={handleNewNote} 
                  className="px-6 py-2.5 bg-emerald-500/10 border border-emerald-500/30 hover:border-emerald-500/60 rounded-xl text-sm font-medium text-emerald-400 hover:text-emerald-300 hover:bg-emerald-500/20 transition-all duration-300 flex items-center gap-2 group shadow-[0_0_15px_rgba(16,185,129,0.05)] hover:shadow-[0_0_20px_rgba(16,185,129,0.15)]"
                >
                  <Plus size={16} className="group-hover:scale-110 transition-transform" /> 
                  Create New Page
                </button>
              </div>
            </div>
          )}
        </div>

      </section>
    </div>
  );
};
