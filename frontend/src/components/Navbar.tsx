import React from 'react';
import { useMemexStore } from '../store/useMemexStore';
import { Logo } from './Logo';
import { Globe, FolderGit2, FileText, Download, Mic, Sparkles, Activity } from 'lucide-react';

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
    <header className="h-16 bg-[#0e1420]/90 backdrop-blur-md border-b border-white/10 px-5 flex items-center justify-between gap-4 select-none z-30 relative shadow-xl shadow-black/40">
      {/* Brand & Custom Styled Project Selector */}
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2.5 group cursor-pointer" onClick={() => setViewMode('global')}>
          <div className="transition-transform group-hover:scale-105 duration-200">
            <Logo size={30} />
          </div>
          <div className="flex flex-col">
            <div className="flex items-center gap-1.5">
              <span className="font-display font-bold text-xl tracking-tight bg-gradient-to-r from-sky-400 via-purple-400 to-emerald-400 bg-clip-text text-transparent">
                Me-Mex
              </span>
              <span className="text-[10px] font-mono font-medium text-slate-400 bg-slate-800/80 px-2 py-0.5 rounded-full border border-slate-700/60 shadow-inner">
                v0.1
              </span>
            </div>
          </div>
        </div>

        <div className="h-5 w-[1px] bg-white/10 mx-1" />

        {/* Custom Styled Project Selector */}
        <div className="flex items-center gap-2">
          <div className="relative">
            <select
              value={activeProjectId}
              onChange={(e) => setActiveProjectId(e.target.value)}
              className="custom-select bg-[#162030] text-slate-200 text-xs font-semibold pl-8 pr-8 py-1.5 rounded-lg border border-cyan-500/30 hover:border-cyan-400/60 focus:outline-none focus:ring-2 focus:ring-cyan-500/40 transition-all cursor-pointer shadow-sm"
            >
              {projects.map((p) => (
                <option key={p.id} value={p.id} className="bg-[#121824] text-slate-200">
                  {p.name} {p.id === 'global' ? '(Master Superset)' : ''}
                </option>
              ))}
            </select>
            <FolderGit2 className="w-3.5 h-3.5 text-cyan-400 absolute left-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
          </div>
        </div>
      </div>

      {/* Center SPA View Switcher */}
      <div className="flex items-center bg-[#090d16] p-1 rounded-xl border border-white/10 shadow-inner">
        <button
          onClick={() => setViewMode('global')}
          className={`flex items-center gap-2 px-3.5 py-1.5 text-xs font-semibold rounded-lg transition-all ${
            viewMode === 'global'
              ? 'bg-gradient-to-r from-sky-500/20 to-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-glow-cyan'
              : 'text-slate-400 hover:text-slate-200 hover:bg-white/5'
          }`}
        >
          <Globe className="w-3.5 h-3.5 text-sky-400" />
          <span>Global Graph</span>
        </button>

        <button
          onClick={() => setViewMode('workspace')}
          className={`flex items-center gap-2 px-3.5 py-1.5 text-xs font-semibold rounded-lg transition-all ${
            viewMode === 'workspace'
              ? 'bg-gradient-to-r from-emerald-500/20 to-teal-500/20 text-emerald-300 border border-emerald-500/40 shadow-sm'
              : 'text-slate-400 hover:text-slate-200 hover:bg-white/5'
          }`}
        >
          <FolderGit2 className="w-3.5 h-3.5 text-emerald-400" />
          <span>Project Workspace</span>
        </button>

        <button
          onClick={() => setViewMode('report')}
          className={`flex items-center gap-2 px-3.5 py-1.5 text-xs font-semibold rounded-md transition-all ${
            viewMode === 'report'
              ? 'bg-gradient-to-r from-purple-500/20 to-indigo-500/20 text-purple-300 border border-purple-500/40 shadow-glow-purple'
              : 'text-slate-400 hover:text-slate-200 hover:bg-white/5'
          }`}
        >
          <FileText className="w-3.5 h-3.5 text-purple-400" />
          <span>Report Studio</span>
        </button>

        <button
          onClick={() => setViewMode('intake')}
          className={`flex items-center gap-2 px-3.5 py-1.5 text-xs font-semibold rounded-md transition-all ${
            viewMode === 'intake'
              ? 'bg-gradient-to-r from-amber-500/20 to-yellow-500/20 text-amber-300 border border-amber-500/40 shadow-glow-amber'
              : 'text-slate-400 hover:text-slate-200 hover:bg-white/5'
          }`}
        >
          <Download className="w-3.5 h-3.5 text-amber-400" />
          <span>Intake Stream</span>
        </button>
      </div>

      {/* Right Stats & Voice Trigger */}
      <div className="flex items-center gap-4">
        <div className="text-xs text-slate-400 font-mono hidden md:flex items-center gap-3 bg-[#121824] px-3 py-1.5 rounded-lg border border-white/5 shadow-inner">
          <span className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-sky-400" />
            <strong className="text-slate-200 font-semibold">{nodes.length}</strong> Nodes
          </span>
          <span className="text-slate-600">•</span>
          <span className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-emerald-400" />
            <strong className="text-slate-200 font-semibold">{edges.length}</strong> Edges
          </span>
        </div>

        {/* Quick Voice Insight Action */}
        <button
          onClick={() =>
            simulateVoiceCommand('Synthesize recent skeletal prior voice notes with Co-Scientist Hypothesis #4')
          }
          className={`flex items-center gap-2 px-3.5 py-1.5 text-xs font-bold rounded-lg transition-all shadow-md ${
            isVoiceListening
              ? 'bg-red-500/20 text-red-400 border border-red-500 animate-pulse shadow-red-900/50'
              : 'bg-gradient-to-r from-emerald-600/30 via-teal-600/30 to-cyan-600/30 hover:from-emerald-500/40 hover:to-cyan-500/40 text-cyan-200 border border-cyan-400/40 hover:border-cyan-400 shadow-cyan-950/50'
          }`}
        >
          <Mic className={`w-3.5 h-3.5 text-cyan-400 ${isVoiceListening ? 'animate-bounce text-red-400' : ''}`} />
          <span>{isVoiceListening ? 'Listening...' : 'Speak Insight'}</span>
          <Sparkles className="w-3.5 h-3.5 text-amber-300 ml-0.5" />
        </button>
      </div>
    </header>
  );
};
