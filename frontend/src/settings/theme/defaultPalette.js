export const themeGroups = [
  {
    id: 'neutral-foundation',
    title: '基础底色',
    description: '界面背景、表面与文字的基础配色。',
    tokens: [
      { label: '背景底色', variable: '--color-bg-base', default: '#eef2f6', format: 'hex' },
      { label: '内容表面', variable: '--color-surface', default: '#ffffff', format: 'hex' },
      { label: '柔和表面', variable: '--color-surface-muted', default: '#e2e9f1', format: 'hex' },
      { label: '柔和边框', variable: '--color-border-soft', default: '#d0d5d9', format: 'hex', variant: 'outline' },
      { label: '正文文本', variable: '--color-text-primary', default: '#1c252c', format: 'hex', previewTextColor: '#ffffff' },
      { label: '次级文本', variable: '--color-text-secondary', default: '#303d47', format: 'hex', variant: 'outline' },
      { label: '辅助文本', variable: '--color-text-muted', default: '#445562', format: 'hex', variant: 'outline' },
      { label: '焦点描边', variable: '--color-focus-outline', default: '#9aafc0', format: 'hex', variant: 'outline' }
    ]
  },
  {
    id: 'brand-hex',
    title: '品牌主色（Hex）',
    description: '用于按钮、标签等关键品牌视觉元素。',
    tokens: [
      { label: 'Brand 300 Hex', variable: '--color-brand-300-hex', default: '#becddd', format: 'hex' },
      { label: 'Brand 400 Hex', variable: '--color-brand-400-hex', default: '#b2c4d7', format: 'hex' },
      { label: 'Brand 500 Hex', variable: '--color-brand-500-hex', default: '#a6bbd1', format: 'hex', previewTextColor: '#ffffff' },
      { label: 'Brand 600 Hex', variable: '--color-brand-600-hex', default: '#9ab2cb', format: 'hex', previewTextColor: '#ffffff' },
      { label: 'Brand 700 Hex', variable: '--color-brand-700-hex', default: '#879db3', format: 'hex', previewTextColor: '#ffffff' }
    ]
  },
  {
    id: 'brand-spectrum',
    title: '品牌主色（RGB 光谱）',
    description: '提供从 50-900 的品牌色阶，用于柔和背景与描边。',
    tokens: [
      { label: 'Brand 50', variable: '--color-brand-50', default: '214 223 233', format: 'rgb' },
      { label: 'Brand 100', variable: '--color-brand-100', default: '214 223 233', format: 'rgb' },
      { label: 'Brand 200', variable: '--color-brand-200', default: '202 214 227', format: 'rgb' },
      { label: 'Brand 300', variable: '--color-brand-300', default: '190 205 221', format: 'rgb' },
      { label: 'Brand 400', variable: '--color-brand-400', default: '178 196 215', format: 'rgb' },
      { label: 'Brand 500', variable: '--color-brand-500', default: '166 187 209', format: 'rgb' },
      { label: 'Brand 600', variable: '--color-brand-600', default: '154 178 203', format: 'rgb' },
      { label: 'Brand 700', variable: '--color-brand-700', default: '135 157 179', format: 'rgb' },
      { label: 'Brand 800', variable: '--color-brand-800', default: '114 133 152', format: 'rgb' },
      { label: 'Brand 900', variable: '--color-brand-900', default: '93 109 125', format: 'rgb' }
    ]
  },
  {
    id: 'accent-hex',
    title: '辅色（Hex）',
    description: '主品牌之外的辅助强调配色。',
    tokens: [
      { label: 'Accent 300 Hex', variable: '--color-accent-300-hex', default: '#a1c3dc', format: 'hex' },
      { label: 'Accent 500 Hex', variable: '--color-accent-500-hex', default: '#7babce', format: 'hex', previewTextColor: '#ffffff' },
      { label: 'Accent 600 Hex', variable: '--color-accent-600-hex', default: '#689fc7', format: 'hex', previewTextColor: '#ffffff' }
    ]
  },
  {
    id: 'accent-spectrum',
    title: '辅色（RGB 光谱）',
    description: '与品牌色搭配的柔和色阶。',
    tokens: [
      { label: 'Accent 50', variable: '--color-accent-50', default: '218 231 241', format: 'rgb' },
      { label: 'Accent 100', variable: '--color-accent-100', default: '199 219 234', format: 'rgb' },
      { label: 'Accent 200', variable: '--color-accent-200', default: '180 207 227', format: 'rgb' },
      { label: 'Accent 300', variable: '--color-accent-300', default: '161 195 220', format: 'rgb' },
      { label: 'Accent 400', variable: '--color-accent-400', default: '142 183 213', format: 'rgb' },
      { label: 'Accent 500', variable: '--color-accent-500', default: '123 171 206', format: 'rgb' },
      { label: 'Accent 600', variable: '--color-accent-600', default: '104 159 199', format: 'rgb' },
      { label: 'Accent 700', variable: '--color-accent-700', default: '91 140 175', format: 'rgb' },
      { label: 'Accent 800', variable: '--color-accent-800', default: '77 119 149', format: 'rgb' },
      { label: 'Accent 900', variable: '--color-accent-900', default: '63 98 123', format: 'rgb' }
    ]
  },
  {
    id: 'success-spectrum',
    title: '成功状态色',
    description: '成功反馈与正向提示色阶。',
    tokens: [
      { label: 'Success 50', variable: '--color-success-50', default: '238 243 239', format: 'rgb' },
      { label: 'Success 100', variable: '--color-success-100', default: '220 232 222', format: 'rgb' },
      { label: 'Success 200', variable: '--color-success-200', default: '194 214 198', format: 'rgb' },
      { label: 'Success 300', variable: '--color-success-300', default: '166 193 171', format: 'rgb' },
      { label: 'Success 400', variable: '--color-success-400', default: '139 170 146', format: 'rgb' },
      { label: 'Success 500', variable: '--color-success-500', default: '110 143 117', format: 'rgb' },
      { label: 'Success 600', variable: '--color-success-600', default: '88 114 94', format: 'rgb' },
      { label: 'Success 700', variable: '--color-success-700', default: '67 85 71', format: 'rgb' },
      { label: 'Success 800', variable: '--color-success-800', default: '46 57 49', format: 'rgb' },
      { label: 'Success 900', variable: '--color-success-900', default: '31 38 31', format: 'rgb' },
      { label: 'Success 500 Hex', variable: '--color-success-500-hex', default: '#6e8f75', format: 'hex', previewTextColor: '#ffffff' }
    ]
  },
  {
    id: 'danger-spectrum',
    title: '错误状态色',
    description: '错误提示与风险警示专用色阶。',
    tokens: [
      { label: 'Danger 50', variable: '--color-danger-50', default: '246 236 236', format: 'rgb' },
      { label: 'Danger 100', variable: '--color-danger-100', default: '235 214 214', format: 'rgb' },
      { label: 'Danger 200', variable: '--color-danger-200', default: '220 182 182', format: 'rgb' },
      { label: 'Danger 300', variable: '--color-danger-300', default: '203 149 150', format: 'rgb' },
      { label: 'Danger 400', variable: '--color-danger-400', default: '184 115 115', format: 'rgb' },
      { label: 'Danger 500', variable: '--color-danger-500', default: '159 89 89', format: 'rgb' },
      { label: 'Danger 600', variable: '--color-danger-600', default: '130 70 70', format: 'rgb' },
      { label: 'Danger 700', variable: '--color-danger-700', default: '100 53 53', format: 'rgb' },
      { label: 'Danger 800', variable: '--color-danger-800', default: '69 36 36', format: 'rgb' },
      { label: 'Danger 900', variable: '--color-danger-900', default: '46 24 24', format: 'rgb' },
      { label: 'Danger 500 Hex', variable: '--color-danger-500-hex', default: '#9f5959', format: 'hex', previewTextColor: '#ffffff' }
    ]
  },
  {
    id: 'warning-spectrum',
    title: '警告状态色',
    description: '警告提醒与风险提示色阶。',
    tokens: [
      { label: 'Warning 50', variable: '--color-warning-50', default: '247 240 228', format: 'rgb' },
      { label: 'Warning 100', variable: '--color-warning-100', default: '237 220 195', format: 'rgb' },
      { label: 'Warning 200', variable: '--color-warning-200', default: '222 198 158', format: 'rgb' },
      { label: 'Warning 300', variable: '--color-warning-300', default: '205 168 114', format: 'rgb' },
      { label: 'Warning 400', variable: '--color-warning-400', default: '187 140 79', format: 'rgb' },
      { label: 'Warning 500', variable: '--color-warning-500', default: '163 113 59', format: 'rgb' },
      { label: 'Warning 600', variable: '--color-warning-600', default: '134 89 47', format: 'rgb' },
      { label: 'Warning 700', variable: '--color-warning-700', default: '104 66 33', format: 'rgb' },
      { label: 'Warning 800', variable: '--color-warning-800', default: '77 47 23', format: 'rgb' },
      { label: 'Warning 900', variable: '--color-warning-900', default: '52 31 15', format: 'rgb' },
      { label: 'Warning 500 Hex', variable: '--color-warning-500-hex', default: '#a3713b', format: 'hex', previewTextColor: '#ffffff' }
    ]
  }
]

export const defaultThemeValues = themeGroups.reduce((accumulator, group) => {
  group.tokens.forEach((token) => {
    accumulator[token.variable] = token.default
  })

  return accumulator
}, {})

export const managedThemeVariables = Object.keys(defaultThemeValues)
