import React, { useState, useRef, useEffect } from 'react';
import { useMemexStore } from '../store/useMemexStore';
import { voiceService } from '../services/voiceService';
import {
  Send,
  Mic,
  Sparkles,
  Bot,
  User,
  Paperclip,
  Activity,
  FileText,
  Tag,
  Radio,
  Copy,
  Check,
  Trash2
} from 'lucide-react';

export const LeftRail: React.FC = () => {
  const {
    activeProjectId,
    projects,
    chatHistory,
    thinkingState,
    sendMessage,
    setSelectedNodeId,
    setVoiceListening,
    isVoiceListening,
    isLoading,
    clearChatHistory
  } = useMemexStore();

  const [inputVal, setInputVal] = useState('');
  const [copiedMsgId, setCopiedMsgId] = useState<string | null>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const activeProject = projects.find((p) => p.id === activeProjectId);
  const messages = chatHistory[activeProjectId] || [];

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, thinkingState]);

  const handleCopy = (msgId: string, text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedMsgId(msgId);
    setTimeout(() => {
      setCopiedMsgId((prev) => (prev === msgId ? null : prev));
    }, 2000);
  };

  const handleSend = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!inputVal.trim() || isLoading) return;
    sendMessage(inputVal.trim(), false);
    setInputVal('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleVoiceRecord = async () => {
    if (isVoiceListening) {
      setVoiceListening(false);
      const transcribedText = await voiceService.stopRecordingAndTranscribe();
      if (transcribedText.trim()) {
        setInputVal((prev) => (prev ? `${prev} ${transcribedText.trim()}` : transcribedText.trim()));
        if (textareaRef.current) {
          textareaRef.current.focus();
        }
      }
      return;
    }

    const started = await voiceService.startRecording();
    if (started) {
      setVoiceListening(true);
    }
  };

  return (
    <aside className="w-[440px] glass-panel border-r border-white/10 flex flex-col h-[calc(100vh-4rem)] text-xs select-none z-20 shadow-2xl shrink-0">
      {/* Scope Header */}
      <div className="p-4 border-b border-white/10 bg-[#090d16]/80 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <span className="w-2.5 h-2.5 rounded-full bg-cyan-400 animate-pulse shadow-glow-cyan" />
          <span className="font-display font-bold text-slate-100 text-sm tracking-tight">
            {activeProjectId === 'global' ? 'Global Master Chat' : activeProject?.name || activeProjectId}
          </span>
        </div>
        <div className="flex items-center gap-2">
          {messages.length > 0 && (
            <button
              type="button"
              onClick={() => {
                if (window.confirm(`Clear chat history for ${activeProjectId === 'global' ? 'Global Master Chat' : activeProject?.name || activeProjectId}?`)) {
                  clearChatHistory();
                }
              }}
              className="text-[11px] font-mono text-slate-400 hover:text-red-300 hover:bg-red-950/40 px-2 py-1 rounded-lg border border-transparent hover:border-red-500/30 transition-colors flex items-center gap-1"
              title="Clear project chat history"
            >
              <Trash2 className="w-3 h-3 text-slate-400 hover:text-red-400" />
              <span>Clear</span>
            </button>
          )}
          <span className="text-[11px] font-mono text-slate-400 bg-slate-800/80 px-2.5 py-1 rounded-full border border-slate-700/60 font-medium">
            {messages.length} messages
          </span>
        </div>
      </div>

      {/* Agent Thinking & Traversal Live Indicator Bar */}
      {thinkingState.isThinking ? (
        <div className="bg-gradient-to-r from-purple-950/40 via-indigo-950/40 to-cyan-950/40 border-b border-purple-500/30 p-3 flex items-center justify-between gap-2 shadow-inner">
          <div className="flex items-center gap-2 text-purple-300 font-mono text-[11px] truncate">
            <Activity className="w-4 h-4 text-purple-400 animate-spin shrink-0" />
            <span className="truncate font-medium">{thinkingState.currentAction}</span>
          </div>
        </div>
      ) : (
        <div className="bg-[#090d16]/60 border-b border-white/5 px-4 py-2 flex items-center justify-between text-[11px] text-slate-400 font-mono">
          <span className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-emerald-400" /> Grounded Agent Observer
          </span>
          <span className="text-slate-500">Live Memory Sync</span>
        </div>
      )}

      {/* Chat Messages Thread */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex flex-col space-y-1.5 ${
              msg.sender === 'user' ? 'items-end' : 'items-start'
            } group`}
          >
            {/* Sender Label & Actions Header */}
            <div className="flex items-center gap-1.5 text-[11px] font-mono text-slate-400 px-1 w-full justify-between">
              <div className="flex items-center gap-1.5">
                {msg.sender === 'user' ? (
                  <>
                    <User className="w-3.5 h-3.5 text-emerald-400" />
                    <span className="font-medium text-slate-300">User</span>
                    {msg.is_voice && (
                      <span className="text-[9px] text-amber-300 bg-amber-950/60 px-2 py-0.5 rounded-full border border-amber-500/30 font-bold flex items-center gap-1">
                        <Radio className="w-2.5 h-2.5 animate-pulse" /> VOICE
                      </span>
                    )}
                  </>
                ) : (
                  <>
                    <Bot className="w-3.5 h-3.5 text-cyan-400" />
                    <span className="text-cyan-400 font-bold">Memex Agent</span>
                  </>
                )}
              </div>

              {/* Copy Message Button */}
              <button
                type="button"
                onClick={() => handleCopy(msg.id, msg.text)}
                className="opacity-60 group-hover:opacity-100 hover:text-slate-200 hover:bg-white/10 p-1 rounded-md transition-all text-slate-400 flex items-center gap-1 text-[10px]"
                title="Copy message text"
              >
                {copiedMsgId === msg.id ? (
                  <>
                    <Check className="w-3 h-3 text-emerald-400" />
                    <span className="text-emerald-400 font-mono text-[9px]">Copied</span>
                  </>
                ) : (
                  <>
                    <Copy className="w-3 h-3" />
                    <span className="hidden group-hover:inline font-mono text-[9px]">Copy</span>
                  </>
                )}
              </button>
            </div>

            {/* Message Bubble Content */}
            <div
              className={`p-4 rounded-2xl max-w-[92%] text-xs leading-relaxed font-medium shadow-md ${
                msg.sender === 'user'
                  ? 'bg-gradient-to-r from-emerald-600/25 to-teal-600/25 text-emerald-100 border border-emerald-500/40 rounded-tr-none'
                  : 'bg-[#121824] text-slate-200 border border-white/10 rounded-tl-none space-y-3'
              }`}
            >
              <div className="whitespace-pre-wrap select-text">{msg.text}</div>

              {/* Grounded Node Chips */}
              {msg.grounded_node_ids && msg.grounded_node_ids.length > 0 && (
                <div className="pt-2.5 border-t border-white/10 flex flex-wrap gap-1.5">
                  <span className="text-[10px] font-mono text-slate-400 font-semibold w-full flex items-center gap-1">
                    <Sparkles className="w-3.5 h-3.5 text-amber-400" /> Grounded Subgraph Nodes:
                  </span>
                  {msg.grounded_node_ids.map((nid) => (
                    <button
                      key={nid}
                      onClick={() => setSelectedNodeId(nid)}
                      className="px-2.5 py-1 rounded-lg text-[10px] font-mono font-semibold bg-cyan-950/80 text-cyan-300 border border-cyan-500/40 hover:bg-cyan-900/80 transition-colors flex items-center gap-1.5 shadow-sm"
                    >
                      <Tag className="w-3 h-3 text-cyan-400" /> {nid}
                    </button>
                  ))}
                </div>
              )}

              {/* Inline Generated Report Card */}
              {msg.report && (
                <div className="mt-2 bg-[#090d16] p-4 rounded-xl border border-purple-500/40 space-y-2.5 shadow-lg">
                  <div className="flex items-center justify-between">
                    <span className="font-display font-bold text-purple-300 flex items-center gap-1.5 text-xs">
                      <FileText className="w-4 h-4 text-purple-400" /> {msg.report.title}
                    </span>
                  </div>
                  <div className="text-[11px] font-mono text-slate-300 line-clamp-4 leading-relaxed bg-[#121824] p-3 rounded-lg border border-slate-800">
                    {msg.report.markdown_content}
                  </div>
                </div>
              )}
            </div>
          </div>
        ))}
        <div ref={chatEndRef} />
      </div>

      {/* Spacious Unified Input Bar (Bottom) */}
      <div className="p-4 bg-[#090d16]/95 border-t border-white/10">
        <form onSubmit={handleSend} className="space-y-2">
          <div className="relative flex flex-col bg-[#121824] rounded-2xl border border-slate-700/80 focus-within:border-cyan-400/80 focus-within:ring-1 focus-within:ring-cyan-400/80 shadow-2xl transition-all p-3">
            {/* Multi-line Taller Textarea Input */}
            <textarea
              ref={textareaRef}
              rows={4}
              placeholder="Ask a question, paste URL/arXiv DOI, state an insight, or ask for a report..."
              value={inputVal}
              onChange={(e) => setInputVal(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={isLoading}
              className="w-full min-h-[96px] max-h-[220px] bg-transparent text-slate-200 px-2 py-1 text-xs focus:outline-none placeholder-slate-500 font-medium leading-relaxed resize-y font-sans"
            />

            {/* Action Buttons Row */}
            <div className="flex items-center justify-between pt-2.5 border-t border-white/5">
              <div className="flex items-center gap-1.5">
                <button
                  type="button"
                  onClick={() => alert('Select PDF or Markdown file to attach...')}
                  className="p-2 text-slate-400 hover:text-slate-200 hover:bg-white/5 rounded-lg transition-colors flex items-center gap-1.5 text-[11px] font-medium"
                  title="Attach File or URL"
                >
                  <Paperclip className="w-3.5 h-3.5" />
                  <span>Attach</span>
                </button>

                <button
                  type="button"
                  onClick={handleVoiceRecord}
                  className={`p-2 rounded-lg transition-all flex items-center gap-1.5 text-[11px] font-semibold ${
                    isVoiceListening
                      ? 'text-red-400 bg-red-500/20 border border-red-500/50 animate-pulse'
                      : 'text-amber-400 hover:text-amber-300 hover:bg-amber-500/10'
                  }`}
                  title="Record Voice Note"
                >
                  <Mic className={`w-3.5 h-3.5 ${isVoiceListening ? 'animate-bounce' : ''}`} />
                  <span>{isVoiceListening ? 'Recording...' : 'Voice'}</span>
                </button>
              </div>

              {/* Send Button */}
              <button
                type="submit"
                disabled={!inputVal.trim() || isLoading}
                className="px-4 py-2 bg-gradient-to-r from-cyan-500 via-teal-500 to-emerald-500 hover:from-cyan-400 hover:to-emerald-400 text-slate-950 font-bold text-xs rounded-xl transition-all shadow-md disabled:opacity-40 flex items-center gap-1.5"
              >
                <span>Send</span>
                <Send className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        </form>
      </div>
    </aside>
  );
};
