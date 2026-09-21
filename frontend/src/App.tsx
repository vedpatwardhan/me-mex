import React, { useEffect } from 'react';
import { useMemexStore } from './store/useMemexStore';
import { Navbar } from './components/Navbar';
import { LeftRail } from './components/LeftRail';
import { GraphCanvas } from './components/GraphCanvas';
import { RightDrawer } from './components/RightDrawer';
import { ReportStudio } from './components/ReportStudio';
import { VoiceAgentBar } from './components/VoiceAgentBar';

export const App: React.FC = () => {
  const { viewMode, fetchGraphData, fetchProjects, fetchProposals } = useMemexStore();

  useEffect(() => {
    fetchGraphData();
    fetchProjects();
    fetchProposals();
  }, []);

  return (
    <div className="flex flex-col h-screen w-screen overflow-hidden bg-[#0d1117] text-slate-100 font-sans">
      {/* Top Navbar */}
      <Navbar />

      {/* Main Workspace Body */}
      {viewMode === 'report' ? (
        <ReportStudio />
      ) : (
        <div className="flex flex-1 overflow-hidden relative">
          {/* Pane 1: Left Rail Intake & Proposals */}
          <LeftRail />

          {/* Pane 2: Center WebGL Graph Canvas */}
          <GraphCanvas />

          {/* Pane 3: Right Markdown Reader & Connection Drawer */}
          <RightDrawer />
        </div>
      )}

      {/* Grounded Voice Agent Floating Bar */}
      <VoiceAgentBar />
    </div>
  );
};

export default App;
