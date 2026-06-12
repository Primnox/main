import { useEffect, useState, useRef, useCallback, useMemo } from 'react';
import ForceGraph2D, { ForceGraphMethods } from 'react-force-graph-2d';
import { Loader2, Search, X, ZoomIn, ZoomOut, RefreshCw, Focus } from 'lucide-react';

interface GraphNode {
  id: string | number;
  name: string;
  group: number;
  val: number;
  type: string;
  x?: number;
  y?: number;
}

interface GraphLink {
  source: string | number;
  target: string | number;
}

interface GraphData {
  nodes: GraphNode[];
  links: GraphLink[];
}

const TYPE_COLORS: Record<string, string> = {
  workspace: '#10b981',  // emerald — workspace/folder nodes
  note:      '#a855f7',  // purple  — note nodes
  tag:       '#f59e0b',  // amber   — tag nodes
  default:   '#6366f1',  // indigo  — fallback
};

const getNodeColor = (node: GraphNode, highlightNodes: Set<string | number>, hovered: string | number | null) => {
  const base = TYPE_COLORS[node.type] ?? TYPE_COLORS.default;
  if (hovered === null) return base;
  if (node.id === hovered) return '#ffffff';
  if (highlightNodes.has(node.id)) return base;
  return base + '33'; // dim non-neighbors
};

const getLinkColor = (link: GraphLink, highlightLinks: Set<string>, hovered: string | number | null) => {
  if (hovered === null) return 'rgba(255,255,255,0.08)';
  const key = `${(link.source as any).id ?? link.source}-${(link.target as any).id ?? link.target}`;
  if (highlightLinks.has(key)) return 'rgba(255,255,255,0.5)';
  return 'rgba(255,255,255,0.02)';
};

export const GraphView = ({ onNodeClick }: { onNodeClick: (noteId: number) => void }) => {
  const [data, setData] = useState<GraphData | null>(null);
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 });
  const [search, setSearch] = useState('');
  const [hovered, setHovered] = useState<string | number | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const fgRef = useRef<ForceGraphMethods>();

  // Neighbor maps for hover highlight
  const { neighborMap } = useMemo(() => {
    if (!data) return { neighborMap: new Map<string | number, Set<string | number>>() };
    const nm = new Map<string | number, Set<string | number>>();
    for (const link of data.links) {
      const s = (link.source as any).id ?? link.source;
      const t = (link.target as any).id ?? link.target;
      if (!nm.has(s)) nm.set(s, new Set());
      if (!nm.has(t)) nm.set(t, new Set());
      nm.get(s)!.add(t);
      nm.get(t)!.add(s);
    }
    return { neighborMap: nm };
  }, [data]);

  const highlightNodes = useMemo((): Set<string | number> => {
    if (hovered === null) return new Set();
    const neighbors = neighborMap.get(hovered) ?? new Set();
    return new Set([hovered, ...neighbors]);
  }, [hovered, neighborMap]);

  const highlightLinks = useMemo((): Set<string> => {
    if (hovered === null) return new Set();
    const result = new Set<string>();
    for (const link of data?.links ?? []) {
      const s = (link.source as any).id ?? link.source;
      const t = (link.target as any).id ?? link.target;
      if (s === hovered || t === hovered) {
        result.add(`${s}-${t}`);
        result.add(`${t}-${s}`);
      }
    }
    return result;
  }, [hovered, data]);

  // Reset hover state when graph data is replaced so stale node IDs don't dim the whole graph
  useEffect(() => { setHovered(null); }, [data]);

  const fetchGraph = useCallback(() => {
    fetch('http://localhost:8000/api/graph')
      .then(r => r.json())
      .then(d => setData(d))
      .catch(e => console.error("Failed to load graph", e));
  }, []);

  useEffect(() => {
    fetchGraph();
    const handler = () => fetchGraph();
    window.addEventListener('primnox:notes-changed', handler);
    return () => window.removeEventListener('primnox:notes-changed', handler);
  }, [fetchGraph]);

  useEffect(() => {
    const measure = () => {
      if (containerRef.current) {
        setDimensions({
          width: containerRef.current.clientWidth,
          height: containerRef.current.clientHeight,
        });
      }
    };
    measure();
    window.addEventListener('resize', measure);
    return () => window.removeEventListener('resize', measure);
  }, []);

  const handleNodeClick = useCallback((node: any) => {
    if (node.type === 'note' && typeof node.id === 'number') {
      onNodeClick(node.id);
    } else if (fgRef.current) {
      fgRef.current.centerAt(node.x, node.y, 1000);
      fgRef.current.zoom(2, 2000);
    }
  }, [onNodeClick]);

  // Search: zoom to matching node
  const handleSearch = useCallback((q: string) => {
    setSearch(q);
    if (!q.trim() || !data || !fgRef.current) return;
    const match = data.nodes.find(n => n.name.toLowerCase().includes(q.toLowerCase()));
    if (match && match.x !== undefined && match.y !== undefined) {
      fgRef.current.centerAt(match.x, match.y, 800);
      fgRef.current.zoom(3, 800);
    }
  }, [data]);

  const zoomIn  = () => fgRef.current?.zoom(((fgRef.current as any)?.__zoomTransform?.k ?? 1) * 1.4 + 0.1, 300);
  const zoomOut = () => fgRef.current?.zoom(((fgRef.current as any)?.__zoomTransform?.k ?? 1) * 0.7, 300);
  const fitAll  = () => fgRef.current?.zoomToFit(500, 60);

  if (!data) {
    return (
      <div className="flex-1 flex items-center justify-center text-white/40 h-full">
        <Loader2 className="animate-spin" />
      </div>
    );
  }

  const nodeCount = data.nodes.length;
  const linkCount = data.links.length;

  return (
    <div ref={containerRef} className="flex-1 h-full w-full bg-black relative overflow-hidden">
      <ForceGraph2D
        ref={fgRef as any}
        width={dimensions.width}
        height={dimensions.height}
        graphData={data}
        nodeLabel="name"
        nodeRelSize={5}
        nodeVal={(node: any) => {
          const base = node.val ?? 1;
          const neighbors = neighborMap.get(node.id)?.size ?? 0;
          return base + neighbors * 0.5;
        }}
        nodeColor={(node: any) => getNodeColor(node, highlightNodes, hovered)}
        linkColor={(link: any) => getLinkColor(link, highlightLinks, hovered)}
        linkWidth={(link: any) => {
          const s = (link.source as any).id ?? link.source;
          const t = (link.target as any).id ?? link.target;
          if (hovered !== null && (s === hovered || t === hovered)) return 2;
          return 1;
        }}
        onNodeClick={handleNodeClick}
        onNodeHover={(node: any) => setHovered(node ? node.id : null)}
        backgroundColor="#000000"
        nodeCanvasObjectMode={() => 'after'}
        nodeCanvasObject={(node: any, ctx, globalScale) => {
          if (globalScale < 1.2) return;
          const label = node.name as string;
          const fontSize = Math.min(14, 12 / globalScale);
          ctx.font = `${fontSize}px monospace`;
          ctx.textAlign = 'center';
          ctx.textBaseline = 'top';
          ctx.fillStyle = node.id === hovered ? 'rgba(255,255,255,0.95)' : 'rgba(255,255,255,0.55)';
          ctx.fillText(label.length > 20 ? label.slice(0, 18) + '…' : label, node.x, node.y + 8);
        }}
        cooldownTicks={100}
      />

      {/* Overlay controls */}
      <div className="absolute top-4 left-4 right-4 flex items-center gap-3 pointer-events-none">
        {/* Search */}
        <div className="flex items-center gap-2 bg-zinc-950/80 border border-white/10 rounded-xl px-4 py-2.5 pointer-events-auto backdrop-blur-xl w-64">
          <Search size={14} className="text-white/30 shrink-0" />
          <input
            value={search}
            onChange={e => handleSearch(e.target.value)}
            placeholder="Search nodes…"
            className="flex-1 bg-transparent text-white/80 text-xs font-mono outline-none placeholder-white/20"
          />
          {search && (
            <button onClick={() => { setSearch(''); fitAll(); }} className="text-white/30 hover:text-white transition-colors">
              <X size={12} />
            </button>
          )}
        </div>

        {/* Stats */}
        <div className="bg-zinc-950/70 border border-white/5 rounded-xl px-4 py-2.5 pointer-events-none backdrop-blur-xl">
          <span className="text-[10px] font-mono text-white/30 uppercase tracking-widest">
            {nodeCount} nodes · {linkCount} links
          </span>
        </div>

        <div className="ml-auto flex items-center gap-2 pointer-events-auto">
          {/* Legend */}
          <div className="hidden sm:flex items-center gap-3 bg-zinc-950/70 border border-white/5 rounded-xl px-4 py-2.5 backdrop-blur-xl">
            {Object.entries(TYPE_COLORS).filter(([k]) => k !== 'default').map(([type, color]) => (
              <span key={type} className="flex items-center gap-1.5 text-[10px] font-mono text-white/40 capitalize">
                <span className="w-2 h-2 rounded-full inline-block" style={{ background: color }} />
                {type}
              </span>
            ))}
          </div>

          {/* Zoom controls */}
          <div className="flex items-center gap-1 bg-zinc-950/80 border border-white/10 rounded-xl p-1.5 backdrop-blur-xl">
            <button onClick={zoomIn}  className="p-1.5 text-white/40 hover:text-white transition-colors rounded-lg hover:bg-white/5"><ZoomIn  size={14} /></button>
            <button onClick={zoomOut} className="p-1.5 text-white/40 hover:text-white transition-colors rounded-lg hover:bg-white/5"><ZoomOut size={14} /></button>
            <button onClick={fitAll}  className="p-1.5 text-white/40 hover:text-white transition-colors rounded-lg hover:bg-white/5"><Focus   size={14} /></button>
            <button onClick={fetchGraph} className="p-1.5 text-white/40 hover:text-white transition-colors rounded-lg hover:bg-white/5"><RefreshCw size={14} /></button>
          </div>
        </div>
      </div>

      {/* Hover tooltip */}
      {hovered !== null && (() => {
        const node = data.nodes.find(n => n.id === hovered);
        if (!node) return null;
        const neighbors = neighborMap.get(hovered)?.size ?? 0;
        return (
          <div className="absolute bottom-6 left-1/2 -translate-x-1/2 bg-zinc-950/90 border border-white/10 rounded-xl px-5 py-3 backdrop-blur-xl pointer-events-none">
            <div className="text-sm font-medium text-white mb-1">{node.name}</div>
            <div className="flex items-center gap-3 text-[10px] font-mono text-white/30">
              <span className="flex items-center gap-1">
                <span className="w-2 h-2 rounded-full" style={{ background: TYPE_COLORS[node.type] ?? TYPE_COLORS.default }} />
                {node.type}
              </span>
              <span>{neighbors} connection{neighbors !== 1 ? 's' : ''}</span>
            </div>
          </div>
        );
      })()}
    </div>
  );
};
