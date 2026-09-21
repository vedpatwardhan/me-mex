import React from 'react';

interface LogoProps {
  className?: string;
  size?: number;
}

export const Logo: React.FC<LogoProps> = ({ className = '', size = 28 }) => {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 100 100"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
    >
      <defs>
        <linearGradient id="memex-logo-grad" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#38bdf8" />
          <stop offset="50%" stopColor="#a855f7" />
          <stop offset="100%" stopColor="#34d399" />
        </linearGradient>
        <filter id="logo-glow" x="-20%" y="-20%" width="140%" height="140%">
          <feGaussianBlur stdDeviation="3" result="blur" />
          <feComposite in="SourceGraphic" in2="blur" operator="over" />
        </filter>
      </defs>

      {/* Hexagon Frame */}
      <polygon
        points="50,5 89,27.5 89,72.5 50,95 11,72.5 11,27.5"
        fill="#161b22"
        stroke="url(#memex-logo-grad)"
        strokeWidth="5"
      />

      {/* Graph Edges */}
      <g stroke="url(#memex-logo-grad)" strokeWidth="3.5" strokeLinecap="round" opacity="0.85">
        <line x1="50" y1="28" x2="28" y2="52" />
        <line x1="50" y1="28" x2="72" y2="52" />
        <line x1="28" y1="52" x2="40" y2="75" />
        <line x1="72" y1="52" x2="60" y2="75" />
        <line x1="28" y1="52" x2="72" y2="52" strokeDasharray="4 3" opacity="0.6" />
        <line x1="40" y1="75" x2="60" y2="75" />
      </g>

      {/* Nodes */}
      <circle cx="50" cy="28" r="7.5" fill="#38bdf8" filter="url(#logo-glow)" />
      <circle cx="28" cy="52" r="6.5" fill="#fbbf24" filter="url(#logo-glow)" />
      <circle cx="72" cy="52" r="6.5" fill="#c084fc" filter="url(#logo-glow)" />
      <circle cx="40" cy="75" r="5.5" fill="#2dd4bf" />
      <circle cx="60" cy="75" r="5.5" fill="#34d399" />
    </svg>
  );
};
