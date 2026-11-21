import React from 'react';
import ReactMarkdown from 'react-markdown';

type Props = {
  children: string;
  className?: string;
};

export const DockMarkdown: React.FC<Props> = ({ children, className = '' }) => (
  <div
    className={`select-text prose prose-invert max-w-none text-sm leading-relaxed space-y-2 ${className}`}
  >
    <ReactMarkdown
      components={{
        h1: ({ ...props }) => (
          <h1 className="text-sm font-bold text-slate-100 mt-2 mb-1 border-b border-white/10 pb-1" {...props} />
        ),
        h2: ({ ...props }) => (
          <h2 className="text-xs font-bold text-cyan-300 mt-2 mb-1" {...props} />
        ),
        h3: ({ ...props }) => (
          <h3 className="text-xs font-semibold text-emerald-300 mt-2 mb-0.5" {...props} />
        ),
        p: ({ ...props }) => <p className="mb-1.5 text-slate-200" {...props} />,
        ul: ({ ...props }) => (
          <ul className="list-disc pl-4 space-y-0.5 text-slate-300 my-1" {...props} />
        ),
        ol: ({ ...props }) => (
          <ol className="list-decimal pl-4 space-y-0.5 text-slate-300 my-1" {...props} />
        ),
        li: ({ ...props }) => <li className="leading-tight" {...props} />,
        strong: ({ ...props }) => <strong className="font-semibold text-slate-100" {...props} />,
        code: ({ ...props }) => (
          <code
            className="bg-slate-900/90 text-cyan-300 px-1 py-0.5 rounded text-[10.5px] font-mono border border-white/5"
            {...props}
          />
        ),
      }}
    >
      {children}
    </ReactMarkdown>
  </div>
);
