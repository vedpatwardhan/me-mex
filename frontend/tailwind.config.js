/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Plus Jakarta Sans"', '-apple-system', 'BlinkMacSystemFont', 'sans-serif'],
        display: ['"Space Grotesk"', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'monospace'],
      },
      colors: {
        background: '#090d16',
        surface: '#121824',
        'surface-elevated': '#1a2332',
        border: '#263144',
        'border-glow': '#3b82f640',
        primary: '#10b981',
        'node-paper': '#38bdf8',
        'node-insight': '#fbbf24',
        'node-hypothesis': '#c084fc',
        'node-concept': '#2dd4bf',
        'node-falsified': '#f87171',
      },
      boxShadow: {
        'glow-cyan': '0 0 20px -5px rgba(56, 189, 248, 0.3)',
        'glow-purple': '0 0 20px -5px rgba(192, 132, 252, 0.3)',
        'glow-amber': '0 0 20px -5px rgba(251, 191, 36, 0.3)',
        'glass': '0 8px 32px 0 rgba(0, 0, 0, 0.37)',
      },
    },
  },
  plugins: [],
}
