import React from 'react';
import { useMemexStore } from '../store/useMemexStore';
import { isRootNode, getRootSubType, isImmutableConcept } from '../types';
import {
  X,
  ExternalLink,
  BookOpen,
  Trophy,
  Lock,
  Edit3,
  GitCommit
} from 'lucide-react';

export const RightDrawer: React.FC = () => {
  const {
    selectedNodeId,
    setSelectedNodeId,
    nodes,
  } = useMemexStore();

  // Collapse completely if no node is selected
  if (!selectedNodeId) return null;

  const selectedNode = nodes.find((n) => n.id === selectedNodeId);

  if (!selectedNode) return null;

  const isRoot = isRootNode(selectedNode);
  const rootType = isRoot ? getRootSubType(selectedNode) : null;
  const isImmutable = isImmutableConcept(selectedNode);
  const umbrellaHubId = selectedNode.metadata?.sub_of_hub;


  const getNodeTypeBadge = () => {
    if (isRoot) {
      if (rootType === 'paper') {
        return <span className="px-3 py-1 rounded-full text-[10px] font-mono font-bold uppercase bg-sky-950/70 text-sky-400 border border-sky-500/40 shadow-sm">Research Paper Root</span>;
      }
      if (rootType === 'blog') {
        return <span className="px-3 py-1 rounded-full text-[10px] font-mono font-bold uppercase bg-emerald-950/70 text-emerald-400 border border-emerald-500/40 shadow-sm">Blog Article Root</span>;
      }
      if (rootType === 'post') {
        return <span className="px-3 py-1 rounded-full text-[10px] font-mono font-bold uppercase bg-purple-950/70 text-purple-400 border border-purple-500/40 shadow-sm">Social / Voice Post Root</span>;
      }
      return <span className="px-3 py-1 rounded-full text-[10px] font-mono font-bold uppercase bg-slate-900 text-slate-300 border border-slate-700 shadow-sm">Document Root</span>;
    }

    // Concept Nodes
    if (isImmutable) {
      return <span className="px-3 py-1 rounded-full text-[10px] font-mono font-bold uppercase bg-sky-950/70 text-sky-300 border border-sky-500/40 shadow-sm">Immutable Concept</span>;
    }
    return <span className="px-3 py-1 rounded-full text-[10px] font-mono font-bold uppercase bg-amber-950/70 text-amber-400 border border-amber-500/40 shadow-sm">Mutable Concept</span>;
  };

  const getMutabilityBadge = () => {
    if (isRoot) {
      return (
        <span className="px-2.5 py-1 rounded-full text-[10px] font-mono font-bold uppercase bg-slate-900 text-slate-400 border border-slate-700 flex items-center gap-1">
          <Lock className="w-3 h-3 text-slate-400" /> Grounded Source
        </span>
      );
    }
    if (isImmutable) {
      return (
        <span className="px-2.5 py-1 rounded-full text-[10px] font-mono font-bold uppercase bg-sky-950/80 text-sky-300 border border-sky-500/40 flex items-center gap-1">
          <Lock className="w-3 h-3 text-sky-400" /> Direct Root Extraction
        </span>
      );
    }
    return (
      <span className="px-2.5 py-1 rounded-full text-[10px] font-mono font-bold uppercase bg-amber-950/80 text-amber-300 border border-amber-500/40 flex items-center gap-1">
        <Edit3 className="w-3 h-3 text-amber-400" /> Persona Synthesized
      </span>
    );
  };

  return (
    <aside className="w-[440px] glass-panel border-l border-white/10 flex flex-col h-[calc(100vh-4rem)] text-xs select-none shadow-2xl z-20 shrink-0 transition-all duration-300">
      {/* Drawer Header */}
      <div className="p-4 border-b border-white/10 bg-[#090d16]/80 flex items-center justify-between">
        <div className="flex items-center gap-2">
          {getNodeTypeBadge()}
          {getMutabilityBadge()}
        </div>
        <div className="flex items-center gap-1.5">
          <button
            onClick={() => setSelectedNodeId(null)}
            className="p-2 text-slate-400 hover:text-slate-100 hover:bg-white/10 rounded-xl transition-colors"
            title="Close Drawer & Unselect Node"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Main Scrollable Drawer Content */}
      <div className="flex-1 overflow-y-auto p-5 space-y-4">
        {/* Title */}
        <div className="space-y-1">
          <h2 className="font-display font-bold text-base text-slate-100 leading-snug tracking-tight">{selectedNode.title}</h2>
          <div className="text-[10px] text-slate-500 font-mono">ID: {selectedNode.id}</div>
        </div>

        {/* Sub-Concept Parent Umbrella Hub Linkage */}
        {umbrellaHubId && (
          <div className="bg-emerald-950/30 border border-emerald-500/30 p-3 rounded-xl flex items-center gap-2 text-[11px] text-emerald-300">
            <GitCommit className="w-4 h-4 text-emerald-400 shrink-0" />
            <div className="truncate">
              Sub-concept generated from Umbrella Hub:{' '}
              <button
                onClick={() => setSelectedNodeId(umbrellaHubId)}
                className="font-mono underline font-bold hover:text-emerald-200"
              >
                {umbrellaHubId}
              </button>
            </div>
          </div>
        )}

        {/* Metadata Badges */}
        {selectedNode.metadata && Object.keys(selectedNode.metadata).length > 0 && (
          <div className="bg-[#121824] p-3.5 rounded-2xl border border-white/10 space-y-2 text-[11px] shadow-sm">
            <div className="text-[10px] font-mono text-slate-400 font-bold uppercase tracking-wider">Metadata Attributes</div>
            {selectedNode.metadata.elo_score && (
              <div className="flex items-center gap-2 text-purple-300 font-bold">
                <Trophy className="w-4 h-4 text-amber-400" />
                <span>Elo Score: {selectedNode.metadata.elo_score}</span>
              </div>
            )}
            {selectedNode.metadata.url && (
              <a
                href={selectedNode.metadata.url}
                target="_blank"
                rel="noreferrer"
                className="text-sky-400 hover:underline flex items-center gap-1.5 truncate font-mono text-[11px] font-medium"
              >
                <ExternalLink className="w-3.5 h-3.5" /> {selectedNode.metadata.url}
              </a>
            )}
            {selectedNode.metadata.authors && (
              <div className="text-slate-400 font-medium">Authors: {selectedNode.metadata.authors.join(', ')}</div>
            )}
          </div>
        )}

        {/* Markdown Note Body */}
        <div className="space-y-2.5 pt-1">
          <div className="flex items-center justify-between">
            <span className="font-display font-semibold text-slate-200 flex items-center gap-1.5 text-xs">
              <BookOpen className="w-4 h-4 text-purple-400" /> Zettelkasten Note Content
            </span>
          </div>

          <div className="bg-[#090d16] p-4 rounded-2xl border border-white/10 text-slate-300 font-mono text-[11px] leading-relaxed whitespace-pre-wrap shadow-inner font-medium">
            {selectedNode.content}
          </div>
        </div>
      </div>
    </aside>
  );
};
