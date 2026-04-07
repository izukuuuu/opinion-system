<template>
  <article class="analysis-chart-card">
    <header class="analysis-chart-card__header">
      <div>
        <h3>{{ title }}</h3>
        <p v-if="description">{{ description }}</p>
      </div>
      <div class="flex items-center gap-2">
        <button
          v-if="hasData && option"
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
    <slot />

    <!-- 展开图表的 Modal -->
    <Teleport to="body">
      <transition
        enter-active-class="transition ease-out duration-200"
        enter-from-class="opacity-0"
        enter-to-class="opacity-100"
        leave-active-class="transition ease-in duration-150"
        leave-from-class="opacity-100"
        leave-to-class="opacity-0"
      >
        <div
          v-if="showModal"
          class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
          @click.self="closeModal"
        >
          <div class="chart-modal" :style="modalStyle">
            <header class="chart-modal__header">
              <div>
                <h2>{{ title }}</h2>
                <p v-if="description">{{ description }}</p>
              </div>
              <button
                type="button"
                class="chart-modal__close-btn"
                @click="closeModal"
                aria-label="关闭"
              >
                <XMarkIcon class="h-5 w-5" />
              </button>
            </header>
            <div class="chart-modal__toolbar">
              <div class="chart-modal__toolbar-group">
                <span class="chart-modal__toolbar-label">高度</span>
                <nav class="chart-modal__size-tabs">
                  <button
                    v-for="size in sizeOptions"
                    :key="`height-${size.value}`"
                    type="button"
                    class="chart-modal__size-tab"
                    :class="{ 'chart-modal__size-tab--active': chartHeight === size.value }"
                    @click="setChartHeight(size.value)"
                  >
                    {{ size.label }}
                  </button>
                </nav>
              </div>
              <div class="chart-modal__toolbar-group">
                <span class="chart-modal__toolbar-label">宽度</span>
                <nav class="chart-modal__size-tabs">
                  <button
                    v-for="size in sizeOptions"
                    :key="`width-${size.value}`"
                    type="button"
                    class="chart-modal__size-tab"
                    :class="{ 'chart-modal__size-tab--active': chartWidth === size.value }"
                    @click="setChartWidth(size.value)"
                  >
                    {{ size.label }}
                  </button>
                </nav>
              </div>
            </div>
            <div class="chart-modal__body">
              <div ref="modalChartRef" class="chart-modal__canvas" :style="canvasStyle"></div>
            </div>
            <footer class="chart-modal__footer">
              <div class="chart-modal__actions">
                <button type="button" class="chart-modal__export-btn" @click="exportChart('png')">
                  <ArrowDownTrayIcon class="h-4 w-4" />
                  <span>导出 PNG</span>
                </button>
                <button type="button" class="chart-modal__export-btn" @click="exportChart('svg')">
                  <ArrowDownTrayIcon class="h-4 w-4" />
                  <span>导出 SVG</span>
                </button>
              </div>
            </footer>
          </div>
        </div>
      </transition>
    </Teleport>
  </article>
</template>

<script setup>
import { echarts } from '@/utils/echarts'
import { onBeforeUnmount, onMounted, ref, watch, nextTick, computed } from 'vue'
import { ArrowsPointingOutIcon, XMarkIcon, ArrowDownTrayIcon } from '@heroicons/vue/24/outline'

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
const modalChartRef = ref(null)
const showModal = ref(false)
const chartWidth = ref('medium')
const chartHeight = ref('medium')
let chartInstance = null
let modalChartInstance = null
let resizeObserver = null

const sizeOptions = [
  { label: '小', value: 'small' },
  { label: '中', value: 'medium' },
  { label: '大', value: 'large' }
]

const sizeWidths = {
  small: '60vw',
  medium: '80vw',
  large: '94vw'
}

const sizeHeights = {
  small: '40vh',
  medium: '55vh',
  large: '70vh'
}

const modalStyle = computed(() => ({
  maxWidth: sizeWidths[chartWidth.value] || sizeWidths.medium
}))

const canvasStyle = computed(() => ({
  height: sizeHeights[chartHeight.value] || sizeHeights.medium
}))

const setChartWidth = async (size) => {
  chartWidth.value = size
  await nextTick()
  if (modalChartInstance) {
    modalChartInstance.resize()
  }
}

const setChartHeight = async (size) => {
  chartHeight.value = size
  await nextTick()
  if (modalChartInstance) {
    modalChartInstance.resize()
  }
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

const renderModalChart = async () => {
  if (!props.option) return
  await nextTick()
  if (!modalChartRef.value) return
  if (!modalChartInstance) {
    modalChartInstance = echarts.init(modalChartRef.value)
  }
  modalChartInstance.setOption(props.option, true)
}

const openModal = async () => {
  showModal.value = true
  chartWidth.value = 'medium'
  chartHeight.value = 'medium'
  await nextTick()
  renderModalChart()
}

const closeModal = () => {
  showModal.value = false
  disposeModalChart()
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

const handleKeydown = (event) => {
  if (showModal.value && event.key === 'Escape') {
    closeModal()
  }
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
  window.addEventListener('keydown', handleKeydown)
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
  disposeModalChart()
  window.removeEventListener('keydown', handleKeydown)
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

/* Modal Styles */
.chart-modal {
  display: flex;
  flex-direction: column;
  width: 90vw;
  max-height: 90vh;
  background: var(--color-surface);
  border-radius: 24px;
  box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
  overflow: hidden;
  transition: max-width 0.2s ease;
}

.chart-modal__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  padding: 1.5rem;
  border-bottom: 1px solid var(--color-border-soft);
}

.chart-modal__header h2 {
  margin: 0;
  font-size: 1.25rem;
  font-weight: 700;
  color: var(--color-text-primary);
}

.chart-modal__header p {
  margin: 0.25rem 0 0;
  font-size: 0.875rem;
  color: var(--color-text-secondary);
}

.chart-modal__close-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 12px;
  border: 1px solid var(--color-border-soft);
  color: var(--color-text-secondary);
  background: var(--color-surface);
  transition: all 0.15s ease;
  cursor: pointer;
}

.chart-modal__close-btn:hover {
  border-color: var(--color-brand-soft);
  color: var(--color-brand-600);
  background: var(--color-accent-faint);
}

.chart-modal__toolbar {
  display: flex;
  justify-content: center;
  gap: 2rem;
  padding: 0.75rem 1.5rem;
  border-bottom: 1px solid var(--color-border-soft);
}

.chart-modal__toolbar-group {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.chart-modal__toolbar-label {
  font-size: 0.8125rem;
  font-weight: 500;
  color: var(--color-text-muted);
}

.chart-modal__size-tabs {
  display: inline-flex;
  gap: 0.25rem;
  padding: 0.25rem;
  border-radius: 12px;
  background: var(--color-surface-muted);
}

.chart-modal__size-tab {
  padding: 0.5rem 1.25rem;
  border-radius: 10px;
  border: none;
  font-size: 0.875rem;
  font-weight: 500;
  color: var(--color-text-secondary);
  background: transparent;
  transition: all 0.15s ease;
  cursor: pointer;
}

.chart-modal__size-tab:hover {
  color: var(--color-text-primary);
}

.chart-modal__size-tab--active {
  background: var(--color-surface);
  color: var(--color-brand-600);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.chart-modal__body {
  flex: 1;
  min-height: 0;
  padding: 1.5rem;
  overflow: auto;
}

.chart-modal__canvas {
  width: 100%;
  min-height: 300px;
  transition: height 0.2s ease;
}

.chart-modal__footer {
  display: flex;
  justify-content: flex-end;
  padding: 1rem 1.5rem;
  border-top: 1px solid var(--color-border-soft);
}

.chart-modal__actions {
  display: flex;
  gap: 0.75rem;
}

.chart-modal__export-btn {
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

.chart-modal__export-btn:hover {
  border-color: var(--color-brand-soft);
  color: var(--color-brand-600);
  background: var(--color-accent-faint);
}
</style>
