import React, { useState } from 'react';
import { useMemexStore } from '../store/useMemexStore';
import { Logo } from './Logo';
import { Globe, FolderGit2, Plus, X } from 'lucide-react';

export const Navbar: React.FC = () => {
  const {
    activeProjectId,
    setActiveProjectId,
    projects,
    nodes,
    edges,
    createProjectWorkspace,
  } = useMemexStore();

  const [showNewProjModal, setShowNewProjModal] = useState(false);
  const [projName, setProjName] = useState('');
  const [projDesc, setProjDesc] = useState('');

  const handleCreateProject = (e: React.FormEvent) => {
    e.preventDefault();
    if (!projName.trim()) return;
    createProjectWorkspace(projName.trim(), projDesc.trim());
    setProjName('');
    setProjDesc('');
    setShowNewProjModal(false);
  };

  return (
    <header className="h-16 bg-[#0e1420]/95 backdrop-blur-md border-b border-white/10 px-6 flex items-center justify-between gap-4 select-none z-30 relative shadow-xl shadow-black/40">
      {/* Far Left: Brand & Logo */}
      <div className="flex items-center gap-3 shrink-0">
        <div
          className="flex items-center gap-2.5 cursor-pointer group"
          onClick={() => setActiveProjectId('global')}
        >
          <div className="transition-transform group-hover:scale-105 duration-200">
            <Logo size={32} />
          </div>
          <div className="flex flex-col">
            <div className="flex items-center gap-2">
              <span className="font-display font-bold text-xl tracking-tight bg-gradient-to-r from-sky-400 via-purple-400 to-emerald-400 bg-clip-text text-transparent">
                Me-Mex
              </span>
              <span className="text-[11px] font-mono font-medium text-slate-400 bg-slate-800/80 px-2 py-0.5 rounded-full border border-slate-700/60 shadow-inner">
                v0.1
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* CENTERED Top Project Tabs (Expands symmetrically from center) */}
      <div className="absolute left-1/2 -translate-x-1/2 flex items-center gap-2 bg-[#090d16]/90 p-1.5 rounded-2xl border border-white/10 shadow-inner max-w-3xl overflow-x-auto no-scrollbar">
        {/* Global Master Tab */}
        <button
          onClick={() => setActiveProjectId('global')}
          className={`flex items-center gap-2 px-4 py-2 text-xs font-semibold rounded-xl transition-all whitespace-nowrap ${
            activeProjectId === 'global'
              ? 'bg-gradient-to-r from-sky-500/20 to-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-glow-cyan font-bold'
              : 'text-slate-400 hover:text-slate-200 hover:bg-white/5'
          }`}
        >
          <Globe className="w-4 h-4 text-sky-400" />
          <span>Global Graph</span>
        </button>

        {/* Individual Project Tabs */}
        {projects
          .filter((p) => p.id !== 'global')
          .map((p) => (
            <button
              key={p.id}
              onClick={() => setActiveProjectId(p.id)}
              className={`flex items-center gap-2 px-4 py-2 text-xs font-semibold rounded-xl transition-all whitespace-nowrap ${
                activeProjectId === p.id
                  ? 'bg-gradient-to-r from-emerald-500/20 to-teal-500/20 text-emerald-300 border border-emerald-500/40 shadow-sm font-bold'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-white/5'
              }`}
            >
              <FolderGit2 className="w-4 h-4 text-emerald-400" />
              <span>{p.name}</span>
            </button>
          ))}

        {/* + New Project Tab Button */}
        <button
          onClick={() => setShowNewProjModal(true)}
          className="flex items-center gap-1.5 px-3 py-2 text-xs font-semibold text-slate-400 hover:text-emerald-300 hover:bg-emerald-500/10 rounded-xl transition-all border border-dashed border-slate-700/80 hover:border-emerald-500/40 whitespace-nowrap"
          title="Create New Project Workspace"
        >
          <Plus className="w-4 h-4" />
          <span>Project</span>
        </button>
      </div>

      {/* Far Right: Stats Display */}
      <div className="flex items-center gap-3 shrink-0">
        <div className="text-xs text-slate-400 font-mono flex items-center gap-3.5 bg-[#121824] px-4 py-2 rounded-xl border border-white/5 shadow-inner">
          <span className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-sky-400 shadow-sm" />
            <strong className="text-slate-200 font-bold">{nodes.length}</strong> Nodes
          </span>
          <span className="text-slate-600">•</span>
          <span className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 shadow-sm" />
            <strong className="text-slate-200 font-bold">{edges.length}</strong> Edges
          </span>
        </div>
      </div>

      {/* Create New Project Modal */}
      {showNewProjModal && (
        <div className="fixed inset-0 bg-black/75 backdrop-blur-md z-50 flex items-center justify-center p-4">
          <div className="bg-[#121824] border border-white/10 rounded-2xl p-6 max-w-md w-full space-y-4 shadow-2xl">
            <div className="flex items-center justify-between border-b border-white/10 pb-3.5">
              <h3 className="font-display font-bold text-base text-slate-100 flex items-center gap-2">
                <FolderGit2 className="w-5 h-5 text-emerald-400" /> Create Project Workspace
              </h3>
              <button
                onClick={() => setShowNewProjModal(false)}
                className="p-1.5 text-slate-400 hover:text-slate-200 rounded-lg hover:bg-white/10 transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleCreateProject} className="space-y-4">
              <div>
                <label className="text-[11px] font-mono text-slate-400 font-bold uppercase tracking-wider block mb-1.5">
                  Project Name
                </label>
                <input
                  type="text"
                  placeholder="e.g. Project: Skeletal Priors"
                  value={projName}
                  onChange={(e) => setProjName(e.target.value)}
                  className="w-full bg-[#090d16] text-slate-200 p-3 rounded-xl border border-slate-700/80 focus:border-emerald-400 focus:outline-none text-xs font-medium"
                />
              </div>

              <div>
                <label className="text-[11px] font-mono text-slate-400 font-bold uppercase tracking-wider block mb-1.5">
                  Description
                </label>
                <textarea
                  rows={3}
                  placeholder="Brief description of research scope..."
                  value={projDesc}
                  onChange={(e) => setProjDesc(e.target.value)}
                  className="w-full bg-[#090d16] text-slate-200 p-3 rounded-xl border border-slate-700/80 focus:border-emerald-400 focus:outline-none text-xs resize-none font-medium leading-relaxed"
                />
              </div>

              <div className="flex items-center justify-end gap-2.5 pt-2">
                <button
                  type="button"
                  onClick={() => setShowNewProjModal(false)}
                  className="px-4 py-2 text-xs font-semibold text-slate-400 hover:text-slate-200 rounded-xl"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={!projName.trim()}
                  className="px-5 py-2 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white font-bold text-xs rounded-xl shadow-lg shadow-emerald-950/50 disabled:opacity-50 transition-all"
                >
                  Create Workspace
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </header>
  );
};
