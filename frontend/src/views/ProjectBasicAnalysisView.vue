<template>
  <div class="basic-analysis">
    <header class="page-hero">
      <div>
        <p class="page-hero__eyebrow">
          <BeakerIcon class="h-4 w-4" />
          专题分析
        </p>
        <h1>远程专题基础分析</h1>
        <p>选定专题、抓取时间段，然后直接查看情感、声量、地域等基础指标。</p>
      </div>
    </header>

    <section class="panel fetch-panel">
      <header class="panel__header">
        <div>
          <p class="panel__eyebrow">第 1 步</p>
          <h2>拉取远程数据</h2>
          <p>确定专题和时间区间，系统会去远程数据库同步该段数据，方便随后分析。</p>
        </div>
        <button type="button" class="btn ghost" :disabled="fetchState.loading" @click="resetFetchForm">
          重置
        </button>
      </header>
      <form class="panel__form" @submit.prevent="runFetch">
        <div class="form-grid">
          <label>
            <span>专题 Topic *</span>
            <div class="select-inline">
              <select
                v-model="fetchForm.topic"
                :disabled="topicsState.loading || !topicOptions.length"
                required
              >
                <option value="" disabled>请选择远程专题</option>
                <option v-for="option in topicOptions" :key="option" :value="option">{{ option }}</option>
              </select>
              <button type="button" class="btn tiny" :disabled="topicsState.loading" @click="loadTopics">
                {{ topicsState.loading ? '加载中…' : '刷新' }}
              </button>
            </div>
            <p class="field-hint" v-if="topicsState.loading">正在从远程数据库读取专题列表…</p>
            <p class="field-hint error" v-else-if="topicsState.error">{{ topicsState.error }}</p>
            <p class="field-hint" v-else>下拉列表展示当前可用的远程专题。</p>
          </label>
          <label>
            <span>开始日期 Start *</span>
            <input v-model="fetchForm.start" type="date" required />
          </label>
          <label>
            <span>结束日期 End *</span>
            <input v-model="fetchForm.end" type="date" required />
          </label>
        </div>
        <p
          class="field-hint availability-hint"
          :class="{ error: Boolean(availableRange.error) }"
          aria-live="polite"
        >
          <template v-if="!fetchForm.topic">
            请选择远程专题以查看可用日期区间。
          </template>
          <template v-else-if="availableRange.loading">
            正在查询该专题的可用日期区间…
          </template>
          <template v-else-if="availableRange.error">
            无法获取可用日期：{{ availableRange.error }}
          </template>
          <template v-else-if="availableRange.start && availableRange.end">
            可用数据区间：{{ availableRange.start }} → {{ availableRange.end }}
          </template>
          <template v-else>
            当前专题暂无 published_at 日期，可能尚未写入远程数据。
          </template>
        </p>
        <div class="panel__actions">
          <button type="submit" class="btn primary" :disabled="fetchState.loading">
            {{ fetchState.loading ? '提取中…' : '执行 Fetch' }}
          </button>
          <span class="panel__hint">点击执行后系统会即时抓取数据，稍等片刻即可继续分析。</span>
        </div>
      </form>
      <ul class="log-list" v-if="fetchLogs.length">
        <li v-for="log in fetchLogs" :key="log.id" :class="['log-item', log.status]">
          <span>{{ log.time }}</span>
          <strong>{{ log.label }}</strong>
          <p>{{ log.message }}</p>
        </li>
      </ul>
      <p v-else class="log-placeholder">暂无提取记录。</p>
    </section>

    <section class="panel analyze-panel">
      <header class="panel__header">
        <div>
          <p class="panel__eyebrow">第 2 步</p>
          <h2>生成分析面板</h2>
          <p>挑选想看的指标，系统会在相同专题与时间范围内跑出图表和数据表。</p>
        </div>
        <div class="analyze-panel__actions">
          <button type="button" class="btn secondary" :disabled="analyzeState.running" @click="selectAll">
            全部选择
          </button>
          <button type="button" class="btn secondary" :disabled="analyzeState.running" @click="clearSelection">
            取消全选
          </button>
        </div>
      </header>

      <form class="panel__form" @submit.prevent="runSelectedFunctions">
        <div class="form-grid">
          <label>
            <span>专题 Topic *</span>
            <select
              v-model="analyzeForm.topic"
              :disabled="topicsState.loading || !topicOptions.length"
              required
            >
              <option value="" disabled>请选择远程专题</option>
              <option v-for="option in topicOptions" :key="`analyze-${option}`" :value="option">{{ option }}</option>
            </select>
            <p class="field-hint">默认为上方已选专题，也可以单独调整。</p>
          </label>
          <label>
            <span>开始日期 Start *</span>
            <input v-model="analyzeForm.start" type="date" required />
          </label>
          <label>
            <span>结束日期 End *</span>
            <input v-model="analyzeForm.end" type="date" required />
          </label>
        </div>
        <div class="panel__actions">
          <button type="submit" class="btn primary" :disabled="analyzeState.running">
            {{ analyzeState.running ? '执行中…' : '运行所选分析' }}
          </button>
          <button
            type="button"
            class="btn ghost"
            :disabled="analyzeState.running || loadState.loading"
            @click="loadResults"
          >
            {{ loadState.loading ? '读取中…' : '刷新当前结果' }}
          </button>
          <span class="panel__hint">运行成功后会自动刷新结果面板，可在下方预览 ECharts 配置。</span>
        </div>
      </form>

      <div class="functions-grid">
        <article
          v-for="func in analysisFunctions"
          :key="func.id"
          :class="['function-card', selectedFunctions.includes(func.id) ? 'selected' : '']"
        >
          <div class="function-card__header">
            <div>
              <label>
                <input
                  type="checkbox"
                  :value="func.id"
                  v-model="selectedFunctions"
                  :disabled="analyzeState.running"
                />
                <span>{{ func.label }}</span>
              </label>
              <p>{{ func.description }}</p>
            </div>
            <button type="button" class="btn tiny" :disabled="analyzeState.running" @click="runSingleFunction(func.id)">
              单独运行
            </button>
          </div>
        </article>
      </div>

      <ul class="log-list" v-if="analyzeLogs.length">
        <li v-for="log in analyzeLogs" :key="log.id" :class="['log-item', log.status]">
          <span>{{ log.time }}</span>
          <strong>{{ log.label }}</strong>
          <p>{{ log.message }}</p>
        </li>
      </ul>
      <p v-else class="log-placeholder">暂无 Analyze 调度记录。</p>
    </section>

<section class="panel summary-panel" v-if="analysisSummary">
      <header class="panel__header">
        <div>
          <p class="panel__eyebrow">结果概览</p>
          <h2>专题「{{ analysisSummary.topic }}」 · {{ analysisSummary.range.start }} → {{ analysisSummary.range.end }}</h2>
          <p>共 {{ analysisSummary.functionCount }} 个分析结果，可直接在下方查看。</p>
          <p class="summary-meta">最近刷新：{{ lastLoaded || '尚未读取' }}</p>
        </div>
        <button type="button" class="btn ghost" :disabled="loadState.loading" @click="loadResults">
          刷新 JSON
        </button>
      </header>
    </section>

    <section v-if="analysisSections.length" class="chart-grid">
      <div v-for="section in analysisSections" :key="section.name" class="chart-block">
        <header class="chart-block__header">
          <div>
            <p>{{ section.name.toUpperCase() }}</p>
            <h3>{{ section.label }}</h3>
            <p>{{ section.description }}</p>
          </div>
          <span>{{ section.targets.length }} 个结果</span>
        </header>
        <div class="chart-block__content">
          <AnalysisChartPanel
            v-for="target in section.targets"
            :key="`${section.name}-${target.target}`"
            :title="target.title"
            :description="target.subtitle"
            :option="target.option"
            :has-data="target.hasData"
          >
            <template #default>
              <div v-if="target.rows.length" class="data-table">
                <table>
                  <thead>
                    <tr>
                      <th>名称</th>
                      <th>数值</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="(row, index) in target.rows" :key="`${target.target}-${index}`">
                      <td>{{ rowName(row) }}</td>
                      <td>{{ rowValue(row) }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <details class="raw-json">
                <summary>查看原始 JSON</summary>
                <pre>{{ target.rawText }}</pre>
              </details>
            </template>
          </AnalysisChartPanel>
        </div>
      </div>
    </section>

    <section v-else class="empty-state">
      <p>暂无分析结果。请先执行 Fetch 和 Analyze，再点击“刷新 JSON”加载数据。</p>
    </section>
  </div>
</template>

<script setup>
import { BeakerIcon } from '@heroicons/vue/24/outline'
import { computed, reactive, ref, watch, onMounted } from 'vue'

import AnalysisChartPanel from '../components/AnalysisChartPanel.vue'
import { useBackendClient } from '../composables/useBackendClient'

const analysisFunctions = [
  {
    id: 'attitude',
    label: '情感分析 attitude',
    description: '统计 Positive / Negative / Neutral 的占比。'
  },
  {
    id: 'classification',
    label: '话题分类 classification',
    description: '基于 classification 字段的数量分布。'
  },
  {
    id: 'geography',
    label: '地域分析 geography',
    description: '按地域字段统计声量，适合地图或水平条形图。'
  },
  {
    id: 'keywords',
    label: '关键词分析 keywords',
    description: '从正文中提取高频关键词并统计词频。'
  },
  {
    id: 'publishers',
    label: '发布者分析 publishers',
    description: '统计 author 列中高频的媒体/账号。'
  },
  {
    id: 'trends',
    label: '趋势分析 trends',
    description: '按日期统计声量趋势，依赖 published_at。'
  },
  {
    id: 'volume',
    label: '声量分析 volume',
    description: '按渠道统计 JSONL 行数，评估声量占比。'
  }
]

const { callApi } = useBackendClient()

const topicsState = reactive({
  loading: false,
  error: '',
  options: []
})

const topicOptions = computed(() => topicsState.options)

const fetchForm = reactive({
  topic: '',
  start: '',
  end: ''
})
const analyzeForm = reactive({
  topic: '',
  start: '',
  end: ''
})

const availableRange = reactive({
  loading: false,
  error: '',
  start: '',
  end: ''
})
let availabilityRequestId = 0

const fetchState = reactive({ loading: false })
const analyzeState = reactive({ running: false })
const loadState = reactive({ loading: false })

const fetchLogs = ref([])
const analyzeLogs = ref([])
const selectedFunctions = ref(analysisFunctions.map((f) => f.id))

const analysisData = ref(null)
const lastLoaded = ref('')

const ensureTopicSelection = () => {
  if (!topicOptions.value.length) return
  if (!fetchForm.topic || !topicOptions.value.includes(fetchForm.topic)) {
    fetchForm.topic = topicOptions.value[0]
  }
  if (!analyzeForm.topic) {
    analyzeForm.topic = fetchForm.topic
  }
}

const resetAvailableRange = () => {
  availableRange.start = ''
  availableRange.end = ''
}

const clearAvailableRange = () => {
  availabilityRequestId += 1
  resetAvailableRange()
  availableRange.error = ''
  availableRange.loading = false
}

const applyAvailableRangeToForms = () => {
  const startValue = availableRange.start || ''
  const endValue = availableRange.end || startValue || ''
  fetchForm.start = startValue
  fetchForm.end = endValue
}

const loadAvailableRange = async () => {
  const topic = (fetchForm.topic || '').trim()
  if (!topic) {
    availableRange.loading = false
    clearAvailableRange()
    return
  }
  const requestId = ++availabilityRequestId
  availableRange.loading = true
  availableRange.error = ''
  try {
    const params = new URLSearchParams({ topic })
    const response = await callApi(`/api/fetch/availability?${params.toString()}`, { method: 'GET' })
    if (requestId !== availabilityRequestId) return
    const range = response?.data?.range ?? {}
    availableRange.start = range.start || ''
    availableRange.end = range.end || ''
    applyAvailableRangeToForms()
  } catch (error) {
    if (requestId !== availabilityRequestId) return
    resetAvailableRange()
    availableRange.error = error instanceof Error ? error.message : String(error)
  } finally {
    if (requestId === availabilityRequestId) {
      availableRange.loading = false
    }
  }
}

const loadTopics = async () => {
  topicsState.loading = true
  topicsState.error = ''
  const previousTopic = fetchForm.topic
  try {
    const response = await callApi('/api/query', { method: 'POST', body: JSON.stringify({}) })
    const databases = response?.data?.databases ?? []
    topicsState.options = databases
      .map((db) => String(db?.name || '').trim())
      .filter((name, index, arr) => name && arr.indexOf(name) === index)
    ensureTopicSelection()
    if (fetchForm.topic === previousTopic) {
      await loadAvailableRange()
    }
  } catch (error) {
    topicsState.error = error instanceof Error ? error.message : '加载远程数据源失败'
    topicsState.options = []
    fetchForm.topic = ''
    analyzeForm.topic = ''
    clearAvailableRange()
  } finally {
    topicsState.loading = false
  }
}

const resetFetchForm = () => {
  fetchForm.topic = topicOptions.value[0] || ''
  if (availableRange.start || availableRange.end) {
    applyAvailableRangeToForms()
  } else {
    fetchForm.start = ''
    fetchForm.end = ''
  }
}

watch(topicOptions, () => {
  ensureTopicSelection()
})

watch(
  () => fetchForm.topic,
  (value) => {
    const topicValue = (value || '').trim()
    if (topicValue) {
      analyzeForm.topic = topicValue
      loadAvailableRange()
    } else {
      analyzeForm.topic = ''
      loadAvailableRange()
    }
  }
)

watch(
  () => fetchForm.start,
  (value) => {
    analyzeForm.start = value
    if (!fetchForm.end) {
      analyzeForm.end = value
    }
  }
)

watch(
  () => fetchForm.end,
  (value) => {
    analyzeForm.end = value || analyzeForm.start || ''
  }
)

const appendLog = (collection, payload) => {
  const now = new Date().toLocaleTimeString()
  collection.value = [
    { id: `${payload.label}-${Date.now()}`, time: now, ...payload },
    ...collection.value
  ].slice(0, 8)
}

const normalizeRange = (form) => {
  const topic = (form.topic || '').trim()
  const start = (form.start || '').trim()
  const end = (form.end || '').trim() || start
  return { topic, start, end }
}

const runFetch = async () => {
  const { topic, start, end } = normalizeRange(fetchForm)
  if (!topic || !start || !end) {
    appendLog(fetchLogs, { label: '参数校验', message: 'Topic / Start / End 为必填', status: 'error' })
    return
  }

  fetchState.loading = true
  try {
    await callApi('/api/fetch', {
      method: 'POST',
      body: JSON.stringify({
        topic,
        start,
        end
      })
    })
    appendLog(fetchLogs, { label: 'Fetch', message: `已触发 ${topic} ${start}→${end}`, status: 'ok' })
  } catch (error) {
    appendLog(fetchLogs, {
      label: 'Fetch',
      message: error instanceof Error ? error.message : String(error),
      status: 'error'
    })
  } finally {
    fetchState.loading = false
  }
}

const invokeAnalyze = async (functions) => {
  const { topic, start, end } = normalizeRange(analyzeForm)
  if (!topic || !start || !end) {
    appendLog(analyzeLogs, { label: '参数校验', message: 'Topic / Start / End 为必填', status: 'error' })
    return
  }

  analyzeState.running = true
  try {
    for (const func of functions) {
      try {
        await callApi('/api/analyze', {
          method: 'POST',
          body: JSON.stringify({
            topic,
            start,
            end,
            function: func
          })
        })
        const meta = analysisFunctions.find((item) => item.id === func)
        appendLog(analyzeLogs, {
          label: meta?.label || func,
          message: '运行成功，结果已写入 analyze 目录',
          status: 'ok'
        })
      } catch (error) {
        appendLog(analyzeLogs, {
          label: func,
          message: error instanceof Error ? error.message : String(error),
          status: 'error'
        })
      }
    }
  } finally {
    analyzeState.running = false
  }
  await loadResults()
}

const runSelectedFunctions = async () => {
  if (!selectedFunctions.value.length) {
    appendLog(analyzeLogs, { label: '提示', message: '请至少选择一个函数', status: 'error' })
    return
  }
  await invokeAnalyze([...selectedFunctions.value])
}

const runSingleFunction = async (funcId) => {
  await invokeAnalyze([funcId])
}

const selectAll = () => {
  selectedFunctions.value = analysisFunctions.map((f) => f.id)
}

const clearSelection = () => {
  selectedFunctions.value = []
}

const loadResults = async () => {
  const { topic, start, end } = normalizeRange(analyzeForm)
  if (!topic || !start || !end) {
    appendLog(analyzeLogs, { label: '读取', message: 'Topic / Start / End 为必填', status: 'error' })
    return
  }
  loadState.loading = true
  try {
    const params = new URLSearchParams({
      topic,
      start,
      end
    })
    const response = await callApi(`/api/analyze/results?${params.toString()}`, { method: 'GET' })
    analysisData.value = response
    lastLoaded.value = new Date().toLocaleString()
  } catch (error) {
    appendLog(analyzeLogs, {
      label: '读取',
      message: error instanceof Error ? error.message : String(error),
      status: 'error'
    })
    analysisData.value = null
  } finally {
    loadState.loading = false
  }
}

onMounted(() => {
  loadTopics()
})

const analysisSummary = computed(() => {
  if (!analysisData.value?.topic) return null
  return {
    topic: analysisData.value.topic,
    range: analysisData.value.range,
    functionCount: analysisData.value.functions?.length || 0
  }
})

const rowName = (row) => {
  if (!row) return '-'
  return row.name ?? row.label ?? row.key ?? '未命名'
}

const rowValue = (row) => {
  if (!row) return 0
  return row.value ?? row.count ?? row.total ?? 0
}

const extractRows = (payload) => {
  if (!payload) return []
  if (Array.isArray(payload)) return payload
  if (Array.isArray(payload.data)) return payload.data
  return []
}

const ensureNumber = (value) => {
  const num = Number(value)
  return Number.isFinite(num) ? num : 0
}

const buildBarOption = (title, rows, orientation = 'vertical', categoryLabel = '类别', valueLabel = '数量') => {
  const categories = rows.map((row) => rowName(row))
  const values = rows.map((row) => ensureNumber(rowValue(row)))
  const isVertical = orientation !== 'horizontal'
  const catAxis = {
    type: 'category',
    data: categories,
    axisLabel: { interval: 0, color: '#303d47' },
    axisLine: { lineStyle: { color: '#d0d5d9' } }
  }
  const valAxis = {
    type: 'value',
    axisLabel: { color: '#303d47' },
    splitLine: { lineStyle: { color: '#e2e9f1' } }
  }
  return {
    color: ['#9ab2cb'],
    title: { text: title, left: 'center', textStyle: { color: '#1c252c' } },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: 60, right: 30, top: 60, bottom: 60, containLabel: true },
    xAxis: isVertical ? catAxis : valAxis,
    yAxis: isVertical ? valAxis : catAxis,
    dataset: {
      dimensions: [categoryLabel, valueLabel],
      source: rows.map((row) => ({ name: rowName(row), value: ensureNumber(rowValue(row)) }))
    },
    series: [
      {
        type: 'bar',
        data: values,
        label: { show: true, color: '#303d47' }
      }
    ]
  }
}

const buildLineOption = (title, rows, categoryLabel = '日期', valueLabel = '数量') => {
  const categories = rows.map((row) => rowName(row))
  const values = rows.map((row) => ensureNumber(rowValue(row)))
  return {
    color: ['#7babce'],
    title: { text: title, left: 'center', textStyle: { color: '#1c252c' } },
    tooltip: { trigger: 'axis' },
    grid: { left: 50, right: 30, top: 60, bottom: 60, containLabel: true },
    xAxis: { type: 'category', boundaryGap: false, data: categories, axisLabel: { color: '#303d47' } },
    yAxis: { type: 'value', axisLabel: { color: '#303d47' }, splitLine: { lineStyle: { color: '#e2e9f1' } } },
    dataset: {
      dimensions: [categoryLabel, valueLabel],
      source: rows.map((row) => ({ name: rowName(row), value: ensureNumber(rowValue(row)) }))
    },
    series: [
      {
        type: 'line',
        smooth: true,
        areaStyle: { opacity: 0.1 },
        data: values
      }
    ]
  }
}

const buildPieOption = (title, rows) => ({
  title: { text: title, left: 'center', textStyle: { color: '#1c252c' } },
  tooltip: { trigger: 'item' },
  legend: { bottom: 0, type: 'scroll', textStyle: { color: '#303d47' } },
  series: [
    {
      type: 'pie',
      radius: ['40%', '70%'],
      center: ['50%', '45%'],
      data: rows.map((row) => ({ name: rowName(row), value: ensureNumber(rowValue(row)) })),
      label: { formatter: '{b}: {d}%' }
    }
  ]
})

const buildFallbackOption = (funcName, rows, targetLabel) => {
  if (!rows.length) return null
  const title = `${funcName} · ${targetLabel}`
  if (funcName === 'trends') return buildLineOption(title, rows)
  if (funcName === 'attitude') return buildPieOption(title, rows)
  const horizontalFunctions = ['geography', 'publishers', 'keywords', 'classification']
  const orientation = horizontalFunctions.includes(funcName) ? 'horizontal' : 'vertical'
  return buildBarOption(title, rows, orientation)
}

const analysisSections = computed(() => {
  const payload = analysisData.value?.functions
  if (!payload) return []
  return payload.map((func) => {
    const meta = analysisFunctions.find((item) => item.id === func.name) || {
      label: func.name,
      description: ''
    }
    const targets = func.targets.map((target) => {
      const rows = extractRows(target.data)
      return {
        target: target.target,
        title: `${meta.label} · ${target.target}`,
        subtitle: `结果文件：${target.file}`,
        option: target.data?.echarts || buildFallbackOption(func.name, rows, target.target),
        hasData: rows.length > 0,
        rows: rows.slice(0, 12),
        rawText: JSON.stringify(target.data ?? {}, null, 2)
      }
    })
    return {
      name: func.name,
      label: meta.label,
      description: meta.description,
      targets
    }
  })
})
</script>

<style scoped>
.basic-analysis {
  display: flex;
  flex-direction: column;
  gap: 2rem;
  color: var(--color-text-primary);
}

.page-hero {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 2rem;
  padding: 2.5rem;
  border-radius: 32px;
  background: linear-gradient(135deg, rgba(154, 178, 203, 0.95), rgba(123, 171, 206, 0.9));
  color: #fff;
}

.page-hero__eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.4rem 1rem;
  border-radius: 999px;
  background: rgb(255 255 255 / 0.12);
  font-size: 0.85rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.page-hero h1 {
  margin: 0.6rem 0 0.3rem;
  font-size: 2.2rem;
}

.page-hero p {
  margin: 0;
  color: rgb(255 255 255 / 0.88);
}

.panel {
  padding: 2rem;
  border-radius: 28px;
  background: var(--color-surface);
  border: 1px solid var(--color-border-soft);
  box-shadow: 0 32px 65px -48px rgba(16, 24, 40, 0.45);
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.panel__header {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
}

.panel__eyebrow {
  margin: 0;
  font-size: 0.8rem;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.1em;
}

.panel__header h2 {
  margin: 0.2rem 0;
  font-size: 1.5rem;
}

.panel__header p {
  margin: 0;
  color: var(--color-text-secondary);
}

.summary-meta {
  margin: 0.4rem 0 0;
  color: var(--color-text-muted);
  font-size: 0.85rem;
}

.panel__form {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 1rem;
}

.form-grid label {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  font-size: 0.9rem;
  color: var(--color-text-secondary);
}

.form-grid input,
.form-grid select {
  border-radius: 18px;
  border: 1px solid var(--color-border-soft);
  padding: 0.65rem 0.9rem;
  font-size: 0.95rem;
  color: var(--color-text-primary);
  background: var(--color-surface);
}

.select-inline {
  display: flex;
  gap: 0.5rem;
  align-items: center;
}

.select-inline select {
  flex: 1;
}

.field-hint {
  margin-top: 0.35rem;
  font-size: 0.8rem;
  color: var(--color-text-muted);
}

.availability-hint {
  margin-bottom: 0;
}

.field-hint.error {
  color: var(--color-danger-500-hex);
}

.panel__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.8rem;
}

.panel__hint {
  font-size: 0.85rem;
  color: var(--color-text-muted);
}

.log-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}

.log-item {
  display: flex;
  gap: 0.7rem;
  padding: 0.8rem 1rem;
  border-radius: 18px;
  background: var(--color-surface-muted);
  border: 1px solid var(--color-border-soft);
  align-items: baseline;
}

.log-item.ok {
  border-color: rgba(110, 143, 117, 0.5);
}

.log-item.error {
  border-color: rgba(159, 89, 89, 0.45);
  color: var(--color-danger-600-hex);
}

.log-item strong {
  min-width: 120px;
}

.log-placeholder {
  margin: 0;
  font-size: 0.9rem;
  color: var(--color-text-muted);
}

.functions-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 1rem;
}

.function-card {
  border: 1px solid var(--color-border-soft);
  border-radius: 20px;
  padding: 1.1rem;
  display: flex;
  flex-direction: column;
  gap: 0.8rem;
  background: var(--color-surface-muted);
}

.function-card.selected {
  border-color: var(--color-brand-400-hex);
  box-shadow: 0 12px 25px -20px rgba(16, 24, 40, 0.35);
}

.function-card__header {
  display: flex;
  justify-content: space-between;
  gap: 0.7rem;
}

.function-card__header label {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
}

.function-card__header span {
  font-weight: 600;
}

.function-card__header p {
  margin: 0;
  font-size: 0.85rem;
  color: var(--color-text-secondary);
}

.chart-grid {
  display: flex;
  flex-direction: column;
  gap: 2rem;
}

.chart-block {
  border: 1px solid var(--color-border-soft);
  border-radius: 26px;
  padding: 1.5rem;
  background: var(--color-surface);
  box-shadow: 0 30px 60px -40px rgba(16, 24, 40, 0.4);
}

.chart-block__header {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
  margin-bottom: 1.25rem;
  color: var(--color-text-secondary);
}

.chart-block__header h3 {
  margin: 0.2rem 0;
  color: var(--color-text-primary);
}

.chart-block__content {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 1.2rem;
}

.data-table {
  margin-top: 1rem;
  border-radius: 16px;
  overflow: hidden;
  border: 1px solid var(--color-border-soft);
}

.data-table table {
  width: 100%;
  border-collapse: collapse;
}

.data-table th,
.data-table td {
  padding: 0.5rem 0.8rem;
  text-align: left;
  font-size: 0.9rem;
}

.data-table thead {
  background: var(--color-surface-muted);
}

.data-table tbody tr:nth-child(even) {
  background: #f6f7f9;
}

.raw-json {
  margin-top: 0.8rem;
}

.raw-json summary {
  cursor: pointer;
  color: var(--color-brand-600-hex);
  font-weight: 600;
}

.raw-json pre {
  margin-top: 0.4rem;
  padding: 0.8rem;
  border-radius: 12px;
  background: #0f172a;
  color: #cbd5f5;
  max-height: 220px;
  overflow: auto;
}

.empty-state {
  padding: 1.5rem;
  border-radius: 24px;
  border: 1px dashed var(--color-border-soft);
  text-align: center;
  color: var(--color-text-muted);
  background: var(--color-surface-muted);
}

.btn {
  border: none;
  border-radius: 24px;
  padding: 0.55rem 1.4rem;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.2s ease;
}

.btn.primary {
  background: var(--color-brand-600-hex);
  color: #fff;
}

.btn.secondary {
  background: transparent;
  border: 1px solid var(--color-border-soft);
  color: var(--color-text-secondary);
}

.btn.ghost {
  background: rgb(var(--color-brand-100) / 0.6);
  color: var(--color-text-primary);
}

.btn.tiny {
  padding: 0.3rem 0.8rem;
  font-size: 0.8rem;
  border: 1px solid var(--color-border-soft);
  background: #fff;
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

@media (max-width: 768px) {
  .page-hero {
    flex-direction: column;
  }

  .panel,
  .chart-block {
    padding: 1.5rem;
  }
}
</style>
