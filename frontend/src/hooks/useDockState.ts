import { useCallback, useEffect, useState } from 'react';

import type { DockItem } from '../components/RecommendationsDock';
import {
  fetchApprovals,
  fetchNudges,
  resumeApproval,
  streamAgentTurn,
} from '../services/dockStreamService';
import type { VoiceSession } from '../services/voiceSession';
import {
  applyStreamEvent,
  emptyDockStreamState,
  resetTurnState,
} from '../utils/dockStreamReducer';

export function useDockState(projectId: string, threadId: string) {
  const [streamState, setStreamState] = useState(emptyDockStreamState);
  const [projectScope, setProjectScope] = useState('');
  const [voiceSession, setVoiceSession] = useState<VoiceSession | null>(null);

  const { latestReply, latestUserText, items } = streamState;

  const refreshApprovals = useCallback(async () => {
    const approvals = await fetchApprovals(projectId, threadId);
    const nudges = await fetchNudges(projectId);
    setStreamState((s) => ({
      ...s,
      items: [
        ...approvals,
        ...nudges,
        ...s.items.filter((i) => i.className === 'job'),
      ],
    }));
  }, [projectId, threadId]);

  useEffect(() => {
    void refreshApprovals();
  }, [refreshApprovals]);

  const applyStreamEventToState = useCallback((ev: Record<string, unknown>) => {
    setStreamState((prev) => applyStreamEvent(prev, ev));
  }, []);

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
            void refreshApprovals();
          },
        },
      );
    },
    [threadId, refreshApprovals, applyStreamEventToState, beginTurn],
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
      if (voiceSession?.isReady()) {
        await voiceSession.sendApproval(approvalId, 'approve', voiceCtx(contextJson));
      } else {
        await resumeApproval({
          thread_id: threadId,
          approval_id: approvalId,
          action: 'approve',
          context_json: contextJson,
        });
      }
      setStreamState((s) => ({
        ...s,
        items: s.items.filter((i) => i.id !== approvalId),
      }));
      await refreshApprovals();
    },
    [threadId, refreshApprovals, voiceSession, voiceCtx],
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
