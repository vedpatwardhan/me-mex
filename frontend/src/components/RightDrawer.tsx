import React, { useState } from 'react';
import { useMemexStore } from '../store/useMemexStore';
import {
  X,
  Edit3,
  ExternalLink,
  GitCommit,
  Tag,
  Share2,
  BookOpen,
  Plus,
  ArrowRight,
  ArrowLeft,
  Trash2,
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

  const [isEditing, setIsEditing] = useState(false);
  const [newEdgeTargetId, setNewEdgeTargetId] = useState('');
  const [newEdgeType, setNewEdgeType] = useState('BUILDS_UPON');

  if (!selectedNodeId) {
    return (
      <aside className="w-96 bg-[#161b22] border-l border-[#30363d] flex flex-col h-[calc(100vh-3.5rem)] items-center justify-center p-6 text-center select-none">
        <BookOpen className="w-10 h-10 text-slate-600 mb-3" />
        <h3 className="text-sm font-semibold text-slate-300">No Node Selected</h3>
        <p className="text-xs text-slate-500 mt-1">
          Click any node on the force graph canvas to open its Markdown reader, takeaway, and provenance connections.
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
        return <span className="px-2 py-0.5 rounded text-[10px] font-mono uppercase bg-blue-950/60 text-blue-400 border border-blue-500/30">External Source (Paper/PDF)</span>;
      case 'human_insight':
        return <span className="px-2 py-0.5 rounded text-[10px] font-mono uppercase bg-yellow-950/60 text-yellow-400 border border-yellow-500/30">Human Voice Insight</span>;
      case 'agent_hypothesis':
        return <span className="px-2 py-0.5 rounded text-[10px] font-mono uppercase bg-purple-950/60 text-purple-400 border border-purple-500/30">Co-Scientist Hypothesis</span>;
      case 'concept_phrase':
        return <span className="px-2 py-0.5 rounded text-[10px] font-mono uppercase bg-cyan-950/60 text-cyan-400 border border-cyan-500/30">HippoRAG 2 Concept</span>;
      case 'falsified_path':
        return <span className="px-2 py-0.5 rounded text-[10px] font-mono uppercase bg-red-950/60 text-red-400 border border-red-500/30">Falsified Path</span>;
      default:
        return null;
    }
  };

  return (
    <aside className="w-96 bg-[#161b22] border-l border-[#30363d] flex flex-col h-[calc(100vh-3.5rem)] text-xs select-none">
      {/* Drawer Header */}
      <div className="p-3 border-b border-[#30363d] bg-[#0d1117] flex items-center justify-between">
        <div className="flex items-center gap-2">
          {getNodeTypeBadge()}
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => generateReport(`Report on ${selectedNode.title}`, [selectedNode.id])}
            className="p-1 text-purple-400 hover:bg-purple-950/40 rounded transition-colors"
            title="Generate Node Report"
          >
            <Sparkles className="w-4 h-4" />
          </button>
          <button
            onClick={() => setSelectedNodeId(null)}
            className="p-1 text-slate-400 hover:text-slate-200 hover:bg-[#21262d] rounded transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Main Scrollable Drawer Content */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* Title */}
        <div className="space-y-1">
          <h2 className="text-sm font-bold text-slate-100 leading-snug">{selectedNode.title}</h2>
          <div className="text-[10px] text-slate-500 font-mono">ID: {selectedNode.id}</div>
        </div>

        {/* Executive 2-Line Takeaway Callout Box */}
        <div className="bg-[#0d1117] p-3 rounded-lg border border-amber-500/30 space-y-1">
          <div className="text-[10px] font-mono text-amber-400 font-semibold uppercase tracking-wider flex items-center gap-1">
            <Sparkles className="w-3 h-3" /> Executive 2-Line Takeaway
          </div>
          <p className="text-slate-200 text-[11px] leading-relaxed italic">
            "{selectedNode.takeaway_2line}"
          </p>
        </div>

        {/* Metadata Badges */}
        {selectedNode.metadata && Object.keys(selectedNode.metadata).length > 0 && (
          <div className="bg-[#0d1117] p-2.5 rounded-lg border border-[#30363d] space-y-1 text-[11px]">
            <div className="text-[10px] font-mono text-slate-400 font-semibold uppercase">Metadata Attributes</div>
            {selectedNode.metadata.elo_score && (
              <div className="flex items-center gap-1.5 text-purple-300 font-semibold">
                <Trophy className="w-3.5 h-3.5 text-amber-400" />
                <span>Elo Score: {selectedNode.metadata.elo_score}</span>
              </div>
            )}
            {selectedNode.metadata.url && (
              <a
                href={selectedNode.metadata.url}
                target="_blank"
                rel="noreferrer"
                className="text-cyan-400 hover:underline flex items-center gap-1 truncate"
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
        <div className="bg-[#0d1117] p-3 rounded-lg border border-[#30363d] space-y-2">
          <div className="flex items-center justify-between">
            <span className="font-semibold text-slate-200 flex items-center gap-1.5">
              <GitCommit className="w-3.5 h-3.5 text-emerald-400" /> Graph Connections
            </span>
            <span className="text-[10px] font-mono text-slate-400">
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
                className="p-2 rounded bg-[#161b22] border border-[#30363d] hover:border-cyan-500/50 cursor-pointer flex items-center justify-between gap-2 transition-all"
              >
                <div className="flex items-center gap-1.5 truncate">
                  <ArrowRight className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                  <span className="text-[10px] font-mono text-emerald-300">{e.edge_type}:</span>
                  <span className="text-slate-200 truncate">{targetNode?.title || targetId}</span>
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
                className="p-2 rounded bg-[#161b22] border border-[#30363d] hover:border-cyan-500/50 cursor-pointer flex items-center justify-between gap-2 transition-all"
              >
                <div className="flex items-center gap-1.5 truncate">
                  <ArrowLeft className="w-3.5 h-3.5 text-cyan-400 shrink-0" />
                  <span className="text-[10px] font-mono text-cyan-300">{e.edge_type}:</span>
                  <span className="text-slate-200 truncate">{sourceNode?.title || sourceId}</span>
                </div>
              </div>
            );
          })}

          {/* Add Connection Form */}
          <form onSubmit={handleAddEdge} className="pt-2 border-t border-[#30363d] space-y-2">
            <div className="text-[10px] font-mono text-slate-400 font-semibold uppercase">+ Connect to another node</div>
            <div className="flex gap-2">
              <select
                value={newEdgeType}
                onChange={(e) => setNewEdgeType(e.target.value)}
                className="bg-[#161b22] text-slate-200 text-[11px] p-1.5 rounded border border-[#30363d]"
              >
                <option value="BUILDS_UPON">BUILDS_UPON</option>
                <option value="CONTRASTS_WITH">CONTRASTS_WITH</option>
                <option value="REFUTES">REFUTES</option>
                <option value="DERIVES_FROM">DERIVES_FROM</option>
              </select>

              <select
                value={newEdgeTargetId}
                onChange={(e) => setNewEdgeTargetId(e.target.value)}
                className="flex-1 bg-[#161b22] text-slate-200 text-[11px] p-1.5 rounded border border-[#30363d]"
              >
                <option value="">Select target node...</option>
                {nodes
                  .filter((n) => n.id !== selectedNodeId)
                  .map((n) => (
                    <option key={n.id} value={n.id}>
                      {n.title.slice(0, 30)}
                    </option>
                  ))}
              </select>
            </div>
            <button
              type="submit"
              disabled={!newEdgeTargetId}
              className="w-full py-1.5 bg-emerald-600/20 hover:bg-emerald-600/30 text-emerald-300 border border-emerald-500/30 rounded font-medium flex items-center justify-center gap-1 transition-all disabled:opacity-50"
            >
              <Plus className="w-3.5 h-3.5" /> Link Nodes
            </button>
          </form>
        </div>

        {/* Markdown Note Body */}
        <div className="space-y-2 pt-2">
          <div className="flex items-center justify-between">
            <span className="font-semibold text-slate-200 flex items-center gap-1.5">
              <BookOpen className="w-3.5 h-3.5 text-purple-400" /> Markdown AST Body
            </span>
          </div>

          <div className="bg-[#0d1117] p-3 rounded-lg border border-[#30363d] text-slate-300 font-mono text-[11px] leading-relaxed whitespace-pre-wrap">
            {selectedNode.content}
          </div>
        </div>
      </div>
    </aside>
  );
};
