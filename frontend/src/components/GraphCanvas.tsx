import React, { useRef, useCallback, useMemo, useEffect } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import { useMemexStore } from '../store/useMemexStore';
import { NodeType, isRootNode, getRootSubType, isConceptNode, isImmutableConcept } from '../types';
import { createGlowTextureCache, drawMeMexNode } from '../utils/graphRenderers';
import { prewarmForceSimulation } from '../utils/physicsPipeline';
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
    thinkingState,
  } = useMemexStore();

  const traversingNodeIds = thinkingState.visitedNodeIds || [];
  const fgRef = useRef<any>(null);

  // Initialize offscreen glow texture sprite cache
  const glowCache = useMemo(() => createGlowTextureCache(), []);

  // Filter nodes & links based on user query/filter
  const rawGraphData = useMemo(() => {
    const filteredNodes = nodes.filter((n) => {
      const matchesSearch =
        !searchQuery ||
        n.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
        (n.content && n.content.toLowerCase().includes(searchQuery.toLowerCase()));

      let matchesType = true;
      if (selectedNodeTypeFilter === 'all') {
        matchesType = true;
      } else if (selectedNodeTypeFilter === 'paper') {
        matchesType = isRootNode(n) && getRootSubType(n) === 'paper';
      } else if (selectedNodeTypeFilter === 'blog') {
        matchesType = isRootNode(n) && getRootSubType(n) === 'blog';
      } else if (selectedNodeTypeFilter === 'post') {
        matchesType = isRootNode(n) && getRootSubType(n) === 'post';
      } else if (selectedNodeTypeFilter === 'immutable_concept') {
        matchesType = isConceptNode(n) && isImmutableConcept(n);
      } else if (selectedNodeTypeFilter === 'mutable_concept') {
        matchesType = isConceptNode(n) && !isImmutableConcept(n);
      }

      return matchesSearch && matchesType;
    });

    const filteredNodeIds = new Set(filteredNodes.map((n) => n.id));

    return {
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
  }, [nodes, edges, searchQuery, selectedNodeTypeFilter]);

  // Headless physics pre-warming simulation to eliminate bouncing on initial mount
  const stabilizedGraphData = useMemo(() => {
    return prewarmForceSimulation(rawGraphData.nodes, rawGraphData.links, 180);
  }, [rawGraphData]);

  // Configure runtime force viscosity parameters
  useEffect(() => {
    if (!fgRef.current) return;
    const fg = fgRef.current;
    if (typeof fg.d3VelocityDecay === 'function') {
      fg.d3VelocityDecay(0.55);
    }
  }, []);

  // Custom high-performance node drawing callback
  const drawNode = useCallback(
    (node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const isSelected = node.id === selectedNodeId;
      const isHovered = node.id === hoveredNodeId;
      const isTraversed = traversingNodeIds.includes(node.id);

      drawMeMexNode(node, ctx, globalScale, glowCache, isSelected, isHovered, isTraversed);
    },
    [selectedNodeId, hoveredNodeId, traversingNodeIds, glowCache]
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

        {/* Node Type Filter Chips with Subtitle Note Below */}
        <div className="flex flex-col items-end gap-1 pointer-events-auto">
          <div className="flex items-center gap-1.5 bg-[#121824]/90 backdrop-blur-md border border-white/10 p-1.5 rounded-xl shadow-xl">
            <Filter className="w-3.5 h-3.5 text-slate-400 mx-1" />

            {[
              { id: 'all', label: 'All', dot: 'bg-slate-400', color: 'text-slate-300' },
              { id: 'paper', label: 'Papers', dot: 'bg-[#38bdf8]', color: 'text-sky-400' },
              { id: 'blog', label: 'Blogs', dot: 'bg-[#34d399]', color: 'text-emerald-400' },
              { id: 'post', label: 'Posts', dot: 'bg-[#c084fc]', color: 'text-purple-400' },
              { id: 'immutable_concept', label: 'Concepts (I)', dot: 'bg-[#fb7185]', color: 'text-rose-400', title: 'Immutable Concepts (direct source extractions)' },
              { id: 'mutable_concept', label: 'Concepts (M)', dot: 'bg-[#fbbf24]', color: 'text-amber-400', title: 'Mutable Concepts (cross-paper synthesized)' },
            ].map((item) => (
              <button
                key={item.id}
                onClick={() => setSelectedNodeTypeFilter(item.id as any)}
                title={item.title}
                className={`flex items-center gap-1.5 px-2.5 py-1 text-[11px] font-semibold rounded-lg transition-all ${
                  selectedNodeTypeFilter === item.id
                    ? 'bg-[#1e293b] text-slate-100 border border-white/20 shadow-sm'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-white/5'
                }`}
              >
                <span className={`w-2 h-2 rounded-full ${item.dot}`} />
                <span className={item.color || ''}>{item.label}</span>
              </button>
            ))}
          </div>
          <span className="text-[10px] text-slate-500 font-mono pr-2 select-none">
            I: Immutable • M: Mutable
          </span>
        </div>
      </div>

      {/* Force Graph Canvas */}
      <ForceGraph2D
        ref={fgRef}
        graphData={stabilizedGraphData}
        nodeCanvasObject={drawNode}
        cooldownTicks={120}
        d3AlphaDecay={0.04}
        d3VelocityDecay={0.55}
        linkCurvature={0.18}
        nodePointerAreaPaint={(node: any, color, ctx) => {
          ctx.fillStyle = color;
          ctx.beginPath();
          ctx.arc(node.x, node.y, 14, 0, 2 * Math.PI, false);
          ctx.fill();
        }}
        linkColor={(link: any) => {
          if (link.description?.includes('SUPERSEDES') || link.is_directional) return '#f59e0b';
          if (link.description?.includes('CONTRASTS')) return '#ef4444';
          return '#334155';
        }}
        linkLineDash={(link: any) => (link.description?.includes('CONTRASTS') ? [3, 2] : null)}
        linkDirectionalArrowLength={4}
        linkDirectionalArrowRelPos={0.95}
        onNodeDragEnd={(node: any) => {
          node.fx = node.x;
          node.fy = node.y;
        }}
        onNodeClick={(node: any) => {
          if (selectedNodeId === node.id) {
            setSelectedNodeId(null);
          } else {
            setSelectedNodeId(node.id);
          }
        }}
        onNodeHover={(node: any) => setHoveredNodeId(node ? node.id : null)}
        backgroundColor="#090d16"
      />

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
