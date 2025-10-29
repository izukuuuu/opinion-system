<template>
  <section class="card-surface space-y-6 p-6">
    <header class="space-y-2">
      <p class="text-xs font-semibold uppercase tracking-[0.4em] text-slate-400">AI 服务</p>
      <h2 class="text-xl font-semibold text-slate-900">大模型配置</h2>
      <p class="text-sm text-slate-500">配置筛选流与对话流使用的模型提供方与参数。</p>
    </header>

    <p v-if="llmState.error" class="rounded-2xl bg-rose-100 px-4 py-3 text-sm text-rose-600">{{ llmState.error }}</p>
    <p v-if="llmState.message" class="rounded-2xl bg-emerald-100 px-4 py-3 text-sm text-emerald-600">{{ llmState.message }}</p>

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

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api'
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

const submitLlmFilter = async () => {
  llmState.message = ''
  llmState.error = ''
  try {
    const response = await fetch(`${API_BASE_URL}/settings/llm/filter`, {
      method: 'POST',
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
    const response = await fetch(`${API_BASE_URL}/settings/llm/assistant`, {
      method: 'POST',
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
    const response = await fetch(`${API_BASE_URL}/settings/llm`)
    if (!response.ok) {
      throw new Error('读取模型配置失败')
    }
    const payload = await response.json()
    const result = payload && typeof payload === 'object' ? payload.data ?? {} : {}
    if (result.filter && typeof result.filter === 'object') {
      Object.assign(llmState.filter, result.filter)
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
})
</script>
