import { useEffect, useState, useRef, useCallback } from 'react';
import ForceGraph2D, { ForceGraphMethods } from 'react-force-graph-2d';
import { Loader2 } from 'lucide-react';

interface GraphData {
  nodes: { id: string | number, name: string, group: number, val: number, type: string }[];
  links: { source: string | number, target: string | number }[];
}

export const GraphView = ({ onNodeClick }: { onNodeClick: (noteId: number) => void }) => {
  const [data, setData] = useState<GraphData | null>(null);
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 });
  const containerRef = useRef<HTMLDivElement>(null);
  const fgRef = useRef<ForceGraphMethods>();

  const fetchGraph = useCallback(() => {
    fetch('http://localhost:8000/api/graph')
      .then(r => r.json())
      .then(d => setData(d))
      .catch(e => console.error("Failed to load graph", e));
  }, []);

  useEffect(() => {
    fetchGraph();
    // Listen for note changes and refresh graph
    const handler = () => fetchGraph();
    window.addEventListener('primnox:notes-changed', handler);
    return () => window.removeEventListener('primnox:notes-changed', handler);
  }, [fetchGraph]);

  useEffect(() => {
    if (containerRef.current) {
      setDimensions({
        width: containerRef.current.clientWidth,
        height: containerRef.current.clientHeight
      });
    }
    const handleResize = () => {
      if (containerRef.current) {
        setDimensions({
          width: containerRef.current.clientWidth,
          height: containerRef.current.clientHeight
        });
      }
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  const handleNodeClick = useCallback((node: any) => {
    if (node.type === 'note' && typeof node.id === 'number') {
      onNodeClick(node.id);
    } else {
      // Center on workspace node
      if (fgRef.current) {
        fgRef.current.centerAt(node.x, node.y, 1000);
        fgRef.current.zoom(2, 2000);
      }
    }
  }, [onNodeClick]);

  if (!data) return <div className="flex-1 flex items-center justify-center text-white/40 h-full"><Loader2 className="animate-spin" /></div>;

  return (
    <div ref={containerRef} className="flex-1 h-full w-full bg-black relative">
      <ForceGraph2D
        ref={fgRef as any}
        width={dimensions.width}
        height={dimensions.height}
        graphData={data}
        nodeLabel="name"
        nodeColor={(node: any) => node.type === 'workspace' ? '#10b981' : '#a855f7'}
        nodeRelSize={6}
        linkColor={() => 'rgba(255,255,255,0.1)'}
        onNodeClick={handleNodeClick}
        backgroundColor="#000000"
      />
    </div>
  );
};
