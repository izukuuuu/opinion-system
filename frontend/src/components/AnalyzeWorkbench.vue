<template>
  <section class="analyze-workbench">
    <header class="analyze-workbench__header">
      <div>
        <h1>Analyze 模块调度中心</h1>
        <p>按照 <code>backend/src/analyze</code> 的流程批量执行分析任务，并直接预览落盘结果。</p>
      </div>
      <div class="analyze-workbench__actions">
        <button type="button" @click="runSelected" :disabled="runLoading">
          {{ runLoading ? '执行中…' : '运行分析' }}
        </button>
        <button type="button" class="ghost" @click="refreshResults" :disabled="fetchLoading">
          {{ fetchLoading ? '加载中…' : '刷新结果' }}
        </button>
      </div>
    </header>

    <div class="analyze-workbench__grid">
      <section class="card">
        <header>
          <h2>基础参数</h2>
          <p>指定专题及日期范围，未选择结束日期时默认与开始日期相同。</p>
        </header>
        <form class="form" @submit.prevent="runSelected">
          <label>
            专题 Topic
            <input v-model="form.topic" type="text" placeholder="例如：示例专题" required />
          </label>
          <label>
            开始日期 Start (YYYY-MM-DD)
            <input v-model="form.start" type="text" placeholder="2024-01-01" required />
          </label>
          <label>
            结束日期 End (YYYY-MM-DD)
            <input v-model="form.end" type="text" placeholder="默认同开始日期" />
          </label>
          <div class="form__actions">
            <button type="submit" :disabled="runLoading">
              {{ runLoading ? '执行中…' : '运行所选分析' }}
            </button>
            <button type="button" class="ghost" @click="refreshResults" :disabled="fetchLoading">
              {{ fetchLoading ? '加载中…' : '仅刷新结果' }}
            </button>
          </div>
        </form>
        <ul class="status-list" v-if="statusLogs.length">
          <li v-for="log in statusLogs" :key="log.id" :class="[`status-list__item`, log.status]">
            <span class="status-list__label">{{ log.label }}</span>
            <span>{{ log.message }}</span>
          </li>
        </ul>
        <p v-else class="status-placeholder">运行记录会显示在这里。</p>
      </section>

      <section class="card">
        <header>
          <h2>分析功能</h2>
          <p>勾选需要调度的函数，不勾选默认执行配置中的全部函数。</p>
        </header>
        <div class="functions">
          <label
            v-for="func in analyzeFunctions"
            :key="func.id"
            class="functions__item"
          >
            <input type="checkbox" :value="func.id" v-model="selected" />
            <div>
              <div class="functions__title">
                <strong>{{ func.label }}</strong>
                <span>{{ func.target }}</span>
              </div>
              <p>{{ func.description }}</p>
              <p class="functions__meta">输出文件：{{ func.filename }}</p>
            </div>
          </label>
        </div>
      </section>
    </div>

    <section class="card card--wide">
      <header>
        <h2>分析结果预览</h2>
        <p>
          {{ results ? `专题「${results.topic}」 / 时间 ${results.range.start} 至 ${results.range.end}` : '执行后可在此查看分析结果 JSON' }}
        </p>
        <p v-if="lastRefreshed" class="card__meta">最近更新时间：{{ lastRefreshed }}</p>
      </header>

      <template v-if="results">
        <div
          v-for="func in enrichedResults"
          :key="func.name"
          class="result-block"
        >
          <div class="result-block__header">
            <h3>{{ func.label }}</h3>
            <p>{{ func.description }}</p>
          </div>
          <div class="result-block__targets">
            <article
              v-for="target in func.targets"
              :key="`${func.name}-${target.target}`"
              class="result-target"
            >
              <header>
                <h4>{{ target.target }}</h4>
                <span class="result-target__file">{{ target.file }}</span>
              </header>
              <div v-if="rowsFor(target.data).length" class="result-table">
                <table>
                  <thead>
                    <tr>
                      <th>名称</th>
                      <th>数值</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="(row, index) in rowsFor(target.data)" :key="rowId(row, index)">
                      <td>{{ rowName(row) }}</td>
                      <td>{{ rowValue(row) }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <details class="result-raw">
                <summary>查看原始 JSON</summary>
                <pre>{{ pretty(target.data) }}</pre>
              </details>
            </article>
          </div>
        </div>
      </template>
      <p v-else class="results-placeholder">
        暂无可展示的数据。请先运行分析，或确认后端已有落盘结果。
      </p>
    </section>
  </section>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'

import { useBackendClient } from '../composables/useBackendClient'

const analyzeFunctions = [
  {
    id: 'volume',
    label: '声量对比 Volume',
    description: '统计总体及各渠道的样本数量对比。',
    target: '总体 / 渠道',
    filename: 'volume.json'
  },
  {
    id: 'attitude',
    label: '情感分布 Attitude',
    description: '统计正面、负面、中性等情感占比。',
    target: '总体 / 渠道',
    filename: 'attitude.json'
  },
  {
    id: 'trends',
    label: '声量趋势 Trends',
    description: '按日期聚合的声量变化趋势。',
    target: '总体 / 渠道',
    filename: 'trends.json'
  },
  {
    id: 'geography',
    label: '地域分布 Geography',
    description: '按地域统计声量，适合地图展示。',
    target: '总体 / 渠道',
    filename: 'geography.json'
  },
  {
    id: 'publishers',
    label: '发布主体 Publishers',
    description: '统计媒体/账号维度的发帖数量。',
    target: '总体 / 渠道',
    filename: 'publishers.json'
  },
  {
    id: 'keywords',
    label: '关键词 Keywords',
    description: '提取高频关键词，为可视化做准备。',
    target: '总体 / 渠道',
    filename: 'keywords.json'
  },
  {
    id: 'classification',
    label: '分类统计 Classification',
    description: '按标签/分类字段统计数量。',
    target: '总体 / 渠道',
    filename: 'classification.json'
  }
]

const form = reactive({
  topic: '',
  start: '',
  end: ''
})

const selected = ref([])
const statusLogs = ref([])
const results = ref(null)
const lastRefreshed = ref('')

const runLoading = ref(false)
const fetchLoading = ref(false)

const { callApi } = useBackendClient()

const enrichedResults = computed(() => {
  if (!results.value?.functions) return []
  return results.value.functions.map((func) => {
    const meta = analyzeFunctions.find((item) => item.id === func.name) || {}
    return {
      ...func,
      label: meta.label || func.name,
      description: meta.description || '',
    }
  })
})

const pretty = (value) => JSON.stringify(value, null, 2)

const rowsFor = (data) => {
  if (!data) return []
  if (Array.isArray(data)) return data
  if (Array.isArray(data.data)) return data.data
  return []
}

const rowId = (row, index) => {
  if (!row) return `row-${index}`
  if (row.name !== undefined) return `name-${row.name}`
  if (row.label !== undefined) return `label-${row.label}`
  if (row.key !== undefined) return `key-${row.key}`
  return `row-${index}`
}

const rowName = (row) => {
  if (!row) return '-'
  return row.name ?? row.label ?? row.key ?? '-'
}

const rowValue = (row) => {
  if (!row) return '-'
  return row.value ?? row.count ?? row.total ?? '-'
}

const normalisePayload = () => {
  const topic = form.topic.trim()
  const start = form.start.trim()
  const end = (form.end && form.end.trim()) || start
  return { topic, start, end }
}

const appendLog = (payload) => {
  statusLogs.value = [payload, ...statusLogs.value].slice(0, 6)
}

const validateForm = () => {
  const { topic, start, end } = normalisePayload()
  if (!topic || !start) {
    appendLog({ id: Date.now(), label: '参数校验', message: 'Topic 与 Start 为必填项', status: 'error' })
    return null
  }
  if (!end) {
    appendLog({ id: Date.now(), label: '参数校验', message: '无法解析结束日期，请检查输入', status: 'error' })
    return null
  }
  return { topic, start, end }
}

const runSelected = async () => {
  const payload = validateForm()
  if (!payload) return

  const functionsToRun = selected.value.length ? [...selected.value] : [null]
  runLoading.value = true
  try {
    for (const func of functionsToRun) {
      const body = { ...payload }
      let label = '全部函数'
      if (func) {
        body.function = func
        const meta = analyzeFunctions.find((item) => item.id === func)
        label = meta ? meta.label : func
      }
      try {
        await callApi('/api/analyze', {
          method: 'POST',
          body: JSON.stringify(body)
        })
        appendLog({ id: `${Date.now()}-${func || 'all'}`, label, message: '触发成功，结果已落盘', status: 'ok' })
      } catch (error) {
        appendLog({
          id: `${Date.now()}-${func || 'all'}-error`,
          label,
          message: error instanceof Error ? error.message : String(error),
          status: 'error'
        })
      }
    }
  } finally {
    runLoading.value = false
  }
  await refreshResults(payload)
}

const refreshResults = async (prefilled) => {
  const payload = prefilled || validateForm()
  if (!payload) return
  fetchLoading.value = true
  try {
    const params = new URLSearchParams({
      topic: payload.topic,
      start: payload.start,
      end: payload.end
    })
    const response = await callApi(`/api/analyze/results?${params.toString()}`, { method: 'GET' })
    results.value = response
    lastRefreshed.value = new Date().toLocaleString()
  } catch (error) {
    results.value = null
    appendLog({
      id: `${Date.now()}-fetch`,
      label: '结果读取',
      message: error instanceof Error ? error.message : String(error),
      status: 'error'
    })
  } finally {
    fetchLoading.value = false
  }
}
</script>

<style scoped>
.analyze-workbench {
  display: flex;
  flex-direction: column;
  gap: 2rem;
}

.analyze-workbench__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1.5rem;
  background: rgba(255, 255, 255, 0.92);
  border-radius: 24px;
  padding: 1.75rem 2rem;
  border: 1px solid rgba(148, 163, 184, 0.16);
  box-shadow: 0 22px 48px -25px rgba(15, 23, 42, 0.35);
}

.analyze-workbench__header h1 {
  margin: 0;
  font-size: 1.8rem;
  font-weight: 700;
}

.analyze-workbench__header p {
  margin: 0.3rem 0 0;
  color: #475569;
}

.analyze-workbench__actions {
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.analyze-workbench__actions button {
  border: none;
  background: linear-gradient(135deg, #2563eb 0%, #7c3aed 100%);
  color: #fff;
  padding: 0.7rem 1.4rem;
  border-radius: 999px;
  cursor: pointer;
  font-weight: 600;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.analyze-workbench__actions button.ghost {
  background: rgba(37, 99, 235, 0.12);
  color: #1d4ed8;
  box-shadow: none;
}

.analyze-workbench__actions button:disabled {
  opacity: 0.65;
  cursor: not-allowed;
}

.analyze-workbench__actions button:not(:disabled):hover {
  transform: translateY(-1px);
  box-shadow: 0 12px 25px rgba(76, 29, 149, 0.25);
}

.analyze-workbench__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 1.75rem;
}

.card {
  background: rgba(255, 255, 255, 0.92);
  border-radius: 24px;
  padding: 1.75rem 1.5rem;
  border: 1px solid rgba(148, 163, 184, 0.16);
  display: flex;
  flex-direction: column;
  gap: 1.15rem;
  box-shadow: 0 22px 48px -28px rgba(15, 23, 42, 0.32);
}

.card header h2 {
  margin: 0;
  font-size: 1.35rem;
  font-weight: 700;
}

.card header p {
  margin: 0.4rem 0 0;
  color: #475569;
}

.card__meta {
  margin: 0;
  color: #1d4ed8;
  font-size: 0.9rem;
}

.card--wide {
  width: 100%;
}

.form {
  display: grid;
  gap: 1rem;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
}

label {
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
  font-weight: 600;
  color: #1e293b;
}

input {
  padding: 0.65rem 0.75rem;
  border-radius: 12px;
  border: 1px solid rgba(148, 163, 184, 0.4);
  font-size: 0.95rem;
  font-family: inherit;
}

.form__actions {
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.form__actions button {
  border: none;
  background: linear-gradient(135deg, #2563eb 0%, #7c3aed 100%);
  color: #fff;
  padding: 0.65rem 1.2rem;
  border-radius: 12px;
  cursor: pointer;
  font-weight: 600;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.form__actions button.ghost {
  background: rgba(37, 99, 235, 0.12);
  color: #1d4ed8;
  box-shadow: none;
}

.form__actions button:disabled {
  opacity: 0.65;
  cursor: not-allowed;
}

.form__actions button:not(:disabled):hover {
  transform: translateY(-1px);
  box-shadow: 0 12px 25px rgba(37, 99, 235, 0.25);
}

.status-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 0.65rem;
}

.status-list__item {
  display: flex;
  gap: 0.75rem;
  align-items: center;
  padding: 0.6rem 0.8rem;
  border-radius: 12px;
  background: rgba(248, 250, 252, 0.85);
  border: 1px solid rgba(148, 163, 184, 0.24);
  font-size: 0.92rem;
}

.status-list__item.ok {
  border-color: rgba(34, 197, 94, 0.35);
  background: rgba(220, 252, 231, 0.4);
}

.status-list__item.error {
  border-color: rgba(248, 113, 113, 0.4);
  background: rgba(254, 226, 226, 0.45);
}

.status-list__label {
  font-weight: 600;
  color: #0f172a;
}

.status-placeholder {
  margin: 0;
  color: #64748b;
  font-size: 0.92rem;
}

.functions {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.functions__item {
  display: flex;
  gap: 0.9rem;
  align-items: flex-start;
  padding: 0.8rem;
  border-radius: 16px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: rgba(248, 250, 252, 0.65);
}

.functions__item input[type='checkbox'] {
  margin-top: 0.4rem;
}

.functions__item p {
  margin: 0.25rem 0 0;
  color: #475569;
  font-size: 0.92rem;
}

.functions__title {
  display: flex;
  gap: 0.6rem;
  align-items: baseline;
}

.functions__title strong {
  font-size: 1rem;
  color: #0f172a;
}

.functions__title span {
  font-size: 0.85rem;
  color: #2563eb;
  font-weight: 600;
}

.functions__meta {
  margin: 0.4rem 0 0;
  font-size: 0.82rem;
  color: #64748b;
}

.result-block {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  padding: 1.25rem;
  border-radius: 20px;
  border: 1px solid rgba(148, 163, 184, 0.2);
  background: rgba(248, 250, 252, 0.65);
}

.result-block__header h3 {
  margin: 0;
  font-size: 1.25rem;
  font-weight: 700;
}

.result-block__header p {
  margin: 0.3rem 0 0;
  color: #475569;
}

.result-block__targets {
  display: grid;
  gap: 1rem;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
}

.result-target {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  padding: 1rem;
  border-radius: 18px;
  border: 1px solid rgba(148, 163, 184, 0.2);
  background: rgba(255, 255, 255, 0.9);
}

.result-target header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 0.75rem;
}

.result-target h4 {
  margin: 0;
  font-size: 1.05rem;
}

.result-target__file {
  font-size: 0.82rem;
  color: #64748b;
}

.result-table {
  overflow-x: auto;
}

.result-table table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.92rem;
}

.result-table th,
.result-table td {
  padding: 0.45rem 0.55rem;
  border-bottom: 1px solid rgba(148, 163, 184, 0.25);
  text-align: left;
}

.result-raw {
  font-size: 0.88rem;
}

.result-raw summary {
  cursor: pointer;
  color: #2563eb;
}

.result-raw pre {
  margin: 0.6rem 0 0;
  background: #0f172a;
  color: #e2e8f0;
  border-radius: 14px;
  padding: 0.85rem;
  max-height: 260px;
  overflow: auto;
  font-size: 0.85rem;
}

.results-placeholder {
  margin: 0;
  color: #64748b;
  font-size: 0.95rem;
}

@media (max-width: 640px) {
  .analyze-workbench__header {
    flex-direction: column;
    align-items: flex-start;
  }

  .analyze-workbench__actions {
    width: 100%;
    justify-content: flex-start;
  }

  .form__actions {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
