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
  Plus
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
    <aside className="w-80 bg-[#161b22] border-r border-[#30363d] flex flex-col h-[calc(100vh-3.5rem)] text-xs select-none">
      {/* Pane 1 Sub-Navigation Tabs */}
      <div className="flex items-center border-b border-[#30363d] bg-[#0d1117] p-1 gap-1">
        <button
          onClick={() => setActiveTab('intake')}
          className={`flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-md font-medium transition-all ${
            activeTab === 'intake'
              ? 'bg-[#21262d] text-amber-400 border border-[#30363d]'
              : 'text-slate-400 hover:text-slate-200'
          }`}
        >
          <Download className="w-3.5 h-3.5" />
          <span>Intake</span>
        </button>

        <button
          onClick={() => setActiveTab('proposals')}
          className={`flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-md font-medium transition-all relative ${
            activeTab === 'proposals'
              ? 'bg-[#21262d] text-cyan-400 border border-[#30363d]'
              : 'text-slate-400 hover:text-slate-200'
          }`}
        >
          <Inbox className="w-3.5 h-3.5" />
          <span>Proposals</span>
          {proposals.filter(p => p.status === 'pending').length > 0 && (
            <span className="w-4 h-4 bg-cyan-500 text-black font-bold text-[10px] rounded-full flex items-center justify-center">
              {proposals.filter(p => p.status === 'pending').length}
            </span>
          )}
        </button>

        <button
          onClick={() => setActiveTab('fsrs')}
          className={`flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-md font-medium transition-all ${
            activeTab === 'fsrs'
              ? 'bg-[#21262d] text-emerald-400 border border-[#30363d]'
              : 'text-slate-400 hover:text-slate-200'
          }`}
        >
          <BrainCircuit className="w-3.5 h-3.5" />
          <span>FSRS</span>
        </button>
      </div>

      {/* Pane 1 Scrollable Content Area */}
      <div className="flex-1 overflow-y-auto p-3 space-y-4">
        {/* INTAKE TAB */}
        {activeTab === 'intake' && (
          <div className="space-y-4">
            {/* Voice Epiphany Card */}
            <div className="bg-[#0d1117] p-3 rounded-lg border border-amber-500/30 space-y-2">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-amber-300 flex items-center gap-1.5">
                  <Mic className="w-3.5 h-3.5 text-amber-400" /> Spoken Insight Stream
                </span>
                <span className="text-[10px] text-slate-400 font-mono">Whisper AI</span>
              </div>
              <p className="text-slate-400 text-[11px] leading-relaxed">
                Speak insights or thoughts. Fast-Whisper transcribes and extracts atomic nodes into the Global Graph.
              </p>
              <button
                onClick={() => simulateVoiceCommand('Joint limits should constrain latent flow field directly during action denoising.')}
                disabled={isLoading}
                className="w-full py-2 bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 border border-amber-500/40 rounded-md font-semibold flex items-center justify-center gap-2 transition-all"
              >
                <Mic className={`w-3.5 h-3.5 ${isVoiceListening ? 'animate-bounce text-red-400' : ''}`} />
                <span>{isVoiceListening ? 'Listening & Extracting...' : 'Record Voice Note'}</span>
              </button>
            </div>

            {/* URL Web Link Snapshot Card */}
            <div className="bg-[#0d1117] p-3 rounded-lg border border-[#30363d] space-y-2">
              <span className="font-semibold text-slate-200 flex items-center gap-1.5">
                <Link className="w-3.5 h-3.5 text-cyan-400" /> Web Link / Tweet / arXiv Entry
              </span>
              <form onSubmit={onUrlSubmit} className="space-y-2">
                <input
                  type="url"
                  placeholder="Paste URL, tweet, or arXiv DOI..."
                  value={urlInput}
                  onChange={(e) => setUrlInput(e.target.value)}
                  className="w-full bg-[#161b22] text-slate-200 p-2 rounded border border-[#30363d] focus:border-cyan-400 focus:outline-none text-xs"
                />
                <button
                  type="submit"
                  disabled={isLoading || !urlInput.trim()}
                  className="w-full py-1.5 bg-cyan-600/20 hover:bg-cyan-600/30 text-cyan-300 border border-cyan-500/30 rounded font-medium flex items-center justify-center gap-1.5 transition-all disabled:opacity-50"
                >
                  <Plus className="w-3.5 h-3.5" /> Fetch & Snapshot HTML
                </button>
              </form>
            </div>

            {/* Raw File / Text Note Intake Card */}
            <div className="bg-[#0d1117] p-3 rounded-lg border border-[#30363d] space-y-2">
              <span className="font-semibold text-slate-200 flex items-center gap-1.5">
                <FileText className="w-3.5 h-3.5 text-emerald-400" /> Quick Text Note / Markdown
              </span>
              <form onSubmit={onTextSubmit} className="space-y-2">
                <textarea
                  rows={3}
                  placeholder="Type an insight, hypothesis premise, or markdown excerpt..."
                  value={textInput}
                  onChange={(e) => setTextInput(e.target.value)}
                  className="w-full bg-[#161b22] text-slate-200 p-2 rounded border border-[#30363d] focus:border-emerald-400 focus:outline-none text-xs resize-none"
                />
                <button
                  type="submit"
                  disabled={isLoading || !textInput.trim()}
                  className="w-full py-1.5 bg-emerald-600/20 hover:bg-emerald-600/30 text-emerald-300 border border-emerald-500/30 rounded font-medium flex items-center justify-center gap-1.5 transition-all disabled:opacity-50"
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
              <div className="text-center py-6 text-slate-500 font-mono">No pending agent proposals.</div>
            ) : (
              proposals.map((prop) => (
                <div
                  key={prop.id}
                  className={`p-3 rounded-lg border space-y-2 transition-all ${
                    prop.status === 'accepted'
                      ? 'bg-emerald-950/20 border-emerald-500/30'
                      : prop.status === 'rejected'
                      ? 'bg-red-950/20 border-red-500/30 opacity-60'
                      : 'bg-[#0d1117] border-cyan-500/30'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-slate-200 flex items-center gap-1.5">
                      <Sparkles className="w-3.5 h-3.5 text-cyan-400" /> {prop.title}
                    </span>
                    <span className="text-[10px] font-mono text-slate-400 uppercase">{prop.proposal_type}</span>
                  </div>

                  <p className="text-slate-300 text-[11px] leading-normal">{prop.description}</p>

                  {prop.status === 'pending' ? (
                    <div className="flex items-center gap-2 pt-1">
                      <button
                        onClick={() => handleProposalAction(prop.id, 'accept')}
                        className="flex-1 py-1 bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-300 border border-emerald-500/40 rounded flex items-center justify-center gap-1 font-medium transition-all"
                      >
                        <CheckCircle2 className="w-3.5 h-3.5" /> Accept
                      </button>
                      <button
                        onClick={() => handleProposalAction(prop.id, 'reject')}
                        className="flex-1 py-1 bg-red-500/20 hover:bg-red-500/30 text-red-300 border border-red-500/40 rounded flex items-center justify-center gap-1 font-medium transition-all"
                      >
                        <XCircle className="w-3.5 h-3.5" /> Reject
                      </button>
                    </div>
                  ) : (
                    <div className="text-[10px] font-mono font-semibold uppercase tracking-wider text-slate-400 pt-1">
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
            <div className="bg-[#0d1117] p-3 rounded-lg border border-emerald-500/30 space-y-2">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-emerald-300 flex items-center gap-1.5">
                  <Clock className="w-3.5 h-3.5 text-emerald-400" /> Morning Spaced Review
                </span>
                <span className="text-[10px] font-mono text-emerald-400 bg-emerald-950/40 px-1.5 py-0.5 rounded border border-emerald-500/30">
                  12 Due Today
                </span>
              </div>
              <p className="text-slate-400 text-[11px] leading-relaxed">
                Memory decay queue based on py-fsrs algorithm. Targeted 15-minute graph recall quizzes.
              </p>
              <button
                onClick={() => alert('Starting 15-minute FSRS-DAG spaced repetition review session!')}
                className="w-full py-2 bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-300 border border-emerald-500/40 rounded-md font-semibold flex items-center justify-center gap-2 transition-all"
              >
                <Zap className="w-3.5 h-3.5" /> Start 15m Review Quiz
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Active Agents Live Status Footer */}
      <div className="p-3 bg-[#0d1117] border-t border-[#30363d] space-y-1.5">
        <div className="text-[10px] font-mono text-slate-400 uppercase tracking-wider font-semibold">
          Active Background Agents
        </div>
        <div className="flex items-center justify-between text-[11px]">
          <span className="flex items-center gap-1.5 text-purple-400">
            <span className="w-2 h-2 rounded-full bg-purple-500 animate-ping" /> Co-Scientist (Elo Arena)
          </span>
          <span className="text-slate-500 font-mono">Cycle 2/5</span>
        </div>
        <div className="flex items-center justify-between text-[11px]">
          <span className="flex items-center gap-1.5 text-cyan-400">
            <span className="w-2 h-2 rounded-full bg-cyan-500" /> HippoRAG 2 (PPR Index)
          </span>
          <span className="text-slate-500 font-mono">Idle</span>
        </div>
      </div>
    </aside>
  );
};
