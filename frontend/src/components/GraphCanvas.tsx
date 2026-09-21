import React, { useRef, useCallback } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import { useMemexStore } from '../store/useMemexStore';
import { GraphNode, NodeType } from '../types';
import { Search, Filter, ZoomIn, ZoomOut, Maximize2 } from 'lucide-react';

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
    if (traversingNodeIds.includes(node.id)) return '#fbbf24'; // Glowing Gold for active intake traversal
    switch (node.node_type) {
      case 'external_source':
        return '#38bdf8'; // Blue
      case 'human_insight':
        return '#fbbf24'; // Yellow
      case 'agent_hypothesis':
        return '#c084fc'; // Purple
      case 'concept_phrase':
        return '#2dd4bf'; // Cyan
      case 'falsified_path':
        return '#f87171'; // Red
      default:
        return '#94a3b8';
    }
  };

  // Node shape canvas rendering with custom typography
  const drawNode = useCallback(
    (node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const label = node.title || '';
      const fontSize = 11 / globalScale;
      const isSelected = node.id === selectedNodeId;
      const isHovered = node.id === hoveredNodeId;
      const isTraversing = traversingNodeIds.includes(node.id);

      const radius = isSelected ? 10 : isHovered ? 8.5 : 6.5;

      // Outer Glow Halo for selection/traversal
      if (isSelected || isHovered || isTraversing) {
        ctx.beginPath();
        ctx.arc(node.x, node.y, radius + (isTraversing ? 7 : 5), 0, 2 * Math.PI, false);
        ctx.fillStyle = isTraversing
          ? 'rgba(251, 191, 36, 0.4)'
          : isSelected
          ? 'rgba(56, 189, 248, 0.35)'
          : 'rgba(255, 255, 255, 0.2)';
        ctx.fill();
      }

      // Draw Main Node Shape
      ctx.beginPath();
      ctx.arc(node.x, node.y, radius, 0, 2 * Math.PI, false);
      ctx.fillStyle = getNodeColor(node as GraphNode);
      ctx.fill();

      // Border Ring
      ctx.lineWidth = isSelected ? 2.5 / globalScale : 1.2 / globalScale;
      ctx.strokeStyle = isSelected ? '#ffffff' : 'rgba(255, 255, 255, 0.2)';
      ctx.stroke();

      // Text Label
      if (globalScale > 1.1 || isSelected || isHovered) {
        ctx.font = `600 ${fontSize}px "Plus Jakarta Sans", sans-serif`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillStyle = isSelected ? '#ffffff' : '#cbd5e1';
        ctx.fillText(
          label.length > 26 ? `${label.slice(0, 23)}...` : label,
          node.x,
          node.y + radius + 11 / globalScale
        );
      }
    },
    [selectedNodeId, hoveredNodeId, traversingNodeIds]
  );

  return (
    <div className="flex-1 h-[calc(100vh-4rem)] relative bg-[#090d16] overflow-hidden select-none">
      {/* Top Floating Search & Filter Toolbar */}
      <div className="absolute top-4 left-4 right-4 z-20 flex items-center justify-between gap-3 pointer-events-none">
        {/* Search Bar */}
        <div className="flex items-center gap-2.5 bg-[#121824]/90 backdrop-blur-md border border-white/10 p-2 rounded-xl shadow-xl pointer-events-auto max-w-md w-full">
          <Search className="w-4 h-4 text-slate-400 ml-1" />
          <input
            type="text"
            placeholder="Search nodes, takeaways, or concepts..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="bg-transparent text-xs text-slate-200 focus:outline-none w-full placeholder-slate-500 font-medium"
          />
        </div>

        {/* Node Type Filter Chips */}
        <div className="flex items-center gap-1.5 bg-[#121824]/90 backdrop-blur-md border border-white/10 p-1.5 rounded-xl shadow-xl pointer-events-auto">
          <Filter className="w-3.5 h-3.5 text-slate-400 mx-1" />

          {[
            { id: 'all', label: 'All' },
            { id: 'external_source', label: 'Papers', color: 'text-sky-400' },
            { id: 'human_insight', label: 'Insights', color: 'text-amber-400' },
            { id: 'agent_hypothesis', label: 'Hypotheses', color: 'text-purple-400' },
            { id: 'concept_phrase', label: 'Concepts', color: 'text-teal-400' },
            { id: 'falsified_path', label: 'Falsified', color: 'text-red-400' },
          ].map((item) => (
            <button
              key={item.id}
              onClick={() => setSelectedNodeTypeFilter(item.id as NodeType | 'all')}
              className={`px-3 py-1 text-[11px] font-bold rounded-lg transition-all ${
                selectedNodeTypeFilter === item.id
                  ? 'bg-[#1e293b] text-slate-100 border border-white/20 shadow-sm'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-white/5'
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
          ctx.arc(node.x, node.y, 11, 0, 2 * Math.PI, false);
          ctx.fill();
        }}
        linkColor={(link: any) => {
          if (link.edge_type === 'REFUTES' || link.edge_type === 'CONTRASTS_WITH') return '#f87171';
          if (link.edge_type === 'CATEGORY_MEMBER') return 'rgba(148, 163, 184, 0.2)';
          return '#10b981'; // Green solid link
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
        backgroundColor="#090d16"
      />

      {/* Canvas Legend Bar */}
      <div className="absolute bottom-4 left-4 z-20 flex items-center gap-3 bg-[#121824]/90 backdrop-blur-md border border-white/10 px-3.5 py-2 rounded-xl shadow-xl text-[11px] font-medium">
        <div className="flex items-center gap-2">
          <span className="w-2.5 h-2.5 rounded-full bg-[#38bdf8] shadow-sm" />
          <span className="text-slate-300">Paper</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-2.5 h-2.5 rounded-full bg-[#fbbf24] shadow-sm" />
          <span className="text-slate-300">Human Insight</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-2.5 h-2.5 rounded-full bg-[#c084fc] shadow-sm" />
          <span className="text-slate-300">Hypothesis</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-2.5 h-2.5 rounded-full bg-[#2dd4bf] shadow-sm" />
          <span className="text-slate-300">Concept</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-2.5 h-2.5 rounded-full bg-[#f87171] shadow-sm" />
          <span className="text-slate-300">Falsified</span>
        </div>
      </div>

      {/* Floating Zoom & Recenter Tools */}
      <div className="absolute bottom-4 right-4 z-20 flex items-center gap-1 bg-[#121824]/90 backdrop-blur-md border border-white/10 p-1.5 rounded-xl shadow-xl">
        <button
          onClick={() => fgRef.current && fgRef.current.zoom(fgRef.current.zoom() * 1.3, 300)}
          className="p-1.5 text-slate-400 hover:text-slate-100 hover:bg-white/10 rounded-lg transition-colors"
          title="Zoom In"
        >
          <ZoomIn className="w-4 h-4" />
        </button>
        <button
          onClick={() => fgRef.current && fgRef.current.zoom(fgRef.current.zoom() / 1.3, 300)}
          className="p-1.5 text-slate-400 hover:text-slate-100 hover:bg-white/10 rounded-lg transition-colors"
          title="Zoom Out"
        >
          <ZoomOut className="w-4 h-4" />
        </button>
        <button
          onClick={() => fgRef.current && fgRef.current.zoomToFit(400, 50)}
          className="p-1.5 text-slate-400 hover:text-slate-100 hover:bg-white/10 rounded-lg transition-colors"
          title="Recenter Graph"
        >
          <Maximize2 className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
};
