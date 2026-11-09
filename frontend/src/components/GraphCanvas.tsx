import React, { useRef, useCallback, useMemo, useEffect } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import { useMemexStore } from '../store/useMemexStore';
import { isRootNode, getRootSubType, isConceptNode, isImmutableConcept } from '../types';
import { createGlowTextureCache, drawMeMexNode } from '../utils/graphRenderers';
import { prewarmForceSimulation } from '../utils/physicsPipeline';
import { isDiscLikeLayout } from '../utils/radialLayout';
import { fitGraphView } from '../utils/graphViewFit';
import { NODE_POINTER_RADIUS } from '../utils/graphNodeMetrics';
import {
  chargeStrengthForNode,
  classifyLayoutLink,
  computeGraphStructureKey,
  getForceParams,
  layoutLinkDistance,
  layoutLinkStrength,
} from '../utils/forceLayoutConfig';
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

  const persistentPositionsRef = useRef<Map<string, { x: number; y: number; fx: number; fy: number }>>(
    new Map()
  );
  const structureKeyRef = useRef<string>('');
  const autoFitKeyRef = useRef<string>('');
  const stabilizedGraphDataRef = useRef<{ nodes: any[]; links: any[] }>({
    nodes: [],
    links: [],
  });

  const glowCache = useMemo(() => createGlowTextureCache(), []);

  const rawGraphData = useMemo(() => {
    const filteredNodes = nodes.filter((n) => {
      const matchesSearch =
        !searchQuery ||
        n.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
        (n.description && n.description.toLowerCase().includes(searchQuery.toLowerCase())) ||
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

  const structureKey = useMemo(
    () =>
      computeGraphStructureKey(
        rawGraphData.nodes.map((n) => ({ id: n.id })),
        rawGraphData.links.map((e) => ({
          id: e.id,
          source: e.source as string,
          target: e.target as string,
        }))
      ),
    [rawGraphData.nodes, rawGraphData.links]
  );

  const stabilizedGraphData = useMemo(() => {
    if (
      structureKey === structureKeyRef.current &&
      stabilizedGraphDataRef.current.nodes.length > 0
    ) {
      return stabilizedGraphDataRef.current;
    }

    const pinned = persistentPositionsRef.current;
    let spreadReset = false;
    if (pinned.size >= 8) {
      const xs: number[] = [];
      const ys: number[] = [];
      pinned.forEach((p) => {
        xs.push(p.x);
        ys.push(p.y);
      });
      const span = Math.max(...xs) - Math.min(...xs) + Math.max(...ys) - Math.min(...ys);
      if (span < 90) spreadReset = true;
      if (!spreadReset && isDiscLikeLayout(pinned.values())) spreadReset = true;
    }
    if (spreadReset) {
      pinned.clear();
    }

    const existingIds = new Set(pinned.keys());
    const newNodeIds = new Set(
      rawGraphData.nodes.filter((n) => !existingIds.has(n.id)).map((n) => n.id)
    );
    const incremental = newNodeIds.size > 0 && existingIds.size > 0 && !spreadReset;

    const res = prewarmForceSimulation(
      rawGraphData.nodes,
      rawGraphData.links,
      incremental ? 90 : 240,
      persistentPositionsRef.current,
      incremental ? { onlyLayoutNewNodeIds: newNodeIds } : undefined
    );

    res.nodes.forEach((n) => {
      persistentPositionsRef.current.set(n.id, {
        x: n.x,
        y: n.y,
        fx: n.fx ?? n.x,
        fy: n.fy ?? n.y,
      });
    });

    structureKeyRef.current = structureKey;
    stabilizedGraphDataRef.current = res;
    return res;
  }, [structureKey, rawGraphData]);

  const forceParams = useMemo(
    () => getForceParams(stabilizedGraphData.nodes.length),
    [stabilizedGraphData.nodes.length]
  );

  useEffect(() => {
    if (!fgRef.current || !stabilizedGraphData.nodes.length) return;
    if (autoFitKeyRef.current === structureKey) return;
    const raf = requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        fitGraphView(fgRef.current, stabilizedGraphData.nodes, {
          durationMs: 0,
          allowZoomIn: true,
        });
        autoFitKeyRef.current = structureKey;
      });
    });
    return () => cancelAnimationFrame(raf);
  }, [structureKey, stabilizedGraphData.nodes]);

  useEffect(() => {
    if (!fgRef.current) return;
    const fg = fgRef.current;
    if (typeof fg.d3VelocityDecay === 'function') {
      fg.d3VelocityDecay(forceParams.velocityDecay);
    }
    if (typeof fg.d3Force === 'function') {
      const linkForce = fg.d3Force('link');
      if (linkForce && typeof linkForce.distance === 'function') {
        linkForce
          .distance((l: any) => {
            const kind = classifyLayoutLink(l.source, l.target);
            return layoutLinkDistance(kind, forceParams);
          })
          .strength((l: any) => {
            const kind = classifyLayoutLink(l.source, l.target);
            return layoutLinkStrength(kind);
          });
      }
      const chargeForce = fg.d3Force('charge');
      if (chargeForce && typeof chargeForce.strength === 'function') {
        chargeForce.strength((d: any) => chargeStrengthForNode(d, forceParams));
      }
      if (typeof fg.d3AlphaMin === 'function') {
        fg.d3AlphaMin(0);
      }
    }
  }, [forceParams]);

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
      <div className="absolute top-4 left-4 right-4 z-20 flex items-center justify-between gap-3 pointer-events-none">
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
            I: Immutable • M: Mutable • {nodes.length} Nodes
          </span>
        </div>
      </div>

      <ForceGraph2D
        ref={fgRef}
        graphData={stabilizedGraphData}
        nodeCanvasObject={drawNode}
        cooldownTicks={0}
        d3AlphaDecay={0.04}
        d3VelocityDecay={forceParams.velocityDecay}
        linkCurvature={0.18}
        nodePointerAreaPaint={(node: any, color, ctx) => {
          ctx.fillStyle = color;
          ctx.beginPath();
          ctx.arc(node.x, node.y, NODE_POINTER_RADIUS, 0, 2 * Math.PI, false);
          ctx.fill();
        }}
        linkColor={() => '#334155'}
        linkLineDash={null}
        linkDirectionalArrowLength={4}
        linkDirectionalArrowRelPos={0.95}
        onNodeDrag={(node: any) => {
          node.fx = node.x;
          node.fy = node.y;
          persistentPositionsRef.current.set(node.id, {
            x: node.x,
            y: node.y,
            fx: node.x,
            fy: node.y,
          });
          if (fgRef.current && typeof fgRef.current.d3AlphaTarget === 'function') {
            fgRef.current.d3AlphaTarget(0);
          }
        }}
        onNodeDragEnd={(node: any) => {
          node.fx = node.x;
          node.fy = node.y;
          persistentPositionsRef.current.set(node.id, {
            x: node.x,
            y: node.y,
            fx: node.x,
            fy: node.y,
          });
          if (fgRef.current && typeof fgRef.current.d3AlphaTarget === 'function') {
            fgRef.current.d3AlphaTarget(0);
          }
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
          onClick={() =>
            fitGraphView(fgRef.current, stabilizedGraphData.nodes, {
              durationMs: 400,
              allowZoomIn: false,
            })
          }
          className="p-1.5 text-slate-400 hover:text-slate-100 hover:bg-white/10 rounded-lg transition-colors"
          title="Center graph (zoom out if needed; won’t zoom in)"
        >
          <Maximize2 className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
};
