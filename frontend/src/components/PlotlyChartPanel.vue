<template>
  <article class="analysis-chart-card">
    <header class="analysis-chart-card__header">
      <div>
        <h3>{{ title }}</h3>
        <p v-if="description">{{ description }}</p>
      </div>
      <slot name="meta" />
    </header>
    <div class="analysis-chart-card__body">
      <div v-if="!hasData" class="analysis-chart-card__empty">
        {{ emptyMessage }}
      </div>
      <div v-else ref="chartRef" class="analysis-chart-card__canvas"></div>
    </div>
    <slot />
  </article>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps({
  title: {
    type: String,
    default: ''
  },
  description: {
    type: String,
    default: ''
  },
  data: {
    type: Array,
    default: () => []
  },
  layout: {
    type: Object,
    default: () => ({})
  },
  config: {
    type: Object,
    default: () => ({
      displayModeBar: true,
      modeBarButtonsToRemove: ['pan2d', 'lasso2d', 'select2d'],
      displaylogo: false,
      responsive: true
    })
  },
  hasData: {
    type: Boolean,
    default: false
  },
  emptyMessage: {
    type: String,
    default: '暂无可视化数据'
  }
})

const chartRef = ref(null)
let resizeTimer = null

// 动态加载Plotly
let Plotly = null
const loadPlotly = async () => {
  if (Plotly) return Plotly
  if (window.Plotly) {
    Plotly = window.Plotly
    return Plotly
  }
  // 如果window没有Plotly，尝试从CDN加载
  return new Promise((resolve, reject) => {
    const script = document.createElement('script')
    script.src = 'https://cdn.plot.ly/plotly-2.27.0.min.js'
    script.onload = () => {
      Plotly = window.Plotly
      resolve(Plotly)
    }
    script.onerror = reject
    document.head.appendChild(script)
  })
}

const renderChart = async () => {
  if (!props.hasData || !chartRef.value) return

  const plotly = await loadPlotly()
  if (!plotly) {
    console.error('Failed to load Plotly')
    return
  }

  await plotly.newPlot(chartRef.value, props.data, props.layout, props.config)
}

const handleResize = () => {
  if (resizeTimer) clearTimeout(resizeTimer)
  resizeTimer = setTimeout(async () => {
    if (chartRef.value && Plotly) {
      await Plotly.Plots.resize(chartRef.value)
    }
  }, 100)
}

watch(
  () => [props.data, props.layout, props.hasData],
  () => {
    renderChart()
  },
  { deep: true }
)

onMounted(() => {
  renderChart()
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  if (resizeTimer) clearTimeout(resizeTimer)
  if (chartRef.value && Plotly) {
    Plotly.purge(chartRef.value)
  }
})
</script>

<style scoped>
.analysis-chart-card {
  border-radius: 24px;
  border: 1px solid var(--color-border-soft);
  background: var(--color-surface);
  padding: 24px;
  box-shadow: 0 10px 25px rgba(22, 30, 52, 0.05);
}

.analysis-chart-card__header {
  margin-bottom: 20px;
}

.analysis-chart-card__header h3 {
  font-size: 1.2rem;
  font-weight: 600;
  color: var(--color-text-primary);
  margin-bottom: 4px;
}

.analysis-chart-card__header p {
  font-size: 0.9rem;
  color: var(--color-text-secondary);
}

.analysis-chart-card__canvas {
  width: 100%;
  min-height: 300px;
}

.analysis-chart-card__empty {
  text-align: center;
  color: var(--color-text-secondary);
  padding: 40px 20px;
  font-size: 0.95rem;
}
</style>

