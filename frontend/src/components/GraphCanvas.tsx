import React, { useRef, useCallback } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import { useMemexStore } from '../store/useMemexStore';
import { GraphNode, NodeType } from '../types';
import { Search, Filter, RefreshCw, ZoomIn, ZoomOut, Maximize2 } from 'lucide-react';

export const GraphCanvas: React.FC = () => {
  const {
    nodes,
    edges,
    selectedNodeId,
    setSelectedNodeId,
    hoveredNodeId,
    setHoveredNodeId,
    searchQuery,
    setSearchQuery,
    selectedNodeTypeFilter,
    setSelectedNodeTypeFilter,
    traversingNodeIds,
  } = useMemexStore();

  const fgRef = useRef<any>(null);

  // Filter nodes based on search and type filter
  const filteredNodes = nodes.filter((n) => {
    const matchesSearch =
      !searchQuery ||
      n.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      n.takeaway_2line.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesType = selectedNodeTypeFilter === 'all' || n.node_type === selectedNodeTypeFilter;
    return matchesSearch && matchesType;
  });

  const filteredNodeIds = new Set(filteredNodes.map((n) => n.id));

  // Format graph data for react-force-graph
  const graphData = {
    nodes: filteredNodes,
    links: edges
      .filter((e) => {
        const sourceId = typeof e.source === 'object' ? (e.source as any).id : e.source;
        const targetId = typeof e.target === 'object' ? (e.target as any).id : e.target;
        return filteredNodeIds.has(sourceId) && filteredNodeIds.has(targetId);
      })
      .map((e) => ({
        ...e,
        source: typeof e.source === 'object' ? (e.source as any).id : e.source,
        target: typeof e.target === 'object' ? (e.target as any).id : e.target,
      })),
  };

  // Node Color taxonomy mapping
  const getNodeColor = (node: GraphNode) => {
    if (traversingNodeIds.includes(node.id)) return '#f59e0b'; // Glowing Gold for active intake traversal
    switch (node.node_type) {
      case 'external_source':
        return '#58a6ff'; // Blue
      case 'human_insight':
        return '#d29922'; // Yellow
      case 'agent_hypothesis':
        return '#a371f7'; // Purple
      case 'concept_phrase':
        return '#39c5cf'; // Cyan
      case 'falsified_path':
        return '#f85149'; // Red
      default:
        return '#8b949e';
    }
  };

  // Node shape canvas rendering
  const drawNode = useCallback(
    (node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const label = node.title || '';
      const fontSize = 12 / globalScale;
      const isSelected = node.id === selectedNodeId;
      const isHovered = node.id === hoveredNodeId;
      const isTraversing = traversingNodeIds.includes(node.id);

      const radius = isSelected ? 9 : isHovered ? 8 : 6;

      // Outer Glow Halo for selection/traversal
      if (isSelected || isHovered || isTraversing) {
        ctx.beginPath();
        ctx.arc(node.x, node.y, radius + (isTraversing ? 6 : 4), 0, 2 * Math.PI, false);
        ctx.fillStyle = isTraversing ? 'rgba(245, 158, 11, 0.4)' : isSelected ? 'rgba(56, 189, 248, 0.35)' : 'rgba(255, 255, 255, 0.2)';
        ctx.fill();
      }

      // Draw Main Node Shape
      ctx.beginPath();
      ctx.arc(node.x, node.y, radius, 0, 2 * Math.PI, false);
      ctx.fillStyle = getNodeColor(node as GraphNode);
      ctx.fill();

      // Border Ring
      ctx.lineWidth = isSelected ? 2 / globalScale : 1 / globalScale;
      ctx.strokeStyle = isSelected ? '#ffffff' : '#30363d';
      ctx.stroke();

      // Text Label
      if (globalScale > 1.2 || isSelected || isHovered) {
        ctx.font = `${fontSize}px Inter, sans-serif`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillStyle = isSelected ? '#ffffff' : '#e6edf3';
        ctx.fillText(label.length > 25 ? `${label.slice(0, 22)}...` : label, node.x, node.y + radius + 10 / globalScale);
      }
    },
    [selectedNodeId, hoveredNodeId, traversingNodeIds]
  );

  return (
    <div className="flex-1 h-[calc(100vh-3.5rem)] relative bg-[#0d1117] overflow-hidden select-none">
      {/* Top Floating Search & Filter Toolbar */}
      <div className="absolute top-4 left-4 right-4 z-20 flex items-center justify-between gap-3 pointer-events-none">
        {/* Search Bar */}
        <div className="flex items-center gap-2 bg-[#161b22]/90 backdrop-blur border border-[#30363d] p-1.5 rounded-lg shadow-lg pointer-events-auto max-w-sm w-full">
          <Search className="w-4 h-4 text-slate-400 ml-1" />
          <input
            type="text"
            placeholder="Search nodes, takeaways, or concepts..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="bg-transparent text-xs text-slate-200 focus:outline-none w-full placeholder-slate-500"
          />
        </div>

        {/* Node Type Filter Chips */}
        <div className="flex items-center gap-1.5 bg-[#161b22]/90 backdrop-blur border border-[#30363d] p-1.5 rounded-lg shadow-lg pointer-events-auto">
          <Filter className="w-3.5 h-3.5 text-slate-400 mx-1" />

          {[
            { id: 'all', label: 'All' },
            { id: 'external_source', label: 'Papers', color: 'text-blue-400' },
            { id: 'human_insight', label: 'Insights', color: 'text-yellow-400' },
            { id: 'agent_hypothesis', label: 'Hypotheses', color: 'text-purple-400' },
            { id: 'concept_phrase', label: 'Concepts', color: 'text-cyan-400' },
            { id: 'falsified_path', label: 'Falsified', color: 'text-red-400' },
          ].map((item) => (
            <button
              key={item.id}
              onClick={() => setSelectedNodeTypeFilter(item.id as NodeType | 'all')}
              className={`px-2.5 py-1 text-[11px] font-medium rounded-md transition-all ${
                selectedNodeTypeFilter === item.id
                  ? 'bg-[#21262d] text-slate-100 border border-[#30363d] font-semibold'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <span className={item.color || ''}>{item.label}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Force Graph WebGL Canvas */}
      <ForceGraph2D
        ref={fgRef}
        graphData={graphData}
        nodeCanvasObject={drawNode}
        nodePointerAreaPaint={(node: any, color, ctx) => {
          ctx.fillStyle = color;
          ctx.beginPath();
          ctx.arc(node.x, node.y, 10, 0, 2 * Math.PI, false);
          ctx.fill();
        }}
        linkColor={(link: any) => {
          if (link.edge_type === 'REFUTES' || link.edge_type === 'CONTRASTS_WITH') return '#f85149';
          if (link.edge_type === 'CATEGORY_MEMBER') return '#30363d';
          return '#3fb950'; // Green solid link
        }}
        linkLineDash={(link: any) => (link.edge_type === 'CATEGORY_MEMBER' ? [3, 3] : null)}
        linkDirectionalArrowLength={4}
        linkDirectionalArrowRelPos={0.9}
        linkWidth={(link: any) => (link.edge_type === 'BUILDS_UPON' ? 2 : 1)}
        onNodeClick={(node: any) => {
          setSelectedNodeId(node.id);
          if (fgRef.current) {
            fgRef.current.centerAt(node.x, node.y, 400);
          }
        }}
        onNodeHover={(node: any) => setHoveredNodeId(node ? node.id : null)}
        backgroundColor="#0d1117"
      />

      {/* Canvas Legend & Controls Bar */}
      <div className="absolute bottom-4 left-4 z-20 flex items-center gap-3 bg-[#161b22]/90 backdrop-blur border border-[#30363d] px-3 py-2 rounded-lg shadow-lg text-[11px]">
        <div className="flex items-center gap-2">
          <span className="w-2.5 h-2.5 rounded-full bg-[#58a6ff]" />
          <span className="text-slate-300">Paper</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-2.5 h-2.5 rounded-full bg-[#d29922]" />
          <span className="text-slate-300">Human Insight</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-2.5 h-2.5 rounded-full bg-[#a371f7]" />
          <span className="text-slate-300">Hypothesis</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-2.5 h-2.5 rounded-full bg-[#39c5cf]" />
          <span className="text-slate-300">Concept</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-2.5 h-2.5 rounded-full bg-[#f85149]" />
          <span className="text-slate-300">Falsified</span>
        </div>
      </div>

      {/* Floating Zoom & Recenter Tools */}
      <div className="absolute bottom-4 right-4 z-20 flex items-center gap-1 bg-[#161b22]/90 backdrop-blur border border-[#30363d] p-1 rounded-lg shadow-lg">
        <button
          onClick={() => fgRef.current && fgRef.current.zoom(fgRef.current.zoom() * 1.3, 300)}
          className="p-1.5 text-slate-400 hover:text-slate-200 hover:bg-[#21262d] rounded"
          title="Zoom In"
        >
          <ZoomIn className="w-4 h-4" />
        </button>
        <button
          onClick={() => fgRef.current && fgRef.current.zoom(fgRef.current.zoom() / 1.3, 300)}
          className="p-1.5 text-slate-400 hover:text-slate-200 hover:bg-[#21262d] rounded"
          title="Zoom Out"
        >
          <ZoomOut className="w-4 h-4" />
        </button>
        <button
          onClick={() => fgRef.current && fgRef.current.zoomToFit(400, 50)}
          className="p-1.5 text-slate-400 hover:text-slate-200 hover:bg-[#21262d] rounded"
          title="Recenter Graph"
        >
          <Maximize2 className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
};
