import React from 'react';
import { useMemexStore } from '../store/useMemexStore';
import { Mic, Sparkles, Volume2, X } from 'lucide-react';

export const VoiceAgentBar: React.FC = () => {
  const { voiceResponse, isVoiceListening, voiceTranscript, simulateVoiceCommand } = useMemexStore();

  if (!voiceResponse && !isVoiceListening) return null;

  return (
    <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-40 max-w-xl w-full px-4">
      <div className="bg-[#161b22]/95 backdrop-blur-md border border-cyan-500/40 p-3.5 rounded-xl shadow-2xl flex items-center justify-between gap-3 text-xs">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-cyan-500/20 text-cyan-400 shrink-0">
            <Volume2 className="w-5 h-5 animate-pulse" />
          </div>
          <div>
            <div className="text-[10px] font-mono text-cyan-400 font-semibold uppercase tracking-wider flex items-center gap-1">
              <Sparkles className="w-3 h-3 text-amber-400" /> Grounded Voice Agent
            </div>
            <div className="text-slate-200 font-medium leading-snug">
              {voiceResponse || voiceTranscript || 'Listening to spoken insight...'}
            </div>
          </div>
        </div>

        <button
          onClick={() =>
            simulateVoiceCommand('Find papers contrasting PhysCtrl with skeletal flow steering')
          }
          className="px-3 py-1 bg-cyan-600/30 hover:bg-cyan-600/50 text-cyan-200 border border-cyan-500/40 rounded-lg shrink-0 font-medium transition-all"
        >
          Reply
        </button>
      </div>
    </div>
  );
};
