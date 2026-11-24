import React, { useCallback, useEffect, useMemo } from 'react';
import { useMemexStore } from './store/useMemexStore';
import { Navbar } from './components/Navbar';
import { GraphCanvas } from './components/GraphCanvas';
import { RecommendationsDock } from './components/RecommendationsDock';
import { VoiceRail } from './components/VoiceRail';
import { RightDrawer } from './components/RightDrawer';
import { useDockState } from './hooks/useDockState';

export const App: React.FC = () => {
  const { fetchGraphData, fetchProjects, activeProjectId, selectedNodeId, projects } =
    useMemexStore();

  const threadId = useMemo(() => `voice-${activeProjectId}`, [activeProjectId]);
  const refreshProjects = useCallback(() => {
    void fetchProjects();
  }, [fetchProjects]);
  const refreshGraph = useCallback(() => {
    void fetchGraphData();
  }, [fetchGraphData]);
  const dock = useDockState(activeProjectId, threadId, refreshProjects, refreshGraph);

  const projectScope = projects.find((p) => p.id === activeProjectId)?.description || '';

  useEffect(() => {
    fetchGraphData();
    fetchProjects();
  }, []);

  useEffect(() => {
    dock.setProjectScope(projectScope);
  }, [projectScope]);

  const contextJson = useMemo(
    () => ({
      active_project_id: activeProjectId,
      selected_node_ids: selectedNodeId ? [selectedNodeId] : [],
    }),
    [activeProjectId, selectedNodeId],
  );

  return (
    <div className="flex flex-col h-screen w-screen overflow-hidden bg-[#090d16] text-slate-100 font-sans">
      <Navbar />
      <div className="flex flex-1 overflow-hidden relative">
        <VoiceRail
          projectId={activeProjectId}
          selectedNodeId={selectedNodeId}
          projectIntroduction={projectScope}
          onDockStreamEvent={dock.applyStreamEvent}
          onVoiceSession={dock.setVoiceSession}
        />
        <GraphCanvas />
        <RightDrawer onGraphChange={() => void dock.refreshApprovals()} />
        <RecommendationsDock
          latestReply={dock.latestReply}
          latestUserText={dock.latestUserText}
          turns={dock.turns}
          jobHistory={dock.jobHistory}
          items={dock.items}
          pendingApprovals={dock.pendingApprovals}
          pendingJobActions={dock.pendingJobActions}
          projectScope={dock.projectScope || projectScope}
          onRevertTurn={(id) => void dock.revertUserTurn(id)}
          onApprove={(id) => void dock.approve(id, contextJson)}
          onDismiss={(id) => void dock.dismiss(id, contextJson)}
          onPauseJob={(id) => void dock.pauseJob(id)}
          onResumeJob={(id) => void dock.resumeJob(id)}
          onCancelJob={(id) => void dock.cancelJob(id)}
          onDeleteJob={(id) => void dock.deleteJob(id)}
        />
      </div>
    </div>
  );
};

export default App;
