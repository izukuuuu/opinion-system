<template>
  <section class="max-w-5xl mx-auto space-y-8 pb-12">


    <!-- Global Feedback -->
    <div v-if="llmState.error || credentialState.error"
      class="rounded-xl bg-red-50 p-4 border border-red-100 flex items-start gap-3 animate-in fade-in slide-in-from-top-2">
      <ExclamationCircleIcon class="w-5 h-5 text-red-600 shrink-0 mt-0.5" />
      <p class="text-sm text-red-700 font-medium">{{ llmState.error || credentialState.error }}</p>
    </div>
    <div v-if="llmState.message || credentialState.message"
      class="rounded-xl bg-green-50 p-4 border border-green-100 flex items-start gap-3 animate-in fade-in slide-in-from-top-2">
      <CheckCircleIcon class="w-5 h-5 text-green-600 shrink-0 mt-0.5" />
      <p class="text-sm text-green-700 font-medium">{{ llmState.message || credentialState.message }}</p>
    </div>

    <!-- API Keys Config -->
    <div class="card-surface">
      <div class="px-6 py-5 border-b border-slate-100 bg-slate-50/50">
        <h3 class="text-base font-semibold text-slate-900">API 凭证管理</h3>
        <p class="text-sm text-slate-500 mt-1">集中管理所有模型服务的访问凭证。</p>
      </div>
      <div class="p-6 space-y-6">
        <div class="grid gap-6 md:grid-cols-2">
          <!-- Qwen Key -->
          <div class="space-y-3">
            <label class="block text-sm font-medium text-slate-700">DashScope API Key (通义千问)</label>
            <div class="relative">
              <input v-model.trim="credentialState.form.qwen_api_key" type="password" autocomplete="new-password"
                placeholder="sk-..."
                class="form-input w-full rounded-xl border-slate-200 focus:border-brand-500 focus:ring-brand-500/20 text-sm py-2.5 transition-shadow" />
              <div class="absolute inset-y-0 right-3 flex items-center">
                <span v-if="credentialState.summary.qwen.configured"
                  class="inline-flex items-center gap-1 rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700">
                  <CheckIcon class="w-3 h-3" />
                  已配置
                </span>
                <span v-else
                  class="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600">
                  未配置
                </span>
              </div>
            </div>
            <div class="flex justify-end" v-if="credentialState.summary.qwen.configured">
              <button type="button" class="text-xs text-slate-400 hover:text-red-500 transition-colors"
                @click="clearCredential('qwen')">
                清除密钥
              </button>
            </div>
          </div>

          <!-- OpenAI Key -->
          <div class="space-y-3">
            <label class="block text-sm font-medium text-slate-700">OpenAI API Key (兼容接口)</label>
            <div class="relative">
              <input v-model.trim="credentialState.form.openai_api_key" type="password" autocomplete="new-password"
                placeholder="sk-..."
                class="form-input w-full rounded-xl border-slate-200 focus:border-brand-500 focus:ring-brand-500/20 text-sm py-2.5 transition-shadow" />
              <div class="absolute inset-y-0 right-3 flex items-center">
                <span v-if="credentialState.summary.openai.configured"
                  class="inline-flex items-center gap-1 rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700">
                  <CheckIcon class="w-3 h-3" />
                  已配置
                </span>
                <span v-else
                  class="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600">
                  未配置
                </span>
              </div>
            </div>
            <div class="flex justify-end" v-if="credentialState.summary.openai.configured">
              <button type="button" class="text-xs text-slate-400 hover:text-red-500 transition-colors"
                @click="clearCredential('openai')">
                清除密钥
              </button>
            </div>
          </div>
        </div>

        <div class="pt-4 border-t border-slate-100">
          <label class="block text-sm font-medium text-slate-700 mb-2">OpenAI Base URL</label>
          <div class="flex gap-4">
            <div class="flex-1">
              <input v-model.trim="credentialState.form.openai_base_url" type="text"
                placeholder="https://api.openai.com/v1"
                class="form-input w-full rounded-xl border-slate-200 focus:border-brand-500 focus:ring-brand-500/20 text-sm py-2.5 transition-shadow" />
              <p class="mt-2 text-xs text-slate-500">仅在使用第三方代理或自建服务时需要修改，留空则使用默认地址。</p>
            </div>
            <div class="shrink-0">
              <button type="button" class="btn-primary" :disabled="credentialState.loading" @click="submitCredentials">
                <span v-if="credentialState.loading">保存中...</span>
                <span v-else>保存凭证</span>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Models Configuration Grid -->
    <div class="grid gap-6 lg:grid-cols-2">
      <!-- Chat Model -->
      <section class="card-surface flex flex-col lg:col-span-2">
        <div class="px-6 py-5 border-b border-slate-100 bg-slate-50/50 flex items-center gap-2">
          <ChatBubbleBottomCenterTextIcon class="w-5 h-5 text-indigo-500" />
          <div>
            <h3 class="text-base font-semibold text-slate-900">对话模型</h3>
            <p class="text-xs text-slate-500">用于 AI 助手问答交互</p>
          </div>
        </div>
        <form @submit.prevent="submitLlmAssistant" class="p-6 space-y-5 flex-1 flex flex-col">
          <div class="space-y-4 flex-1">
            <div class="grid grid-cols-2 gap-4">
              <div class="col-span-2">
                <label class="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">服务提供方</label>
                <select v-model="llmState.assistant.provider"
                  class="form-select w-full rounded-xl border-slate-200 focus:border-brand-500 focus:ring-brand-500/20 text-sm py-2.5">
                  <option v-for="opt in providerOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
                </select>
              </div>

              <div class="col-span-2">
                <label class="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">模型名称</label>
                <input v-model.trim="llmState.assistant.model" type="text" :placeholder="assistantModelPlaceholder"
                  class="form-input w-full rounded-xl border-slate-200 focus:border-brand-500 focus:ring-brand-500/20 text-sm py-2.5" />
              </div>

              <div v-if="llmState.assistant.provider === 'openai'" class="col-span-2">
                <label class="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">Base URL</label>
                <input v-model.trim="llmState.assistant.base_url" type="text" placeholder="继承全局设置"
                  class="form-input w-full rounded-xl border-slate-200 focus:border-brand-500 focus:ring-brand-500/20 text-sm py-2.5" />
              </div>

              <div class="col-span-2">
                <label class="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">系统提示词 (System
                  Prompt)</label>
                <textarea v-model.trim="llmState.assistant.system_prompt" rows="4"
                  placeholder="如：你是一个专业的舆情分析助手，请结合提供的知识库内容回答问题。"
                  class="form-textarea w-full rounded-xl border-slate-200 focus:border-brand-500 focus:ring-brand-500/20 text-sm py-2.5 transition-shadow resize-none"></textarea>
                <p class="mt-1.5 text-xs text-slate-400">定义 AI 助手的角色、语气和基本行为准则。</p>
              </div>

              <div>
                <label class="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">最大
                  Tokens</label>
                <input v-model.number="llmState.assistant.max_tokens" type="number"
                  class="form-input w-full rounded-xl border-slate-200 focus:border-brand-500 focus:ring-brand-500/20 text-sm py-2.5" />
              </div>
              <div>
                <label
                  class="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">Temperature</label>
                <input v-model.number="llmState.assistant.temperature" type="number" step="0.1"
                  class="form-input w-full rounded-xl border-slate-200 focus:border-brand-500 focus:ring-brand-500/20 text-sm py-2.5" />
              </div>
            </div>
          </div>
          <div class="pt-4 flex justify-end">
            <button type="submit"
              class="rounded-full bg-brand-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-brand-500 hover:shadow disabled:opacity-60 disabled:shadow-none">保存对话配置</button>
          </div>
        </form>
      </section>

      <!-- Knowledge Base Info (New) -->
      <section class="bg-indigo-50/50 rounded-2xl border border-indigo-100 p-6 space-y-4 lg:col-span-2">
        <div class="flex items-center gap-2">
          <BookOpenIcon class="w-5 h-5 text-indigo-600" />
          <h3 class="text-base font-semibold text-indigo-900">Markdown 知识库</h3>
        </div>
        <div class="grid md:grid-cols-2 gap-6 items-start">
          <div class="text-sm text-indigo-800 space-y-2">
            <p>系统现在支持自动化的知识库注入。只需将您的研究文档、业务规范或参考资料以 <code>.md</code> 格式放入以下文件夹：</p>
            <div class="bg-white/60 p-2 rounded-lg border border-indigo-200 font-mono text-xs">
              backend/knowledge_base/
            </div>
            <p class="text-xs text-indigo-600/80 mt-2 italic">提示：后端会自动聚合该目录下所有文档内容并作为上下文提供给对话模型。</p>
          </div>
          <div class="bg-indigo-600 rounded-xl p-4 text-white">
            <h4 class="text-xs font-bold uppercase tracking-wider opacity-80 mb-2">生效方式</h4>
            <ul class="text-xs space-y-2 opacity-90">
              <li class="flex gap-2">
                <span class="font-bold">1.</span>
                <span>放入文件后立即对下一次对话生效</span>
              </li>
              <li class="flex gap-2">
                <span class="font-bold">2.</span>
                <span>建议配合上方“系统提示词”引导 AI 优先参考知识库</span>
              </li>
              <li class="flex gap-2">
                <span class="font-bold">3.</span>
                <span>如果文件较多，请注意不要超过模型的 Context Window 限制</span>
              </li>
            </ul>
          </div>
        </div>
      </section>

      <!-- Filter Model -->
      <section class="card-surface flex flex-col">
        <div class="px-6 py-5 border-b border-slate-100 bg-slate-50/50 flex items-center gap-2">
          <FunnelIcon class="w-5 h-5 text-indigo-500" />
          <div>
            <h3 class="text-base font-semibold text-slate-900">筛选模型</h3>
            <p class="text-xs text-slate-500">用于数据清洗与相关性判断</p>
          </div>
        </div>
        <form @submit.prevent="submitLlmFilter" class="p-6 space-y-5 flex-1 flex flex-col">
          <div class="space-y-4 flex-1">
            <div class="grid grid-cols-2 gap-4">
              <div class="col-span-2">
                <label class="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">服务提供方</label>
                <select v-model="llmState.filter.provider"
                  class="form-select w-full rounded-xl border-slate-200 focus:border-brand-500 focus:ring-brand-500/20 text-sm py-2.5">
                  <option v-for="opt in providerOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
                </select>
              </div>
              <div class="col-span-2">
                <label class="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">模型名称</label>
                <input v-model.trim="llmState.filter.model" type="text" :placeholder="filterModelPlaceholder"
                  class="form-input w-full rounded-xl border-slate-200 focus:border-brand-500 focus:ring-brand-500/20 text-sm py-2.5" />
              </div>
              <div v-if="llmState.filter.provider === 'openai'" class="col-span-2">
                <label class="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">Base URL</label>
                <input v-model.trim="llmState.filter.base_url" type="text" placeholder="继承全局设置"
                  class="form-input w-full rounded-xl border-slate-200 focus:border-brand-500 focus:ring-brand-500/20 text-sm py-2.5" />
              </div>
              <div>
                <label class="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">QPS 限制</label>
                <input v-model.number="llmState.filter.qps" type="number"
                  class="form-input w-full rounded-xl border-slate-200 focus:border-brand-500 focus:ring-brand-500/20 text-sm py-2.5" />
              </div>
              <div>
                <label class="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">Batch
                  Size</label>
                <input v-model.number="llmState.filter.batch_size" type="number"
                  class="form-input w-full rounded-xl border-slate-200 focus:border-brand-500 focus:ring-brand-500/20 text-sm py-2.5" />
              </div>
            </div>
          </div>
          <div class="pt-4 flex justify-end">
            <button type="submit"
              class="rounded-full bg-brand-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-brand-500 hover:shadow disabled:opacity-60 disabled:shadow-none">保存筛选配置</button>
          </div>
        </form>
      </section>

      <!-- Embedding Model -->
      <section class="card-surface flex flex-col md:col-span-2 lg:col-span-1">
        <div class="px-6 py-5 border-b border-slate-100 bg-slate-50/50 flex items-center gap-2">
          <CpuChipIcon class="w-5 h-5 text-indigo-500" />
          <div>
            <h3 class="text-base font-semibold text-slate-900">向量模型</h3>
            <p class="text-xs text-slate-500">用于检索增强生成 (RAG) 与聚类</p>
          </div>
        </div>
        <form @submit.prevent="submitLlmEmbedding" class="p-6 space-y-5 flex-1 flex flex-col">
          <div class="space-y-4 flex-1">
            <div class="grid grid-cols-2 gap-4">
              <div class="col-span-2">
                <label class="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">服务提供方</label>
                <select v-model="llmState.embedding.provider"
                  class="form-select w-full rounded-xl border-slate-200 focus:border-brand-500 focus:ring-brand-500/20 text-sm py-2.5">
                  <option v-for="opt in providerOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
                </select>
              </div>
              <div class="col-span-2">
                <label class="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">模型名称</label>
                <input v-model.trim="llmState.embedding.model" type="text" :placeholder="embeddingModelPlaceholder"
                  class="form-input w-full rounded-xl border-slate-200 focus:border-brand-500 focus:ring-brand-500/20 text-sm py-2.5" />
              </div>
              <div v-if="llmState.embedding.provider === 'openai'" class="col-span-2">
                <label class="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">Base URL</label>
                <input v-model.trim="llmState.embedding.base_url" type="text" placeholder="继承全局设置"
                  class="form-input w-full rounded-xl border-slate-200 focus:border-brand-500 focus:ring-brand-500/20 text-sm py-2.5" />
              </div>
              <div>
                <label class="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">向量维度</label>
                <input v-model.number="llmState.embedding.dimension" type="number"
                  class="form-input w-full rounded-xl border-slate-200 focus:border-brand-500 focus:ring-brand-500/20 text-sm py-2.5" />
              </div>
            </div>
          </div>
          <div class="pt-4 flex justify-end">
            <button type="submit"
              class="rounded-full bg-brand-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-brand-500 hover:shadow disabled:opacity-60 disabled:shadow-none">保存向量配置</button>
          </div>
        </form>
      </section>
    </div>
  </section>
</template>

<script setup>
import { computed, onMounted, reactive, watch } from 'vue'
import {
  SparklesIcon,
  CheckBadgeIcon as CheckIcon,
  ExclamationCircleIcon,
  CheckCircleIcon,
  ChatBubbleBottomCenterTextIcon,
  FunnelIcon,
  CpuChipIcon,
  BookOpenIcon
} from '@heroicons/vue/24/outline'
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
    base_url: '',
    system_prompt: ''
  },
  embedding: {
    provider: 'qwen',
    model: '',
    dimension: 0,
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
const embeddingModelPlaceholder = computed(() =>
  llmState.embedding.provider === 'openai' ? '如：text-embedding-3-small' : '如：text-embedding-v4'
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

watch(
  () => llmState.embedding.provider,
  (provider) => {
    if (provider !== 'openai') {
      llmState.embedding.base_url = ''
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

const submitLlmEmbedding = async () => {
  llmState.message = ''
  llmState.error = ''
  try {
    const endpoint = await buildApiUrl('/settings/llm/embedding')
    const response = await fetch(endpoint, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(llmState.embedding)
    })
    if (!response.ok) {
      throw new Error('保存向量化配置失败')
    }
    llmState.message = '向量化配置已保存'
  } catch (err) {
    llmState.error = err instanceof Error ? err.message : '保存向量化配置失败'
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
    if (result.embedding_llm && typeof result.embedding_llm === 'object') {
      Object.assign(llmState.embedding, result.embedding_llm)
    } else if (result.embedding && typeof result.embedding === 'object') {
      Object.assign(llmState.embedding, result.embedding)
    }
    if (!llmState.embedding.provider) {
      llmState.embedding.provider = 'qwen'
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
