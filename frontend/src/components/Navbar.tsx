import React from 'react';
import { useMemexStore } from '../store/useMemexStore';
import { Globe, FolderGit2, FileText, Download, Mic, Sparkles, Network } from 'lucide-react';

export const Navbar: React.FC = () => {
  const {
    viewMode,
    setViewMode,
    activeProjectId,
    setActiveProjectId,
    projects,
    nodes,
    edges,
    simulateVoiceCommand,
    isVoiceListening,
  } = useMemexStore();

  return (
    <header className="h-14 bg-[#161b22] border-b border-[#30363d] px-4 flex items-center justify-between gap-4 select-none z-30 relative">
      {/* Brand & Project Selector */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2 font-bold text-lg text-[#3fb950] tracking-wide">
          <Network className="w-5 h-5 text-cyan-400 animate-pulse" />
          <span>Graph-Memex</span>
          <span className="text-xs font-mono text-slate-400 bg-[#21262d] px-2 py-0.5 rounded border border-[#30363d]">
            me-mex v0.1
          </span>
        </div>

        <div className="h-4 w-[1px] bg-[#30363d] mx-1" />

        {/* Project Selector (Superset Rule Indicator) */}
        <div className="flex items-center gap-2">
          <FolderGit2 className="w-4 h-4 text-slate-400" />
          <select
            value={activeProjectId}
            onChange={(e) => setActiveProjectId(e.target.value)}
            className="bg-[#21262d] text-slate-200 text-xs font-medium px-2 py-1 rounded border border-[#30363d] focus:outline-none focus:border-[#3fb950] transition-colors"
          >
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name} {p.id === 'global' ? '(Master Superset)' : ''}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Center SPA View Switcher */}
      <div className="flex items-center bg-[#0d1117] p-1 rounded-lg border border-[#30363d] shadow-inner">
        <button
          onClick={() => setViewMode('global')}
          className={`flex items-center gap-1.5 px-3 py-1 text-xs font-medium rounded-md transition-all ${
            viewMode === 'global'
              ? 'bg-[#21262d] text-cyan-400 border border-[#30363d] shadow-sm'
              : 'text-slate-400 hover:text-slate-200'
          }`}
        >
          <Globe className="w-3.5 h-3.5" />
          <span>Global Graph</span>
        </button>

        <button
          onClick={() => setViewMode('workspace')}
          className={`flex items-center gap-1.5 px-3 py-1 text-xs font-medium rounded-md transition-all ${
            viewMode === 'workspace'
              ? 'bg-[#21262d] text-emerald-400 border border-[#30363d] shadow-sm'
              : 'text-slate-400 hover:text-slate-200'
          }`}
        >
          <FolderGit2 className="w-3.5 h-3.5" />
          <span>Project Workspace</span>
        </button>

        <button
          onClick={() => setViewMode('report')}
          className={`flex items-center gap-1.5 px-3 py-1 text-xs font-medium rounded-md transition-all ${
            viewMode === 'report'
              ? 'bg-[#21262d] text-purple-400 border border-[#30363d] shadow-sm'
              : 'text-slate-400 hover:text-slate-200'
          }`}
        >
          <FileText className="w-3.5 h-3.5" />
          <span>Report Studio</span>
        </button>

        <button
          onClick={() => setViewMode('intake')}
          className={`flex items-center gap-1.5 px-3 py-1 text-xs font-medium rounded-md transition-all ${
            viewMode === 'intake'
              ? 'bg-[#21262d] text-amber-400 border border-[#30363d] shadow-sm'
              : 'text-slate-400 hover:text-slate-200'
          }`}
        >
          <Download className="w-3.5 h-3.5" />
          <span>Intake Stream</span>
        </button>
      </div>

      {/* Right Stats & Voice Trigger */}
      <div className="flex items-center gap-3">
        <div className="text-xs text-slate-400 font-mono hidden md:flex items-center gap-3">
          <span>
            <strong className="text-cyan-400">{nodes.length}</strong> Nodes
          </span>
          <span>•</span>
          <span>
            <strong className="text-emerald-400">{edges.length}</strong> Edges
          </span>
        </div>

        {/* Quick Voice Insight Action */}
        <button
          onClick={() =>
            simulateVoiceCommand('Synthesize recent skeletal prior voice notes with Co-Scientist Hypothesis #4')
          }
          className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg transition-all border ${
            isVoiceListening
              ? 'bg-red-500/20 text-red-400 border-red-500 animate-pulse'
              : 'bg-gradient-to-r from-emerald-600/20 to-cyan-600/20 text-cyan-300 border-cyan-500/30 hover:border-cyan-400'
          }`}
        >
          <Mic className={`w-3.5 h-3.5 ${isVoiceListening ? 'animate-bounce' : ''}`} />
          <span>{isVoiceListening ? 'Listening...' : 'Speak Insight'}</span>
          <Sparkles className="w-3 h-3 text-amber-400 ml-0.5" />
        </button>
      </div>
    </header>
  );
};
