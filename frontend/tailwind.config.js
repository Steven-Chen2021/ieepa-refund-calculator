/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        'navy-blue': '#011837',
        'logo-blue': '#00A8E2',
        'logo-orange': '#F68B39',
        'logo-orange-dark': '#E07A2E',
        'accent-cyan': '#6BFFFF',
        'dark-gray': '#465363',
        'brand-gray': '#8B95A0',
        'gray-white': '#E7EEF1',
        primary: '#011837', // Navy Blue
        success: '#16A34A',
        warning: '#F68B39', // Logo Orange
        error: '#DC2626',
      },
      fontFamily: {
        heading: ['"Work Sans"', 'sans-serif'],
        body: ['"Open Sans"', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
