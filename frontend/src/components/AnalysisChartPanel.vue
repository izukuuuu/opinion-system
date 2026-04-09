<template>
  <article class="analysis-chart-card">
    <header class="analysis-chart-card__header">
      <div>
        <h3>{{ title }}</h3>
        <p v-if="description">{{ description }}</p>
      </div>
      <div class="flex items-center gap-2">
        <!-- 关键词展示方式切换 -->
        <div v-if="isKeywords" class="tab-switch">
          <button
            type="button"
            class="tab-switch-btn"
            :class="{ 'tab-switch-btn--active': keywordsChartMode === 'bar' }"
            @click="setKeywordsMode('bar')"
          >
            <Bars3Icon class="h-4 w-4" />
            <span>柱状图</span>
          </button>
          <button
            type="button"
            class="tab-switch-btn"
            :class="{ 'tab-switch-btn--active': keywordsChartMode === 'wordcloud' }"
            @click="setKeywordsMode('wordcloud')"
          >
            <CloudIcon class="h-4 w-4" />
            <span>词云</span>
          </button>
        </div>
        <button
          v-if="hasData && computedOption"
          type="button"
          class="analysis-chart-card__expand-btn"
          title="展开查看"
          @click="openModal"
        >
          <ArrowsPointingOutIcon class="h-4 w-4" />
        </button>
        <slot name="meta" />
      </div>
    </header>
    <div class="analysis-chart-card__body">
      <div v-if="!hasData" class="analysis-chart-card__empty">
        {{ emptyMessage }}
      </div>
      <div v-else ref="chartRef" class="analysis-chart-card__canvas"></div>
    </div>
    <!-- 词云数量选择控件 -->
    <div v-if="isKeywords && keywordsChartMode === 'wordcloud'" class="keywords-wordcount-control">
      <span class="keywords-wordcount-label">展示词数量：</span>
      <div class="keywords-wordcount-options">
        <button
          v-for="count in wordCountOptions"
          :key="count"
          type="button"
          class="keywords-wordcount-btn"
          :class="{ 'keywords-wordcount-btn--active': keywordsWordCount === count }"
          @click="setKeywordsWordCount(count)"
        >
          {{ count }}
        </button>
      </div>
    </div>
    <slot />

    <!-- 展开图表的 Modal -->
    <AppModal
      v-model="showModal"
      :title="title"
      :description="description"
      :show-footer="false"
      width="max-w-5xl"
      scrollable
    >
      <div class="flex justify-center gap-6 pb-4">
        <div class="flex items-center gap-3">
          <span class="text-xs font-medium text-muted">高度</span>
          <nav class="inline-flex gap-0.5 rounded-xl bg-surface-muted p-1">
            <button
              v-for="size in sizeOptions"
              :key="`height-${size.value}`"
              type="button"
              class="chart-size-tab"
              :class="{ 'chart-size-tab--active': chartHeight === size.value }"
              @click="setChartHeight(size.value)"
            >
              {{ size.label }}
            </button>
          </nav>
        </div>
        <div class="flex items-center gap-3">
          <span class="text-xs font-medium text-muted">宽度</span>
          <nav class="inline-flex gap-0.5 rounded-xl bg-surface-muted p-1">
            <button
              v-for="size in sizeOptions"
              :key="`width-${size.value}`"
              type="button"
              class="chart-size-tab"
              :class="{ 'chart-size-tab--active': chartWidth === size.value }"
              @click="setChartWidth(size.value)"
            >
              {{ size.label }}
            </button>
          </nav>
        </div>
      </div>
      <div ref="modalChartRef" class="mx-auto" :style="canvasStyle"></div>
      <div class="flex justify-end gap-3 pt-4">
        <button type="button" class="chart-export-btn" @click="exportChart('png')">
          <ArrowDownTrayIcon class="h-4 w-4" />
          <span>导出 PNG</span>
        </button>
        <button type="button" class="chart-export-btn" @click="exportChart('svg')">
          <ArrowDownTrayIcon class="h-4 w-4" />
          <span>导出 SVG</span>
        </button>
      </div>
    </AppModal>
  </article>
</template>

<script setup>
import { echarts } from '@/utils/echarts'
import { buildWordCloudOption } from '@/utils/chartBuilder'
import { onBeforeUnmount, onMounted, ref, watch, nextTick, computed } from 'vue'
import { ArrowsPointingOutIcon, ArrowDownTrayIcon, Bars3Icon, CloudIcon } from '@heroicons/vue/24/outline'
import AppModal from './AppModal.vue'

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
  },
  isKeywords: {
    type: Boolean,
    default: false
  },
  allRows: {
    type: Array,
    default: () => []
  }
})

const chartRef = ref(null)
const modalChartRef = ref(null)
const showModal = ref(false)
const chartWidth = ref('medium')
const chartHeight = ref('medium')
const keywordsChartMode = ref('bar')
const keywordsWordCount = ref(30)
let chartInstance = null
let modalChartInstance = null
let resizeObserver = null

const wordCountOptions = [20, 30, 50, 100]

const sizeOptions = [
  { label: '小', value: 'small' },
  { label: '中', value: 'medium' },
  { label: '大', value: 'large' }
]

const sizeWidths = {
  small: '60%',
  medium: '80%',
  large: '100%'
}

const sizeHeights = {
  small: '40vh',
  medium: '55vh',
  large: '70vh'
}

const canvasStyle = computed(() => ({
  width: sizeWidths[chartWidth.value] || sizeWidths.medium,
  height: sizeHeights[chartHeight.value] || sizeHeights.medium
}))

const setKeywordsMode = (mode) => {
  if (keywordsChartMode.value === mode) return
  keywordsChartMode.value = mode
}

const setKeywordsWordCount = (count) => {
  if (keywordsWordCount.value === count) return
  keywordsWordCount.value = count
}

const computedOption = computed(() => {
  if (!props.hasData) return null
  if (props.isKeywords && keywordsChartMode.value === 'wordcloud') {
    const slicedRows = props.allRows.slice(0, keywordsWordCount.value)
    return buildWordCloudOption(slicedRows, props.title)
  }
  return props.option
})

const resizeModalChart = () => {
  setTimeout(() => {
    if (modalChartInstance) {
      modalChartInstance.resize()
    }
  }, 50)
}

const setChartWidth = (size) => {
  chartWidth.value = size
  resizeModalChart()
}

const setChartHeight = (size) => {
  chartHeight.value = size
  resizeModalChart()
}

const disposeChart = () => {
  if (chartInstance) {
    chartInstance.dispose()
    chartInstance = null
  }
}

const disposeModalChart = () => {
  if (modalChartInstance) {
    modalChartInstance.dispose()
    modalChartInstance = null
  }
}

const renderChart = () => {
  if (!props.hasData || !computedOption.value) {
    disposeChart()
    return
  }
  if (!chartRef.value) return
  if (!chartInstance) {
    chartInstance = echarts.init(chartRef.value)
  }
  chartInstance.setOption(computedOption.value, true)
}

const renderModalChart = async () => {
  if (!computedOption.value) return
  await nextTick()
  if (!modalChartRef.value) return
  if (!modalChartInstance) {
    modalChartInstance = echarts.init(modalChartRef.value)
  }
  modalChartInstance.setOption(computedOption.value, true)
}

const openModal = async () => {
  showModal.value = true
  chartWidth.value = 'medium'
  chartHeight.value = 'medium'
  await nextTick()
  renderModalChart()
}

const exportChart = (type) => {
  if (!modalChartInstance) return
  const url = modalChartInstance.getDataURL({
    type,
    pixelRatio: 2,
    backgroundColor: '#fff'
  })
  const link = document.createElement('a')
  link.download = `${props.title || 'chart'}.${type}`
  link.href = url
  link.click()
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
  () => [computedOption.value, props.hasData],
  () => {
    renderChart()
  },
  { deep: true }
)

watch(showModal, (value) => {
  if (!value) {
    disposeModalChart()
  }
})

onBeforeUnmount(() => {
  if (resizeObserver && chartRef.value) {
    resizeObserver.disconnect()
  }
  disposeChart()
  disposeModalChart()
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

.analysis-chart-card__expand-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 8px;
  border: 1px solid var(--color-border-soft);
  color: var(--color-text-muted);
  background: var(--color-surface);
  transition: all 0.15s ease;
  cursor: pointer;
}

.analysis-chart-card__expand-btn:hover {
  border-color: var(--color-brand-soft);
  color: var(--color-brand-600);
  background: var(--color-accent-faint);
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

.chart-size-tab {
  padding: 0.375rem 1rem;
  border-radius: 10px;
  border: none;
  font-size: 0.8125rem;
  font-weight: 500;
  color: var(--color-text-secondary);
  background: transparent;
  transition: all 0.15s ease;
  cursor: pointer;
}

.chart-size-tab:hover {
  color: var(--color-text-primary);
}

.chart-size-tab--active {
  background: var(--color-surface);
  color: var(--color-brand-600);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.chart-export-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 1rem;
  border-radius: 10px;
  border: 1px solid var(--color-border-soft);
  font-size: 0.875rem;
  font-weight: 500;
  color: var(--color-text-secondary);
  background: var(--color-surface);
  transition: all 0.15s ease;
  cursor: pointer;
}

.chart-export-btn:hover {
  border-color: var(--color-brand-soft);
  color: var(--color-brand-600);
  background: var(--color-accent-faint);
}

.keywords-wordcount-control {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem 0 0;
  border-top: 1px dashed var(--color-border-soft);
  margin-top: 0.5rem;
}

.keywords-wordcount-label {
  font-size: 0.8125rem;
  font-weight: 500;
  color: var(--color-text-muted);
}

.keywords-wordcount-options {
  display: inline-flex;
  gap: 0.25rem;
}

.keywords-wordcount-btn {
  padding: 0.375rem 0.75rem;
  border-radius: 0.5rem;
  border: 1px solid var(--color-border-soft);
  font-size: 0.75rem;
  font-weight: 500;
  color: var(--color-text-secondary);
  background: var(--color-surface);
  transition: all 0.15s ease;
  cursor: pointer;
}

.keywords-wordcount-btn:hover {
  border-color: var(--color-brand-soft);
  color: var(--color-text-primary);
}

.keywords-wordcount-btn--active {
  border-color: var(--color-brand-soft);
  color: var(--color-brand-600);
  background: var(--color-accent-faint);
}
</style>
