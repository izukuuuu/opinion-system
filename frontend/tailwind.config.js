const withOpacityValue = (variable) => ({ opacityValue }) => {
  if (opacityValue !== undefined) {
    return `rgb(var(${variable}) / ${opacityValue})`
  }
  return `rgb(var(${variable}))`
}

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
          DEFAULT: withOpacityValue('--color-brand-600'),
          light: withOpacityValue('--color-brand-400'),
          dark: withOpacityValue('--color-brand-700')
        },
        indigo: {
          50: withOpacityValue('--color-brand-50'),
          100: withOpacityValue('--color-brand-100'),
          200: withOpacityValue('--color-brand-200'),
          300: withOpacityValue('--color-brand-300'),
          400: withOpacityValue('--color-brand-400'),
          500: withOpacityValue('--color-brand-500'),
          600: withOpacityValue('--color-brand-600'),
          700: withOpacityValue('--color-brand-700'),
          800: withOpacityValue('--color-brand-800'),
          900: withOpacityValue('--color-brand-900')
        },
        sky: {
          50: withOpacityValue('--color-accent-50'),
          100: withOpacityValue('--color-accent-100'),
          200: withOpacityValue('--color-accent-200'),
          300: withOpacityValue('--color-accent-300'),
          400: withOpacityValue('--color-accent-400'),
          500: withOpacityValue('--color-accent-500'),
          600: withOpacityValue('--color-accent-600'),
          700: withOpacityValue('--color-accent-700'),
          800: withOpacityValue('--color-accent-800'),
          900: withOpacityValue('--color-accent-900')
        },
        emerald: {
          50: withOpacityValue('--color-success-50'),
          100: withOpacityValue('--color-success-100'),
          200: withOpacityValue('--color-success-200'),
          300: withOpacityValue('--color-success-300'),
          400: withOpacityValue('--color-success-400'),
          500: withOpacityValue('--color-success-500'),
          600: withOpacityValue('--color-success-600'),
          700: withOpacityValue('--color-success-700'),
          800: withOpacityValue('--color-success-800'),
          900: withOpacityValue('--color-success-900')
        },
        rose: {
          50: withOpacityValue('--color-danger-50'),
          100: withOpacityValue('--color-danger-100'),
          200: withOpacityValue('--color-danger-200'),
          300: withOpacityValue('--color-danger-300'),
          400: withOpacityValue('--color-danger-400'),
          500: withOpacityValue('--color-danger-500'),
          600: withOpacityValue('--color-danger-600'),
          700: withOpacityValue('--color-danger-700'),
          800: withOpacityValue('--color-danger-800'),
          900: withOpacityValue('--color-danger-900')
        },
        amber: {
          50: withOpacityValue('--color-warning-50'),
          100: withOpacityValue('--color-warning-100'),
          200: withOpacityValue('--color-warning-200'),
          300: withOpacityValue('--color-warning-300'),
          400: withOpacityValue('--color-warning-400'),
          500: withOpacityValue('--color-warning-500'),
          600: withOpacityValue('--color-warning-600'),
          700: withOpacityValue('--color-warning-700'),
          800: withOpacityValue('--color-warning-800'),
          900: withOpacityValue('--color-warning-900')
        }
      },
      boxShadow: {
        card: '0 18px 36px rgba(15, 23, 42, 0.08)'
      }
    }
  },
  plugins: []
}
