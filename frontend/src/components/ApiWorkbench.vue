<template>
  <section class="workbench">
    <header class="workbench__header">
      <div>
        <h1>Opinion System API 测试台</h1>
        <p>在此页面快速验证后端接口，辅助排查数据管线及数据库交互问题。</p>
      </div>
      <button type="button" class="workbench__status" @click="checkStatus" :disabled="loading.status">
        {{ loading.status ? '检查中…' : '检查后端状态' }}
      </button>
    </header>

    <div class="workbench__grid">
      <section class="card">
        <header>
          <h2>服务状态</h2>
          <p>确认 Flask 服务可用并返回实时状态。</p>
        </header>
        <pre>{{ statusResult }}</pre>
      </section>

      <section class="card">
        <header>
          <h2>数据库查询</h2>
          <p>执行默认查询以验证数据库连接。</p>
        </header>
        <button type="button" class="card__action" @click="runQuery" :disabled="loading.query">
          {{ loading.query ? '执行中…' : '查询数据' }}
        </button>
        <pre>{{ queryResult }}</pre>
      </section>
    </div>

    <section class="card card--wide">
      <header>
        <h2>数据管线操作</h2>
        <p>触发合并、清洗、筛选或上传流程。</p>
      </header>
      <form class="form" @submit.prevent="runPipeline">
        <label>
          专题 Topic
          <input v-model="pipelineForm.topic" type="text" placeholder="例如：示例专题" required />
        </label>
        <label>
          日期 Date (YYYY-MM-DD)
          <input v-model="pipelineForm.date" type="text" placeholder="2024-01-01" required />
        </label>
        <label>
          操作 Operation
          <select v-model="pipelineForm.operation" required>
            <option value="merge">Merge</option>
            <option value="clean">Clean</option>
            <option value="filter">Filter</option>
            <option value="upload">Upload</option>
          </select>
        </label>
        <button type="submit" :disabled="loading.pipeline">
          {{ loading.pipeline ? '执行中…' : '执行操作' }}
        </button>
      </form>
      <pre>{{ pipelineResult }}</pre>
    </section>

    <section class="card card--wide">
      <header>
        <h2>数据提取</h2>
        <p>按时间范围获取专题数据。</p>
      </header>
      <form class="form" @submit.prevent="fetchData">
        <label>
          专题 Topic
          <input v-model="fetchForm.topic" type="text" placeholder="例如：示例专题" required />
        </label>
        <label>
          开始日期 Start (YYYY-MM-DD)
          <input v-model="fetchForm.start" type="text" placeholder="2024-01-01" required />
        </label>
        <label>
          结束日期 End (YYYY-MM-DD)
          <input v-model="fetchForm.end" type="text" placeholder="2024-01-07" required />
        </label>
        <button type="submit" :disabled="loading.fetch">
          {{ loading.fetch ? '提取中…' : '提取数据' }}
        </button>
      </form>
      <pre>{{ fetchResult }}</pre>
    </section>

    <section class="card card--wide">
      <header>
        <h2>数据分析</h2>
        <p>运行分析函数，可选指定函数名。</p>
      </header>
      <form class="form" @submit.prevent="analyzeData">
        <label>
          专题 Topic
          <input v-model="analyzeForm.topic" type="text" placeholder="例如：示例专题" required />
        </label>
        <label>
          开始日期 Start (YYYY-MM-DD)
          <input v-model="analyzeForm.start" type="text" placeholder="2024-01-01" required />
        </label>
        <label>
          结束日期 End (YYYY-MM-DD)
          <input v-model="analyzeForm.end" type="text" placeholder="2024-01-07" required />
        </label>
        <label>
          (可选) 指定函数 Function
          <input v-model="analyzeForm.functionName" type="text" placeholder="函数名称" />
        </label>
        <button type="submit" :disabled="loading.analyze">
          {{ loading.analyze ? '分析中…' : '运行分析' }}
        </button>
      </form>
      <pre>{{ analyzeResult }}</pre>
    </section>
  </section>
</template>

<script setup>
import { reactive, ref } from 'vue'

const API_BASE_FALLBACK = 'http://127.0.0.1:8000'

const backendBase = ref(API_BASE_FALLBACK)
const configLoaded = ref(false)

const loading = reactive({
  status: false,
  query: false,
  pipeline: false,
  fetch: false,
  analyze: false
})

const statusResult = ref('等待调用...')
const queryResult = ref('等待调用...')
const pipelineResult = ref('等待调用...')
const fetchResult = ref('等待调用...')
const analyzeResult = ref('等待调用...')

const pipelineForm = reactive({
  topic: '',
  date: '',
  operation: 'merge'
})

const fetchForm = reactive({
  topic: '',
  start: '',
  end: ''
})

const analyzeForm = reactive({
  topic: '',
  start: '',
  end: '',
  functionName: ''
})

const prettify = (data) => JSON.stringify(data, null, 2)

const errorPayload = (error) => ({
  status: 'error',
  message: error instanceof Error ? error.message : String(error)
})

const ensureConfig = async () => {
  if (configLoaded.value) return
  try {
    const response = await fetch(`${backendBase.value}/api/config`)
    if (!response.ok) throw new Error(`配置获取失败: ${response.status}`)
    const config = await response.json()
    if (config.backend?.base_url) {
      backendBase.value = config.backend.base_url
    } else if (config.backend?.host && config.backend?.port) {
      backendBase.value = `http://${config.backend.host}:${config.backend.port}`
    }
  } catch (error) {
    console.warn('加载配置失败，使用默认后端地址', error)
  } finally {
    configLoaded.value = true
  }
}

const callApi = async (path, options = {}) => {
  await ensureConfig()
  const response = await fetch(`${backendBase.value}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options
  })
  if (!response.ok) {
    const message = await response.text()
    throw new Error(message || `请求失败: ${response.status}`)
  }
  return response.json()
}

const withLoading = async (key, fn, onSuccess) => {
  if (loading[key]) return
  loading[key] = true
  try {
    const data = await fn()
    onSuccess(prettify(data))
  } catch (error) {
    onSuccess(prettify(errorPayload(error)))
  } finally {
    loading[key] = false
  }
}

const checkStatus = () =>
  withLoading('status', () => callApi('/api/status', { method: 'GET' }), (value) => {
    statusResult.value = value
  })

const runQuery = () =>
  withLoading('query', () => callApi('/api/query', { method: 'POST', body: JSON.stringify({}) }), (value) => {
    queryResult.value = value
  })

const runPipeline = () =>
  withLoading(
    'pipeline',
    () =>
      callApi(`/api/${pipelineForm.operation}`, {
        method: 'POST',
        body: JSON.stringify({ topic: pipelineForm.topic, date: pipelineForm.date })
      }),
    (value) => {
      pipelineResult.value = value
    }
  )

const fetchData = () =>
  withLoading(
    'fetch',
    () =>
      callApi('/api/fetch', {
        method: 'POST',
        body: JSON.stringify({
          topic: fetchForm.topic,
          start: fetchForm.start,
          end: fetchForm.end
        })
      }),
    (value) => {
      fetchResult.value = value
    }
  )

const analyzeData = () =>
  withLoading(
    'analyze',
    () => {
      const payload = {
        topic: analyzeForm.topic,
        start: analyzeForm.start,
        end: analyzeForm.end
      }
      if (analyzeForm.functionName) {
        payload.function = analyzeForm.functionName
      }
      return callApi('/api/analyze', { method: 'POST', body: JSON.stringify(payload) })
    },
    (value) => {
      analyzeResult.value = value
    }
  )

checkStatus()
</script>

<style scoped>
.workbench {
  display: flex;
  flex-direction: column;
  gap: 2rem;
}

.workbench__header {
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

.workbench__header h1 {
  margin: 0;
  font-size: 1.8rem;
  font-weight: 700;
}

.workbench__header p {
  margin: 0.35rem 0 0;
  color: #475569;
}

.workbench__status {
  border: none;
  background: linear-gradient(135deg, #2563eb 0%, #7c3aed 100%);
  color: #fff;
  padding: 0.7rem 1.4rem;
  border-radius: 999px;
  cursor: pointer;
  font-weight: 600;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.workbench__status:disabled {
  opacity: 0.65;
  cursor: not-allowed;
}

.workbench__status:not(:disabled):hover {
  transform: translateY(-1px);
  box-shadow: 0 12px 25px rgba(37, 99, 235, 0.25);
}

.workbench__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 1.75rem;
}

.card {
  background: rgba(255, 255, 255, 0.92);
  border-radius: 24px;
  padding: 1.75rem 1.5rem;
  border: 1px solid rgba(148, 163, 184, 0.16);
  display: flex;
  flex-direction: column;
  gap: 1rem;
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

.card__action {
  align-self: flex-start;
  border: none;
  background: rgba(37, 99, 235, 0.12);
  color: #1d4ed8;
  font-weight: 600;
  padding: 0.65rem 1.1rem;
  border-radius: 999px;
  cursor: pointer;
  transition: background 0.2s ease;
}

.card__action:hover {
  background: rgba(37, 99, 235, 0.2);
}

.card--wide pre {
  min-height: 140px;
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

input,
select,
button[type='submit'] {
  padding: 0.65rem 0.75rem;
  border-radius: 12px;
  border: 1px solid rgba(148, 163, 184, 0.4);
  font-size: 0.95rem;
  font-family: inherit;
}

button[type='submit'] {
  background: linear-gradient(135deg, #2563eb 0%, #7c3aed 100%);
  color: #fff;
  font-weight: 600;
  cursor: pointer;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

button[type='submit']:disabled {
  opacity: 0.65;
  cursor: not-allowed;
}

button[type='submit']:not(:disabled):hover {
  transform: translateY(-1px);
  box-shadow: 0 12px 25px rgba(76, 29, 149, 0.25);
}

pre {
  margin: 0;
  background: #0f172a;
  color: #e2e8f0;
  border-radius: 18px;
  padding: 1.2rem;
  overflow-x: auto;
  font-size: 0.9rem;
  line-height: 1.6;
}

@media (max-width: 640px) {
  .workbench__header {
    flex-direction: column;
    align-items: flex-start;
  }

  .card {
    border-radius: 20px;
  }
}
</style>
