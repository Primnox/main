import { useState } from 'react';
import { Search, Globe, Library, ArrowRight, Loader2, BookOpen } from 'lucide-react';


export const ResearchView = () => {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<any>(null);

  const handleSearch = async () => {
    if (!query.trim()) return;
    setLoading(true);
    // TODO: Wire to actual Primnox research endpoint
    setTimeout(() => {
      setResults({
        summary: "Primnox is currently aggregating information from the web. Deep research mode activates multi-agent internet browsing to compile comprehensive answers.",
        sources: [
          { title: "Internet Archive", url: "https://archive.org" },
          { title: "Wikipedia: Deep Learning", url: "https://wikipedia.org/wiki/Deep_learning" },
          { title: "ArXiv Preprints", url: "https://arxiv.org" }
        ]
      });
      setLoading(false);
    }, 2000);
  };

  return (
    <div className="h-full w-full flex flex-col bg-black text-white relative overflow-hidden">
      {/* Dynamic Background */}
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-indigo-900/20 via-black to-black opacity-60 z-0 pointer-events-none" />
      
      <div className="flex-1 flex flex-col items-center justify-center p-8 z-10 w-full max-w-4xl mx-auto">
        
        {/* Header */}
        <div className="text-center mb-12 animate-in fade-in slide-in-from-bottom-4 duration-1000">
          <div className="inline-flex items-center justify-center p-3 bg-indigo-500/10 rounded-full mb-6 ring-1 ring-indigo-500/30">
            <Globe className="text-indigo-400" size={32} />
          </div>
          <h1 className="text-4xl md:text-5xl font-bold tracking-tighter mb-4">Deep Research</h1>
          <p className="text-white/40 text-sm md:text-base font-light max-w-lg mx-auto">
            Deploy autonomous agents to crawl the web, synthesize documentation, and generate comprehensive research briefs.
          </p>
        </div>

        {/* Search Bar */}
        <div className="w-full relative group animate-in fade-in slide-in-from-bottom-8 duration-1000 delay-150">
          <div className="absolute -inset-1 bg-gradient-to-r from-indigo-500 to-purple-500 rounded-2xl blur opacity-20 group-hover:opacity-40 transition duration-1000 group-hover:duration-200" />
          <div className="relative bg-zinc-950 border border-white/10 rounded-2xl flex items-center p-2 shadow-2xl">
            <Search className="text-white/30 ml-4 shrink-0" size={20} />
            <input 
              type="text" 
              value={query}
              onChange={e => setQuery(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSearch()}
              placeholder="What do you want to research today?"
              className="w-full bg-transparent border-none outline-none text-white px-4 py-4 text-lg placeholder:text-white/20"
            />
            <button 
              onClick={handleSearch}
              disabled={!query.trim() || loading}
              className="bg-indigo-500 hover:bg-indigo-600 disabled:bg-white/5 disabled:text-white/30 text-white rounded-xl px-6 py-4 font-bold transition-all flex items-center gap-2"
            >
              {loading ? <Loader2 size={18} className="animate-spin" /> : <ArrowRight size={18} />}
            </button>
          </div>
        </div>

        {/* Categories (Placeholder) */}
        {!results && !loading && (
          <div className="flex gap-4 mt-12 animate-in fade-in duration-1000 delay-300">
            {['Academic Papers', 'News & Current Events', 'Technical Documentation'].map(cat => (
              <button key={cat} className="px-4 py-2 rounded-full border border-white/5 bg-white/5 text-white/40 text-xs font-mono hover:text-white hover:bg-white/10 transition-colors">
                {cat}
              </button>
            ))}
          </div>
        )}

        {/* Results View */}
        {results && (
          <div className="w-full mt-12 space-y-6 animate-in fade-in slide-in-from-bottom-8 duration-500 text-left">
            <div className="p-6 rounded-2xl bg-white/5 border border-white/10">
              <h3 className="text-sm font-bold text-indigo-400 uppercase tracking-widest mb-4 flex items-center gap-2">
                <Library size={16} /> Research Synthesis
              </h3>
              <p className="text-white/80 leading-relaxed">
                {results.summary}
              </p>
            </div>
            
            <div className="space-y-3">
              <h4 className="text-xs font-mono text-white/40 uppercase tracking-wider pl-2">Cited Sources</h4>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {results.sources.map((src: any, i: number) => (
                  <a key={i} href={src.url} target="_blank" rel="noreferrer" className="p-4 rounded-xl border border-white/5 bg-white/5 hover:bg-white/10 transition-colors flex items-center gap-3">
                    <BookOpen size={16} className="text-white/30" />
                    <span className="text-sm text-white/70 truncate">{src.title}</span>
                  </a>
                ))}
              </div>
            </div>
          </div>
        )}

      </div>
    </div>
  );
};
