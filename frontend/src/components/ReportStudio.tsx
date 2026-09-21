import React from 'react';
import { useMemexStore } from '../store/useMemexStore';
import { FileText, Sparkles, ArrowLeft, Download, Layers } from 'lucide-react';

export const ReportStudio: React.FC = () => {
  const { currentReport, setViewMode, setSelectedNodeId, generateReport, nodes } = useMemexStore();

  const handleGenerateSample = () => {
    generateReport('Cross-Paradigm Scientific Synthesis', nodes.map((n) => n.id));
  };

  return (
    <div className="flex-1 h-[calc(100vh-3.5rem)] bg-[#0d1117] text-slate-100 p-6 overflow-y-auto select-none">
      {/* Report Studio Header */}
      <div className="max-w-4xl mx-auto space-y-6">
        <div className="flex items-center justify-between border-b border-[#30363d] pb-4">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setViewMode('global')}
              className="p-2 text-slate-400 hover:text-slate-200 bg-[#161b22] border border-[#30363d] rounded-lg transition-all flex items-center gap-1.5 text-xs"
            >
              <ArrowLeft className="w-4 h-4" /> Back to Graph
            </button>
            <div>
              <h1 className="text-lg font-bold text-slate-100 flex items-center gap-2">
                <FileText className="w-5 h-5 text-purple-400" /> Interactive Node-Grounded Report Studio
              </h1>
              <p className="text-xs text-slate-400">
                Synthesized markdown report with color-coded provenance phrase highlights mapped directly to graph nodes.
              </p>
            </div>
          </div>

          <button
            onClick={handleGenerateSample}
            className="px-3 py-1.5 bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white text-xs font-semibold rounded-lg border border-purple-400/30 flex items-center gap-1.5 transition-all shadow-lg shadow-purple-900/20"
          >
            <Sparkles className="w-4 h-4" /> Generate Fresh Report
          </button>
        </div>

        {/* Report Content Panel */}
        {!currentReport ? (
          <div className="bg-[#161b22] border border-[#30363d] rounded-xl p-12 text-center space-y-4">
            <Layers className="w-12 h-12 text-purple-400 mx-auto animate-pulse" />
            <div className="space-y-1">
              <h3 className="text-base font-semibold text-slate-200">No Active Report Generated</h3>
              <p className="text-xs text-slate-400 max-w-md mx-auto">
                Click "Generate Fresh Report" or select nodes on the graph canvas to generate an interactive node-grounded Markdown synthesis.
              </p>
            </div>
            <button
              onClick={handleGenerateSample}
              className="px-4 py-2 bg-purple-600 hover:bg-purple-500 text-white text-xs font-semibold rounded-lg shadow transition-all"
            >
              Generate Synthesis Report
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Main Interactive Markdown Document */}
            <div className="lg:col-span-2 bg-[#161b22] border border-[#30363d] rounded-xl p-6 space-y-4 shadow-xl">
              <div className="flex items-center justify-between border-b border-[#30363d] pb-3">
                <span className="text-xs font-mono text-purple-400 font-semibold uppercase">
                  ID: {currentReport.id}
                </span>
                <span className="text-xs font-mono text-slate-400">
                  {new Date(currentReport.created_at).toLocaleString()}
                </span>
              </div>

              {/* Rendered Markdown Body with Interactive Provenance Badges */}
              <div className="prose prose-invert max-w-none text-xs text-slate-200 leading-relaxed font-mono space-y-4 whitespace-pre-wrap">
                {currentReport.markdown_content}
              </div>
            </div>

            {/* Right Interactive Provenance Map Panel */}
            <div className="space-y-4">
              <div className="bg-[#161b22] border border-[#30363d] rounded-xl p-4 space-y-3">
                <h3 className="text-xs font-bold text-slate-200 uppercase tracking-wider flex items-center gap-1.5">
                  <Sparkles className="w-3.5 h-3.5 text-amber-400" /> Grounded Node Mappings
                </h3>
                <p className="text-[11px] text-slate-400 leading-relaxed">
                  Click any mapped phrase below to highlight its source node on the force-directed canvas.
                </p>

                <div className="space-y-2 pt-1">
                  {Object.entries(currentReport.provenance_mappings).map(([phrase, nodeId], idx) => {
                    const mappedNode = nodes.find((n) => n.id === nodeId);
                    return (
                      <div
                        key={idx}
                        onClick={() => {
                          setSelectedNodeId(nodeId);
                          setViewMode('global');
                        }}
                        className="p-2.5 rounded-lg bg-[#0d1117] border border-[#30363d] hover:border-purple-500/50 cursor-pointer transition-all space-y-1 group"
                      >
                        <div className="flex items-center justify-between">
                          <span className="text-[10px] font-mono font-semibold text-purple-400 group-hover:underline">
                            Source: {nodeId}
                          </span>
                          <span className="text-[9px] font-mono text-slate-500 uppercase">
                            {mappedNode?.node_type || 'node'}
                          </span>
                        </div>
                        <div className="text-[11px] text-slate-200 font-medium leading-snug">
                          "{phrase}"
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
