<template>
  <figure class="report-chart-figure">
    <div v-if="hasData" ref="chartRef" class="report-chart-figure__canvas"></div>
    <p v-else class="report-chart-figure__empty">{{ emptyMessage }}</p>
    <figcaption v-if="caption" class="report-chart-figure__caption">{{ caption }}</figcaption>
  </figure>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { echarts } from '@/utils/echarts'

const props = defineProps({
  contract: {
    type: Object,
    default: () => ({})
  }
})

const chartRef = ref(null)
let chartInstance = null

const caption = computed(() => String(props.contract?.caption || '图表').trim())
const option = computed(() => (props.contract?.option && typeof props.contract.option === 'object' ? props.contract.option : {}))
const hasData = computed(() => Boolean(props.contract?.hasData && Object.keys(option.value || {}).length))
const emptyMessage = computed(() => String(props.contract?.emptyMessage || '暂无图表数据').trim() || '暂无图表数据')

async function renderChart() {
  await nextTick()
  if (!chartRef.value || !hasData.value) {
    if (chartInstance) {
      chartInstance.dispose()
      chartInstance = null
    }
    return
  }
  if (!chartInstance) {
    chartInstance = echarts.init(chartRef.value)
  }
  chartInstance.setOption(option.value || {}, true)
  chartInstance.resize()
}

function disposeChart() {
  if (chartInstance) {
    chartInstance.dispose()
    chartInstance = null
  }
}

onMounted(() => {
  renderChart()
  window.addEventListener('resize', renderChart)
})

watch(option, () => {
  renderChart()
}, { deep: true })

watch(hasData, () => {
  renderChart()
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', renderChart)
  disposeChart()
})
</script>

<style scoped>
.report-chart-figure {
  margin: 1.5rem auto;
  max-width: 720px;
  text-align: center;
}

.report-chart-figure__canvas {
  width: 100%;
  height: 360px;
  margin: 0 auto;
}

.report-chart-figure__empty {
  margin: 0;
  color: var(--color-text-secondary, #6b7280);
  font-size: 0.95rem;
}

.report-chart-figure__caption {
  margin-top: 0.75rem;
  color: var(--color-text-secondary, #6b7280);
  font-size: 0.85rem;
  line-height: 1.5;
}
</style>
