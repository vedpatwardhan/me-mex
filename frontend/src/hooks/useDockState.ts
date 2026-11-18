import { useCallback, useEffect, useState } from 'react';

import type { DockItem } from '../components/RecommendationsDock';
import {
  fetchApprovals,
  fetchNudges,
  resumeApproval,
  streamAgentTurn,
} from '../services/dockStreamService';

export function useDockState(projectId: string, threadId: string) {
  const [latestReply, setLatestReply] = useState('');
  const [latestUserText, setLatestUserText] = useState('');
  const [items, setItems] = useState<DockItem[]>([]);
  const [projectScope, setProjectScope] = useState('');

  const refreshApprovals = useCallback(async () => {
    const approvals = await fetchApprovals(projectId, threadId);
    const nudges = await fetchNudges(projectId);
    setItems([...approvals, ...nudges]);
  }, [projectId, threadId]);

  useEffect(() => {
    void refreshApprovals();
  }, [refreshApprovals]);

  const runTextTurn = useCallback(
    async (text: string, contextJson: Record<string, unknown>) => {
      setLatestUserText(text);
      let acc = '';
      await streamAgentTurn(
        { text, thread_id: threadId, context_json: contextJson },
        {
          onToken: (t) => {
            acc += t;
            setLatestReply(acc);
          },
          onTurnEnd: (body) => {
            const reply = (body.reply as string) || acc;
            setLatestReply(reply);
            const approvalId = (body.details as { approval_id?: string })?.approval_id;
            if (approvalId) {
              setItems((prev) => [
                {
                  id: approvalId,
                  className: 'approval',
                  title: reply || 'Pending approval',
                  detail: String(approvalId),
                },
                ...prev,
              ]);
            }
            void refreshApprovals();
          },
        },
      );
    },
    [threadId, refreshApprovals],
  );

  const approve = useCallback(
    async (approvalId: string, contextJson: Record<string, unknown>) => {
      await resumeApproval({
        thread_id: threadId,
        approval_id: approvalId,
        action: 'approve',
        context_json: contextJson,
      });
      setItems((prev) => prev.filter((i) => i.id !== approvalId));
      await refreshApprovals();
    },
    [threadId, refreshApprovals],
  );

  const dismiss = useCallback(
    async (approvalId: string, contextJson: Record<string, unknown>) => {
      await resumeApproval({
        thread_id: threadId,
        approval_id: approvalId,
        action: 'dismiss',
        context_json: contextJson,
      });
      setItems((prev) => prev.filter((i) => i.id !== approvalId));
    },
    [threadId],
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
  };
}
