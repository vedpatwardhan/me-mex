import React, { useState } from 'react';
import { useMemexStore } from '../store/useMemexStore';
import {
  Download,
  Link,
  Mic,
  FileText,
  Inbox,
  CheckCircle2,
  XCircle,
  BrainCircuit,
  Clock,
  Zap,
  Sparkles,
  Plus,
  Radio
} from 'lucide-react';

export const LeftRail: React.FC = () => {
  const {
    handleIntake,
    proposals,
    handleProposalAction,
    simulateVoiceCommand,
    isVoiceListening,
    isLoading
  } = useMemexStore();

  const [urlInput, setUrlInput] = useState('');
  const [textInput, setTextInput] = useState('');
  const [activeTab, setActiveTab] = useState<'intake' | 'proposals' | 'fsrs'>('intake');

  const onUrlSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!urlInput.trim()) return;
    handleIntake('url', urlInput.trim());
    setUrlInput('');
  };

  const onTextSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!textInput.trim()) return;
    handleIntake('text', textInput.trim());
    setTextInput('');
  };

  return (
    <aside className="w-80 glass-panel border-r border-white/10 flex flex-col h-[calc(100vh-4rem)] text-xs select-none z-20 shadow-2xl">
      {/* Pane 1 Sub-Navigation Tabs */}
      <div className="flex items-center border-b border-white/10 bg-[#090d16]/70 p-1.5 gap-1.5">
        <button
          onClick={() => setActiveTab('intake')}
          className={`flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-lg font-semibold transition-all ${
            activeTab === 'intake'
              ? 'bg-[#1a2332] text-amber-300 border border-amber-500/30 shadow-glow-amber'
              : 'text-slate-400 hover:text-slate-200 hover:bg-white/5'
          }`}
        >
          <Download className="w-3.5 h-3.5 text-amber-400" />
          <span>Intake</span>
        </button>

        <button
          onClick={() => setActiveTab('proposals')}
          className={`flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-lg font-semibold transition-all relative ${
            activeTab === 'proposals'
              ? 'bg-[#1a2332] text-cyan-300 border border-cyan-500/30 shadow-glow-cyan'
              : 'text-slate-400 hover:text-slate-200 hover:bg-white/5'
          }`}
        >
          <Inbox className="w-3.5 h-3.5 text-cyan-400" />
          <span>Proposals</span>
          {proposals.filter((p) => p.status === 'pending').length > 0 && (
            <span className="w-4 h-4 bg-cyan-400 text-slate-950 font-bold text-[10px] rounded-full flex items-center justify-center shadow-md">
              {proposals.filter((p) => p.status === 'pending').length}
            </span>
          )}
        </button>

        <button
          onClick={() => setActiveTab('fsrs')}
          className={`flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-lg font-semibold transition-all ${
            activeTab === 'fsrs'
              ? 'bg-[#1a2332] text-emerald-300 border border-emerald-500/30'
              : 'text-slate-400 hover:text-slate-200 hover:bg-white/5'
          }`}
        >
          <BrainCircuit className="w-3.5 h-3.5 text-emerald-400" />
          <span>FSRS</span>
        </button>
      </div>

      {/* Pane 1 Scrollable Content Area */}
      <div className="flex-1 overflow-y-auto p-3.5 space-y-4">
        {/* INTAKE TAB */}
        {activeTab === 'intake' && (
          <div className="space-y-4">
            {/* Voice Epiphany Card */}
            <div className="bg-[#121824]/90 p-3.5 rounded-xl border border-amber-500/30 space-y-2.5 shadow-lg relative overflow-hidden group">
              <div className="absolute top-0 right-0 w-24 h-24 bg-amber-500/5 rounded-full blur-xl pointer-events-none group-hover:bg-amber-500/10 transition-colors" />
              <div className="flex items-center justify-between">
                <span className="font-display font-semibold text-amber-300 flex items-center gap-1.5">
                  <Mic className="w-4 h-4 text-amber-400" /> Spoken Insight Stream
                </span>
                <span className="text-[10px] text-amber-400/80 font-mono bg-amber-950/40 px-2 py-0.5 rounded-full border border-amber-500/30">
                  Fast-Whisper
                </span>
              </div>
              <p className="text-slate-400 text-[11px] leading-relaxed">
                Speak raw insights or research thoughts. Fast-Whisper transcribes and extracts atomic nodes into the Global Graph.
              </p>
              <button
                onClick={() => simulateVoiceCommand('Joint limits should constrain latent flow field directly during action denoising.')}
                disabled={isLoading}
                className="w-full py-2 bg-gradient-to-r from-amber-500/20 to-yellow-500/20 hover:from-amber-500/30 hover:to-yellow-500/30 text-amber-200 border border-amber-500/40 rounded-lg font-bold flex items-center justify-center gap-2 transition-all shadow-md"
              >
                <Radio className={`w-3.5 h-3.5 ${isVoiceListening ? 'animate-ping text-red-400' : 'text-amber-400'}`} />
                <span>{isVoiceListening ? 'Listening & Extracting...' : 'Record Voice Note'}</span>
              </button>
            </div>

            {/* URL Web Link Snapshot Card */}
            <div className="bg-[#121824]/90 p-3.5 rounded-xl border border-cyan-500/20 space-y-2.5 shadow-lg">
              <span className="font-display font-semibold text-slate-200 flex items-center gap-1.5">
                <Link className="w-4 h-4 text-cyan-400" /> Web Link / Tweet / arXiv Entry
              </span>
              <form onSubmit={onUrlSubmit} className="space-y-2">
                <input
                  type="url"
                  placeholder="Paste URL, tweet, or arXiv DOI..."
                  value={urlInput}
                  onChange={(e) => setUrlInput(e.target.value)}
                  className="w-full bg-[#090d16] text-slate-200 p-2.5 rounded-lg border border-slate-700/80 focus:border-cyan-400 focus:ring-1 focus:ring-cyan-400 focus:outline-none text-xs transition-all placeholder-slate-500 font-mono"
                />
                <button
                  type="submit"
                  disabled={isLoading || !urlInput.trim()}
                  className="w-full py-2 bg-gradient-to-r from-cyan-600/20 to-blue-600/20 hover:from-cyan-600/30 hover:to-blue-600/30 text-cyan-300 border border-cyan-500/40 rounded-lg font-bold flex items-center justify-center gap-1.5 transition-all shadow-md disabled:opacity-50"
                >
                  <Plus className="w-3.5 h-3.5" /> Fetch & Snapshot HTML
                </button>
              </form>
            </div>

            {/* Raw File / Text Note Intake Card */}
            <div className="bg-[#121824]/90 p-3.5 rounded-xl border border-emerald-500/20 space-y-2.5 shadow-lg">
              <span className="font-display font-semibold text-slate-200 flex items-center gap-1.5">
                <FileText className="w-4 h-4 text-emerald-400" /> Quick Text Note / Markdown
              </span>
              <form onSubmit={onTextSubmit} className="space-y-2">
                <textarea
                  rows={3}
                  placeholder="Type an insight, hypothesis premise, or markdown excerpt..."
                  value={textInput}
                  onChange={(e) => setTextInput(e.target.value)}
                  className="w-full bg-[#090d16] text-slate-200 p-2.5 rounded-lg border border-slate-700/80 focus:border-emerald-400 focus:ring-1 focus:ring-emerald-400 focus:outline-none text-xs resize-none transition-all placeholder-slate-500 font-mono"
                />
                <button
                  type="submit"
                  disabled={isLoading || !textInput.trim()}
                  className="w-full py-2 bg-gradient-to-r from-emerald-600/20 to-teal-600/20 hover:from-emerald-600/30 hover:to-teal-600/30 text-emerald-300 border border-emerald-500/40 rounded-lg font-bold flex items-center justify-center gap-1.5 transition-all shadow-md disabled:opacity-50"
                >
                  <Plus className="w-3.5 h-3.5" /> Add Note to Global Graph
                </button>
              </form>
            </div>
          </div>
        )}

        {/* PROPOSALS TAB */}
        {activeTab === 'proposals' && (
          <div className="space-y-3">
            <div className="text-slate-400 text-[11px] leading-relaxed">
              Background agents generate candidate graph mutations. Accept or reject proposals to update the master graph.
            </div>

            {proposals.length === 0 ? (
              <div className="text-center py-8 text-slate-500 font-mono">No pending agent proposals.</div>
            ) : (
              proposals.map((prop) => (
                <div
                  key={prop.id}
                  className={`p-3.5 rounded-xl border space-y-2.5 transition-all shadow-md ${
                    prop.status === 'accepted'
                      ? 'bg-emerald-950/20 border-emerald-500/40'
                      : prop.status === 'rejected'
                      ? 'bg-red-950/20 border-red-500/30 opacity-60'
                      : 'bg-[#121824] border-cyan-500/30 hover:border-cyan-400/50'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-display font-semibold text-slate-200 flex items-center gap-1.5">
                      <Sparkles className="w-3.5 h-3.5 text-cyan-400" /> {prop.title}
                    </span>
                    <span className="text-[10px] font-mono text-cyan-400 bg-cyan-950/60 px-1.5 py-0.5 rounded border border-cyan-500/30 uppercase">
                      {prop.proposal_type}
                    </span>
                  </div>

                  <p className="text-slate-300 text-[11px] leading-relaxed">{prop.description}</p>

                  {prop.status === 'pending' ? (
                    <div className="flex items-center gap-2 pt-1">
                      <button
                        onClick={() => handleProposalAction(prop.id, 'accept')}
                        className="flex-1 py-1.5 bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-300 border border-emerald-500/40 rounded-lg flex items-center justify-center gap-1.5 font-bold transition-all"
                      >
                        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> Accept
                      </button>
                      <button
                        onClick={() => handleProposalAction(prop.id, 'reject')}
                        className="flex-1 py-1.5 bg-red-500/20 hover:bg-red-500/30 text-red-300 border border-red-500/40 rounded-lg flex items-center justify-center gap-1.5 font-bold transition-all"
                      >
                        <XCircle className="w-3.5 h-3.5 text-red-400" /> Reject
                      </button>
                    </div>
                  ) : (
                    <div className="text-[10px] font-mono font-bold uppercase tracking-wider text-slate-400 pt-1">
                      Status: {prop.status}
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        )}

        {/* FSRS TAB */}
        {activeTab === 'fsrs' && (
          <div className="space-y-3">
            <div className="bg-[#121824]/90 p-3.5 rounded-xl border border-emerald-500/30 space-y-2.5 shadow-lg">
              <div className="flex items-center justify-between">
                <span className="font-display font-semibold text-emerald-300 flex items-center gap-1.5">
                  <Clock className="w-4 h-4 text-emerald-400" /> Morning Spaced Review
                </span>
                <span className="text-[10px] font-mono text-emerald-400 bg-emerald-950/60 px-2 py-0.5 rounded-full border border-emerald-500/30 font-semibold">
                  12 Due Today
                </span>
              </div>
              <p className="text-slate-400 text-[11px] leading-relaxed">
                Memory decay queue based on py-fsrs algorithm. Targeted 15-minute graph recall quizzes.
              </p>
              <button
                onClick={() => alert('Starting 15-minute FSRS-DAG spaced repetition review session!')}
                className="w-full py-2 bg-gradient-to-r from-emerald-600/20 to-teal-600/20 hover:from-emerald-600/30 hover:to-teal-600/30 text-emerald-300 border border-emerald-500/40 rounded-lg font-bold flex items-center justify-center gap-2 transition-all shadow-md"
              >
                <Zap className="w-3.5 h-3.5 text-amber-400" /> Start 15m Review Quiz
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Active Agents Live Status Footer */}
      <div className="p-3.5 bg-[#090d16]/90 border-t border-white/10 space-y-2">
        <div className="text-[10px] font-mono text-slate-400 uppercase tracking-wider font-semibold">
          Active Background Agents
        </div>
        <div className="flex items-center justify-between text-[11px]">
          <span className="flex items-center gap-2 text-purple-300 font-medium">
            <span className="w-2 h-2 rounded-full bg-purple-400 animate-ping" /> Co-Scientist (Elo Arena)
          </span>
          <span className="text-slate-500 font-mono text-[10px]">Cycle 2/5</span>
        </div>
        <div className="flex items-center justify-between text-[11px]">
          <span className="flex items-center gap-2 text-cyan-300 font-medium">
            <span className="w-2 h-2 rounded-full bg-cyan-400" /> HippoRAG 2 (PPR Index)
          </span>
          <span className="text-slate-500 font-mono text-[10px]">Idle</span>
        </div>
      </div>
    </aside>
  );
};
