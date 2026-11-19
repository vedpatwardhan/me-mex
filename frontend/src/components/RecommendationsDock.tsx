import React from 'react';

export type DockItem = {
  id: string;
  className: 'nudge' | 'approval' | 'informational' | 'job';
  title: string;
  detail?: string;
};

type Props = {
  latestReply?: string;
  latestUserText?: string;
  items?: DockItem[];
  projectScope?: string;
  onApprove?: (id: string) => void;
  onDismiss?: (id: string) => void;
};

export const RecommendationsDock: React.FC<Props> = ({
  latestReply = '',
  latestUserText = '',
  items = [],
  projectScope = '',
  onApprove,
  onDismiss,
}) => (
  <aside className="w-80 shrink-0 border-l border-slate-800 bg-[#0c1018] p-3 flex flex-col gap-3 overflow-y-auto">
    <div className="text-xs uppercase tracking-wide text-slate-500">Recommendations dock</div>
    {projectScope ? (
      <div className="rounded border border-slate-700 bg-slate-900/50 p-2 text-xs text-slate-300">
        <div className="font-medium text-slate-400">Project scope</div>
        {projectScope}
      </div>
    ) : null}
    <section className="rounded border border-slate-700 p-2">
      <div className="text-xs text-slate-500">Latest turn</div>
      {latestUserText ? <p className="text-sm text-slate-400">{latestUserText}</p> : null}
      <p className="text-sm text-slate-100 whitespace-pre-wrap">{latestReply || '—'}</p>
    </section>
    <section>
      <div className="text-xs text-slate-500 mb-2">Recommendations</div>
      <ul className="space-y-2">
        {items.length === 0 ? (
          <li className="text-xs text-slate-600">No pending items</li>
        ) : (
          items.map((item) => (
            <li
              key={item.id}
              className="rounded border border-slate-700 px-2 py-1 text-xs text-slate-200"
            >
              <span
                className={
                  item.className === 'job'
                    ? 'text-amber-500'
                    : item.className === 'approval'
                      ? 'text-emerald-500'
                      : 'text-slate-500'
                }
              >
                {item.className}
              </span>{' '}
              {item.title}
              {item.detail ? <div className="text-slate-400">{item.detail}</div> : null}
              {item.className === 'approval' && onApprove && onDismiss ? (
                <div className="mt-2 flex gap-2">
                  <button
                    type="button"
                    className="rounded bg-emerald-700 px-2 py-0.5 text-white"
                    onClick={() => onApprove(item.id)}
                  >
                    Approve
                  </button>
                  <button
                    type="button"
                    className="rounded bg-slate-700 px-2 py-0.5"
                    onClick={() => onDismiss(item.id)}
                  >
                    Dismiss
                  </button>
                </div>
              ) : null}
            </li>
          ))
        )}
      </ul>
    </section>
  </aside>
);
