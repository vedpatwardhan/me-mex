import { useCallback, useEffect, useRef, useState } from 'react';

import type { DockItem } from '../components/RecommendationsDock';
import {
  fetchApprovals,
  fetchNudges,
  resumeApproval,
  streamAgentTurn,
} from '../services/dockStreamService';
import type { VoiceSession } from '../services/voiceSession';
import { reconcileQueueItems } from '../utils/dockQueueSort';
import {
  applyStreamEvent,
  emptyDockStreamState,
  flattenDockEvents,
  isScopeCommittedEvent,
  resetTurnState,
} from '../utils/dockStreamReducer';

export function useDockState(
  projectId: string,
  threadId: string,
  onScopeCommitted?: () => void,
) {
  const [streamState, setStreamState] = useState(emptyDockStreamState);
  const [projectScope, setProjectScope] = useState('');
  const [voiceSession, setVoiceSession] = useState<VoiceSession | null>(null);
  const [pendingApprovals, setPendingApprovals] = useState<Set<string>>(() => new Set());

  const { latestReply, latestUserText, items } = streamState;

  const refreshDebounce = useRef<ReturnType<typeof setTimeout> | null>(null);

  const refreshApprovals = useCallback(async () => {
    const approvals = await fetchApprovals(projectId, threadId);
    const nudges = await fetchNudges(projectId);
    setStreamState((s) => ({
      ...s,
      items: reconcileQueueItems(approvals, nudges, s.items),
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

  useEffect(() => {
    void refreshApprovals();
  }, [refreshApprovals]);

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
        const job = event.job as Record<string, unknown> | undefined;
        if (isScopeCommittedEvent(event)) onScopeCommitted?.();
        if (type === 'turn_end') void reconcilePendingApprovals();
        const shouldRefresh =
          type === 'turn_end' ||
          type === 'recommendation' ||
          type === 'approval' ||
          type === 'awaiting_approval' ||
          (type === 'job_update' && job?.status === 'awaiting_approval');
        if (shouldRefresh) scheduleRefreshApprovals();
      }
    },
    [scheduleRefreshApprovals, onScopeCommitted, reconcilePendingApprovals],
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
          context_json: contextJson,
        });
        if (result?.scope_committed === true) onScopeCommitted?.();
        setStreamState((s) => ({
          ...s,
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
    [threadId, refreshApprovals, voiceSession, voiceCtx, onScopeCommitted],
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

  return {
    latestReply,
    latestUserText,
    items,
    pendingApprovals,
    projectScope,
    setProjectScope,
    runTextTurn,
    approve,
    dismiss,
    refreshApprovals,
    applyStreamEvent: applyStreamEventToState,
    beginTurn,
    setVoiceSession,
    voiceSession,
  };
}
