import { useCallback, useEffect, useRef, useState } from 'react';

import type { DockItem } from '../components/RecommendationsDock';
import {
  fetchApprovals,
  fetchJobHistory,
  fetchJobs,
  fetchNudges,
  revertTurn,
  resumeApproval,
  streamAgentTurn,
  controlJob as controlJobRequest,
} from '../services/dockStreamService';
import type { JobAction } from '../services/dockStreamService';
import type { VoiceSession } from '../services/voiceSession';
import { reconcileQueueItems } from '../utils/dockQueueSort';
import {
  applyStreamEvent,
  emptyDockStreamState,
  flattenDockEvents,
  isGraphWriteEvent,
  isScopeCommittedEvent,
  resetTurnState,
} from '../utils/dockStreamReducer';

export function useDockState(
  projectId: string,
  threadId: string,
  onScopeCommitted?: () => void,
  onGraphCommitted?: () => void,
) {
  const [streamState, setStreamState] = useState(emptyDockStreamState);
  const [projectScope, setProjectScope] = useState('');
  const [voiceSession, setVoiceSession] = useState<VoiceSession | null>(null);
  const [pendingApprovals, setPendingApprovals] = useState<Set<string>>(() => new Set());
  const [pendingJobActions, setPendingJobActions] = useState<Set<string>>(() => new Set());

  const { latestReply, latestUserText, items, turns, jobHistory } = streamState;

  const refreshDebounce = useRef<ReturnType<typeof setTimeout> | null>(null);

  const refreshApprovals = useCallback(async () => {
    const [approvals, jobs, nudges] = await Promise.all([
      fetchApprovals(projectId, threadId),
      fetchJobs(projectId, threadId),
      fetchNudges(projectId),
    ]);
    setStreamState((s) => ({
      ...s,
      items: reconcileQueueItems([...approvals, ...jobs], nudges, s.items),
    }));
    return approvals;
  }, [projectId, threadId]);

  const reconcilePendingApprovals = useCallback(async () => {
    try {
      const approvals = await refreshApprovals();
      const pendingIds = new Set(approvals.map((item) => item.id));
      setPendingApprovals((current) => {
        const next = new Set(current);
        for (const id of current) {
          if (!pendingIds.has(id)) next.delete(id);
        }
        return next;
      });
    } catch (error) {
      console.error('Failed to refresh approvals after approval action:', error);
      setPendingApprovals(new Set());
    }
  }, [refreshApprovals]);

  const refreshJobHistory = useCallback(async () => {
    const rows = await fetchJobHistory(threadId);
    setStreamState((s) => ({ ...s, jobHistory: rows }));
  }, [threadId]);

  useEffect(() => {
    void refreshApprovals();
    void refreshJobHistory();
  }, [refreshApprovals, refreshJobHistory]);

  const scheduleRefreshApprovals = useCallback(() => {
    if (refreshDebounce.current) clearTimeout(refreshDebounce.current);
    refreshDebounce.current = setTimeout(() => {
      void refreshApprovals();
    }, 300);
  }, [refreshApprovals]);

  const applyStreamEventToState = useCallback(
    (ev: Record<string, unknown>) => {
      for (const event of flattenDockEvents(ev)) {
        setStreamState((prev) => applyStreamEvent(prev, event));
        const type = event.type as string | undefined;
        if (isScopeCommittedEvent(event)) onScopeCommitted?.();
        if (isGraphWriteEvent(event)) onGraphCommitted?.();
        const job = event.job as Record<string, unknown> | undefined;
        if (type === 'turn_end' || type === 'turn_reverted') {
          void reconcilePendingApprovals();
          void refreshJobHistory();
        }
        if (type === 'turn_reverted') onGraphCommitted?.();
        const shouldRefresh =
          type === 'turn_end' ||
          type === 'recommendation' ||
          type === 'approval' ||
          type === 'awaiting_approval' ||
          (type === 'job_update' && job?.status === 'awaiting_approval');
        if (shouldRefresh) scheduleRefreshApprovals();
      }
    },
    [
      scheduleRefreshApprovals,
      onScopeCommitted,
      onGraphCommitted,
      reconcilePendingApprovals,
      refreshJobHistory,
    ],
  );

  const beginTurn = useCallback((userText: string) => {
    setStreamState((prev) => resetTurnState(prev, userText));
  }, []);

  const runTextTurn = useCallback(
    async (text: string, contextJson: Record<string, unknown>) => {
      beginTurn(text);
      await streamAgentTurn(
        { text, thread_id: threadId, context_json: contextJson },
        {
          onEvent: (ev) => applyStreamEventToState(ev),
          onTurnEnd: () => {
            void reconcilePendingApprovals();
          },
        },
      );
    },
    [threadId, reconcilePendingApprovals, applyStreamEventToState, beginTurn],
  );

  const voiceCtx = useCallback(
    (contextJson: Record<string, unknown>) => ({
      active_project_id: String(contextJson.active_project_id || projectId),
      muted: false,
      custom_fields: (contextJson.custom_fields as Record<string, string>) || {},
      selected_node_ids: (contextJson.selected_node_ids as string[]) || [],
      thread_id: threadId,
    }),
    [projectId, threadId],
  );

  const approve = useCallback(
    async (approvalId: string, contextJson: Record<string, unknown>) => {
      setPendingApprovals((current) => new Set(current).add(approvalId));
      let result: Record<string, unknown> | undefined;
      try {
        if (voiceSession?.isReady()) {
          await voiceSession.sendApproval(approvalId, 'approve', voiceCtx(contextJson));
          return;
        }
        result = await resumeApproval({
          thread_id: threadId,
          approval_id: approvalId,
          action: 'approve',
          context_json: {
            ...contextJson,
            turn_id: `turn_${Date.now().toString(36)}`,
          },
        });
        if (result?.scope_committed === true) onScopeCommitted?.();
        if (result?.graph_write === true) onGraphCommitted?.();
        setStreamState((s) => ({
          ...s,
          latestReply: typeof result?.reply === 'string' ? result.reply : s.latestReply,
          items: s.items.filter((i) => i.id !== approvalId),
        }));
        await refreshApprovals();
        setPendingApprovals((current) => {
          const next = new Set(current);
          next.delete(approvalId);
          return next;
        });
      } catch (error) {
        setPendingApprovals((current) => {
          const next = new Set(current);
          next.delete(approvalId);
          return next;
        });
        throw error;
      }
    },
    [threadId, refreshApprovals, voiceSession, voiceCtx, onScopeCommitted, onGraphCommitted],
  );

  const dismiss = useCallback(
    async (approvalId: string, contextJson: Record<string, unknown>) => {
      if (voiceSession?.isReady()) {
        await voiceSession.sendApproval(approvalId, 'cancel', voiceCtx(contextJson));
      } else {
        await resumeApproval({
          thread_id: threadId,
          approval_id: approvalId,
          action: 'dismiss',
          context_json: contextJson,
        });
      }
      setStreamState((s) => ({
        ...s,
        items: s.items.filter((i) => i.id !== approvalId),
      }));
    },
    [threadId, voiceSession, voiceCtx],
  );

  const runJobAction = useCallback(
    async (jobId: string, action: JobAction) => {
      setPendingJobActions((current) => new Set(current).add(jobId));
      try {
        const job = await controlJobRequest(projectId, threadId, jobId, action);
        if (action === 'delete') {
          setStreamState((state) => ({
            ...state,
            items: state.items.filter((item) => item.id !== jobId),
          }));
        } else {
          setStreamState((state) => applyStreamEvent(state, { type: 'job_update', job }));
        }
      } catch (error) {
        console.error(`Failed to ${action} job ${jobId}:`, error);
      } finally {
        setPendingJobActions((current) => {
          const next = new Set(current);
          next.delete(jobId);
          return next;
        });
      }
    },
    [projectId, threadId],
  );

  const pauseJob = useCallback((jobId: string) => runJobAction(jobId, 'pause'), [runJobAction]);
  const resumeJob = useCallback((jobId: string) => runJobAction(jobId, 'resume'), [runJobAction]);
  const cancelJob = useCallback((jobId: string) => runJobAction(jobId, 'cancel'), [runJobAction]);
  const deleteJob = useCallback((jobId: string) => runJobAction(jobId, 'delete'), [runJobAction]);

  const revertUserTurn = useCallback(
    async (turnId: string) => {
      const result = await revertTurn(projectId, threadId, turnId);
      if (result.ok) {
        applyStreamEventToState({
          type: 'turn_reverted',
          turn_id: turnId,
          removed_turn_ids: result.removed_turn_ids || [],
        });
        await refreshApprovals();
        onGraphCommitted?.();
      }
    },
    [projectId, threadId, applyStreamEventToState, refreshApprovals, onGraphCommitted],
  );

  return {
    latestReply,
    latestUserText,
    items,
    turns,
    jobHistory,
    pendingApprovals,
    pendingJobActions,
    projectScope,
    setProjectScope,
    runTextTurn,
    approve,
    dismiss,
    pauseJob,
    resumeJob,
    cancelJob,
    deleteJob,
    refreshApprovals,
    refreshJobHistory,
    revertUserTurn,
    applyStreamEvent: applyStreamEventToState,
    beginTurn,
    setVoiceSession,
    voiceSession,
  };
}
