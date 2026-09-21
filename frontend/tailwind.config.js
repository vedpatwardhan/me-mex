/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: '#0d1117',
        surface: '#161b22',
        border: '#30363d',
        primary: '#3fb950',
        'node-paper': '#58a6ff',
        'node-insight': '#d29922',
        'node-hypothesis': '#a371f7',
        'node-concept': '#39c5cf',
        'node-falsified': '#f85149',
      },
    },
  },
  plugins: [],
}
