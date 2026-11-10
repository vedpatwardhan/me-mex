import React, { useState } from 'react';
import { useMemexStore } from '../store/useMemexStore';
import { isRootNode, getRootSubType, isImmutableConcept } from '../types';
import {
  X,
  FileText,
  GitCommit,
  Trash2,
  AlertTriangle,
} from 'lucide-react';

export const RightDrawer: React.FC = () => {
  const {
    selectedNodeId,
    setSelectedNodeId,
    nodes,
    deleteNode,
    updateNodeDescription,
  } = useMemexStore();

  const [isDeleting, setIsDeleting] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [isEditingDesc, setIsEditingDesc] = useState(false);
  const [draftDescription, setDraftDescription] = useState('');
  const [isSavingDesc, setIsSavingDesc] = useState(false);

  // Collapse completely if no node is selected
  if (!selectedNodeId) return null;

  const selectedNode = nodes.find((n) => n.id === selectedNodeId);

  if (!selectedNode) return null;

  const isRoot = isRootNode(selectedNode);
  const rootType = isRoot ? getRootSubType(selectedNode) : null;
  const isImmutable = isImmutableConcept(selectedNode);
  const umbrellaHubId = selectedNode.metadata?.sub_of_hub;
  const isGenesis = Boolean(selectedNode.metadata?.is_genesis);
  const canEditDescription = !isImmutable || isGenesis;


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
      return <span className="px-3 py-1 rounded-full text-[10px] font-mono font-bold uppercase bg-rose-950/70 text-rose-300 border border-rose-500/40 shadow-sm">Concepts (I)</span>;
    }
    return <span className="px-3 py-1 rounded-full text-[10px] font-mono font-bold uppercase bg-amber-950/70 text-amber-400 border border-amber-500/40 shadow-sm">Concepts (M)</span>;
  };

  return (
    <aside className="w-[440px] glass-panel border-l border-white/10 flex flex-col h-[calc(100vh-4rem)] text-xs shadow-2xl z-20 shrink-0 transition-all duration-300">
      {/* Drawer Header */}
      <div className="p-4 border-b border-white/10 bg-[#090d16]/80 flex items-center justify-between select-none">
        <div className="flex items-center gap-2">
          {getNodeTypeBadge()}
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
          <h2 className="font-display font-bold text-base text-slate-100 leading-snug tracking-tight select-text cursor-text">
            {selectedNode.title}
          </h2>
          <div className="text-[10px] text-slate-500 font-mono select-text cursor-text">ID: {selectedNode.id}</div>
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

        {/* Description Section */}
        <div className="space-y-2.5 pt-1">
          <div className="flex items-center justify-between">
            <span className="font-display font-semibold text-slate-200 flex items-center gap-1.5 text-xs">
              <FileText className="w-4 h-4 text-purple-400" /> Description
            </span>
            {canEditDescription && !isEditingDesc && (
              <button
                type="button"
                onClick={() => {
                  setDraftDescription(selectedNode.description || selectedNode.content || '');
                  setIsEditingDesc(true);
                }}
                className="text-[10px] uppercase font-mono text-purple-300 hover:text-purple-100"
              >
                Edit
              </button>
            )}
          </div>

          {isEditingDesc ? (
            <div className="space-y-2">
              <textarea
                value={draftDescription}
                onChange={(e) => setDraftDescription(e.target.value)}
                className="w-full min-h-[140px] bg-[#090d16] p-4 rounded-2xl border border-purple-500/30 text-slate-200 font-mono text-[11px] leading-relaxed"
              />
              <div className="flex gap-2">
                <button
                  type="button"
                  disabled={isSavingDesc}
                  onClick={async () => {
                    setIsSavingDesc(true);
                    const ok = await updateNodeDescription(selectedNode.id, draftDescription);
                    setIsSavingDesc(false);
                    if (ok) setIsEditingDesc(false);
                  }}
                  className="flex-1 py-1.5 rounded-xl bg-purple-600 hover:bg-purple-500 text-white text-xs font-medium"
                >
                  {isSavingDesc ? 'Saving…' : 'Save'}
                </button>
                <button
                  type="button"
                  onClick={() => setIsEditingDesc(false)}
                  className="py-1.5 px-3 rounded-xl bg-white/10 text-slate-300 text-xs"
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <div className="bg-[#090d16] p-4 rounded-2xl border border-white/10 text-slate-300 font-mono text-[11px] leading-relaxed whitespace-pre-wrap shadow-inner font-medium select-text cursor-text">
              {selectedNode.description || selectedNode.content || 'No description provided.'}
            </div>
          )}
        </div>

        {/* Delete Node Action Section */}
        <div className="pt-4 border-t border-white/10 select-none">
          {!confirmDelete ? (
            <button
              onClick={() => setConfirmDelete(true)}
              className="w-full py-2.5 px-3 rounded-xl border border-rose-500/30 bg-rose-950/20 hover:bg-rose-950/50 text-rose-400 hover:text-rose-200 transition-all flex items-center justify-center gap-2 font-medium text-xs group"
            >
              <Trash2 className="w-4 h-4 text-rose-400 group-hover:scale-110 transition-transform" />
              <span>Delete Node from Database</span>
            </button>
          ) : (
            <div className="bg-rose-950/40 border border-rose-500/40 p-3.5 rounded-2xl space-y-3">
              <div className="flex items-start gap-2 text-rose-300 text-xs leading-snug">
                <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
                <span>
                  Are you sure you want to delete <strong>{selectedNode.title}</strong>? All connected edges will also be deleted permanently.
                </span>
              </div>
              <div className="flex items-center gap-2">
                <button
                  disabled={isDeleting}
                  onClick={async () => {
                    setIsDeleting(true);
                    await deleteNode(selectedNode.id);
                    setIsDeleting(false);
                    setConfirmDelete(false);
                  }}
                  className="flex-1 py-1.5 px-3 rounded-xl bg-rose-600 hover:bg-rose-500 text-white font-medium text-xs transition-colors flex items-center justify-center gap-1.5"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                  <span>{isDeleting ? 'Deleting...' : 'Yes, Delete'}</span>
                </button>
                <button
                  disabled={isDeleting}
                  onClick={() => setConfirmDelete(false)}
                  className="py-1.5 px-3 rounded-xl bg-white/10 hover:bg-white/15 text-slate-300 font-medium text-xs transition-colors"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </aside>
  );
};
