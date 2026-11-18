import React, { useEffect } from 'react';
import { useMemexStore } from './store/useMemexStore';
import { Navbar } from './components/Navbar';
import { GraphCanvas } from './components/GraphCanvas';
import { RecommendationsDock } from './components/RecommendationsDock';
import { VoiceRail } from './components/VoiceRail';

export const App: React.FC = () => {
  const { fetchGraphData, fetchProjects, activeProjectId } = useMemexStore();

  useEffect(() => {
    fetchGraphData();
    fetchProjects();
  }, []);

  return (
    <div className="flex flex-col h-screen w-screen overflow-hidden bg-[#090d16] text-slate-100 font-sans">
      {/* Top Project Tabs Navbar */}
      <Navbar />

      {/* Main Workspace Body (3-Pane Workspace) */}
      <div className="flex flex-1 overflow-hidden relative">
        <VoiceRail projectId={activeProjectId} />
        <GraphCanvas />
        <RecommendationsDock />
      </div>
    </div>
  );
};

export default App;
