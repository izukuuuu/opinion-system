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
import * as echarts from 'echarts'
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
  option: {
    type: Object,
    default: null
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
let chartInstance = null
let resizeObserver = null

const disposeChart = () => {
  if (chartInstance) {
    chartInstance.dispose()
    chartInstance = null
  }
}

const renderChart = () => {
  if (!props.hasData || !props.option) {
    disposeChart()
    return
  }
  if (!chartRef.value) return
  if (!chartInstance) {
    chartInstance = echarts.init(chartRef.value)
  }
  chartInstance.setOption(props.option, true)
}

onMounted(() => {
  if (chartRef.value && typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(() => {
      if (chartInstance) {
        chartInstance.resize()
      }
    })
    resizeObserver.observe(chartRef.value)
  }
  renderChart()
})

watch(
  () => [props.option, props.hasData],
  () => {
    renderChart()
  },
  { deep: true }
)

onBeforeUnmount(() => {
  if (resizeObserver && chartRef.value) {
    resizeObserver.disconnect()
  }
  disposeChart()
})
</script>

<style scoped>
.analysis-chart-card {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  padding: 1.5rem;
  border-radius: 24px;
  background: var(--color-surface);
  border: 1px solid var(--color-border-soft);
  box-shadow: 0 20px 40px -28px rgba(16, 24, 40, 0.35);
}

.analysis-chart-card__header {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
}

.analysis-chart-card__header h3 {
  margin: 0;
  font-size: 1.05rem;
  font-weight: 700;
  color: var(--color-text-primary);
}

.analysis-chart-card__header p {
  margin: 0.35rem 0 0;
  font-size: 0.9rem;
  color: var(--color-text-secondary);
}

.analysis-chart-card__body {
  min-height: 260px;
}

.analysis-chart-card__canvas {
  width: 100%;
  height: 400px;
}

.analysis-chart-card__empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  border-radius: 18px;
  background: var(--color-surface-muted);
  color: var(--color-text-muted);
  border: 1px dashed var(--color-border-soft);
}
</style>
