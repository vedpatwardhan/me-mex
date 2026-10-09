import React, { useEffect } from 'react';
import { useMemexStore } from './store/useMemexStore';
import { voiceService } from './services/voiceService';
import { Navbar } from './components/Navbar';
import { LeftRail } from './components/LeftRail';
import { GraphCanvas } from './components/GraphCanvas';
import { RightDrawer } from './components/RightDrawer';

export const App: React.FC = () => {
  const { fetchGraphData, fetchProjects, fetchChatHistory } = useMemexStore();

  useEffect(() => {
    fetchGraphData();
    fetchProjects();
    fetchChatHistory();
    // Pre-warm Whisper-base.en and Kokoro-82M in the background
    voiceService.prewarm();
  }, []);

  return (
    <div className="flex flex-col h-screen w-screen overflow-hidden bg-[#090d16] text-slate-100 font-sans">
      {/* Top Project Tabs Navbar */}
      <Navbar />

      {/* Main Workspace Body (3-Pane Workspace) */}
      <div className="flex flex-1 overflow-hidden relative">
        {/* Pane 1: Project Chat Window + Observer */}
        <LeftRail />

        {/* Pane 2: Base of Knowledge Graph Visualizer */}
        <GraphCanvas />

        {/* Pane 3: Node Reader & Metadata Inspector Drawer */}
        <RightDrawer />
      </div>
    </div>
  );
};

export default App;
