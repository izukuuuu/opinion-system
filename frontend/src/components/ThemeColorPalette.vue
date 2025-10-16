<template>
  <section class="palette">
    <header class="palette__intro">
      <h2>主题色板</h2>
      <p>
        这些颜色来自 <code>colors.css</code>，用于界面的基础底色、品牌风格以及状态提示。开发时可直接引用对应的 CSS
        变量，保持视觉系统的一致性。
      </p>
    </header>

    <div class="palette__grid">
      <article
        v-for="group in colorGroups"
        :key="group.name"
        class="palette__group"
      >
        <div class="palette__group-header">
          <h3>{{ group.name }}</h3>
          <p>{{ group.description }}</p>
        </div>

        <div class="palette__swatches">
          <div
            v-for="color in group.colors"
            :key="color.label"
            class="palette__swatch"
            :class="color.variant"
            :style="{
              backgroundColor: swatchBackground(color),
              color: color.textColor || defaultTextColor(color),
              borderColor: swatchBorder(color)
            }"
          >
            <span class="palette__swatch-label">{{ color.label }}</span>
            <code class="palette__swatch-token">{{ color.variable }}</code>
          </div>
        </div>
      </article>
    </div>
  </section>
</template>

<script setup>
const colorGroups = [
  {
    name: '基础底色',
    description: '页面背景与正文的主要填充色。',
    colors: [
      { label: '背景底色', variable: '--color-bg-base', format: 'hex' },
      { label: '内容表面', variable: '--color-surface', format: 'hex' },
      { label: '柔和表面', variable: '--color-surface-muted', format: 'hex' },
      { label: '正文文本', variable: '--color-text-primary', format: 'hex', textColor: '#ffffff' }
    ]
  },
  {
    name: '品牌色',
    description: '品牌主色调，用于按钮、强调与导航。',
    colors: [
      { label: 'Brand 300', variable: '--color-brand-300-hex', format: 'hex' },
      { label: 'Brand 500', variable: '--color-brand-500-hex', format: 'hex', textColor: '#ffffff' },
      { label: 'Brand 700', variable: '--color-brand-700-hex', format: 'hex', textColor: '#ffffff' }
    ]
  },
  {
    name: '辅色',
    description: '与品牌色搭配的辅助配色。',
    colors: [
      { label: 'Accent 300', variable: '--color-accent-300-hex', format: 'hex' },
      { label: 'Accent 500', variable: '--color-accent-500-hex', format: 'hex', textColor: '#ffffff' },
      { label: 'Accent 600', variable: '--color-accent-600-hex', format: 'hex', textColor: '#ffffff' }
    ]
  },
  {
    name: '状态色',
    description: '用于反馈成功、警告及错误状态。',
    colors: [
      { label: 'Success 500', variable: '--color-success-500-hex', format: 'hex', textColor: '#ffffff' },
      { label: 'Warning 500', variable: '--color-warning-500-hex', format: 'hex', textColor: '#ffffff' },
      { label: 'Danger 500', variable: '--color-danger-500-hex', format: 'hex', textColor: '#ffffff' }
    ]
  },
  {
    name: '柔和层次',
    description: '浅色层次，可用于卡片背景或高亮。',
    colors: [
      { label: 'Brand 100', variable: '--color-brand-100', format: 'rgb', textColor: 'var(--color-brand-700-hex)' },
      { label: 'Accent 100', variable: '--color-accent-100', format: 'rgb', textColor: 'var(--color-accent-700-hex)' },
      { label: 'Success 100', variable: '--color-success-100', format: 'rgb', textColor: 'rgb(var(--color-success-700) / 1)' }
    ]
  },
  {
    name: '边框与描边',
    description: '边框、分割线与焦点提示的专用颜色。',
    colors: [
      { label: '柔和边框', variable: '--color-border-soft', format: 'hex', variant: 'outline' },
      { label: '焦点描边', variable: '--color-focus-outline', format: 'hex', variant: 'outline' },
      { label: '文本次级', variable: '--color-text-secondary', format: 'hex', variant: 'outline' }
    ]
  }
]

const swatchBackground = (color) => {
  if (color.variant === 'outline') {
    return 'var(--color-surface)'
  }

  return cssValue(color)
}

const defaultTextColor = (color) => (color.variant === 'outline' ? 'var(--color-text-secondary)' : 'var(--color-text-primary)')

const swatchBorder = (color) => (color.variant === 'outline' ? cssValue(color) : 'transparent')

function cssValue(color) {
  if (color.format === 'rgb') {
    return `rgb(var(${color.variable}) / 1)`
  }

  return `var(${color.variable})`
}
</script>

<style scoped>
.palette {
  display: flex;
  flex-direction: column;
  gap: 2rem;
}

.palette__intro h2 {
  margin: 0 0 0.75rem;
  font-size: 1.75rem;
  font-weight: 700;
  color: var(--color-text-primary);
}

.palette__intro p {
  margin: 0;
  color: var(--color-text-secondary);
  line-height: 1.6;
}

.palette__grid {
  display: grid;
  gap: 1.5rem;
}

.palette__group {
  background: rgba(255, 255, 255, 0.9);
  border-radius: 18px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  padding: 1.5rem;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.3);
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.palette__group-header h3 {
  margin: 0;
  font-size: 1.2rem;
  font-weight: 600;
  color: var(--color-text-primary);
}

.palette__group-header p {
  margin: 0.35rem 0 0;
  color: var(--color-text-muted);
}

.palette__swatches {
  display: grid;
  gap: 0.75rem;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
}

.palette__swatch {
  position: relative;
  padding: 1rem;
  border-radius: 14px;
  border: 1px solid transparent;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  box-shadow: 0 8px 18px rgba(15, 23, 42, 0.08);
}

.palette__swatch:hover {
  transform: translateY(-2px);
  box-shadow: 0 14px 32px rgba(15, 23, 42, 0.12);
}

.palette__swatch.outline {
  background-color: var(--color-surface);
  border-style: dashed;
}

.palette__swatch-label {
  font-weight: 600;
  font-size: 0.95rem;
}

.palette__swatch-token {
  font-family: 'Menlo', 'Monaco', 'Courier New', monospace;
  font-size: 0.8rem;
  background: rgba(15, 23, 42, 0.08);
  color: inherit;
  padding: 0.2rem 0.4rem;
  border-radius: 6px;
  align-self: flex-start;
}

@media (max-width: 768px) {
  .palette__group {
    padding: 1.1rem;
  }

  .palette__swatches {
    grid-template-columns: 1fr;
  }
}
</style>
