import type { DockItem } from '../components/RecommendationsDock';

const CLASS_ORDER: Record<DockItem['className'], number> = {
  approval: 0,
  job: 1,
  nudge: 2,
  informational: 3,
};

/** Hide job rows when an approval row already covers the same approval_id. */
export function dedupeApprovalJobs(items: DockItem[]): DockItem[] {
  const approvalIds = new Set(
    items.filter((i) => i.className === 'approval').map((i) => i.id),
  );
  return items.filter((i) => {
    if (i.className !== 'job') return true;
    const aid = i.approvalId;
    if (!aid) return true;
    return !approvalIds.has(aid);
  });
}

export function sortQueueItems(items: DockItem[]): DockItem[] {
  return [...items].sort((a, b) => {
    const ca = CLASS_ORDER[a.className] ?? 9;
    const cb = CLASS_ORDER[b.className] ?? 9;
    if (ca !== cb) return ca - cb;
    return a.title.localeCompare(b.title);
  });
}

export function reconcileQueueItems(
  approvals: DockItem[],
  nudges: DockItem[],
  streamItems: DockItem[],
): DockItem[] {
  const jobs = streamItems.filter((i) => i.className === 'job');
  const other = streamItems.filter((i) => i.className !== 'job' && i.className !== 'approval');
  const byId = new Map<string, DockItem>();
  for (const list of [approvals, nudges, other, jobs]) {
    for (const item of list) {
      const key = `${item.className}:${item.id}`;
      byId.set(key, { ...(byId.get(key) || {}), ...item });
    }
  }
  const merged = Array.from(byId.values());
  return sortQueueItems(dedupeApprovalJobs(merged));
}
