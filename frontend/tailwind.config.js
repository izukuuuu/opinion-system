/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{vue,js,ts,jsx,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: [
          'Segoe UI',
          'PingFang SC',
          'Microsoft YaHei',
          'Helvetica Neue',
          'Arial',
          'sans-serif'
        ]
      },
      colors: {
        brand: {
          DEFAULT: '#4338CA',
          light: '#6366F1',
          dark: '#312E81'
        }
      },
      boxShadow: {
        card: '0 18px 36px rgba(15, 23, 42, 0.08)'
      }
    }
  },
  plugins: []
}
