const withOpacityValue = (variable) => ({ opacityValue }) => {
  if (opacityValue !== undefined) {
    return `rgb(var(${variable}) / ${opacityValue})`
  }
  return `rgb(var(${variable}))`
}

const buildScale = (prefix) => ({
  50: withOpacityValue(`--color-${prefix}-50`),
  100: withOpacityValue(`--color-${prefix}-100`),
  200: withOpacityValue(`--color-${prefix}-200`),
  300: withOpacityValue(`--color-${prefix}-300`),
  400: withOpacityValue(`--color-${prefix}-400`),
  500: withOpacityValue(`--color-${prefix}-500`),
  600: withOpacityValue(`--color-${prefix}-600`),
  700: withOpacityValue(`--color-${prefix}-700`),
  800: withOpacityValue(`--color-${prefix}-800`),
  900: withOpacityValue(`--color-${prefix}-900`)
})

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
          ...buildScale('brand'),
          DEFAULT: withOpacityValue('--color-brand-600'),
          light: withOpacityValue('--color-brand-400'),
          dark: withOpacityValue('--color-brand-700')
        },
        accent: buildScale('accent'),
        success: buildScale('success'),
        danger: buildScale('danger'),
        warning: buildScale('warning'),
        indigo: buildScale('brand'),
        sky: buildScale('accent'),
        emerald: buildScale('success'),
        rose: buildScale('danger'),
        amber: buildScale('warning')
      },
      boxShadow: {
        card: '0 18px 36px rgba(15, 23, 42, 0.08)'
      }
    }
  },
  plugins: []
}
