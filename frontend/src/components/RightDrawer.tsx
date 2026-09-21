import React, { useState } from 'react';
import { useMemexStore } from '../store/useMemexStore';
import {
  X,
  ExternalLink,
  GitCommit,
  BookOpen,
  Plus,
  ArrowRight,
  ArrowLeft,
  Sparkles,
  Trophy
} from 'lucide-react';

export const RightDrawer: React.FC = () => {
  const {
    selectedNodeId,
    setSelectedNodeId,
    nodes,
    edges,
    createEdge,
    generateReport
  } = useMemexStore();

  const [newEdgeTargetId, setNewEdgeTargetId] = useState('');
  const [newEdgeType, setNewEdgeType] = useState('BUILDS_UPON');

  if (!selectedNodeId) {
    return (
      <aside className="w-96 glass-panel border-l border-white/10 flex flex-col h-[calc(100vh-4rem)] items-center justify-center p-6 text-center select-none shadow-2xl">
        <BookOpen className="w-12 h-12 text-slate-600 mb-3 animate-pulse" />
        <h3 className="font-display text-base font-bold text-slate-300">No Node Selected</h3>
        <p className="text-xs text-slate-500 mt-1 leading-relaxed max-w-xs">
          Click any node on the force graph canvas to open its Markdown reader, executive takeaway, and provenance connections.
        </p>
      </aside>
    );
  }

  const selectedNode = nodes.find((n) => n.id === selectedNodeId);

  if (!selectedNode) return null;

  // Compute incoming and outgoing edges
  const outgoingEdges = edges.filter((e) => {
    const s = typeof e.source === 'object' ? (e.source as any).id : e.source;
    return s === selectedNodeId;
  });

  const incomingEdges = edges.filter((e) => {
    const t = typeof e.target === 'object' ? (e.target as any).id : e.target;
    return t === selectedNodeId;
  });

  const handleAddEdge = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newEdgeTargetId) return;
    createEdge(selectedNodeId, newEdgeTargetId, newEdgeType);
    setNewEdgeTargetId('');
  };

  const getNodeTypeBadge = () => {
    switch (selectedNode.node_type) {
      case 'external_source':
        return <span className="px-2.5 py-1 rounded-full text-[10px] font-mono font-bold uppercase bg-sky-950/60 text-sky-400 border border-sky-500/30">External Source (Paper/PDF)</span>;
      case 'human_insight':
        return <span className="px-2.5 py-1 rounded-full text-[10px] font-mono font-bold uppercase bg-amber-950/60 text-amber-400 border border-amber-500/30">Human Voice Insight</span>;
      case 'agent_hypothesis':
        return <span className="px-2.5 py-1 rounded-full text-[10px] font-mono font-bold uppercase bg-purple-950/60 text-purple-400 border border-purple-500/30">Co-Scientist Hypothesis</span>;
      case 'concept_phrase':
        return <span className="px-2.5 py-1 rounded-full text-[10px] font-mono font-bold uppercase bg-teal-950/60 text-teal-400 border border-teal-500/30">HippoRAG 2 Concept</span>;
      case 'falsified_path':
        return <span className="px-2.5 py-1 rounded-full text-[10px] font-mono font-bold uppercase bg-red-950/60 text-red-400 border border-red-500/30">Falsified Path</span>;
      default:
        return null;
    }
  };

  return (
    <aside className="w-96 glass-panel border-l border-white/10 flex flex-col h-[calc(100vh-4rem)] text-xs select-none shadow-2xl z-20">
      {/* Drawer Header */}
      <div className="p-3.5 border-b border-white/10 bg-[#090d16]/80 flex items-center justify-between">
        <div className="flex items-center gap-2">
          {getNodeTypeBadge()}
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => generateReport(`Report on ${selectedNode.title}`, [selectedNode.id])}
            className="p-1.5 text-purple-400 hover:bg-purple-950/50 hover:text-purple-300 rounded-lg transition-colors border border-purple-500/20"
            title="Generate Node Report"
          >
            <Sparkles className="w-4 h-4" />
          </button>
          <button
            onClick={() => setSelectedNodeId(null)}
            className="p-1.5 text-slate-400 hover:text-slate-100 hover:bg-white/10 rounded-lg transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Main Scrollable Drawer Content */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* Title */}
        <div className="space-y-1">
          <h2 className="font-display font-bold text-base text-slate-100 leading-snug">{selectedNode.title}</h2>
          <div className="text-[10px] text-slate-500 font-mono">ID: {selectedNode.id}</div>
        </div>

        {/* Executive 2-Line Takeaway Callout Box */}
        <div className="bg-[#121824] p-3.5 rounded-xl border border-amber-500/30 space-y-1.5 shadow-lg relative overflow-hidden">
          <div className="text-[10px] font-mono text-amber-400 font-bold uppercase tracking-wider flex items-center gap-1">
            <Sparkles className="w-3.5 h-3.5" /> Executive 2-Line Takeaway
          </div>
          <p className="text-slate-200 text-[11px] leading-relaxed italic">
            "{selectedNode.takeaway_2line}"
          </p>
        </div>

        {/* Metadata Badges */}
        {selectedNode.metadata && Object.keys(selectedNode.metadata).length > 0 && (
          <div className="bg-[#121824] p-3 rounded-xl border border-white/10 space-y-1.5 text-[11px] shadow-sm">
            <div className="text-[10px] font-mono text-slate-400 font-bold uppercase tracking-wider">Metadata Attributes</div>
            {selectedNode.metadata.elo_score && (
              <div className="flex items-center gap-1.5 text-purple-300 font-bold">
                <Trophy className="w-3.5 h-3.5 text-amber-400" />
                <span>Elo Score: {selectedNode.metadata.elo_score}</span>
              </div>
            )}
            {selectedNode.metadata.url && (
              <a
                href={selectedNode.metadata.url}
                target="_blank"
                rel="noreferrer"
                className="text-sky-400 hover:underline flex items-center gap-1 truncate font-mono text-[10px]"
              >
                <ExternalLink className="w-3 h-3" /> {selectedNode.metadata.url}
              </a>
            )}
            {selectedNode.metadata.authors && (
              <div className="text-slate-400">Authors: {selectedNode.metadata.authors.join(', ')}</div>
            )}
          </div>
        )}

        {/* Explicit Connections Manager */}
        <div className="bg-[#121824] p-3.5 rounded-xl border border-white/10 space-y-2.5 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="font-display font-semibold text-slate-200 flex items-center gap-1.5">
              <GitCommit className="w-4 h-4 text-emerald-400" /> Graph Connections
            </span>
            <span className="text-[10px] font-mono text-slate-400 font-semibold bg-slate-800 px-2 py-0.5 rounded-full border border-slate-700">
              {outgoingEdges.length + incomingEdges.length} total
            </span>
          </div>

          {/* Outgoing Edges */}
          {outgoingEdges.map((e) => {
            const targetId = typeof e.target === 'object' ? (e.target as any).id : e.target;
            const targetNode = nodes.find((n) => n.id === targetId);
            return (
              <div
                key={e.id}
                onClick={() => setSelectedNodeId(targetId)}
                className="p-2.5 rounded-lg bg-[#090d16] border border-slate-800 hover:border-emerald-500/50 cursor-pointer flex items-center justify-between gap-2 transition-all group"
              >
                <div className="flex items-center gap-1.5 truncate">
                  <ArrowRight className="w-3.5 h-3.5 text-emerald-400 shrink-0 group-hover:translate-x-0.5 transition-transform" />
                  <span className="text-[10px] font-mono font-bold text-emerald-400">{e.edge_type}:</span>
                  <span className="text-slate-200 truncate font-medium">{targetNode?.title || targetId}</span>
                </div>
              </div>
            );
          })}

          {/* Incoming Edges */}
          {incomingEdges.map((e) => {
            const sourceId = typeof e.source === 'object' ? (e.source as any).id : e.source;
            const sourceNode = nodes.find((n) => n.id === sourceId);
            return (
              <div
                key={e.id}
                onClick={() => setSelectedNodeId(sourceId)}
                className="p-2.5 rounded-lg bg-[#090d16] border border-slate-800 hover:border-cyan-500/50 cursor-pointer flex items-center justify-between gap-2 transition-all group"
              >
                <div className="flex items-center gap-1.5 truncate">
                  <ArrowLeft className="w-3.5 h-3.5 text-cyan-400 shrink-0 group-hover:-translate-x-0.5 transition-transform" />
                  <span className="text-[10px] font-mono font-bold text-cyan-400">{e.edge_type}:</span>
                  <span className="text-slate-200 truncate font-medium">{sourceNode?.title || sourceId}</span>
                </div>
              </div>
            );
          })}

          {/* Add Connection Form */}
          <form onSubmit={handleAddEdge} className="pt-2 border-t border-white/10 space-y-2">
            <div className="text-[10px] font-mono text-slate-400 font-bold uppercase tracking-wider">+ Connect to another node</div>
            <div className="flex flex-col gap-2">
              <select
                value={newEdgeType}
                onChange={(e) => setNewEdgeType(e.target.value)}
                className="custom-select bg-[#090d16] text-slate-200 text-[11px] p-2 rounded-lg border border-slate-700/80 font-mono focus:outline-none focus:border-emerald-400"
              >
                <option value="BUILDS_UPON">BUILDS_UPON</option>
                <option value="CONTRASTS_WITH">CONTRASTS_WITH</option>
                <option value="REFUTES">REFUTES</option>
                <option value="DERIVES_FROM">DERIVES_FROM</option>
              </select>

              <select
                value={newEdgeTargetId}
                onChange={(e) => setNewEdgeTargetId(e.target.value)}
                className="custom-select bg-[#090d16] text-slate-200 text-[11px] p-2 rounded-lg border border-slate-700/80 focus:outline-none focus:border-emerald-400"
              >
                <option value="">Select target node...</option>
                {nodes
                  .filter((n) => n.id !== selectedNodeId)
                  .map((n) => (
                    <option key={n.id} value={n.id}>
                      {n.title.slice(0, 32)}
                    </option>
                  ))}
              </select>
            </div>
            <button
              type="submit"
              disabled={!newEdgeTargetId}
              className="w-full py-2 bg-gradient-to-r from-emerald-600/20 to-teal-600/20 hover:from-emerald-600/30 hover:to-teal-600/30 text-emerald-300 border border-emerald-500/40 rounded-lg font-bold flex items-center justify-center gap-1.5 transition-all shadow-md disabled:opacity-50"
            >
              <Plus className="w-3.5 h-3.5" /> Link Nodes
            </button>
          </form>
        </div>

        {/* Markdown Note Body */}
        <div className="space-y-2 pt-1">
          <div className="flex items-center justify-between">
            <span className="font-display font-semibold text-slate-200 flex items-center gap-1.5">
              <BookOpen className="w-4 h-4 text-purple-400" /> Markdown AST Body
            </span>
          </div>

          <div className="bg-[#090d16] p-3.5 rounded-xl border border-white/10 text-slate-300 font-mono text-[11px] leading-relaxed whitespace-pre-wrap shadow-inner">
            {selectedNode.content}
          </div>
        </div>
      </div>
    </aside>
  );
};
