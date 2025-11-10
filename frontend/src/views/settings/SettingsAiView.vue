<template>
  <section class="card-surface space-y-6 p-6">
    <header class="space-y-2">
      <p class="text-xs font-semibold uppercase tracking-[0.4em] text-slate-400">AI 服务</p>
      <h2 class="text-xl font-semibold text-slate-900">大模型配置</h2>
      <p class="text-sm text-slate-500">配置筛选流与对话流使用的模型提供方与参数。</p>
    </header>

    <p v-if="llmState.error" class="rounded-2xl bg-rose-100 px-4 py-3 text-sm text-rose-600">{{ llmState.error }}</p>
    <p v-if="llmState.message" class="rounded-2xl bg-emerald-100 px-4 py-3 text-sm text-emerald-600">{{ llmState.message }}</p>


    <p v-if="credentialState.error" class="rounded-2xl bg-rose-100 px-4 py-3 text-sm text-rose-600">{{ credentialState.error }}</p>
    <p v-if="credentialState.message" class="rounded-2xl bg-emerald-100 px-4 py-3 text-sm text-emerald-600">{{ credentialState.message }}</p>

    <form class="space-y-4 card-surface p-5" @submit.prevent="submitCredentials">
      <header class="space-y-1">
        <h3 class="text-lg font-semibold text-slate-900">API 密钥配置</h3>
        <p class="text-sm text-slate-500">集中管理千问 DashScope 与 OpenAI 兼容接口的 API Key 以及 Base URL。</p>
      </header>
      <div class="grid gap-4 md:grid-cols-2">
        <div class="flex flex-col gap-2 text-sm font-medium text-slate-600">
          <label class="flex flex-col gap-2">
            <span>DashScope API Key</span>
            <input
              v-model.trim="credentialState.form.qwen_api_key"
              type="password"
              autocomplete="new-password"
              placeholder="输入新的 DashScope API Key"
              class="rounded-2xl border border-slate-300 bg-white px-3 py-2 text-sm focus:border-indigo-300 focus:outline-none focus:ring-2 focus:ring-indigo-100"
            />
          </label>
          <p class="text-xs font-normal text-slate-500">
            当前状态：
            <span v-if="credentialState.summary.qwen.configured">已配置 (****{{ credentialState.summary.qwen.last_four }})</span>
            <span v-else>未配置</span>
          </p>
          <button
            v-if="credentialState.summary.qwen.configured"
            type="button"
            class="w-max rounded-full border border-slate-300 px-4 py-1 text-xs font-semibold text-slate-600 hover:bg-slate-50 disabled:opacity-60"
            :disabled="credentialState.loading"
            @click="clearCredential('qwen')"
          >
            清空千问密钥
          </button>
        </div>
        <div class="flex flex-col gap-2 text-sm font-medium text-slate-600">
          <label class="flex flex-col gap-2">
            <span>OpenAI API Key</span>
            <input
              v-model.trim="credentialState.form.openai_api_key"
              type="password"
              autocomplete="new-password"
              placeholder="输入新的 OpenAI API Key"
              class="rounded-2xl border border-slate-300 bg-white px-3 py-2 text-sm focus:border-indigo-300 focus:outline-none focus:ring-2 focus:ring-indigo-100"
            />
          </label>
          <p class="text-xs font-normal text-slate-500">
            当前状态：
            <span v-if="credentialState.summary.openai.configured">已配置 (****{{ credentialState.summary.openai.last_four }})</span>
            <span v-else>未配置</span>
          </p>
          <button
            v-if="credentialState.summary.openai.configured"
            type="button"
            class="w-max rounded-full border border-slate-300 px-4 py-1 text-xs font-semibold text-slate-600 hover:bg-slate-50 disabled:opacity-60"
            :disabled="credentialState.loading"
            @click="clearCredential('openai')"
          >
            清空 OpenAI 密钥
          </button>
        </div>
      </div>
      <label class="flex flex-col gap-2 text-sm font-medium text-slate-600">
        <span>OpenAI Base URL</span>
        <input
          v-model.trim="credentialState.form.openai_base_url"
          type="text"
          placeholder="https://api.example.com/v1"
          class="rounded-2xl border border-slate-300 bg-white px-3 py-2 text-sm focus:border-indigo-300 focus:outline-none focus:ring-2 focus:ring-indigo-100"
        />
        <span class="text-xs font-normal text-slate-500">若使用自建或代理服务，请配置该地址；留空则使用官方默认地址。</span>
      </label>
      <div class="flex flex-wrap gap-3">
        <button
          type="submit"
          class="rounded-full bg-indigo-600 px-5 py-2 text-sm font-semibold text-white shadow hover:bg-indigo-500 disabled:opacity-60"
          :disabled="credentialState.loading"
        >
          保存 API 凭证
        </button>
      </div>
    </form>

    <form class="space-y-4 card-surface p-5" @submit.prevent="submitLlmFilter">
      <header class="space-y-1">
        <h3 class="text-lg font-semibold text-slate-900">筛选模型配置</h3>
        <p class="text-sm text-slate-500">用于舆情筛选流程的 LLM 服务参数。</p>
      </header>
      <div class="grid gap-4 md:grid-cols-2">
        <label class="flex flex-col gap-2 text-sm font-medium text-slate-600">
          <span>服务提供方</span>
          <select
            v-model="llmState.filter.provider"
            class="rounded-2xl border border-slate-300 bg-white px-3 py-2 text-sm focus:border-indigo-300 focus:outline-none focus:ring-2 focus:ring-indigo-100"
          >
            <option
              v-for="option in providerOptions"
              :key="`filter-${option.value}`"
              :value="option.value"
            >
              {{ option.label }}
            </option>
          </select>
        </label>
        <label
          v-if="llmState.filter.provider === 'openai'"
          class="flex flex-col gap-2 text-sm font-medium text-slate-600"
        >
          <span>API Base URL</span>
          <input
            v-model.trim="llmState.filter.base_url"
            type="text"
            placeholder="https://api.example.com/v1"
            class="rounded-2xl border border-slate-300 bg-white px-3 py-2 text-sm focus:border-indigo-300 focus:outline-none focus:ring-2 focus:ring-indigo-100"
          />
        </label>
        <label class="flex flex-col gap-2 text-sm font-medium text-slate-600">
          <span>模型名称</span>
          <input
            v-model.trim="llmState.filter.model"
            type="text"
            :placeholder="filterModelPlaceholder"
            class="rounded-2xl border border-slate-300 bg-white px-3 py-2 text-sm focus:border-indigo-300 focus:outline-none focus:ring-2 focus:ring-indigo-100"
          />
        </label>
        <label class="flex flex-col gap-2 text-sm font-medium text-slate-600">
          <span>QPS</span>
          <input
            v-model.number="llmState.filter.qps"
            type="number"
            min="0"
            class="rounded-2xl border border-slate-300 bg-white px-3 py-2 text-sm focus:border-indigo-300 focus:outline-none focus:ring-2 focus:ring-indigo-100"
          />
        </label>
        <label class="flex flex-col gap-2 text-sm font-medium text-slate-600">
          <span>批处理大小</span>
          <input
            v-model.number="llmState.filter.batch_size"
            type="number"
            min="1"
            class="rounded-2xl border border-slate-300 bg-white px-3 py-2 text-sm focus:border-indigo-300 focus:outline-none focus:ring-2 focus:ring-indigo-100"
          />
        </label>
        <label class="flex flex-col gap-2 text-sm font-medium text-slate-600">
          <span>截断长度</span>
          <input
            v-model.number="llmState.filter.truncation"
            type="number"
            min="0"
            class="rounded-2xl border border-slate-300 bg-white px-3 py-2 text-sm focus:border-indigo-300 focus:outline-none focus:ring-2 focus:ring-indigo-100"
          />
        </label>
      </div>
      <div class="flex flex-wrap gap-3">
        <button type="submit" class="rounded-full bg-indigo-600 px-5 py-2 text-sm font-semibold text-white shadow hover:bg-indigo-500">
          保存筛选配置
        </button>
      </div>
    </form>

    <form class="space-y-4 card-surface p-5" @submit.prevent="submitLlmAssistant">
      <header class="space-y-1">
        <h3 class="text-lg font-semibold text-slate-900">对话模型配置</h3>
        <p class="text-sm text-slate-500">用于项目汇报与问答交互的模型参数。</p>
      </header>
      <div class="grid gap-4 md:grid-cols-2">
        <label class="flex flex-col gap-2 text-sm font-medium text-slate-600">
          <span>服务提供方</span>
          <select
            v-model="llmState.assistant.provider"
            class="rounded-2xl border border-slate-300 bg-white px-3 py-2 text-sm focus:border-indigo-300 focus:outline-none focus:ring-2 focus:ring-indigo-100"
          >
            <option
              v-for="option in providerOptions"
              :key="`assistant-${option.value}`"
              :value="option.value"
            >
              {{ option.label }}
            </option>
          </select>
        </label>
        <label
          v-if="llmState.assistant.provider === 'openai'"
          class="flex flex-col gap-2 text-sm font-medium text-slate-600"
        >
          <span>API Base URL</span>
          <input
            v-model.trim="llmState.assistant.base_url"
            type="text"
            placeholder="https://api.example.com/v1"
            class="rounded-2xl border border-slate-300 bg-white px-3 py-2 text-sm focus:border-indigo-300 focus:outline-none focus:ring-2 focus:ring-indigo-100"
          />
        </label>
        <label class="flex flex-col gap-2 text-sm font-medium text-slate-600">
          <span>模型名称</span>
          <input
            v-model.trim="llmState.assistant.model"
            type="text"
            :placeholder="assistantModelPlaceholder"
            class="rounded-2xl border border-slate-300 bg-white px-3 py-2 text-sm focus:border-indigo-300 focus:outline-none focus:ring-2 focus:ring-indigo-100"
          />
        </label>
        <label class="flex flex-col gap-2 text-sm font-medium text-slate-600">
          <span>最大 Tokens</span>
          <input
            v-model.number="llmState.assistant.max_tokens"
            type="number"
            min="0"
            class="rounded-2xl border border-slate-300 bg-white px-3 py-2 text-sm focus:border-indigo-300 focus:outline-none focus:ring-2 focus:ring-indigo-100"
          />
        </label>
        <label class="flex flex-col gap-2 text-sm font-medium text-slate-600">
          <span>温度</span>
          <input
            v-model.number="llmState.assistant.temperature"
            type="number"
            min="0"
            step="0.1"
            class="rounded-2xl border border-slate-300 bg-white px-3 py-2 text-sm focus:border-indigo-300 focus:outline-none focus:ring-2 focus:ring-indigo-100"
          />
        </label>
      </div>
      <div class="flex flex-wrap gap-3">
        <button type="submit" class="rounded-full bg-indigo-600 px-5 py-2 text-sm font-semibold text-white shadow hover:bg-indigo-500">
          保存对话配置
        </button>
      </div>
    </form>
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, watch } from 'vue'
import { useApiBase } from '../../composables/useApiBase'

const { ensureApiBase } = useApiBase()
const buildApiUrl = async (path) => {
  const baseUrl = await ensureApiBase()
  return `${baseUrl}${path}`
}
const providerOptions = [
  { label: '阿里通义千问（DashScope）', value: 'qwen' },
  { label: 'OpenAI / 兼容 API', value: 'openai' }
]

const llmState = reactive({
  filter: {
    provider: 'qwen',
    model: '',
    qps: 0,
    batch_size: 1,
    truncation: 0,
    base_url: ''
  },
  assistant: {
    provider: 'qwen',
    model: '',
    max_tokens: 0,
    temperature: 0,
    base_url: ''
  },
  loading: false,
  error: '',
  message: ''
})

const credentialState = reactive({
  summary: {
    qwen: { configured: false, last_four: '' },
    openai: { configured: false, last_four: '' },
    openai_base_url: ''
  },
  form: {
    qwen_api_key: '',
    openai_api_key: '',
    openai_base_url: ''
  },
  loading: false,
  error: '',
  message: ''
})

const filterModelPlaceholder = computed(() =>
  llmState.filter.provider === 'openai' ? '如：gpt-3.5-turbo' : '如：qwen-plus'
)
const assistantModelPlaceholder = computed(() =>
  llmState.assistant.provider === 'openai' ? '如：gpt-4o-mini' : '如：qwen-turbo'
)

watch(
  () => llmState.filter.provider,
  (provider) => {
    if (provider !== 'openai') {
      llmState.filter.base_url = ''
    }
  }
)

watch(
  () => llmState.assistant.provider,
  (provider) => {
    if (provider !== 'openai') {
      llmState.assistant.base_url = ''
    }
  }
)

const applyCredentialResult = (result) => {
  const qwenSummary = result && typeof result === 'object' && typeof result.qwen === 'object' ? result.qwen : {}
  const openaiSummary = result && typeof result === 'object' && typeof result.openai === 'object' ? result.openai : {}
  credentialState.summary.qwen.configured = Boolean(qwenSummary.configured)
  credentialState.summary.qwen.last_four = qwenSummary.last_four || ''
  credentialState.summary.openai.configured = Boolean(openaiSummary.configured)
  credentialState.summary.openai.last_four = openaiSummary.last_four || ''
  credentialState.summary.openai_base_url = typeof result.openai_base_url === 'string' ? result.openai_base_url : ''
  credentialState.form.openai_base_url = credentialState.summary.openai_base_url
  credentialState.form.qwen_api_key = ''
  credentialState.form.openai_api_key = ''
}

const fetchLlmCredentials = async () => {
  credentialState.loading = true
  credentialState.error = ''
  credentialState.message = ''
  try {
    const endpoint = await buildApiUrl('/settings/llm/credentials')
    const response = await fetch(endpoint)
    if (!response.ok) {
      throw new Error('读取 API 凭证失败')
    }
    const payload = await response.json()
    const result = payload && typeof payload === 'object' ? payload.data ?? {} : {}
    applyCredentialResult(result)
  } catch (err) {
    credentialState.error = err instanceof Error ? err.message : '读取 API 凭证失败'
  } finally {
    credentialState.loading = false
  }
}

const updateCredentials = async (payload, successMessage = 'API 凭证已更新') => {
  if (!payload || Object.keys(payload).length === 0) {
    return
  }
  credentialState.loading = true
  credentialState.error = ''
  credentialState.message = ''
  try {
    const endpoint = await buildApiUrl('/settings/llm/credentials')
    const response = await fetch(endpoint, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
    if (!response.ok) {
      throw new Error('保存 API 凭证失败')
    }
    const payloadResult = await response.json()
    const result = payloadResult && typeof payloadResult === 'object' ? payloadResult.data ?? {} : {}
    applyCredentialResult(result)
    credentialState.message = successMessage
  } catch (err) {
    credentialState.error = err instanceof Error ? err.message : '保存 API 凭证失败'
  } finally {
    credentialState.loading = false
  }
}

const submitCredentials = async () => {
  credentialState.message = ''
  credentialState.error = ''
  const payload = {}
  const qwenInput = (credentialState.form.qwen_api_key || '').trim()
  const openaiInput = (credentialState.form.openai_api_key || '').trim()
  const baseUrlInput = (credentialState.form.openai_base_url || '').trim()
  const currentBaseUrl = credentialState.summary.openai_base_url || ''

  if (qwenInput) {
    payload.qwen_api_key = qwenInput
  }
  if (openaiInput) {
    payload.openai_api_key = openaiInput
  }
  if (baseUrlInput !== currentBaseUrl) {
    payload.openai_base_url = baseUrlInput
  }

  if (Object.keys(payload).length === 0) {
    credentialState.error = '请填写需要更新的字段'
    return
  }

  await updateCredentials(payload)
}

const clearCredential = async (provider) => {
  credentialState.error = ''
  credentialState.message = ''
  if (provider === 'qwen') {
    await updateCredentials({ qwen_api_key: '' }, '千问 API Key 已清空')
  } else if (provider === 'openai') {
    await updateCredentials({ openai_api_key: '' }, 'OpenAI API Key 已清空')
  }
}

const submitLlmFilter = async () => {
  llmState.message = ''
  llmState.error = ''
  try {
    const endpoint = await buildApiUrl('/settings/llm/filter')
    const response = await fetch(endpoint, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(llmState.filter)
    })
    if (!response.ok) {
      throw new Error('保存筛选配置失败')
    }
    llmState.message = '筛选配置已保存'
  } catch (err) {
    llmState.error = err instanceof Error ? err.message : '保存筛选配置失败'
  }
}

const submitLlmAssistant = async () => {
  llmState.message = ''
  llmState.error = ''
  try {
    const endpoint = await buildApiUrl('/settings/llm/assistant')
    const response = await fetch(endpoint, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(llmState.assistant)
    })
    if (!response.ok) {
      throw new Error('保存对话配置失败')
    }
    llmState.message = '对话配置已保存'
  } catch (err) {
    llmState.error = err instanceof Error ? err.message : '保存对话配置失败'
  }
}

const fetchLlmSettings = async () => {
  llmState.loading = true
  llmState.error = ''
  try {
    const endpoint = await buildApiUrl('/settings/llm')
    const response = await fetch(endpoint)
    if (!response.ok) {
      throw new Error('读取模型配置失败')
    }
    const payload = await response.json()
    const result = payload && typeof payload === 'object' ? payload.data ?? {} : {}
    const filterConfig =
      result && typeof result === 'object'
        ? (result.filter_llm && typeof result.filter_llm === 'object'
            ? result.filter_llm
            : result.filter && typeof result.filter === 'object'
              ? result.filter
              : {})
        : {}
    if (filterConfig && typeof filterConfig === 'object') {
      Object.assign(llmState.filter, filterConfig)
    }
    if (!llmState.filter.provider) {
      llmState.filter.provider = 'qwen'
    }
    if (result.assistant && typeof result.assistant === 'object') {
      Object.assign(llmState.assistant, result.assistant)
    }
    if (!llmState.assistant.provider) {
      llmState.assistant.provider = 'qwen'
    }
  } catch (err) {
    llmState.error = err instanceof Error ? err.message : '读取模型配置失败'
  } finally {
    llmState.loading = false
  }
}

onMounted(() => {
  fetchLlmSettings()
  fetchLlmCredentials()
})
</script>
