/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        primary: '#1E40AF',
        success: '#16A34A',
        warning: '#D97706',
        error: '#DC2626',
      },
    },
  },
  plugins: [],
}
