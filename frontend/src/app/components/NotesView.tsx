import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { Search, Plus, FileText, ChevronRight, Trash2, Sparkles, X, Loader2, Folder, Pin, Clock, Hash, AlignLeft, PanelRightOpen, PanelRightClose } from 'lucide-react';
import "@blocknote/core/fonts/inter.css";
import "@blocknote/mantine/style.css";
import { BlockNoteView } from "@blocknote/mantine";
import { useCreateBlockNote, SuggestionMenuController, getDefaultReactSlashMenuItems, DefaultReactSuggestionItem } from "@blocknote/react";
import { BlockNoteSchema, defaultBlockSpecs } from "@blocknote/core";
import { NoteGeneratorPanel } from './NoteGeneratorPanel';
import { API_BASE } from '../../config';

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
          const res = await fetch(`${API_BASE}/api/generate`, {
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
        <div className="w-full bg-success/10 border border-success/30 rounded-lg p-3 my-2 flex flex-col gap-2 shadow-[0_0_15px_rgba(16,185,129,0.1)]">
          <div className="flex items-center gap-2 text-success font-mono text-xs uppercase tracking-widest font-bold">
            <Sparkles size={14} /> AI Generation
          </div>
          <div className="flex gap-2">
            <input 
              autoFocus
              disabled={isGenerating}
              className="flex-1 bg-surface/50 border border-success/20 rounded px-3 py-1.5 text-sm focus:outline-none focus:border-success/50 text-on-surface placeholder-on-surface/30"
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
              className="px-3 py-1.5 bg-success/20 hover:bg-success/30 text-success rounded text-sm transition-colors flex items-center gap-2 disabled:opacity-50"
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

export const NotesIconSidebar = ({ notes = [], onExport, onRefresh }: { notes: Note[], onExport?: () => void, onRefresh?: () => void, sendMessage?: (text: string) => void }) => {
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
  const [showContextPanel, setShowContextPanel] = useState(true);
  const [addingWorkspace, setAddingWorkspace] = useState(false);
  const [newWsName, setNewWsName] = useState('');

  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const wsEscapeRef  = useRef(false);

  const activeNote = notes.find(n => n.id === activeNoteId) ?? notes[0];

  // Every workspace that actually has a note in it, "General" always first.
  // Shared by the workspace tab row, the AI builder's folder picker, and the
  // "move to workspace" control below, so all three agree on the same list.
  const allWorkspaces = useMemo(
    () => ['General', ...Array.from(new Set(notes.map(n => n.project).filter((p): p is string => Boolean(p)))).filter(p => p !== 'General')],
    [notes]
  );

  const prevNoteIdRef = useRef<number | null | undefined>(undefined);

  // Sync editor state when switching notes
  useEffect(() => {
    if (activeNote && prevNoteIdRef.current !== activeNote?.id) {
      // Cancel any pending save from the PREVIOUS note before switching
      if (saveTimerRef.current) {
        clearTimeout(saveTimerRef.current);
        saveTimerRef.current = null;
      }
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

  // editor.replaceBlocks() below fires BlockNote's onChange the same as a
  // real keystroke would — with nothing to distinguish them, switching to a
  // newly-created note replayed a stale `editTitle` closure (still holding
  // the PREVIOUS note's title, since that state update hadn't re-rendered
  // yet) into a debounced save aimed at the NEW note's id, silently
  // overwriting it with the old title and empty text. Found live by
  // creating a note right after editing another one. This flag brackets
  // every programmatic content load so onEditorChange can tell "the note
  // switched under us" apart from "the user actually typed something."
  const isLoadingContentRef = useRef(false);

  useEffect(() => {
    async function loadContent() {
      if (activeNote && prevNoteIdRef.current === activeNote?.id) {
        isLoadingContentRef.current = true;
        if (activeNote.text) {
          const blocks = await editor.tryParseMarkdownToBlocks(activeNote.text);
          editor.replaceBlocks(editor.document, blocks);
        } else {
          editor.replaceBlocks(editor.document, [{ type: "paragraph", content: "" }]);
        }
        isLoadingContentRef.current = false;
      }
    }
    // Only load if the text has changed significantly or we just switched (we rely on the previous effect to set text)
    loadContent();
  }, [activeNote?.id, editor]); // We trigger this when activeNote?.id changes

  const onEditorChange = async () => {
    if (isLoadingContentRef.current) return; // programmatic load, not a user edit — see note above
    const markdown = await editor.blocksToMarkdownLossy(editor.document);
    setEditText(markdown);
    // Capture the current note ID at the moment of the edit, not lazily
    const currentNoteId = activeNote?.id ?? 0;
    const currentTitle = editTitle;
    debouncedSave(currentTitle, markdown, currentNoteId, activeWorkspace);
  };

  // [[ ]] wiki-link autocomplete. By the time onItemClick fires, BlockNote
  // has already removed the "[[query" text (same mechanism as the "/"
  // slash-menu) — so the brackets have to be re-added here for the saved
  // markdown to contain a literal [[Title]] the backend can parse
  // (notes_manager.py's WIKILINK_PATTERN / _resolve_and_set_links).
  const getWikiLinkItems = useCallback(async (query: string): Promise<DefaultReactSuggestionItem[]> => {
    try {
      const res = await fetch(`${API_BASE}/api/notes/search-titles?q=${encodeURIComponent(query)}&limit=8`);
      const data = await res.json();
      const results: { id: number; title: string }[] = data?.notes ?? [];
      if (results.length === 0) {
        return [{
          title: query ? `No notes match "${query}"` : 'Start typing a note title…',
          onItemClick: () => {},
          icon: <Hash size={14} />,
        }];
      }
      return results.map(n => ({
        title: n.title,
        subtext: 'Link to note',
        icon: <FileText size={14} />,
        onItemClick: () => {
          editor.insertInlineContent(`[[${n.title}]] `);
        },
      }));
    } catch {
      return [];
    }
  }, [editor]);

  // ─── Auto-Save with Debounce ────────────────────────────────
  const persistNote = useCallback(async (title: string, text: string, id: number, project: string) => {
    if (id === 0) return; // Don't save if there's no valid note ID
    setSaveStatus('saving');
    try {
      const res = await fetch(`${API_BASE}/notes/update`, {
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

  // ─── Move to a different workspace ─────────────────────────────
  // There was no way to change a note's project after creation — the
  // Project field in Page Details was a read-only label. Every other save
  // path uses `activeWorkspace` (the currently selected tab) rather than
  // the note's own project, which is fine as long as you're only ever
  // editing notes within the tab you're viewing; this is the one place that
  // deliberately overrides it, since moving IS the point.
  const moveToWorkspace = useCallback((newProject: string) => {
    if (!activeNote?.id || newProject === (activeNote.project || 'General')) return;
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    persistNote(editTitle, editText, activeNote.id, newProject);
    setActiveWorkspace(newProject);
  }, [activeNote, editTitle, editText, persistNote]);

  const deleteNote = async () => {
    if (notes.length === 0 || !activeNote?.id) return;
    try {
      await fetch(`${API_BASE}/notes/${activeNote.id}`, {
        method: 'DELETE'
      });
      setActiveNoteId(null);
      onRefresh?.();
    } catch (e) {
      console.error("Delete failed:", e);
    }
  };

  // ─── AI Note Builder result ───────────────────────────────────
  // If the AI edited the note that's currently open, its id doesn't change
  // — the switch-note effects above only refire on an id change, so they'd
  // never pick up the new content. Patch the editor directly here instead
  // of fighting that effect's timing. A different/new note just switches to
  // it normally, which the existing effects already handle correctly.
  const handleGeneratedNote = useCallback(async (note: { id: number; title: string; text: string }) => {
    if (activeNote && note.id === activeNote.id) {
      isLoadingContentRef.current = true;
      setEditTitle(note.title || "");
      setEditText(note.text || "");
      if (note.text) {
        const blocks = await editor.tryParseMarkdownToBlocks(note.text);
        editor.replaceBlocks(editor.document, blocks);
      } else {
        editor.replaceBlocks(editor.document, [{ type: "paragraph", content: "" }]);
      }
      isLoadingContentRef.current = false;
    } else {
      setActiveNoteId(note.id);
    }
    onRefresh?.();
  }, [activeNote, editor, onRefresh]);

  // ─── New Note ───────────────────────────────────────────────
  const handleNewNote = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/notes/update`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: "Untitled", text: "", project: activeWorkspace })
      });
      const data = await res.json();
      if (data.id) {
        await onRefresh?.();
        setActiveNoteId(data.id);
      }
    } catch (e) {
      console.error("Failed to create note:", e);
    }
  }, [activeWorkspace, onRefresh]);

  // Keyboard shortcut: Ctrl+S and Ctrl+N; also respond to palette new-note event
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
    const paletteNewNote = () => handleNewNote();
    window.addEventListener('keydown', handler);
    window.addEventListener('primnox:new-note', paletteNewNote);
    return () => {
      window.removeEventListener('keydown', handler);
      window.removeEventListener('primnox:new-note', paletteNewNote);
    };
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
      
      const res = await fetch(`${API_BASE}/api/generate`, {
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
      const res = await fetch(`${API_BASE}/notes/update`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: "Untitled", text: "", project: activeWorkspace, parent_id: parentId })
      });
      const data = await res.json();
      if (data.id) {
        await onRefresh?.();
        setActiveNoteId(data.id);
      }
    } catch (e) {
      console.error("Failed to create subnote:", e);
    }
  };

  const togglePin = async (id: number, currentStatus: boolean) => {
    try {
      await fetch(`${API_BASE}/notes/pin`, {
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
          className={`px-3 py-1.5 text-sm cursor-pointer rounded flex items-center justify-between group transition-colors duration-300 ${activeNoteId === note.id ? 'bg-on-surface/10 text-on-surface' : 'text-on-surface/60 hover:bg-on-surface/5 hover:text-on-surface/90'}`}
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
                  className={`p-1 hover:bg-on-surface/20 rounded transition-colors ${note.pinned ? 'text-warn opacity-100' : 'text-on-surface/50 hover:text-on-surface'}`} 
                  title={note.pinned ? "Unpin" : "Pin to top"}
                >
                  <Pin size={12} className={note.pinned ? "fill-warn/25" : ""} />
                </button>
              <button 
                onClick={(e) => {
                  e.stopPropagation();
                  handleNewSubNote(note.id!);
                }} 
                className="p-1 hover:bg-on-surface/20 rounded text-on-surface/50 hover:text-on-surface transition-colors" title="Add Subpage"
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
    <div className="h-full flex flex-col md:flex-row overflow-hidden bg-surface text-on-surface font-sans">
      
      {/* ─── Sidebar ─────────────────────────────────────────── */}
      <aside className="w-full md:w-64 h-auto md:h-full border-r border-on-surface/10 flex flex-col bg-on-surface/5 backdrop-blur-2xl pb-20 shrink-0 z-10">
        <div className="p-4 space-y-4 pt-8">
          <div className="flex justify-between items-center mb-2">
            <div className="flex gap-2 bg-surface/40 p-1 rounded-lg w-full text-xs overflow-x-auto custom-scrollbar flex-nowrap shrink-0">
              {allWorkspaces.map(ws => (
                <button
                  key={ws}
                  onClick={() => setActiveWorkspace(ws)}
                  className={`flex-1 min-w-[max-content] px-3 py-1 rounded transition-colors ${activeWorkspace === ws ? 'bg-on-surface/10 text-on-surface' : 'text-on-surface/60 hover:text-on-surface/80'}`}
                >
                  {ws}
                </button>
              ))}
              <button
                onClick={() => { setAddingWorkspace(true); setNewWsName(''); }}
                className="px-2 py-1 rounded transition-colors text-on-surface/60 hover:text-on-surface hover:bg-on-surface/10 flex items-center shrink-0"
                title="Add Project"
              >
                <Plus size={12} />
              </button>
            </div>
          </div>
          {addingWorkspace && (
            <div className="flex gap-2 mt-1">
              <input
                autoFocus
                value={newWsName}
                onChange={e => setNewWsName(e.target.value)}
                onKeyDown={e => {
                  if (e.key === 'Enter' && newWsName.trim()) {
                    setActiveWorkspace(newWsName.trim());
                    setAddingWorkspace(false);
                  }
                  if (e.key === 'Escape') { wsEscapeRef.current = true; setAddingWorkspace(false); }
                }}
                onBlur={() => {
                  if (!wsEscapeRef.current && newWsName.trim()) setActiveWorkspace(newWsName.trim());
                  wsEscapeRef.current = false;
                  setAddingWorkspace(false);
                }}
                placeholder="Workspace name…"
                className="flex-1 bg-surface/40 border border-on-surface/10 rounded px-2 py-1 text-xs text-on-surface outline-none focus:border-primary/40 placeholder-on-surface/25"
              />
            </div>
          )}
          <div className="flex justify-between items-center">
            <h2 className="text-sm font-semibold text-on-surface/80 tracking-wide flex items-center gap-2">
              <Folder size={14} /> {activeWorkspace}
            </h2>
            <div className="flex gap-1">
              <button onClick={() => setShowGenerator(!showGenerator)} title="AI Note Builder — write a new note or edit this one" className="w-6 h-6 flex items-center justify-center hover:bg-on-surface/10 rounded transition-colors text-success/70 hover:text-success">
                <Sparkles size={14} />
              </button>
              <button onClick={handleNewNote} title="New page (Ctrl+N)" className="w-6 h-6 flex items-center justify-center hover:bg-on-surface/10 rounded transition-colors text-on-surface/50 hover:text-on-surface">
                <Plus size={14} />
              </button>
            </div>
          </div>
          
          <div className="relative group">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-on-surface/55 group-focus-within:text-on-surface/80 transition-colors" />
            <input 
              className="w-full bg-surface/20 border border-transparent pl-9 pr-3 py-1.5 text-xs focus-visible:ring-1 focus-visible:ring-success/50 outline-none transition-all placeholder-on-surface/30 rounded" 
              placeholder="Search notes..." 
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
          </div>
          {showGenerator && (
            <NoteGeneratorPanel
              onDone={() => setShowGenerator(false)}
              activeWorkspace={activeWorkspace}
              activeNote={activeNote ? { id: activeNote.id!, title: activeNote.title, text: activeNote.text } : null}
              onGenerated={handleGeneratedNote}
              workspaces={allWorkspaces}
            />
          )}
        </div>

        <div className="flex-1 overflow-y-auto custom-scrollbar px-2 space-y-0.5">
          {renderNoteTree(null, 0)}
        </div>

        {/* Sidebar Footer */}
        <div className="px-4 py-3 border-t border-on-surface/5 text-[10px] text-on-surface/55 font-mono">
          {notes.length} page{notes.length !== 1 ? 's' : ''}
        </div>
      </aside>

      {/* ─── Main Editor + Context Panel ────────────────────── */}
      <div className="flex-1 h-full flex overflow-hidden">

        {/* ─── Editor Area ───────────────────────────────────── */}
        <section className="flex-1 h-full flex flex-col bg-transparent relative z-0 min-w-0">
          
          {/* Top bar */}
          <div className="h-12 border-b border-on-surface/10 flex items-center gap-3 px-6 justify-between bg-transparent shrink-0">
            {/* min-w-0 + truncate: without them the breadcrumb refused to shrink
                and the action labels collided into each other ("Auto-Untitledsaveon"). */}
            <div className="flex items-center gap-2 text-xs text-on-surface/50 min-w-0 flex-1">
              <span className="truncate shrink-0 max-w-[35%]">{activeWorkspace}</span>
              <ChevronRight size={12} className="shrink-0" />
              <span className="text-on-surface/80 truncate">{activeNote?.title || "Untitled"}</span>
            </div>
            <div className="flex items-center gap-2 shrink-0 whitespace-nowrap">
              {/* Auto-save indicator */}
              <div className="flex items-center gap-1.5 text-[10px] font-mono mr-2 whitespace-nowrap shrink-0">
                {saveStatus === 'saving' && (
                  <span className="text-warn/80 flex items-center gap-1"><Loader2 size={10} className="animate-spin" /> Saving...</span>
                )}
                {saveStatus === 'saved' && (
                  <span className="text-success/80">✓ Saved</span>
                )}
                {saveStatus === 'idle' && activeNote && (
                  <span className="text-on-surface/48">Auto-save on</span>
                )}
              </div>
              
              {/* Ask AI Button */}
              <button 
                onClick={() => setShowAskAI(!showAskAI)} 
                className={`flex items-center gap-1.5 text-xs px-3 py-1.5 rounded transition-colors ${showAskAI ? 'bg-primary/20 text-primary' : 'text-on-surface/60 hover:text-on-surface hover:bg-on-surface/5'}`}
                title="Ask AI about this note"
              >
                <Sparkles size={14} /> Ask AI
              </button>
              <button onClick={onExport} className="text-xs text-on-surface/60 hover:text-on-surface px-3 py-1.5 rounded hover:bg-on-surface/5 transition-colors">
                Export
              </button>
              <button onClick={deleteNote} className="text-on-surface/60 hover:text-error p-1.5 rounded hover:bg-error/10 transition-colors" title="Delete note">
                <Trash2 size={14} />
              </button>
              <div className="w-px h-5 bg-on-surface/10 mx-1" />
              <button 
                onClick={() => setShowContextPanel(!showContextPanel)} 
                className="text-on-surface/60 hover:text-on-surface p-1.5 rounded hover:bg-on-surface/5 transition-colors" 
                title={showContextPanel ? 'Hide details' : 'Show details'}
              >
                {showContextPanel ? <PanelRightClose size={14} /> : <PanelRightOpen size={14} />}
              </button>
            </div>
          </div>

          {/* Ask AI Panel */}
          {showAskAI && (
            <div className="border-b border-on-surface/5 bg-primary/20/[0.03] px-6 py-4 flex flex-col gap-3 shrink-0">
              <div className="flex items-center gap-2 text-xs text-primary/80 font-semibold">
                <Sparkles size={14} /> Ask Primnox about "{activeNote?.title}"
                <button onClick={() => { setShowAskAI(false); setAiAnswer(""); }} className="ml-auto text-on-surface/60 hover:text-on-surface"><X size={14} /></button>
              </div>
              <div className="flex gap-2">
                <input
                  value={aiQuery}
                  onChange={e => setAiQuery(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && handleAskAI()}
                  placeholder="e.g. 'What are the action items?' or 'Summarize in 3 bullets'"
                  className="flex-1 bg-surface/30 border border-on-surface/10 px-3 py-2 text-sm rounded outline-none focus-visible:ring-1 focus-visible:ring-success/50 placeholder-on-surface/20"
                />
                <button 
                  onClick={handleAskAI} 
                  disabled={aiLoading || !aiQuery.trim()}
                  className="px-4 py-2 bg-primary/20 text-primary rounded text-xs font-bold hover:bg-primary/30 transition-colors disabled:opacity-40"
                >
                  {aiLoading ? <Loader2 size={14} className="animate-spin" /> : 'Ask'}
                </button>
              </div>
              {aiAnswer && (
                <div className="bg-surface/30 border border-primary/10 rounded p-3 text-sm text-on-surface/70 leading-relaxed">
                  {aiAnswer}
                </div>
              )}
              <div className="flex gap-2 flex-wrap">
                {['Summarize this note', 'What are the action items?', 'Key takeaways'].map(q => (
                  <button key={q} onClick={() => { setAiQuery(q); }} className="text-[10px] px-2 py-1 bg-on-surface/5 border border-on-surface/10 rounded text-on-surface/50 hover:text-on-surface/80 hover:bg-on-surface/10 transition-colors">
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Editor Content — fills full width, padding controls reading width */}
          <div className="flex-1 overflow-y-auto custom-scrollbar relative w-full">
            {activeNote ? (
              // Padding was px-16 lg:px-28 xl:px-36. Those variants key off the
              // VIEWPORT, but this element sits in a column between a 256px note
              // list and a 280px details panel — so at a 961px window the column
              // was 165px wide and 128px of that was padding, leaving 31px of
              // text: the editor rendered one character per line. Base padding is
              // now column-appropriate and only grows when there is room.
              <div className="w-full px-6 sm:px-8 lg:px-14 xl:px-20 pt-20 pb-40 flex flex-col min-h-full">
                <input
                  value={editTitle}
                  onChange={e => onTitleChange(e.target.value)}
                  className="bg-transparent border-none outline-none text-4xl font-bold text-on-surface w-full placeholder-on-surface/20 mb-2"
                  placeholder="Untitled"
                />
                <p className="text-[10px] text-on-surface/48 font-mono mb-10">
                  {wordCount} words · {readingTime} min read · {activeNote.timestamp ? new Date(activeNote.timestamp).toLocaleDateString() : 'just now'}
                </p>
                
                <div className="notion-editor-wrapper flex-1">
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
                    <SuggestionMenuController
                      triggerCharacter={"[["}
                      getItems={getWikiLinkItems}
                    />
                  </BlockNoteView>
                </div>
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center h-full gap-6 p-8">
                <div className="relative flex items-center justify-center w-24 h-24">
                  <div className="absolute inset-0 bg-success/20 rounded-full blur-2xl animate-pulse" />
                  <div className="relative bg-on-surface/5 border border-success/30 rounded-2xl p-6 shadow-[0_0_20px_rgba(16,185,129,0.15)] flex items-center justify-center">
                    <FileText size={40} className="text-success/80 drop-shadow-[0_0_8px_rgba(16,185,129,0.5)]" />
                  </div>
                </div>
                
                <div className="text-center space-y-2">
                  <h3 className="text-xl font-bold text-on-surface tracking-wide">Workspace Empty</h3>
                  <p className="text-sm text-on-surface/60 max-w-sm">Nothing written down yet. Pick a page on the left, or start a new one — it never leaves this machine.</p>
                </div>
                
                <div className="flex gap-4 mt-2">
                  <button 
                    onClick={handleNewNote} 
                    className="px-6 py-2.5 bg-success/10 border border-success/30 hover:border-success/60 rounded-xl text-sm font-medium text-success hover:text-success hover:bg-success/20 transition-all duration-300 flex items-center gap-2 group shadow-[0_0_15px_rgba(16,185,129,0.05)] hover:shadow-[0_0_20px_rgba(16,185,129,0.15)]"
                  >
                    <Plus size={16} className="group-hover:scale-110 transition-transform" /> 
                    Create New Page
                  </button>
                </div>
              </div>
            )}
          </div>

        </section>

        {/* ─── Context / Details Panel ───────────────────────── */}
        {showContextPanel && activeNote && (
          // 280px of fixed width on top of the 256px note list starved the editor
          // on anything narrower than a wide desktop. Yield it back until there
          // is room for all three panes.
          <aside className="w-[280px] h-full border-l border-on-surface/10 bg-on-surface/[0.02] hidden xl:flex flex-col shrink-0 overflow-y-auto custom-scrollbar">
            
            {/* Panel Header */}
            <div className="h-12 border-b border-on-surface/10 flex items-center px-5 shrink-0">
              <h3 className="text-xs font-semibold text-on-surface/60 tracking-wide uppercase">Page Details</h3>
            </div>

            <div className="p-5 space-y-6 text-xs">

              {/* Properties Section */}
              <div className="space-y-3">
                <h4 className="text-on-surface/60 uppercase tracking-widest text-[10px] font-semibold">Properties</h4>
                
                <div className="space-y-2.5">
                  <div className="flex items-center gap-3">
                    <Clock size={13} className="text-on-surface/55 shrink-0" />
                    <span className="text-on-surface/60 w-16 shrink-0">Created</span>
                    <span className="text-on-surface/70">{activeNote.timestamp ? new Date(activeNote.timestamp).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : '—'}</span>
                  </div>
                  <div className="flex items-center gap-3">
                    <Folder size={13} className="text-on-surface/55 shrink-0" />
                    <span className="text-on-surface/60 w-16 shrink-0">Project</span>
                    <select
                      value={activeNote.project || 'General'}
                      onChange={e => moveToWorkspace(e.target.value)}
                      title="Move this note to a different workspace"
                      className="flex-1 bg-transparent text-on-surface/70 outline-none focus-visible:ring-1 focus-visible:ring-success/50 rounded cursor-pointer hover:text-on-surface"
                    >
                      {allWorkspaces.map(ws => <option key={ws} value={ws} className="bg-surface text-on-surface">{ws}</option>)}
                    </select>
                  </div>
                  <div className="flex items-center gap-3">
                    <Hash size={13} className="text-on-surface/55 shrink-0" />
                    <span className="text-on-surface/60 w-16 shrink-0">ID</span>
                    <span className="text-on-surface/50 font-mono">{activeNote.id}</span>
                  </div>
                  <div className="flex items-center gap-3">
                    <Pin size={13} className="text-on-surface/55 shrink-0" />
                    <span className="text-on-surface/60 w-16 shrink-0">Pinned</span>
                    <span className="text-on-surface/70">{activeNote.pinned ? 'Yes' : 'No'}</span>
                  </div>
                </div>
              </div>

              <div className="h-px bg-on-surface/5" />

              {/* Stats Section */}
              <div className="space-y-3">
                <h4 className="text-on-surface/60 uppercase tracking-widest text-[10px] font-semibold">Statistics</h4>
                <div className="grid grid-cols-2 gap-3">
                  <div className="bg-on-surface/[0.03] rounded-lg p-3 text-center">
                    <div className="text-lg font-bold text-on-surface/80">{wordCount}</div>
                    <div className="text-[10px] text-on-surface/55">Words</div>
                  </div>
                  <div className="bg-on-surface/[0.03] rounded-lg p-3 text-center">
                    <div className="text-lg font-bold text-on-surface/80">{readingTime}</div>
                    <div className="text-[10px] text-on-surface/55">Min read</div>
                  </div>
                  <div className="bg-on-surface/[0.03] rounded-lg p-3 text-center">
                    <div className="text-lg font-bold text-on-surface/80">{editText.split('\n').filter(Boolean).length}</div>
                    <div className="text-[10px] text-on-surface/55">Lines</div>
                  </div>
                  <div className="bg-on-surface/[0.03] rounded-lg p-3 text-center">
                    <div className="text-lg font-bold text-on-surface/80">{editText.length}</div>
                    <div className="text-[10px] text-on-surface/55">Characters</div>
                  </div>
                </div>
              </div>

              <div className="h-px bg-on-surface/5" />

              {/* Outline Section */}
              <div className="space-y-3">
                <h4 className="text-on-surface/60 uppercase tracking-widest text-[10px] font-semibold flex items-center gap-2">
                  <AlignLeft size={12} /> Outline
                </h4>
                <div className="space-y-1">
                  {editText.split('\n').filter(l => l.startsWith('#')).length > 0 ? (
                    editText.split('\n').filter(l => l.startsWith('#')).map((heading, i) => {
                      const level = heading.match(/^#+/)?.[0].length || 1;
                      const text = heading.replace(/^#+\s*/, '');
                      return (
                        <div key={i} className="text-on-surface/50 hover:text-on-surface/80 cursor-pointer transition-colors py-0.5 truncate" style={{ paddingLeft: `${(level - 1) * 12}px` }}>
                          {text}
                        </div>
                      );
                    })
                  ) : (
                    <p className="text-on-surface/48 italic">No headings found</p>
                  )}
                </div>
              </div>

              <div className="h-px bg-on-surface/5" />

              {/* Quick Actions */}
              <div className="space-y-3">
                <h4 className="text-on-surface/60 uppercase tracking-widest text-[10px] font-semibold">Quick Actions</h4>
                <div className="space-y-1">
                  <button onClick={() => setShowAskAI(true)} className="w-full text-left px-3 py-2 rounded hover:bg-on-surface/5 text-on-surface/50 hover:text-on-surface/80 transition-colors flex items-center gap-2">
                    <Sparkles size={13} /> Ask AI about this note
                  </button>
                  <button onClick={onExport} className="w-full text-left px-3 py-2 rounded hover:bg-on-surface/5 text-on-surface/50 hover:text-on-surface/80 transition-colors flex items-center gap-2">
                    <FileText size={13} /> Export as Markdown
                  </button>
                  <button onClick={deleteNote} className="w-full text-left px-3 py-2 rounded hover:bg-error/10 text-on-surface/50 hover:text-error transition-colors flex items-center gap-2">
                    <Trash2 size={13} /> Delete page
                  </button>
                </div>
              </div>

            </div>
          </aside>
        )}

      </div>
    </div>
  );
};
