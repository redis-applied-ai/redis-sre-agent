/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./src/**/*.{js,ts,jsx,tsx}",
    "../src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'redis-red': '#ff4438',
        'redis-red-dark': '#351d22',
        'redis-lime': '#5bc69b',
        'redis-green': '#3cde67',
        'redis-yellow-300': '#ffcc00',
        'redis-yellow-500': '#dcff1e',
        'redis-blue-01': '#364dd9',
        'redis-blue-02': '#3044bf',
        'redis-blue-03': '#405bff',
        'redis-blue-04': '#16284f',
        'redis-gray-01': '#f8f8f8',
        'redis-dusk-01': '#f3f3f3',
        'redis-dusk-02': '#e9e9e9',
        'redis-dusk-03': '#d9d9d9',
        'redis-dusk-04': '#b9c2c6',
        'redis-dusk-05': '#8a99a0',
        'redis-dusk-06': '#5c707a',
        'redis-dusk-07': '#2d4754',
        'redis-dusk-08': '#163341',
        'redis-dusk-09': '#0d212c',
        'redis-midnight': '#091a23',
      },
      spacing: {
        'redis-gap': '15px',
        'redis-pad-x': '30px',
        'redis-pad-t': '22px',
        'redis-pad-b': '30px',
      },
      fontSize: {
        'redis-xs': '12px',
        'redis-sm': '14px',
        'redis-base': '16px',
        'redis-lg': '20px',
        'redis-xl': '24px',
      },
      borderRadius: {
        'redis-xs': '3px',
        'redis-sm': '5px',
        'redis-md': '10px',
      },
      fontFamily: {
        'geist': ['Geist', 'sans-serif'],
        'geist-mono': ['Geist Mono', 'monospace'],
        'redis': ['Geist', 'Space Grotesk', 'sans-serif'],
        'redis-mono': ['Geist Mono', 'Space Mono', 'monospace'],
      },
    },
  },
  plugins: [],
  safelist: [
    // Responsive grid classes used in Dashboard
    'grid-cols-1',
    'grid-cols-2',
    'grid-cols-3',
    'grid-cols-4',
    'md:grid-cols-2',
    'md:grid-cols-4',
    'lg:grid-cols-2',
    'lg:grid-cols-3',
    'lg:grid-cols-4',
    'xl:grid-cols-4'
  ]
}
